# Paper Networks Audit — HyperFrames demo

Independent product demo video for [Paper Networks Audit](../audit-network/). Not wired into the app — this is a standalone [HyperFrames](https://hyperframes.video/) composition with styled mock UI.

**Duration:** 36 seconds · **Resolution:** 1920×1080 · **FPS:** 30

## Scenes

1. **Intro** — tool name and purpose
2. **Clusters** — filters, graph, connection list
3. **Compare** — side-by-side table with shared highlights
4. **Team tracking** — seen / checked / resolved / flagged
5. **Flags** — flagged list, CSV export, manager summary
6. **Outro** — shareable URL

## Commands

```bash
cd audit-network-demo
npm run dev      # preview in browser (hot reload)
npm run check    # lint + layout validation
npm run render   # output/output.mp4 (draft: add -- --quality draft)
```

Render to a specific file:

```bash
npx hyperframes render --output output/paper-networks-audit-demo.mp4
```

## Notes

- Mock UI only — no dependency on `audit-network/index.html` or live data.
- Edit `index.html` directly or use HyperFrames skills in your agent (`/hyperframes`).
- Requires Node 22+, FFmpeg, and Chrome for local render.
