"""Synthesize Leo's voice-over and lay out the video timeline.

Reads video/script.json, writes one wav per line to build/vo/ and
build/timeline.json, which index.html and mix.py both consume.

Two voices:
  python3 tools/tts.py --model <kokoro-multi-lang-v1_1 dir>
      stock Kokoro voice (speaker id from script.json)
  python3 tools/tts.py --model <zipvoice dir> --vocoder vocos_24khz.onnx \
      --ref voice/ref.wav --ref-text voice/ref.txt
      ZipVoice zero-shot clone of the speaker in ref.wav (exact transcript in ref.txt)

With --asr <sense-voice dir>, every generated line is transcribed back and
regenerated (keeping the best take) when it drifts from the script.
Models: https://github.com/k2-fsa/sherpa-onnx/releases (tts-models, vocoder-models, asr-models)
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

LEAD_IN = 0.6      # silence before the first line
LINE_GAP = 0.28    # pause between lines inside a scene
SCENE_GAP = 0.55   # extra pause on a scene change
TAIL = 2.2         # hold on the end card
MAX_CHUNK = 15     # subtitle chunk width, in CJK characters


def width(s):
    """Rough rendered width: Latin letters are about half a CJK glyph."""
    return sum(1 if ord(c) > 0x2E80 else 0.55 for c in s)


def load_kokoro(d: Path):
    d = str(d) + "/"
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                model=d + "model.onnx", voices=d + "voices.bin", tokens=d + "tokens.txt",
                data_dir=d + "espeak-ng-data", dict_dir=d + "dict",
                lexicon=d + "lexicon-us-en.txt," + d + "lexicon-zh.txt"),
            num_threads=4),
        rule_fsts=d + "date-zh.fst," + d + "phone-zh.fst," + d + "number-zh.fst",
        max_num_sentences=1)
    return sherpa_onnx.OfflineTts(cfg)


def load_zipvoice(d: Path, vocoder: Path):
    d = str(d) + "/"
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            zipvoice=sherpa_onnx.OfflineTtsZipvoiceModelConfig(
                tokens=d + "tokens.txt", encoder=d + "encoder.int8.onnx", decoder=d + "decoder.int8.onnx",
                vocoder=str(vocoder), data_dir=d + "espeak-ng-data", lexicon=d + "lexicon.txt"),
            num_threads=8))
    return sherpa_onnx.OfflineTts(cfg)


def load_asr(d: Path):
    d = str(d) + "/"
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=d + "model.int8.onnx", tokens=d + "tokens.txt", use_itn=True, language="zh")


def norm(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s.lower())


def cer(ref, hyp):
    """Character error rate (edit distance / reference length)."""
    a, b = norm(ref), norm(hyp)
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / max(1, len(a))


def transcribe(asr, x, sr):
    s = asr.create_stream()
    s.accept_waveform(sr, x)
    asr.decode_stream(s)
    return s.result.text


def trim(x, sr, thresh=0.01):
    """Cut leading/trailing silence, keeping a few ms of air."""
    idx = np.where(np.abs(x) > thresh)[0]
    if not len(idx):
        return x
    pad = int(0.04 * sr)
    return x[max(0, idx[0] - pad): idx[-1] + pad]


def chunks(text):
    """Split a line into subtitle chunks at punctuation, then by length."""
    parts = [p for p in re.split(r"(?<=[，。；？！：、])", text) if p.strip()]
    out = []
    for p in parts:
        p = p.strip()
        if out and width(out[-1]) + width(p) <= MAX_CHUNK:
            out[-1] += p
        else:
            out.append(p)
    return [c.rstrip("，。；、") or c for c in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--vocoder", type=Path)
    ap.add_argument("--ref", type=Path, help="reference clip to clone (ZipVoice)")
    ap.add_argument("--ref-text", type=Path, help="exact transcript of --ref")
    ap.add_argument("--asr", type=Path, help="SenseVoice dir: check each line and retake if needed")
    ap.add_argument("--speed", type=float)
    args = ap.parse_args()

    script = json.loads((ROOT / "video" / "script.json").read_text())
    voice = script["voice"]
    speed = args.speed or voice["clone_speed" if args.ref else "speed"]
    if args.ref:
        tts = load_zipvoice(args.model, args.vocoder)
        ref, ref_sr = sf.read(args.ref, dtype="float32")
        ref_text = args.ref_text.read_text().strip()

        def speak(text, k):
            # Retakes nudge the pace and sampling steps; flow matching varies per take.
            return tts.generate(text, prompt_text=ref_text, prompt_samples=ref.tolist(), sample_rate=ref_sr,
                                speed=speed * (1, 0.96, 1.04, 1.0)[k], num_steps=(8, 8, 8, 12)[k])
    else:
        tts = load_kokoro(args.model)

        def speak(text, k):
            return tts.generate(text, sid=voice["sid"], speed=speed)
    asr = load_asr(args.asr) if args.asr else None
    report = []
    (BUILD / "vo").mkdir(parents=True, exist_ok=True)

    t = LEAD_IN
    scenes = []
    n = 0
    for si, scene in enumerate(script["scenes"]):
        if si:
            t += SCENE_GAP
        start = t
        lines = []
        for li, line in enumerate(scene["lines"]):
            if li:
                t += LINE_GAP
            best = None
            for k in range(4 if asr else 1):
                audio = speak(line.get("tts", line["text"]), k)
                sr = audio.sample_rate
                x = trim(np.asarray(audio.samples, dtype=np.float32), sr)
                heard = transcribe(asr, x, sr) if asr else ""
                err = cer(line.get("asr", line["text"]), heard) if asr else 0.0
                if best is None or err < best[0]:
                    best = (err, x, heard)
                if err <= 0.03:
                    break
            err, x, heard = best
            if asr:
                report.append(f"{err:4.0%}  {line['text']}\n      heard: {heard}")
            name = f"{n:02d}_{scene['id']}_{li}.wav"
            sf.write(BUILD / "vo" / name, x, sr)
            dur = len(x) / sr
            # Time subtitle chunks by their share of the spoken characters.
            cs = chunks(line["text"])
            weights = [max(1, len(re.sub(r"[\s，。；？！：、]", "", c))) for c in cs]
            total, acc, subs = sum(weights), 0.0, []
            for c, w in zip(cs, weights):
                subs.append({"text": c, "start": round(t + dur * acc / total, 3),
                             "end": round(t + dur * (acc + w) / total, 3)})
                acc += w
            lines.append({"file": name, "text": line["text"], "start": round(t, 3),
                          "dur": round(dur, 3), "subs": subs})
            print(f"{name}  {dur:5.2f}s  {line['text']}")
            t += dur
            n += 1
        scenes.append({"id": scene["id"], "start": round(start, 3), "lines": lines})

    # Each scene runs until the next one starts.
    end = t + TAIL
    for a, b in zip(scenes, scenes[1:] + [None]):
        a["end"] = round(b["start"] - SCENE_GAP / 2 if b else end, 3)
    timeline = {"title": script["title"], "duration": round(end, 3), "scenes": scenes}
    (BUILD / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
    print(f"total {end:.2f}s")
    if report:
        (BUILD / "asr_report.txt").write_text("\n".join(report) + "\n")
        print("\n".join(report))


if __name__ == "__main__":
    main()
