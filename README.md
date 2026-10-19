# Lensfx

[![CI](https://github.com/ESRSchao/lensfx/actions/workflows/ci.yml/badge.svg)](https://github.com/ESRSchao/lensfx/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/ESRSchao/lensfx)](https://github.com/ESRSchao/lensfx/releases)

把 AI 静帧和视频走一遍**手机出图**路径：抬阴影、咬高光、1080p、JPEG / H.264、轻微手持。不是污渍或模糊滤镜。

界面布局参照 [Upscayl](https://github.com/upscayl/upscayl)：左侧 350px 设置栏，右侧前后对比滑块。处理在本地完成，HTTP 服务只绑定 `127.0.0.1`。

## 功能

- 图片：JPG / PNG / WEBP（输出 JPEG，静帧走 `spp` DCT 再压）
- 视频：MP4 / MOV / WEBM / MKV（H.264，`tmix` + 1/f 手持 crop-in）
- 预设：`auto` · `iphone` · `ugc` · `night` · `compress`
- 左右对比滑块（左原片 / 右处理后），静帧 / 视频切换
- CLI 与桌面壳共用同一套引擎

## 需要的环境

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) 4.4+（`ffmpeg` 与 `ffprobe` 在 PATH 上）
- 可选：Node.js 20+（只在打包桌面应用时需要）

Windows 本机若已安装 FFmpeg，也可设环境变量：

```
LENSFX_FFMPEG=C:\path\to\ffmpeg.exe
LENSFX_PORT=18765
LENSFX_JOBS=%TEMP%\lensfx\jobs
```

## 安装（开发）

```bash
git clone https://github.com/ESRSchao/lensfx.git
cd lensfx
pip install -r requirements.txt
python -m lensfx doctor
```

## 用法

### 命令行

```bash
python -m lensfx input.jpg -o out.jpg --preset iphone
python -m lensfx input.mp4 -o out.mp4 --preset ugc --strength 1.0 --shutter 0.25 --handheld 0.25
python -m lensfx input.mp4 --analyze-only
```

### 本地界面

```bash
python -m lensfx serve
```

浏览器打开 <http://127.0.0.1:18765/>。上传上限 80 MB。任务写在系统临时目录 `lensfx/jobs`。

Windows 也可双击 `demo.cmd`。

### 桌面应用（Electron）

```bash
npm install
npm start
```

打包 Windows 安装包与便携版：

```bash
npm run dist
```

产物在 `dist/`：`Lensfx Setup x.y.z.exe`（NSIS）和 zip。安装包启动时会拉起本机 Python 引擎，因此目标机器仍需 Python 与 FFmpeg。

GitHub Releases 会在打 `v*` 标签时由 Actions 构建。

## 预设

| 预设 | 作用 |
| --- | --- |
| `auto` | 自适应：抬阴影、咬高光、轻度 JPEG，长边最多 1440 |
| `iphone` | 计算摄影：略暖、阴影更开、luma CAS |
| `ugc` | 1080p、略过曝、手持更明显、再压一遍 |
| `night` | 偏冷、阴影颗粒，暗部不抬飞 |
| `compress` | 两次编码，接近转发压缩 |

强度范围 `0.4–1.6`，默认 `1.0`。运动模糊 `--shutter` 范围 `0–1`（仅视频，默认约 `0.22`，`0` 关闭）。手持抖动 `--handheld` 范围 `0–1`（仅视频，默认约 `0.28`，`0` 关闭）。

## 项目结构

```
lensfx/          Python 引擎（pipeline + CLI + HTTP）
renderer/        静态 UI（Electron 与浏览器共用）
electron/        Electron 主进程 / preload
demo/            示例脚本（样本视频不进 git）
tests/           pytest
.github/         CI、Release、Issue 模板
```

处理图：`scale(never upscale) → tmix → crop-in handheld → lutyuv lift/clip → hue/eq → cas → spp(stills) → chromashift? → luma noise → yuv420p`。

## 开发

见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) 与 [CONTRIBUTING.md](CONTRIBUTING.md)。

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## 许可

[MIT](LICENSE)
