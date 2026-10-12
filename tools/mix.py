"""Mix the soundtrack: voice-over + a synthesized lo-fi loop + UI sound effects.

Everything is generated here (no sample packs), so the track is free to use.
Reads build/timeline.json, build/vo/*.wav and build/cues.json (sound cues the
page reports while rendering); writes build/soundtrack.wav.
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SR = 48000
rng = np.random.default_rng(7)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a, d, sustain=0.0, curve=4.0):
    """Attack then exponential decay to `sustain`, n samples long."""
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), sustain + (1 - sustain) * np.exp(-(t - a) * curve / max(d, 1e-4)))
    return e.astype(np.float32)


def keys(freq, dur, vel=1.0):
    """Soft electric-piano-ish tone: a few decaying partials plus slight detune."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.zeros(n, np.float32)
    for k, amp, dec in ((1, 1.0, 1.0), (2, 0.35, 1.8), (3, 0.12, 2.6), (4, 0.05, 3.5)):
        tone += amp * np.sin(2 * np.pi * freq * k * t * (1 + 0.0015 * (k - 1))) * np.exp(-t * dec * 1.4)
    tone *= 0.5 + 0.5 * np.sin(2 * np.pi * 4.5 * t) * 0.15 + 0.5
    return tone * env(n, 0.012, dur, 0.0, 2.2) * vel


def kick(n=None):
    n = n or int(0.35 * SR)
    t = np.arange(n) / SR
    f = 48 + 90 * np.exp(-t * 28)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)).astype(np.float32)


def hat(dur=0.06, vel=1.0):
    n = int(dur * SR)
    x = rng.standard_normal(n).astype(np.float32)
    x = np.diff(np.concatenate([[0], x]))  # crude high-pass
    return x * np.exp(-np.arange(n) / SR * 70) * 0.25 * vel


def snare():
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 22) * 0.35
    return x + 0.25 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)


def add(buf, x, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    x = x[: len(buf) - i]
    buf[i: i + len(x)] += x


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # one-pole; fine for a minute or two of audio
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def bgm(dur):
    bpm = 88
    beat = 60 / bpm
    bar = 4 * beat
    # Fmaj7 - Em7 - Dm7 - Cmaj7 : a gentle descending loop.
    chords = [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]]
    bass = [41, 40, 38, 36]
    melody = [72, None, 69, 67, None, 64, 67, None]
    buf = np.zeros(int((dur + 2) * SR), np.float32)
    t, i = 0.0, 0
    while t < dur:
        c = chords[i % 4]
        for j, n in enumerate(c):  # lightly strummed chord, re-struck on beat 3
            add(buf, keys(midi(n), bar, 0.16), t + j * 0.018)
            add(buf, keys(midi(n), beat * 2, 0.08), t + 2 * beat + 0.3 * beat + j * 0.012)
        b = midi(bass[i % 4])
        n = int(bar * SR)
        tt = np.arange(n) / SR
        add(buf, (np.sin(2 * np.pi * b * tt) * env(n, 0.02, bar, 0.3, 1.5) * 0.22).astype(np.float32), t)
        if i % 2 == 1:  # sparse melody every other bar
            for k, m in enumerate(melody):
                if m is not None:
                    add(buf, keys(midi(m + (0 if i % 4 == 1 else -3)), beat, 0.07), t + k * beat / 2)
        if i >= 1:  # drums come in after the first bar
            for k in range(4):
                if k in (0, 2):
                    add(buf, kick() * 0.5, t + k * beat)
                if k in (1, 3):
                    add(buf, snare() * 0.32, t + k * beat)
            for k in range(8):
                swing = 0.06 * beat if k % 2 else 0
                add(buf, hat(vel=0.8 if k % 2 else 1.0), t + k * beat / 2 + swing)
        t += bar
        i += 1
    buf = buf[: int(dur * SR)]
    buf = lowpass(buf, 5200)
    fade = int(1.5 * SR)
    buf[:fade] *= np.linspace(0, 1, fade)
    buf[-fade * 2:] *= np.linspace(1, 0, fade * 2)
    return buf


# ---- sound effects ---------------------------------------------------------

def sfx_pop():
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    f = 500 + 900 * np.exp(-t * 40)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35) * 0.5).astype(np.float32)


def sfx_whoosh():
    n = int(0.45 * SR)
    x = rng.standard_normal(n).astype(np.float32)
    x = lowpass(x, 2400) - lowpass(x, 300)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    return x * e * 0.9


def sfx_tick():
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 180) * 0.2).astype(np.float32)


def sfx_ding():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((1318.5, 0.5), (1975.5, 0.25), (2637, 0.12)))
    return (x * np.exp(-t * 5) * 0.45).astype(np.float32)


def sfx_boing():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 220 + 260 * np.sin(t * 30) * np.exp(-t * 6) + 120 * t
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8) * 0.45).astype(np.float32)


SFX = {"pop": sfx_pop, "whoosh": sfx_whoosh, "tick": sfx_tick, "ding": sfx_ding, "boing": sfx_boing}


def main():
    tl = json.loads((BUILD / "timeline.json").read_text())
    cues = json.loads((BUILD / "cues.json").read_text()) if (BUILD / "cues.json").exists() else []
    dur = tl["duration"]
    n = int(dur * SR)

    vo = np.zeros(n, np.float32)
    for s in tl["scenes"]:
        for line in s["lines"]:
            x, sr = sf.read(BUILD / "vo" / line["file"], dtype="float32")
            if sr != SR:  # linear resample is plenty for speech at these rates
                idx = np.arange(int(len(x) * SR / sr)) * sr / SR
                x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
            add(vo, x, line["start"])
    peak = np.abs(vo).max() or 1
    vo *= 0.85 / peak

    # Duck the music while Leo talks (smoothed so it breathes, not pumps).
    talking = np.zeros(n, np.float32)
    for s in tl["scenes"]:
        for line in s["lines"]:
            talking[int(line["start"] * SR): int((line["start"] + line["dur"]) * SR)] = 1
    k = int(0.25 * SR)
    talking = np.convolve(talking, np.ones(k) / k, mode="same")
    music = bgm(dur) * (0.30 - 0.17 * talking)

    fx = np.zeros(n, np.float32)
    cache = {}
    for c in cues:
        name = c["sfx"]
        if name not in cache:
            cache[name] = SFX[name]()
        add(fx, cache[name] * c.get("gain", 1.0), c["t"])

    mix = vo + music + fx * 0.6
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    sf.write(BUILD / "soundtrack.wav", np.stack([mix, mix], axis=1), SR)
    print(f"soundtrack {dur:.2f}s, {len(cues)} cues")


if __name__ == "__main__":
    main()
