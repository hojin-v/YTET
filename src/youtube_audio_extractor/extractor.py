from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .tagger import EmbedReport, TaggingError, embed_audio_metadata


ProgressCallback = Callable[[dict[str, Any]], None]

MAX_LYRICS_CHARS = 50_000
SUPPORTED_AUDIO_FORMATS = {"m4a", "mp3", "original"}
SUPPORTED_VIDEO_QUALITIES = {"best", "1080", "720", "480"}
SUBTITLE_LANGUAGES = ["ko", "ko-KR", "en", "en-US", "en-GB"]

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

TITLE_NOISE_PATTERNS = [
    r"\s*\((?:official\s+)?(?:music\s+)?video\)\s*",
    r"\s*\[(?:official\s+)?(?:music\s+)?video\]\s*",
    r"\s*\((?:official\s+)?audio\)\s*",
    r"\s*\[(?:official\s+)?audio\]\s*",
    r"\s*\((?:official\s+)?lyrics?\)\s*",
    r"\s*\[(?:official\s+)?lyrics?\]\s*",
    r"\s*\(mv\)\s*",
    r"\s*\[mv\]\s*",
    r"\s*\(뮤직비디오\)\s*",
    r"\s*\[뮤직비디오\]\s*",
    r"\s*\(가사\)\s*",
    r"\s*\[가사\]\s*",
]


class ExtractorError(RuntimeError):
    """Raised for user-facing extraction errors."""


@dataclass(frozen=True)
class TrackMetadata:
    source_url: str
    video_id: str | None
    title: str
    artist: str
    channel: str | None
    album: str | None
    duration_seconds: int | None
    duration_label: str | None
    upload_date: str | None
    webpage_url: str | None
    cover_source_url: str | None
    lyrics: str | None
    lyrics_source: str | None


@dataclass(frozen=True)
class ExtractedFile:
    name: str
    path: str
    bytes: int
    mime_type: str


@dataclass(frozen=True)
class ExtractionResult:
    metadata: TrackMetadata
    audio: ExtractedFile
    cover: ExtractedFile | None
    metadata_file: ExtractedFile | None
    embed_report: EmbedReport
    extracted_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VideoExtractionResult:
    metadata: TrackMetadata
    video: ExtractedFile
    subtitle_languages: list[str]
    subtitle_files: list[ExtractedFile]
    audio_languages: list[str]
    video_quality: str | None
    subtitles_embedded: bool
    extracted_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_youtube_url(url: str) -> str:
    candidate = (url or "").strip()
    if not candidate:
        raise ExtractorError("YouTube URL을 입력하세요.")

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ExtractorError("http 또는 https로 시작하는 YouTube URL만 지원합니다.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS and not host.endswith(".youtube.com"):
        raise ExtractorError("YouTube, YouTube Music, youtu.be URL만 지원합니다.")

    return candidate


def load_yt_dlp() -> Any:
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
    except ModuleNotFoundError as exc:
        raise ExtractorError(
            "yt-dlp가 설치되어 있지 않습니다. `python -m pip install -e .`를 실행하세요."
        ) from exc
    return YoutubeDL, DownloadError


def normalize_audio_format(value: str | None = None) -> str:
    audio_format = (value or os.environ.get("YTET_AUDIO_FORMAT") or os.environ.get("YME_AUDIO_FORMAT") or "m4a").strip().lower()
    if audio_format in {"best", "highest", "source"}:
        audio_format = "original"
    if audio_format not in SUPPORTED_AUDIO_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_FORMATS))
        raise ExtractorError(f"지원하지 않는 오디오 포맷입니다: {audio_format}. 지원: {supported}")
    return audio_format


def normalize_video_quality(value: str | None = None) -> str:
    quality = (value or os.environ.get("YTET_VIDEO_QUALITY") or os.environ.get("YME_VIDEO_QUALITY") or "best").strip().lower()
    aliases = {
        "highest": "best",
        "source": "best",
        "original": "best",
        "max": "best",
        "4k": "best",
        "8k": "best",
        "2160": "best",
        "2160p": "best",
        "1080p": "1080",
        "fhd": "1080",
        "720p": "720",
        "hd": "720",
        "480p": "480",
        "sd": "480",
    }
    quality = aliases.get(quality, quality.rstrip("p"))
    if quality not in SUPPORTED_VIDEO_QUALITIES:
        supported = ", ".join(["best", "1080", "720", "480"])
        raise ExtractorError(f"지원하지 않는 영상 화질입니다: {quality}. 지원: {supported}")
    return quality


