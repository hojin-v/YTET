from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .extractor import ExtractorError, extract_youtube, extract_youtube_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YTET: extract audio or video from a YouTube URL.")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument(
        "--media",
        choices=["audio", "video"],
        default="audio",
        help="Extract audio or video. Video mode embeds registered subtitles when available.",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output directory")
    parser.add_argument(
        "-f",
        "--format",
        choices=["m4a", "mp3", "original"],
        default=None,
        help="Output audio format. original keeps YouTube's best audio codec when possible.",
    )
    parser.add_argument(
        "--video-quality",
        choices=["best", "1080", "720", "480"],
        default=None,
        help="Video quality preset. best keeps the highest YouTube stream and may create MKV.",
    )
    parser.add_argument(
        "--include-subtitles",
        action="store_true",
        help="Include registered Korean/English subtitles in video mode.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output or Path("downloads") / time.strftime("cli-%Y%m%d-%H%M%S")

    def progress(payload: dict[str, Any]) -> None:
        percent = int(payload.get("percent") or 0)
        message = payload.get("message") or "처리 중"
        print(f"[{percent:3d}%] {message}", flush=True)

    try:
        if args.media == "video":
            result = extract_youtube_video(
                args.url,
                output_dir,
                progress,
                args.video_quality,
                include_subtitles=args.include_subtitles,
            )
        else:
            result = extract_youtube(args.url, output_dir, progress, args.format)
    except ExtractorError as exc:
        print(f"오류: {exc}")
        return 1

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
