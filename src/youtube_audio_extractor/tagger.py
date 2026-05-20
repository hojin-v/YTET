from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .extractor import ExtractedFile, TrackMetadata


@dataclass(frozen=True)
class EmbedReport:
    embedded: bool
    format: str
    fields: list[str]
    warning: str | None = None


class TaggingError(RuntimeError):
    """Raised when audio metadata cannot be embedded."""


def embed_audio_metadata(
    audio_path: Path,
    metadata: "TrackMetadata",
    cover_file: "ExtractedFile | None",
) -> EmbedReport:
    suffix = audio_path.suffix.lower()
    if suffix in {".m4a", ".mp4"}:
        return embed_mp4(audio_path, metadata, cover_file)
    if suffix == ".mp3":
        return embed_mp3(audio_path, metadata, cover_file)
    if suffix == ".opus":
        return embed_ogg_opus(audio_path, metadata, cover_file)
    raise TaggingError(
        f"{suffix or 'unknown'} 포맷은 내부 메타데이터 임베딩을 지원하지 않습니다. "
        "m4a, mp3, original-opus 모드를 사용하세요."
    )


def embed_mp4(
    audio_path: Path,
    metadata: "TrackMetadata",
    cover_file: "ExtractedFile | None",
) -> EmbedReport:
    try:
        from mutagen.mp4 import MP4, MP4Cover
    except ModuleNotFoundError as exc:
        raise TaggingError("mutagen이 설치되어 있지 않아 m4a 태그를 쓸 수 없습니다.") from exc

    audio = MP4(str(audio_path))
    fields: list[str] = []

    set_mp4_text(audio, "\xa9nam", metadata.title, fields, "title")
    set_mp4_text(audio, "\xa9ART", metadata.artist, fields, "artist")
    set_mp4_text(audio, "aART", metadata.artist, fields, "album_artist")
    set_mp4_text(audio, "\xa9alb", metadata.album, fields, "album")
    set_mp4_text(audio, "\xa9day", format_date(metadata.upload_date), fields, "date")
    set_mp4_text(audio, "\xa9lyr", metadata.lyrics, fields, "lyrics")
    set_mp4_text(audio, "desc", metadata.channel, fields, "description")
    set_mp4_text(audio, "purl", metadata.webpage_url or metadata.source_url, fields, "url")
    set_mp4_text(audio, "\xa9cmt", comment_text(metadata), fields, "comment")

    cover_bytes, cover_format = mp4_cover_payload(cover_file)
    if cover_bytes and cover_format is not None:
        audio["covr"] = [MP4Cover(cover_bytes, imageformat=cover_format)]
        fields.append("cover")

    audio.save()
    return EmbedReport(embedded=True, format="mp4", fields=fields)


def embed_mp3(
    audio_path: Path,
    metadata: "TrackMetadata",
    cover_file: "ExtractedFile | None",
) -> EmbedReport:
    try:
        from mutagen.id3 import APIC, COMM, ID3, TALB, TDRC, TIT2, TPE1, TPE2, USLT, WXXX
        from mutagen.mp3 import MP3
    except ModuleNotFoundError as exc:
        raise TaggingError("mutagen이 설치되어 있지 않아 mp3 태그를 쓸 수 없습니다.") from exc

    audio = MP3(str(audio_path), ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    assert audio.tags is not None

    tags = audio.tags
    fields: list[str] = []

    set_id3_text(tags, "TIT2", TIT2, metadata.title, fields, "title")
    set_id3_text(tags, "TPE1", TPE1, metadata.artist, fields, "artist")
    set_id3_text(tags, "TPE2", TPE2, metadata.artist, fields, "album_artist")
    set_id3_text(tags, "TALB", TALB, metadata.album, fields, "album")
    set_id3_text(tags, "TDRC", TDRC, format_date(metadata.upload_date), fields, "date")

    if metadata.lyrics:
        tags.delall("USLT")
        tags.add(USLT(encoding=3, lang="und", desc="lyrics", text=metadata.lyrics))
        fields.append("lyrics")

    tags.delall("COMM")
    tags.add(COMM(encoding=3, lang="und", desc="source", text=comment_text(metadata)))
    fields.append("comment")

    if metadata.webpage_url or metadata.source_url:
        tags.delall("WXXX")
        tags.add(WXXX(encoding=3, desc="Source", url=metadata.webpage_url or metadata.source_url))
        fields.append("url")

    cover_bytes, cover_mime = cover_payload(cover_file)
    if cover_bytes and cover_mime:
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_bytes))
        fields.append("cover")

    audio.save(v2_version=3)
    return EmbedReport(embedded=True, format="mp3", fields=fields)