def extract_youtube(
    url: str,
    output_dir: Path,
    progress: ProgressCallback | None = None,
    audio_format: str | None = None,
) -> ExtractionResult:
    safe_url = validate_youtube_url(url)
    selected_audio_format = normalize_audio_format(audio_format)
    output_dir.mkdir(parents=True, exist_ok=True)

    emit(progress, stage="metadata", percent=3, message="영상 정보를 읽는 중")
    info = fetch_video_info(safe_url)
    metadata = build_track_metadata(info, safe_url)

    with tempfile.TemporaryDirectory(prefix="ytet-") as temp_dir:
        emit(progress, stage="cover", percent=18, message="표지 이미지를 가져오는 중")
        cover_file = download_cover(metadata.cover_source_url, Path(temp_dir))

        emit(progress, stage="audio", percent=25, message="오디오 다운로드를 시작하는 중")
        audio_file = download_audio(safe_url, output_dir, progress, selected_audio_format)

        emit(progress, stage="tagging", percent=97, message="오디오 파일에 태그를 쓰는 중")
        try:
            embed_report = embed_audio_metadata(Path(audio_file.path), metadata, cover_file)
        except TaggingError as exc:
            raise ExtractorError(str(exc)) from exc

    audio_path = rename_audio_file(Path(audio_file.path), metadata)
    audio_file = file_record(audio_path, audio_file.mime_type)

    emit(progress, stage="done", percent=100, message="추출 완료")
    return ExtractionResult(
        metadata=metadata,
        audio=audio_file,
        cover=None,
        metadata_file=None,
        embed_report=embed_report,
        extracted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )


def extract_youtube_video(
    url: str,
    output_dir: Path,
    progress: ProgressCallback | None = None,
    video_quality: str | None = None,
) -> VideoExtractionResult:
    safe_url = validate_youtube_url(url)
    selected_video_quality = normalize_video_quality(video_quality)
    output_dir.mkdir(parents=True, exist_ok=True)

    emit(progress, stage="metadata", percent=3, message="영상 정보를 읽는 중")
    info = fetch_video_info(safe_url)
    metadata = build_track_metadata(info, safe_url, include_lyrics=False)

    emit(progress, stage="video", percent=20, message="영상 다운로드를 시작하는 중")
    video_file, _requested_subtitle_languages, subtitle_paths, audio_languages = download_video(
        safe_url,
        output_dir,
        progress,
        selected_video_quality,
    )
    video_path = rename_video_file(Path(video_file.path), metadata)
    video_file = file_record(video_path, video_file.mime_type)
    subtitle_files = [file_record(path, mime_for_subtitle(path)) for path in rename_subtitle_sidecars(subtitle_paths, video_path)]
    subtitle_languages = actual_subtitle_languages(video_path, [Path(item.path) for item in subtitle_files])
    subtitles_embedded = bool(subtitle_stream_languages(video_path))

    emit(progress, stage="done", percent=100, message="영상 추출 완료")
    return VideoExtractionResult(
        metadata=metadata,
        video=video_file,
        subtitle_languages=subtitle_languages,
        subtitle_files=subtitle_files,
        audio_languages=audio_languages,
        video_quality=video_quality_from_file(video_path) or video_quality_from_info(info),
        subtitles_embedded=subtitles_embedded,
        extracted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )


def fetch_video_info(url: str) -> dict[str, Any]:
    YoutubeDL, DownloadError = load_yt_dlp()
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise ExtractorError(f"YouTube 정보를 가져오지 못했습니다: {exc}") from exc

    if not isinstance(info, dict):
        raise ExtractorError("YouTube 응답을 해석하지 못했습니다.")
    if "entries" in info:
        raise ExtractorError("플레이리스트가 아닌 단일 영상 URL을 입력하세요.")
    return info


