# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.7] — 2026-10-27

### Fixed

- Windows installers now bundle the Python processing engine, NumPy, Pillow, FFmpeg, and ffprobe. Lensfx no longer requires a separate Python or FFmpeg installation.
- Desktop startup now reports the actual embedded-engine error instead of timing out with a generic dependency message.

## [0.1.6] — 2026-10-27

### Added

- A separate **Matte** surface control (`0–1`, default `0.35`) for images and video. It combines luma-only contrast reduction, highlight de-glossing, edge-preserving microcontrast softening, and fine texture after the softening pass.
- CLI (`--matte`), HTTP API, desktop/web UI, and render-report support for reproducible matte settings. `--matte 0` cleanly disables the new stage.
- Debounced live preview while changing modes, lighting, exposure, shadows, highlights, strength, or Matte. Uploaded media is cached once, video uses a 960px middle-frame plate, and full export reuses the original source.

### Changed

- The processing graph now treats capture motion and surface character as independent controls: camera movement remains in shutter/handheld, while plastic-looking material response is handled by Matte.

## [0.1.5] — 2026-10-21

### Added

- Lighting looks, independent of capture mode: **跟随 / 窗光 / 正午 / 过曝 / 混合 / 暗场**, plus exposure / shadows / highlights sliders (0.5 = that look's default).
- Mixed and window light use `colorcorrect` on red/blue shadows vs highlights (cool window + warm bounce). No hue rotation.

## [0.1.4] — 2026-10-21

### Changed

- Capture **modes** actually diverge, from X consensus (locked-off / 4K-clean / plastic-sharp / identical wobble are the tells):
  - **ugc 转发**: ~2% handheld in the first 1–3s then settle, more grain, 1080p, harder recompress, AE hunting
  - **iphone**: warmer, OIS-still, light AE
  - **cctv 监控**: locked-off, heavy grain, 960, low bitrate, more shutter
  - **night / compress**: stronger grain and codec pressure
- Switching a mode in the UI loads that mode's shutter and handheld. They no longer all sit on 0.25.
- Too-sharp plates skip CAS (an AI tell) and get more luma grain.

## [0.1.3] — 2026-10-20

### Fixed

- Default path no longer hue-rotates toward green. Auto is color-neutral. Phone WB is temperature only (`colortemperature`, preserve lightness); green/magenta tint stays off. Video no longer always inserts a `hue` filter. RGB `eq` gamma/contrast/saturation stay identity — those were olive-shifting skin on 8-bit YUV.

## [0.1.2] — 2026-10-19

### Changed

- Handheld crop-in walk is a separate 0–1 **handheld** control. Default is light (~0.28); 0 turns it off. Independent of overall strength and shutter. First-second envelope is milder.

## [0.1.1] — 2026-10-19

### Changed

- Motion blur (`tmix`) is a separate 0–1 **shutter** control. Default is light (~0.22); 0 turns it off. Current frame keeps weight 1 so it no longer equal-blends 2–3 frames.

## [0.1.0] — 2026-10-19

### Added

- Phone-ISP pipeline for stills and video (`auto` / `iphone` / `ugc` / `night` / `compress`)
- CLI: `python -m lensfx`, `serve`, `doctor`
- Local web UI on `127.0.0.1:18765` with Upscayl-style sidebar and compare slider
- Electron desktop shell (NSIS installer + zip)
- GitHub Actions CI and tagged Windows release builds
