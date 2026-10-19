# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Motion blur (`tmix`) is a separate 0–1 **shutter** control. Default is light (~0.22); 0 turns it off. Current frame keeps weight 1 so it no longer equal-blends 2–3 frames.

## [0.1.0] — 2026-10-19

### Added

- Phone-ISP pipeline for stills and video (`auto` / `iphone` / `ugc` / `night` / `compress`)
- CLI: `python -m lensfx`, `serve`, `doctor`
- Local web UI on `127.0.0.1:18765` with Upscayl-style sidebar and compare slider
- Electron desktop shell (NSIS installer + zip)
- GitHub Actions CI and tagged Windows release builds