def build_track_metadata(
    info: dict[str, Any],
    source_url: str,
    include_lyrics: bool = True,
) -> TrackMetadata:
    explicit_artist = first_text(info.get("artist"), info.get("creator"))
    fallback_artist = first_text(info.get("uploader"), info.get("channel"))
    channel = first_text(info.get("channel"), info.get("uploader"))
    track = first_text(info.get("track"))
    raw_title = first_text(info.get("title"), info.get("fulltitle"), "untitled")

    if track:
        title = clean_title(track)
        artist = explicit_artist or fallback_artist or "Unknown artist"
    else:
        parsed = split_artist_title(raw_title)
        if parsed and not explicit_artist:
            artist, title = parsed
        else:
            title = clean_title(raw_title)
            artist = explicit_artist or fallback_artist or "Unknown artist"

    duration = as_int(info.get("duration"))
    lyrics, lyrics_source = pick_lyrics(info) if include_lyrics else (None, None)
    return TrackMetadata(
        source_url=source_url,
        video_id=first_text(info.get("id")),
        title=title,
        artist=artist,
        channel=channel,
        album=first_text(info.get("album")),
        duration_seconds=duration,
        duration_label=format_duration(duration),
        upload_date=first_text(info.get("upload_date")),
        webpage_url=first_text(info.get("webpage_url"), source_url),
        cover_source_url=pick_cover_url(info),
        lyrics=lyrics,
        lyrics_source=lyrics_source,
    )


def split_artist_title(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None

    pieces = re.split(r"\s+[-–—]\s+", value, maxsplit=1)
    if len(pieces) != 2:
        return None

    artist = clean_title(pieces[0])
    title = clean_title(pieces[1])
    if not artist or not title:
        return None
    return artist, title


def clean_title(value: str | None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    for pattern in TITLE_NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" -–—") or "untitled"


def pick_cover_url(info: dict[str, Any]) -> str | None:
    thumbnails = info.get("thumbnails")
    if not isinstance(thumbnails, list):
        return first_text(info.get("thumbnail"))

    candidates: list[tuple[int, int, str]] = []
    for item in thumbnails:
        if not isinstance(item, dict):
            continue
        url = first_text(item.get("url"))
        if not url:
            continue
        width = as_int(item.get("width")) or 0
        height = as_int(item.get("height")) or 0
        area = width * height
        extension_bonus = 10_000 if urlparse(url).path.lower().endswith((".jpg", ".jpeg", ".png")) else 0
        candidates.append((area + extension_bonus, len(url), url))

    if not candidates:
        return first_text(info.get("thumbnail"))
    return sorted(candidates, reverse=True)[0][2]


def pick_lyrics(info: dict[str, Any]) -> tuple[str | None, str | None]:
    explicit = first_text(
        info.get("lyrics"),
        info.get("lyric"),
        info.get("unsynced_lyrics"),
        info.get("unsyncedlyrics"),
    )
    if explicit:
        return normalize_lyrics(explicit), "metadata"

    selected = select_subtitle(info.get("subtitles"))
    if not selected and (os.environ.get("YTET_USE_AUTO_LYRICS") == "1" or os.environ.get("YME_USE_AUTO_LYRICS") == "1"):
        selected = select_subtitle(info.get("automatic_captions"), automatic=True)
    if not selected:
        return None, None

    url, extension, language, automatic = selected
    lyrics = download_subtitle_lyrics(url, extension)
    if not lyrics:
        return None, None

    source_kind = "auto subtitle" if automatic else "subtitle"
    return lyrics, f"YouTube {source_kind}: {language}"


def select_subtitle(
    subtitles: Any,
    automatic: bool = False,
) -> tuple[str, str, str, bool] | None:
    if not isinstance(subtitles, dict) or not subtitles:
        return None

    priority = SUBTITLE_LANGUAGES
    languages = [lang for lang in priority if lang in subtitles]
    languages.extend(lang for lang in sorted(subtitles) if lang not in languages)

    for language in languages:
        entries = subtitles.get(language)
        if not isinstance(entries, list):
            continue
        for extension in ["json3", "vtt", "ttml", "srv3"]:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = first_text(entry.get("url"))
                if url and first_text(entry.get("ext")) == extension:
                    return url, extension, language, automatic
    return None


def download_subtitle_lyrics(url: str, extension: str) -> str | None:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            text = response.read(5 * 1024 * 1024).decode("utf-8", errors="replace")
    except OSError:
        return None

    if extension == "json3":
        return lyrics_from_json3(text)
    return lyrics_from_timed_text(text)


def lyrics_from_json3(text: str) -> str | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    lines: list[str] = []
    events = data.get("events")
    if not isinstance(events, list):
        return None

    for event in events:
        if not isinstance(event, dict):
            continue
        segments = event.get("segs")
        if not isinstance(segments, list):
            continue
        line = "".join(str(segment.get("utf8") or "") for segment in segments if isinstance(segment, dict))
        if line.strip():
            lines.append(line)
    return normalize_lyrics("\n".join(lines))


def lyrics_from_timed_text(text: str) -> str | None:
    lines: list[str] = []
    skip_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            skip_block = False
            continue
        upper = line.upper()
        if upper.startswith(("WEBVTT", "KIND:", "LANGUAGE:", "REGION")):
            continue
        if upper.startswith(("NOTE", "STYLE")):
            skip_block = True
            continue
        if skip_block or "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<br\s*/?>", "\n", line, flags=re.IGNORECASE)
        line = re.sub(r"<[^>]+>", "", line)
        lines.append(line)
    return normalize_lyrics("\n".join(lines))


