# Cluster Analysis — technical pitch (HyperFrames)

Separate from the product UI demo (`../audit-network-demo/`). Same visual system;
numbers-first explainer of the AIRA Cluster Analysis check.

```bash
npm run dev      # Studio + storyboard board
npm run check
npm run render   # after final approval
```

Board: `http://localhost:8788/?view=storyboard#project/cluster-analysis-tech-demo`

## Narration

`STORYBOARD.md` is the source of truth for the spoken words — the `- voiceover:` line
in each frame's section is what gets said. `scripts/narrate.py` reads those lines and
regenerates the audio, so the storyboard cannot drift from the film.

```bash
python scripts/narrate.py                                  # list, write nothing
~/.venvs/hf-media/bin/python scripts/narrate.py 04-tokens   # regenerate one frame
```

`[[0.85]]` inside a voiceover line holds that many seconds of silence there — used
for the deliberate beats in the opening greeting. See the script's docstring for the
voice blend and what to do when a line changes length.

Slot lengths are sized to the narration, so a length change means retiming
`index.html` and rebuilding `assets/bgm/track.wav` to the new total.

## Starting a new film

Don't fork this project. `../../frontiers-product-video-kit` is the template, with
the design system, slide catalogue and tone rules extracted, and a build that derives
the whole timeline from the narration.
