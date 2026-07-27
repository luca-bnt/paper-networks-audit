#!/usr/bin/env python3
"""Rebuild 00-title.wav as three spoken segments with deliberate pauses.

Kokoro will not hold a beat on punctuation alone — a period buys ~0.2s, which
reads as normal sentence rhythm rather than an intentional pause. So each segment
is synthesised separately, trimmed to its actual speech, and joined with silence
of a chosen length.
"""
import pathlib
import wave

import numpy as np
from kokoro_onnx import Kokoro

CACHE = pathlib.Path.home() / ".cache/hyperframes/tts"
DEST = pathlib.Path(
    "/Users/luca.bontempi/Documents/Code/paper-networks-audit/"
    "cluster-analysis-tech-demo/assets/voice/00-title.wav"
)

BLEND = [("af_heart", 0.6), ("af_nicole", 0.4)]

# (text, silence to hold after it)
SEGMENTS = [
    ("Hi.", 0.85),
    ("Let's take a look at how AIRA's Cluster Analysis works.", 0.70),
    ("Papermills don't submit one paper. They submit hundreds, often from the "
     "same laptop. This is the check that notices.", 0.0),
]

# Trim threshold: anything under this is treated as room tone, not speech.
FLOOR = 0.004
KEEP = 0.03   # seconds of headroom left either side so consonants aren't clipped


def trim(samples, rate):
    loud = np.where(np.abs(samples) > FLOOR)[0]
    if not len(loud):
        return samples
    pad = int(KEEP * rate)
    return samples[max(0, loud[0] - pad):min(len(samples), loud[-1] + pad)]


model = Kokoro(str(CACHE / "models/kokoro-v1.0.onnx"), str(CACHE / "voices/voices-v1.0.bin"))
style = sum(w * model.get_voice_style(n) for n, w in BLEND)

pieces, rate = [], None
for text, gap in SEGMENTS:
    samples, rate = model.create(text, voice=style, speed=1.0, lang="en-us")
    spoken = trim(np.asarray(samples), rate)
    pieces.append(spoken)
    print(f"  {spoken.shape[0] / rate:5.2f}s  +{gap:.2f}s pause   {text[:52]}")
    if gap:
        pieces.append(np.zeros(int(gap * rate), dtype=spoken.dtype))

out = np.concatenate(pieces)
pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
with wave.open(str(DEST), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(pcm.tobytes())

print(f"\n00-title.wav — {len(out) / rate:.3f}s")