def normalize_lyrics(value: str | None) -> str | None:
    if not value:
        return None

    cleaned_lines: list[str] = []
    previous = ""
    for raw_line in html.unescape(value).replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if line.lower() in {"[music]", "[applause]", "[음악]", "♪"}:
            continue
        if line == previous:
            continue
        cleaned_lines.append(line)
        previous = line

    lyrics = "\n".join(cleaned_lines).strip()
    if not lyrics:
        return None
    return lyrics[:MAX_LYRICS_CHARS]


def download_cover(url: str | None, output_dir: Path) -> ExtractedFile | None:
    if not url:
        return None

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type() or "image/jpeg"
            data = response.read(25 * 1024 * 1024)
    except OSError:
        return None

    suffix = suffix_for_image(url, content_type)
    path = output_dir / f"cover{suffix}"
    path.write_bytes(data)
    return file_record(path, content_type)


def download_audio(
    url: str,
    output_dir: Path,
    progress: ProgressCallback | None = None,
    audio_format: str | None = None,
) -> ExtractedFile:
    YoutubeDL, DownloadError = load_yt_dlp()
    audio_format = normalize_audio_format(audio_format)
    options = audio_download_options(output_dir, audio_format, progress)

    try:
        with YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise ExtractorError(f"오디오 다운로드에 실패했습니다: {exc}") from exc

    audio_path = find_downloaded_audio(output_dir)
    if audio_format == "original":
        audio_path = remux_webm_opus_if_needed(audio_path)
    return file_record(audio_path, mime_for_audio(audio_path))


def download_video(
    url: str,
    output_dir: Path,
    progress: ProgressCallback | None = None,
    video_quality: str | None = None,
) -> tuple[ExtractedFile, list[str], list[Path], list[str]]:
    YoutubeDL, DownloadError = load_yt_dlp()
    options = video_download_options(output_dir, progress, video_quality)

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise ExtractorError(f"영상 다운로드에 실패했습니다: {exc}") from exc

    video_path = find_downloaded_video(output_dir)
    audio_languages = ensure_korean_audio_if_available(video_path, info, url, progress)
    subtitle_paths = collect_subtitle_sidecars(output_dir)
    return file_record(video_path, mime_for_video(video_path)), subtitle_languages_from_info(info), subtitle_paths, audio_languages


def audio_download_options(
    output_dir: Path,
    audio_format: str,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    ffmpeg_location = None
    if audio_format == "mp3":
        ffmpeg_location = require_ffmpeg()

    if audio_format == "mp3":
        format_selector = "bestaudio/best"
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ]
    elif audio_format == "original":
        format_selector = "bestaudio/best"
        postprocessors = []
    else:
        format_selector = "bestaudio[ext=m4a]/bestaudio/best"
        postprocessors = []

    options = {
        "format": format_selector,
        "outtmpl": {"default": str(output_dir / "audio.%(ext)s")},
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
        "progress_hooks": [make_progress_hook(progress)],
        "postprocessors": postprocessors,
    }
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    return options


def video_download_options(
    output_dir: Path,
    progress: ProgressCallback | None,
    video_quality: str | None = None,
) -> dict[str, Any]:
    ffmpeg_location = require_ffmpeg()
    format_selector, merge_output_format = video_quality_profile(video_quality)
    return {
        "format": format_selector,
        "outtmpl": {"default": str(output_dir / "video.%(ext)s")},
        "merge_output_format": merge_output_format,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
        "progress_hooks": [make_video_progress_hook(progress)],
        "ffmpeg_location": ffmpeg_location,
        "writesubtitles": True,
        "writeautomaticsub": False,
        "subtitleslangs": SUBTITLE_LANGUAGES,
        "subtitlesformat": "srt/vtt/best",
        "postprocessors": [
            {
                "key": "FFmpegEmbedSubtitle",
                "already_have_subtitle": True,
            }
        ],
    }


