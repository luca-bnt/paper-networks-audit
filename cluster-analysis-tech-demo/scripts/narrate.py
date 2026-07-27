#!/usr/bin/env python3
"""Generate the narration for this film from STORYBOARD.md.

    python scripts/narrate.py                 # list what would be generated
    python scripts/narrate.py --all           # (re)generate every frame
    python scripts/narrate.py 04-tokens       # one frame, after a rewrite

Needs an environment with kokoro-onnx and numpy:

    ~/.venvs/hf-media/bin/python scripts/narrate.py 04-tokens

STORYBOARD.md is the single source of truth for the words. The `- voiceover:` line
in each frame's section is what gets spoken, so the storyboard can never drift from
the audio the way a separate script full of hardcoded strings does.

## Voice

A 60/40 blend of the Kokoro af_heart and af_nicole style vectors. A single stock
voice reads either too warm or too clipped for a technical pitch; the mix gives a
presenter who sounds interested without selling. The CLI only accepts one voice id,
which is why this talks to the model directly. Keep the blend identical across
every frame — the voice is part of the film.

## Deliberate pauses

`[[0.85]]` in a voiceover line holds that many seconds of silence at that point.

Punctuation alone will not do this: Kokoro gives a period about 0.2s, which reads
as ordinary sentence rhythm rather than an intentional beat. So a line containing
markers is synthesised as separate segments, each trimmed to its actual speech, and
joined with silence of exactly the length asked for.

Place a pause where something is moving on screen. Silence over a static frame
reads as dead air; silence over a reveal reads as intentional.

## After regenerating

Slot lengths are sized to the narration, so a line that changes length means the
timeline needs retiming and the music bed rebuilding to the new total. This script
prints the delta against the file it replaced so you know whether that is needed.
"""
import pathlib
import re
import sys
import wave

PROJ = pathlib.Path(__file__).resolve().parent.parent
STORYBOARD = PROJ / "STORYBOARD.md"
OUT = PROJ / "assets" / "voice"
CACHE = pathlib.Path.home() / ".cache/hyperframes/tts"

BLEND = [("af_heart", 0.6), ("af_nicole", 0.4)]
SPEED = 1.0
LANG = "en-us"

PAUSE = re.compile(r"\[\[\s*([\d.]+)\s*\]\]")
# Anything quieter than this is room tone, not speech.
FLOOR = 0.004
KEEP = 0.03      # seconds left either side of a segment so consonants aren't clipped


def script():
    """Frame id -> voiceover text, read in play order from the storyboard.

    A frame section gives its file in `- src:` and its words in `- voiceover:`; the
    id is the filename stem, which is also what index.html mounts.
    """
    lines, frame_id = {}, None
    for line in STORYBOARD.read_text().splitlines():
        src = re.match(r"\s*-\s*src:\s*compositions/frames/(\S+)\.html", line)
        if src:
            frame_id = src.group(1)
            continue
        vo = re.match(r"\s*-\s*voiceover:\s*(.+?)\s*$", line)
        if vo and frame_id:
            lines[frame_id] = vo.group(1)
            frame_id = None
    return lines


def wav_length(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def segments(text):
    """Split a line into (spoken text, silence after it) pairs."""
    parts = PAUSE.split(text)
    out = []
    for i in range(0, len(parts), 2):
        spoken = parts[i].strip()
        gap = float(parts[i + 1]) if i + 1 < len(parts) else 0.0
        if spoken:
            out.append((spoken, gap))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    write = "--all" in sys.argv[1:] or bool(args)

    lines = script()
    targets = args or list(lines)
    unknown = [t for t in targets if t not in lines]
    if unknown:
        raise SystemExit(f"no voiceover in STORYBOARD.md for: {', '.join(unknown)}")

    if not write:
        print(f"{len(lines)} narrated frames in STORYBOARD.md\n")
        for name in targets:
            segs = segments(lines[name])
            shape = " + ".join(
                f"{len(s.split())}w" + (f" +{g:g}s" if g else "") for s, g in segs
            )
            existing = OUT / f"{name}.wav"
            have = f"{wav_length(existing):6.2f}s" if existing.exists() else "  --  "
            print(f"  {name:16s} {have}  {shape}")
        print("\nnothing written — pass frame ids, or --all")
        return

    import numpy as np
    from kokoro_onnx import Kokoro

    model = Kokoro(str(CACHE / "models/kokoro-v1.0.onnx"),
                   str(CACHE / "voices/voices-v1.0.bin"))
    style = sum(w * model.get_voice_style(n) for n, w in BLEND)
    print("voice: " + " + ".join(f"{n}*{w}" for n, w in BLEND) + f" @ speed {SPEED}\n")

    def trim(samples, rate):
        loud = np.where(np.abs(samples) > FLOOR)[0]
        if not len(loud):
            return samples
        pad = int(KEEP * rate)
        return samples[max(0, loud[0] - pad):min(len(samples), loud[-1] + pad)]

    OUT.mkdir(parents=True, exist_ok=True)
    for name in targets:
        segs = segments(lines[name])
        dest = OUT / f"{name}.wav"
        before = wav_length(dest) if dest.exists() else None

        pieces, rate = [], None
        for spoken, gap in segs:
            samples, rate = model.create(spoken, voice=style, speed=SPEED, lang=LANG)
            samples = np.asarray(samples)
            # Only trim when we are stitching — a single-segment line keeps the
            # model's own lead-in and tail, so existing audio reproduces exactly.
            if len(segs) > 1:
                samples = trim(samples, rate)
            pieces.append(samples)
            if gap:
                pieces.append(np.zeros(int(gap * rate), dtype=samples.dtype))

        out = np.concatenate(pieces) if len(pieces) > 1 else pieces[0]
        pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
        with wave.open(str(dest), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm.tobytes())

        length = len(out) / rate
        delta = f"  ({length - before:+.2f}s vs before)" if before else ""
        print(f"  {name:16s} {length:6.2f}s{delta}")

    print("\nIf any length changed, retime index.html and rebuild the music bed to "
          "the new total.")


if __name__ == "__main__":
    main()