def embed_ogg_opus(
    audio_path: Path,
    metadata: "TrackMetadata",
    cover_file: "ExtractedFile | None",
) -> EmbedReport:
    try:
        from mutagen.oggopus import OggOpus
    except ModuleNotFoundError as exc:
        raise TaggingError("mutagen이 설치되어 있지 않아 opus 태그를 쓸 수 없습니다.") from exc

    audio = OggOpus(str(audio_path))
    audio.clear()
    fields = write_vorbis_comments(audio, metadata)

    picture = metadata_block_picture(cover_file)
    if picture:
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
        fields.append("cover")

    audio.save()
    return EmbedReport(embedded=True, format="ogg-opus", fields=fields)


def set_mp4_text(audio: object, key: str, value: str | None, fields: list[str], field_name: str) -> None:
    if not value:
        return
    audio[key] = [value]
    fields.append(field_name)


def set_id3_text(tags: object, frame_id: str, frame_type: object, value: str | None, fields: list[str], field_name: str) -> None:
    if not value:
        return
    tags.delall(frame_id)
    tags.add(frame_type(encoding=3, text=[value]))
    fields.append(field_name)


def cover_payload(cover_file: "ExtractedFile | None") -> tuple[bytes | None, str | None]:
    if not cover_file:
        return None, None
    mime_type = cover_file.mime_type
    if mime_type not in {"image/jpeg", "image/png"}:
        return None, None
    path = Path(cover_file.path)
    if not path.is_file():
        return None, None
    return path.read_bytes(), mime_type


def metadata_block_picture(cover_file: "ExtractedFile | None") -> object | None:
    try:
        from mutagen.flac import Picture
    except ModuleNotFoundError as exc:
        raise TaggingError("mutagen이 설치되어 있지 않아 커버 이미지를 쓸 수 없습니다.") from exc

    cover_bytes, mime_type = cover_payload(cover_file)
    if not cover_bytes or not mime_type:
        return None

    picture = Picture()
    picture.type = 3
    picture.mime = mime_type
    picture.desc = "Cover"
    picture.data = cover_bytes
    return picture


def mp4_cover_payload(cover_file: "ExtractedFile | None") -> tuple[bytes | None, int | None]:
    try:
        from mutagen.mp4 import MP4Cover
    except ModuleNotFoundError as exc:
        raise TaggingError("mutagen이 설치되어 있지 않아 커버 이미지를 쓸 수 없습니다.") from exc

    cover_bytes, mime_type = cover_payload(cover_file)
    if not cover_bytes:
        return None, None
    image_format = MP4Cover.FORMAT_PNG if mime_type == "image/png" else MP4Cover.FORMAT_JPEG
    return cover_bytes, image_format


def comment_text(metadata: "TrackMetadata") -> str:
    lines = [
        f"Source: {metadata.webpage_url or metadata.source_url}",
        f"Video ID: {metadata.video_id}" if metadata.video_id else None,
        f"Channel: {metadata.channel}" if metadata.channel else None,
        f"Lyrics source: {metadata.lyrics_source}" if metadata.lyrics_source else None,
    ]
    return "\n".join(line for line in lines if line)


def write_vorbis_comments(audio: object, metadata: "TrackMetadata") -> list[str]:
    fields: list[str] = []
    set_vorbis_text(audio, "title", metadata.title, fields, "title")
    set_vorbis_text(audio, "artist", metadata.artist, fields, "artist")
    set_vorbis_text(audio, "albumartist", metadata.artist, fields, "album_artist")
    set_vorbis_text(audio, "album", metadata.album, fields, "album")
    set_vorbis_text(audio, "date", format_date(metadata.upload_date), fields, "date")
    set_vorbis_text(audio, "lyrics", metadata.lyrics, fields, "lyrics")
    set_vorbis_text(audio, "description", metadata.channel, fields, "description")
    set_vorbis_text(audio, "website", metadata.webpage_url or metadata.source_url, fields, "url")
    set_vorbis_text(audio, "comment", comment_text(metadata), fields, "comment")
    return fields


def set_vorbis_text(audio: object, key: str, value: str | None, fields: list[str], field_name: str) -> None:
    if not value:
        return
    audio[key] = [value]
    fields.append(field_name)


def format_date(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value