def video_quality_profile(video_quality: str | None = None) -> tuple[str, str]:
    quality = normalize_video_quality(video_quality)
    if quality == "best":
        return "bestvideo+bestaudio/best", "mkv"

    max_height = int(quality)
    format_selector = (
        f"bestvideo[height<={max_height}][vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
        f"best[height<={max_height}][vcodec^=avc1][ext=mp4]/"
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"best[height<={max_height}][ext=mp4]/"
        f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best"
    )
    return format_selector, "mp4"


def ensure_korean_audio_if_available(
    video_path: Path,
    info: Any,
    url: str,
    progress: ProgressCallback | None = None,
) -> list[str]:
    audio_languages = selected_audio_languages_from_info(info)
    if any(is_korean_language(language) for language in audio_languages):
        return audio_languages

    korean_format = select_korean_audio_format(info)
    if not korean_format:
        return audio_languages

    emit(progress, stage="audio", percent=97, message="한국어 오디오 트랙을 추가하는 중")
    with tempfile.TemporaryDirectory(prefix="youtube-audio-korean-") as temp_dir:
        korean_audio = download_format_to_temp(url, str(korean_format["format_id"]), Path(temp_dir))
        mux_extra_audio_track(
            video_path,
            korean_audio,
            language="kor",
            title="Korean",
            transcode_to_aac=not is_aac_format(korean_format),
        )

    languages = list(audio_languages)
    if not any(is_korean_language(language) for language in languages):
        languages.append("ko")
    return languages


def selected_audio_languages_from_info(info: Any) -> list[str]:
    if not isinstance(info, dict):
        return []
    formats = info.get("requested_formats")
    if not isinstance(formats, list):
        formats = [info]

    languages: list[str] = []
    for item in formats:
        if not isinstance(item, dict) or not has_audio(item):
            continue
        language = first_text(item.get("language"))
        if language and language not in languages:
            languages.append(language)
    return languages


def select_korean_audio_format(info: Any) -> dict[str, Any] | None:
    if not isinstance(info, dict):
        return None
    formats = info.get("formats")
    if not isinstance(formats, list):
        return None

    candidates = [
        item
        for item in formats
        if isinstance(item, dict)
        and item.get("format_id")
        and is_audio_only(item)
        and is_korean_language(first_text(item.get("language")))
    ]
    if not candidates:
        return None

    return max(candidates, key=korean_audio_quality_key)


def korean_audio_quality_key(item: dict[str, Any]) -> tuple[int, int, int, int]:
    extension = first_text(item.get("ext")) or ""
    codec = first_text(item.get("acodec")) or ""
    bitrate = as_int(item.get("abr")) or as_int(item.get("tbr")) or 0
    filesize = as_int(item.get("filesize")) or as_int(item.get("filesize_approx")) or 0
    return (
        1 if extension == "m4a" else 0,
        1 if codec.startswith("mp4a") else 0,
        bitrate,
        filesize,
    )


def is_audio_only(item: dict[str, Any]) -> bool:
    return has_audio(item) and first_text(item.get("vcodec"), "none") == "none"


def has_audio(item: dict[str, Any]) -> bool:
    return first_text(item.get("acodec"), "none") != "none"


def is_aac_format(item: dict[str, Any]) -> bool:
    return (first_text(item.get("ext")) == "m4a") or (first_text(item.get("acodec")) or "").startswith("mp4a")


def is_korean_language(language: str | None) -> bool:
    if not language:
        return False
    normalized = language.replace("_", "-").lower()
    return normalized == "ko" or normalized.startswith("ko-") or normalized == "kor"


def download_format_to_temp(url: str, format_id: str, output_dir: Path) -> Path:
    YoutubeDL, DownloadError = load_yt_dlp()
    options = {
        "format": format_id,
        "outtmpl": {"default": str(output_dir / "audio.%(ext)s")},
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "windowsfilenames": True,
    }
    try:
        with YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise ExtractorError(f"한국어 오디오 다운로드에 실패했습니다: {exc}") from exc

    candidates = [path for path in output_dir.glob("audio.*") if path.is_file() and path.suffix.lower() not in {".part", ".ytdl", ".json"}]
    if not candidates:
        raise ExtractorError("다운로드된 한국어 오디오 파일을 찾지 못했습니다.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def mux_extra_audio_track(
    video_path: Path,
    audio_path: Path,
    language: str,
    title: str,
    transcode_to_aac: bool,
) -> None:
    ffmpeg_path = require_ffmpeg()
    temp_path = video_path.with_name(f"{video_path.stem}.temp-audio{video_path.suffix}")
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0",
        "-map",
        "1:a:0",
        "-c",
        "copy",
    ]
    if transcode_to_aac:
        command.extend(["-c:a:1", "aac", "-b:a:1", "160k"])
    command.extend(
        [
            "-metadata:s:a:1",
            f"language={language}",
            "-metadata:s:a:1",
            f"title={title}",
            str(temp_path),
        ]
    )

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not temp_path.is_file():
        temp_path.unlink(missing_ok=True)
        raise ExtractorError(f"한국어 오디오 트랙 추가에 실패했습니다: {completed.stderr.strip()}")
    temp_path.replace(video_path)


