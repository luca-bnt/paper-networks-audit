# Cluster Analysis tech pitch — design

Match sibling `audit-network-demo` exactly. Do not invent a new look.

## Canvas

- 1920×1080 · 30 fps · landscape

## Palette

| Token | Value | Use |
| --- | --- | --- |
| bg deep | `#0b1670` → `#1a32c4` | Scene gradient (same radial stack as product demo) |
| glass | `rgba(255,255,255,0.10)` | Panels |
| glass border | `rgba(255,255,255,0.22)` | Panel edges |
| text | `#ffffff` | Primary |
| text soft | `rgba(255,255,255,0.78)` | Subcopy |
| cyan | `#7ee8ff` | Accent, labels, focal numbers |
| mint | `#9dffb8` | PASS / positive |
| coral | `#ff7b9c` | BLOCK / alert |
| lavender | `#c4b5ff` | WARN / secondary signal |

## Type

- Family: **Inter** (400 / 500 / 600 / 700)
- Scene title: ~48px / 700 / −0.035em
- Hero number: 72–96px / 700 / mono-ish tracking
- Body: 17px soft
- Labels: 12px uppercase, letter-spacing 0.16em, cyan pill

## Chrome

- Upper-left brand bar on **every** frame: Frontiers logo (`assets/frontiers.png`) · pipe `|` · `AIRA · Cluster Analysis`
- Scene label pill top-right (content frames; optional on title)
- Glass cards: 24px radius, soft blue shadow + inset highlight
- Infographic blocks use glass + cyan number callouts — not product UI mockups
- Title slide opens the film before the hook

## Motion (later build)

- Title rise (`expo.out`), label blur-slide, number count-up, pipeline node stagger
- Scene crossfade ~0.38s
- Prefer-reduced-motion: still readable at key posters
