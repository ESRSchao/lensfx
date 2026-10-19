# Contributing

Thanks for working on Lensfx.

## Setup

```bash
git clone https://github.com/ESRSchao/lensfx.git
cd lensfx
pip install -r requirements-dev.txt
python -m lensfx doctor
```

Optional desktop shell:

```bash
npm install
npm start
```

## How to change things

- **Look / ISP graph** — `lensfx/pipeline.py` (`map_params`, `build_filter`, `process`)
- **HTTP API / jobs** — `lensfx/server.py`
- **UI** — `renderer/index.html`, `renderer/styles.css`, `renderer/app.js`
- **Desktop window** — `electron/main.js`, `electron/preload.js`

Keep the renderer free of a build step. The same files are served by `python -m lensfx serve` and loaded by Electron.

Do not add overlay dirt, vignette, barrel+pad, or RGB grain. The pipeline stays YUV, never upscales, and uses crop-in handheld (no black bars).

## Tests

```bash
python -m pytest
```

Tests that need FFmpeg skip automatically when `ffmpeg` is missing.

## Pull requests

1. Branch from `main`.
2. Keep the change small and described in the PR body.
3. Update `CHANGELOG.md` under Unreleased.
4. CI on GitHub must pass.

Use [GitHub Issues](https://github.com/ESRSchao/lensfx/issues) for bugs and feature ideas.
