# Development

## Architecture

Lensfx follows the same split as [Upscayl](https://github.com/upscayl/upscayl): a native engine plus a dark desktop UI.

```
renderer  ──HTTP /api──►  python -m lensfx serve  ──ffmpeg──►  pipeline
    ▲                            ▲
    └── Electron loads 127.0.0.1:18765 after spawning the engine
```

- `lensfx/pipeline.py` — analyze, map presets, build the FFmpeg filter graph, encode
- `lensfx/server.py` — loopback HTTP, job queue, static renderer
- `renderer/` — one HTML/CSS/JS UI (no React build)
- `electron/` — window, spawn Python, file dialogs

The browser path and the desktop path share the renderer. Electron does not reimplement the ISP.

## Ports

Default `18765`. Override with `LENSFX_PORT`. Do not use `8765` on this machine (HPC dashboard).

## Caches on D:

This PC keeps C: tight. For npm / electron builds:

```powershell
$env:npm_config_cache = "D:\Temp\npm-cache"
$env:ELECTRON_CACHE = "D:\Temp\electron-cache"
$env:ELECTRON_BUILDER_CACHE = "D:\Temp\electron-builder-cache"
npm install
npm run dist
```

Jobs land in `%TEMP%\lensfx\jobs` (on this PC that is `D:\Temp\lensfx\jobs`).

## Demo gallery

Sample mp4s are gitignored (~90 MB). To rebuild the eight-clip gallery:

```bash
python demo/run_demo.py
```

Put source files in `demo/samples/{id}.mp4` first (`demo/download_selected.py`).

## Release

1. Bump version in `pyproject.toml`, `lensfx/__init__.py`, `package.json`, `CHANGELOG.md`.
2. `git tag v0.x.y && git push origin v0.x.y`
3. The Release workflow builds NSIS + zip and attaches them to the GitHub Release.

The installer still needs Python 3.10+ and FFmpeg on the target PC.
