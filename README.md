<div align="center">

# YTET

YouTube Extractor Toolkit

YouTube URL 하나로 오디오와 영상을 저장하는 Windows용 데스크톱 추출 도구입니다.

[![CI](https://github.com/hojin-v/YTET/actions/workflows/ci.yml/badge.svg)](https://github.com/hojin-v/YTET/actions/workflows/ci.yml)
[![Release](https://github.com/hojin-v/YTET/actions/workflows/release.yml/badge.svg)](https://github.com/hojin-v/YTET/actions/workflows/release.yml)
[![Latest Release](https://img.shields.io/github/v/release/hojin-v/YTET?label=release)](https://github.com/hojin-v/YTET/releases)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)

[Download](https://github.com/hojin-v/YTET/releases) · [Features](#features) · [Tech Stack](#tech-stack) · [Caution](#caution)

</div>

## Overview

YTET는 YouTube 링크를 오디오 파일이나 영상 파일로 저장합니다.

오디오는 커버 이미지와 제목, 아티스트, 원본 URL 같은 메타데이터를 파일 안에 포함합니다. 영상은 기본적으로 YouTube가 제공하는 최고 품질을 선택하고, 필요하면 1080p, 720p, 480p 이하의 낮은 용량 옵션으로 저장할 수 있습니다.

| Mode | Best For | Output |
| --- | --- | --- |
| Audio | 음악, 강의, 플레이리스트 정리 | `M4A (AAC)`, `Original Opus`, `MP3` |
| Video | 롱폼, 숏폼, 고화질 보관 | 최고 품질 `MKV` 또는 호환 우선 `MP4` |
| Subtitles | 한국어/영어 등록 자막 보관 | 영상 내 자막 트랙 + `.srt` |
| Multi Audio | 다국어 오디오 영상 | 원본 오디오 + 한국어 오디오 트랙 |

## Features

| Feature | Description |
| --- | --- |
| URL 기반 추출 | YouTube URL을 넣고 저장 폴더를 고르면 추출을 시작합니다. |
| 오디오 메타데이터 | 제목, 아티스트, 원본 URL, 커버 이미지를 가능한 범위에서 파일에 기록합니다. |
| 자동 파일명 | 오디오는 `artist - title`, 영상은 `channel - title` 형식으로 저장합니다. |
| 4K/8K 지원 | 최고 품질 모드에서 YouTube가 제공하는 고해상도 스트림을 선택합니다. |
| 저용량 영상 옵션 | 1080p, 720p, 480p 이하 품질로 저장할 수 있습니다. |
| 자막 처리 | 등록된 한국어/영어 자막을 저장하고 영상에도 삽입합니다. |
| 다중 오디오 | 한국어 오디오 트랙이 별도로 제공되면 영상에 함께 추가합니다. |

## Quick Start

1. [Releases](https://github.com/hojin-v/YTET/releases)에서 최신 `YTET.exe` 또는 `YTET-버전-windows-x64.zip`을 받습니다.
2. `YTET.exe`를 실행합니다.
3. YouTube URL을 입력합니다.
4. `음원` 또는 `영상 - 자막/다중 오디오 포함`을 선택합니다.
5. 저장 폴더와 포맷 또는 품질을 고릅니다.
6. `추출`을 누릅니다.

## Audio

| Format | When to Use |
| --- | --- |
| `M4A (AAC)` | Android와 Windows에서 무난하게 재생할 기본 추천 포맷 |
| `Original Opus` | YouTube 원본 오디오에 가깝고 용량 효율이 좋은 포맷 |
| `MP3` | 오래된 기기나 앱과의 호환성이 필요한 경우 |

오디오 추출 결과에는 가능한 경우 다음 정보가 포함됩니다.

- 제목
- 아티스트
- 원본 URL
- 커버 이미지
- 가사 또는 자막 기반 텍스트 정보

오디오 추출 시 별도의 커버 이미지 파일이나 메타데이터 파일은 남기지 않습니다.

## Video

| Quality Option | Container | Notes |
| --- | --- | --- |
| 최고 품질 - 4K/8K 가능 | `MKV` 가능 | YouTube가 제공하는 최고 영상 스트림과 최고 오디오 스트림을 저장합니다. |
| 1080p 이하 | `MP4` 우선 | 화질과 호환성의 균형이 좋습니다. |
| 720p 이하 | `MP4` 우선 | 용량을 줄이고 싶을 때 적합합니다. |
| 480p 이하 | `MP4` 우선 | 최소 용량이 중요할 때 사용합니다. |

YouTube의 4K 이상 영상은 보통 H.264 MP4가 아니라 VP9 또는 AV1 같은 고효율 코덱으로 제공됩니다. 그래서 최고 품질 결과는 `.mkv`가 될 수 있습니다.

호환성이 더 중요하면 1080p 이하 옵션을 권장합니다.

추출이 끝나면 앱의 결과 영역에서 최종 형식과 실제 화질/코덱을 확인할 수 있습니다.

```text
형식: MKV (.mkv)
화질/코덱: 3840x2160, 30fps, av1
```

## Subtitles & Audio Tracks

YTET는 업로더가 등록한 한국어와 영어 자막만 저장합니다.

저장 가능한 자막이 있으면 영상 파일 안에 자막 트랙을 넣고, 플레이어 호환을 위해 같은 이름의 `.srt` 파일도 함께 저장합니다.

자동 생성 자막만 있는 영상은 기본적으로 자막을 저장하지 않습니다.

여러 오디오 언어가 제공되는 영상에서는 원본 오디오를 유지합니다. 원본 오디오가 한국어가 아니고 YouTube가 한국어 오디오 트랙을 제공하면, 한국어 오디오도 함께 추가합니다.

## Output Rules

```text
audio:    artist - title.ext
video:    channel - title.ext
subtitle: channel - title.ko.srt
subtitle: channel - title.en.srt
```

## How It Works

```mermaid
flowchart LR
    A[YouTube URL] --> B[yt-dlp metadata lookup]
    B --> C{Mode}
    C -->|Audio| D[Download best audio]
    D --> E[Embed metadata and cover]
    E --> F[Save audio file]
    C -->|Video| G[Select quality profile]
    G --> H[Download video and audio streams]
    H --> I[Merge with FFmpeg]
    I --> J[Embed subtitles and extra Korean audio if available]
    J --> K[Save video and subtitle files]
```

## Tech Stack

| Layer | Technology | Role |
| --- | --- | --- |
| App | Python, Tkinter | Lightweight Windows desktop UI |
| Extraction | yt-dlp | YouTube metadata, stream selection, download orchestration |
| Media Processing | FFmpeg via imageio-ffmpeg | Audio conversion, video merge, subtitle/audio track muxing |
| Tagging | mutagen | Audio metadata and cover image embedding |
| Packaging | PyInstaller | Single-file Windows executable build |
| Automation | GitHub Actions | CI, Windows build, release publishing |

## Release Pipeline

```mermaid
flowchart TD
    A[Push to main] --> B[CI]
    B --> C[Windows build]
    C --> D[Nightly prerelease]
    E[Push v* tag] --> F[CI]
    F --> G[Windows build]
    G --> H[Versioned GitHub Release]
```

Every release build uploads:

- `YTET.exe`
- `YTET-버전-windows-x64.zip`

## Caution

- 권한이 있는 콘텐츠에만 사용하세요.
- YouTube 서비스 약관과 지역 법규를 확인해야 합니다.
- 영상 제공 품질, 자막, 다중 오디오 여부는 YouTube와 업로더 설정에 따라 달라집니다.
- 4K 이상 영상은 파일 크기가 클 수 있고, 일부 플레이어에서 코덱 지원이 필요할 수 있습니다.
- 처음 내려받은 실행 파일은 Windows 보안 경고가 표시될 수 있습니다. 신뢰할 수 있는 출처에서 받은 파일인지 확인한 뒤 실행하세요.
