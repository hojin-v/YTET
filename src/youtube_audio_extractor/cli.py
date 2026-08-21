from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from . import __version__
from .extractor import ExtractorError, extract_youtube, extract_youtube_video
from .updater import check_yt_dlp_update, get_installed_yt_dlp_version, update_yt_dlp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YTET: extract audio or video from a YouTube URL.")
    parser.add_argument("url", nargs="?", default=None, help="YouTube URL")
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Show YTET and yt-dlp version info.",
    )
    parser.add_argument(
        "--update",
        "--update-engine",
        action="store_true",
        dest="update_engine",
        help="Update yt-dlp and plugins to the latest version.",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="Check if a newer version of yt-dlp is available.",
    )
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

    if args.version:
        yt_dlp_ver = get_installed_yt_dlp_version() or "not installed"
        print(f"YTET version: {__version__}")
        print(f"yt-dlp version: {yt_dlp_ver}")
        return 0

    if args.check_update:
        print("yt-dlp 업데이트 확인 중...")
        info = check_yt_dlp_update()
        print(f"현재 설치된 버전: {info['installed']}")
        print(f"최신 버전: {info['latest']}")
        if info["update_available"]:
            print(">> 새로운 버전이 있습니다. `ytet --update`를 실행하여 업데이트하세요.")
        else:
            print(">> 최신 버전을 사용 중입니다.")
        return 0

    if args.update_engine:
        print("yt-dlp 엔진 업데이트를 시작합니다...")
        success, message = update_yt_dlp(progress_callback=lambda msg: print(f"[*] {msg}"))
        print(message)
        return 0 if success else 1

    if not args.url:
        parser.print_help()
        return 1

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
        print("\n[안내] YouTube 변경으로 인한 오류인 경우 `ytet --update` 명령어로 yt-dlp 엔진을 최신 버전으로 업데이트해보세요.")
        return 1

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
