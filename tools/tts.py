"""Synthesize Leo's voice-over and lay out the video timeline.

Reads video/script.json, writes one wav per line to build/vo/ and
build/timeline.json, which index.html and mix.py both consume.

Usage: python3 tools/tts.py --model <kokoro-multi-lang-v1_1 dir>
Model: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models
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


def load_tts(d: Path):
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
    args = ap.parse_args()

    script = json.loads((ROOT / "video" / "script.json").read_text())
    voice = script["voice"]
    tts = load_tts(args.model)
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
            audio = tts.generate(line.get("tts", line["text"]), sid=voice["sid"], speed=voice["speed"])
            sr = audio.sample_rate
            x = trim(np.asarray(audio.samples, dtype=np.float32), sr)
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


if __name__ == "__main__":
    main()