def require_ffmpeg() -> str:
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        raise ExtractorError("mp3 변환은 ffmpeg가 필요합니다. `python -m pip install -e .`를 다시 실행하세요.")
    return ffmpeg_path


def find_ffmpeg() -> str | None:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
    except ModuleNotFoundError:
        return None
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    if ffmpeg_path and Path(ffmpeg_path).is_file():
        return ffmpeg_path
    return None


def remux_webm_opus_if_needed(audio_path: Path) -> Path:
    if audio_path.suffix.lower() != ".webm":
        return audio_path

    ffmpeg_path = require_ffmpeg()
    opus_path = audio_path.with_suffix(".opus")
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(audio_path),
        "-vn",
        "-c:a",
        "copy",
        str(opus_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not opus_path.is_file():
        raise ExtractorError(f"최고음질 Opus remux에 실패했습니다: {completed.stderr.strip()}")
    audio_path.unlink(missing_ok=True)
    return opus_path


def rename_audio_file(audio_path: Path, metadata: TrackMetadata) -> Path:
    target_name = safe_audio_filename(metadata, audio_path.suffix)
    target_path = unique_path(audio_path.with_name(target_name))
    if target_path == audio_path:
        return audio_path
    audio_path.rename(target_path)
    return target_path


def rename_video_file(video_path: Path, metadata: TrackMetadata) -> Path:
    target_name = safe_video_filename(metadata, video_path.suffix)
    target_path = unique_path(video_path.with_name(target_name))
    if target_path == video_path:
        return video_path
    video_path.rename(target_path)
    return target_path


def rename_subtitle_sidecars(subtitle_paths: Sequence[Path], video_path: Path) -> list[Path]:
    renamed: list[Path] = []
    for subtitle_path in subtitle_paths:
        if not subtitle_path.exists():
            continue
        language = subtitle_language_from_path(subtitle_path)
        target_path = unique_path(video_path.with_name(f"{video_path.stem}.{language}{subtitle_path.suffix.lower()}"))
        if target_path != subtitle_path:
            subtitle_path.rename(target_path)
        renamed.append(target_path)
    return renamed


def safe_audio_filename(metadata: TrackMetadata, suffix: str) -> str:
    artist = sanitize_filename_part(metadata.artist or "Unknown artist")
    title = sanitize_filename_part(metadata.title or "untitled")
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{artist} - {title}{extension}"


def safe_video_filename(metadata: TrackMetadata, suffix: str) -> str:
    channel = sanitize_filename_part(metadata.channel or metadata.artist or "Unknown channel")
    title = sanitize_filename_part(metadata.title or "untitled")
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{channel} - {title}{extension}"


def sanitize_filename_part(value: str, fallback: str = "untitled") -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(". ")
    text = re.sub(r"_+", "_", text)
    text = text.rstrip("_. ")
    return text[:120].strip(". ") or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
    raise ExtractorError("중복되지 않는 오디오 파일명을 만들지 못했습니다.")


def make_progress_hook(progress: ProgressCallback | None) -> Callable[[dict[str, Any]], None]:
    def hook(state: dict[str, Any]) -> None:
        status = state.get("status")
        if status == "downloading":
            downloaded = state.get("downloaded_bytes") or 0
            total = state.get("total_bytes") or state.get("total_bytes_estimate") or 0
            percent = 25
            if total:
                percent = 25 + min(70, int((downloaded / total) * 70))
            emit(
                progress,
                stage="audio",
                percent=percent,
                message="오디오 다운로드 중",
                downloaded_bytes=downloaded,
                total_bytes=total or None,
            )
        elif status == "finished":
            emit(progress, stage="audio", percent=96, message="오디오 파일 정리 중")

    return hook


def make_video_progress_hook(progress: ProgressCallback | None) -> Callable[[dict[str, Any]], None]:
    def hook(state: dict[str, Any]) -> None:
        status = state.get("status")
        if status == "downloading":
            downloaded = state.get("downloaded_bytes") or 0
            total = state.get("total_bytes") or state.get("total_bytes_estimate") or 0
            percent = 20
            if total:
                percent = 20 + min(75, int((downloaded / total) * 75))
            emit(
                progress,
                stage="video",
                percent=percent,
                message="영상 다운로드 중",
                downloaded_bytes=downloaded,
                total_bytes=total or None,
            )
        elif status == "finished":
            emit(progress, stage="video", percent=96, message="영상 파일과 자막을 정리하는 중")

    return hook


def find_downloaded_audio(output_dir: Path) -> Path:
    ignored_suffixes = {".part", ".ytdl", ".json", ".jpg", ".jpeg", ".png", ".webp"}
    candidates = [
        path
        for path in output_dir.glob("audio.*")
        if path.is_file() and path.suffix.lower() not in ignored_suffixes
    ]
    if not candidates:
        raise ExtractorError("다운로드된 오디오 파일을 찾지 못했습니다.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def find_downloaded_video(output_dir: Path) -> Path:
    ignored_suffixes = {
        ".part",
        ".ytdl",
        ".json",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".vtt",
        ".srt",
        ".ttml",
        ".srv1",
        ".srv2",
        ".srv3",
    }
    candidates = [
        path
        for path in output_dir.glob("video.*")
        if path.is_file() and path.suffix.lower() not in ignored_suffixes
    ]
    if not candidates:
        raise ExtractorError("다운로드된 영상 파일을 찾지 못했습니다.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def collect_subtitle_sidecars(output_dir: Path) -> list[Path]:
    subtitle_suffixes = {".vtt", ".srt", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}
    paths = [
        path
        for path in output_dir.glob("video.*")
        if path.is_file() and path.suffix.lower() in subtitle_suffixes
    ]
    return sorted(paths)


def cleanup_subtitle_sidecars(output_dir: Path) -> None:
    subtitle_suffixes = {".vtt", ".srt", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}
    for path in output_dir.glob("video.*"):
        if path.suffix.lower() in subtitle_suffixes:
            path.unlink(missing_ok=True)


def subtitle_language_from_path(path: Path) -> str:
    pieces = path.name.split(".")
    if len(pieces) >= 3:
        return sanitize_filename_part(pieces[-2], "und")
    return "und"


def subtitle_languages_from_info(info: Any) -> list[str]:
    if not isinstance(info, dict):
        return []
    requested = info.get("requested_subtitles")
    if not isinstance(requested, dict):
        return []
    return sorted(str(language) for language in requested if language)


def actual_subtitle_languages(video_path: Path, subtitle_paths: Sequence[Path]) -> list[str]:
    languages: list[str] = []
    for language in subtitle_stream_languages(video_path):
        if language not in languages:
            languages.append(language)
    for path in subtitle_paths:
        language = subtitle_language_from_path(path)
        if language not in languages:
            languages.append(language)
    return languages


def subtitle_stream_languages(video_path: Path) -> list[str]:
    data = ffprobe_json(video_path)
    languages: list[str] = []
    if data:
        for stream in data.get("streams", []):
            if not isinstance(stream, dict) or stream.get("codec_type") != "subtitle":
                continue
            tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
            language = normalize_media_language(first_text(tags.get("language"), tags.get("handler_name"), "und"))
            if language and language not in languages:
                languages.append(language)
    if languages:
        return languages
    return parse_subtitle_languages_from_ffmpeg_output(ffmpeg_probe_text(video_path) or "")
    return languages


def video_quality_from_info(info: Any) -> str | None:
    if not isinstance(info, dict):
        return None
    video_format = None
    formats = info.get("requested_formats")
    if isinstance(formats, list):
        video_format = next((item for item in formats if isinstance(item, dict) and first_text(item.get("vcodec"), "none") != "none"), None)
    if not isinstance(video_format, dict):
        video_format = info
    height = as_int(video_format.get("height"))
    width = as_int(video_format.get("width"))
    fps = as_int(video_format.get("fps"))
    codec = first_text(video_format.get("vcodec"))
    parts: list[str] = []
    if width and height:
        parts.append(f"{width}x{height}")
    elif height:
        parts.append(f"{height}p")
    if fps:
        parts.append(f"{fps}fps")
    if codec and codec != "none":
        parts.append(codec)
    return ", ".join(parts) or None


def video_quality_from_file(video_path: Path) -> str | None:
    data = ffprobe_json(video_path)
    if data:
        for stream in data.get("streams", []):
            if not isinstance(stream, dict) or stream.get("codec_type") != "video":
                continue
            return format_video_quality(
                as_int(stream.get("width")),
                as_int(stream.get("height")),
                format_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
                first_text(stream.get("codec_name")),
            )
    return parse_video_quality_from_ffmpeg_output(ffmpeg_probe_text(video_path) or "")


def format_video_quality(width: int | None, height: int | None, fps: str | None, codec: str | None) -> str | None:
    parts: list[str] = []
    if width and height:
        parts.append(f"{width}x{height}")
    elif height:
        parts.append(f"{height}p")
    if fps:
        parts.append(f"{fps}fps")
    if codec and codec != "none":
        parts.append(codec)
    return ", ".join(parts) or None


def format_fps(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return str(int(value)) if float(value).is_integer() else f"{float(value):.2f}".rstrip("0").rstrip(".")

    text = str(value).strip()
    if not text or text == "0/0":
        return None
    if "/" not in text:
        number = as_float(text)
        if not number:
            return None
        return str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")

    numerator_text, denominator_text = text.split("/", 1)
    numerator = as_float(numerator_text)
    denominator = as_float(denominator_text)
    if not numerator or not denominator:
        return None
    fps = numerator / denominator
    return str(int(fps)) if fps.is_integer() else f"{fps:.2f}".rstrip("0").rstrip(".")


def ffmpeg_probe_text(path: Path) -> str | None:
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        return None
    completed = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = "\n".join(part for part in [completed.stderr, completed.stdout] if part)
    return text or None


def parse_video_quality_from_ffmpeg_output(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "Video:" not in line:
            continue
        codec_match = re.search(r"Video:\s*([^,\s]+)", line)
        size_match = re.search(r"(?<![\w])(\d{2,5})x(\d{2,5})(?![\w])", line)
        fps_match = re.search(r",\s*([0-9]+(?:\.[0-9]+)?)\s*fps\b", line)
        width = as_int(size_match.group(1)) if size_match else None
        height = as_int(size_match.group(2)) if size_match else None
        fps = format_fps(fps_match.group(1)) if fps_match else None
        codec = codec_match.group(1) if codec_match else None
        quality = format_video_quality(width, height, fps, codec)
        if quality:
            return quality
    return None


def parse_subtitle_languages_from_ffmpeg_output(text: str) -> list[str]:
    languages: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "Subtitle:" not in line:
            continue
        match = re.search(r"Stream\s+#\d+:\d+(?:\[[^\]]+\])?(?:\(([^)]+)\))?:\s*Subtitle:", line)
        language = normalize_media_language(match.group(1) if match else None)
        if language and language not in languages:
            languages.append(language)
    return languages


def normalize_media_language(language: str | None) -> str | None:
    value = (language or "").strip().replace("_", "-")
    if not value:
        return None
    lowered = value.lower()
    mapped = {
        "eng": "en",
        "english": "en",
        "en-us": "en",
        "en-gb": "en",
        "kor": "ko",
        "korean": "ko",
        "ko-kr": "ko",
    }.get(lowered)
    return mapped or lowered


def ffprobe_json(path: Path) -> dict[str, Any] | None:
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        return None
    probe_path = str(Path(ffmpeg_path).with_name("ffprobe"))
    if not Path(probe_path).is_file():
        probe_path = shutil.which("ffprobe") or ""
    if not probe_path:
        return None

    completed = subprocess.run(
        [probe_path, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def file_record(path: Path, mime_type: str) -> ExtractedFile:
    return ExtractedFile(
        name=path.name,
        path=str(path.resolve()),
        bytes=path.stat().st_size,
        mime_type=mime_type,
    )


def suffix_for_image(url: str, content_type: str) -> str:
    by_type = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    if content_type in by_type:
        return by_type[content_type]

    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def mime_for_audio(path: Path) -> str:
    return {
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".webm": "audio/webm",
        ".opus": "audio/ogg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
    }.get(path.suffix.lower(), "application/octet-stream")


def mime_for_video(path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
    }.get(path.suffix.lower(), "application/octet-stream")


def mime_for_subtitle(path: Path) -> str:
    return {
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",
        ".ttml": "application/ttml+xml",
    }.get(path.suffix.lower(), "text/plain")


def first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def emit(progress: ProgressCallback | None, **payload: Any) -> None:
    if progress:
        progress(payload)
