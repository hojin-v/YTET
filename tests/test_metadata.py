import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from youtube_audio_extractor.extractor import (
    ExtractorError,
    extract_youtube,
    extract_youtube_video,
    build_track_metadata,
    clean_title,
    file_record,
    normalize_audio_format,
    normalize_video_quality,
    parse_subtitle_languages_from_ffmpeg_output,
    parse_video_quality_from_ffmpeg_output,
    pick_cover_url,
    remux_m4a_for_compatibility,
    lyrics_from_json3,
    lyrics_from_timed_text,
    split_artist_title,
    safe_audio_filename,
    safe_video_filename,
    rename_subtitle_sidecars,
    subtitle_stream_languages,
    subtitle_languages_from_info,
    video_download_options,
    video_quality_from_info,
    validate_youtube_url,
    yt_dlp_base_options,
)
from youtube_audio_extractor.tagger import EmbedReport


class MetadataTests(unittest.TestCase):
    def test_validates_youtube_urls(self):
        self.assertEqual(
            validate_youtube_url("https://youtu.be/abc123"),
            "https://youtu.be/abc123",
        )
        with self.assertRaises(ExtractorError):
            validate_youtube_url("https://example.com/watch?v=abc123")

    def test_splits_artist_and_title(self):
        self.assertEqual(
            split_artist_title("New Order - Blue Monday (Official Video)"),
            ("New Order", "Blue Monday"),
        )

    def test_prefers_structured_track_metadata(self):
        metadata = build_track_metadata(
            {
                "id": "abc123",
                "title": "Uploaded video title",
                "track": "Blue Monday",
                "artist": "New Order",
                "channel": "New Order",
                "duration": 447,
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
            },
            "https://www.youtube.com/watch?v=abc123",
        )
        self.assertEqual(metadata.title, "Blue Monday")
        self.assertEqual(metadata.artist, "New Order")
        self.assertEqual(metadata.duration_label, "7:27")

    def test_uses_title_heuristic_when_artist_missing(self):
        metadata = build_track_metadata(
            {
                "id": "abc123",
                "title": "Artist Name - Song Name [Official Audio]",
                "uploader": "Uploader Channel",
            },
            "https://youtu.be/abc123",
        )
        self.assertEqual(metadata.artist, "Artist Name")
        self.assertEqual(metadata.title, "Song Name")

    def test_cleans_noisy_titles(self):
        self.assertEqual(clean_title("Song Title (Official Music Video)"), "Song Title")

    def test_picks_high_quality_cover(self):
        cover = pick_cover_url(
            {
                "thumbnails": [
                    {"url": "https://i.ytimg.com/vi/x/default.jpg", "width": 120, "height": 90},
                    {"url": "https://i.ytimg.com/vi/x/maxresdefault.jpg", "width": 1280, "height": 720},
                ]
            }
        )
        self.assertEqual(cover, "https://i.ytimg.com/vi/x/maxresdefault.jpg")

    def test_extracts_json3_lyrics(self):
        lyrics = lyrics_from_json3(
            '{"events":[{"segs":[{"utf8":"hello "},{"utf8":"world"}]},'
            '{"segs":[{"utf8":"hello world"}]},'
            '{"segs":[{"utf8":"next line"}]}]}'
        )
        self.assertEqual(lyrics, "hello world\nnext line")

    def test_extracts_vtt_lyrics(self):
        lyrics = lyrics_from_timed_text(
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.000\n"
            "<c>first line</c>\n\n"
            "2\n"
            "00:00:02.000 --> 00:00:04.000\n"
            "second&nbsp;line\n"
        )
        self.assertEqual(lyrics, "first line\nsecond line")

    def test_builds_safe_artist_title_filename(self):
        metadata = build_track_metadata(
            {
                "id": "abc123",
                "title": 'Artist/Name - Song: Name? [Official Audio]',
                "uploader": "Uploader Channel",
            },
            "https://youtu.be/abc123",
        )
        self.assertEqual(
            safe_audio_filename(metadata, ".m4a"),
            "Artist_Name - Song_ Name.m4a",
        )

    def test_builds_safe_channel_title_video_filename(self):
        metadata = build_track_metadata(
            {
                "id": "abc123",
                "title": "A Video: Title?",
                "channel": "Channel/Name",
            },
            "https://youtu.be/abc123",
        )
        self.assertEqual(
            safe_video_filename(metadata, ".mp4"),
            "Channel_Name - A Video_ Title.mp4",
        )

    def test_flac_is_not_a_supported_extraction_format(self):
        with self.assertRaises(ExtractorError):
            normalize_audio_format("flac")

    def test_video_quality_defaults_to_best(self):
        self.assertEqual(normalize_video_quality(None), "best")
        self.assertEqual(normalize_video_quality("4k"), "best")
        self.assertEqual(normalize_video_quality("1080p"), "1080")
        with self.assertRaises(ExtractorError):
            normalize_video_quality("144")

    def test_reads_requested_subtitle_languages(self):
        self.assertEqual(
            subtitle_languages_from_info({"requested_subtitles": {"en": {}, "ko": {}}}),
            ["en", "ko"],
        )

    def test_video_subtitle_languages_are_limited_to_korean_and_english(self):
        from youtube_audio_extractor.extractor import SUBTITLE_LANGUAGES

        self.assertEqual(SUBTITLE_LANGUAGES, ["ko", "ko-KR", "en", "en-US", "en-GB"])

    def test_yt_dlp_disk_cache_is_disabled(self):
        self.assertFalse(yt_dlp_base_options()["cachedir"])

    def test_formats_video_quality_label(self):
        self.assertEqual(
            video_quality_from_info(
                {"requested_formats": [{"vcodec": "avc1.640028", "width": 1920, "height": 1080, "fps": 30}]}
            ),
            "1920x1080, 30fps, avc1.640028",
        )
        self.assertIsNone(video_quality_from_info({"vcodec": "vp9", "width": 1920, "height": 1080, "fps": 60}))

    def test_video_download_defaults_to_highest_quality_mkv(self):
        with patch("youtube_audio_extractor.extractor.require_ffmpeg", return_value="ffmpeg"):
            options = video_download_options(Path("."), None, "best")

        self.assertEqual(options["format"], "bestvideo+bestaudio")
        self.assertEqual(options["merge_output_format"], "mkv")
        self.assertEqual(options["check_formats"], "selected")
        self.assertNotIn("writesubtitles", options)
        self.assertEqual(options["postprocessors"], [])

    def test_video_download_can_include_subtitles(self):
        with patch("youtube_audio_extractor.extractor.require_ffmpeg", return_value="ffmpeg"):
            options = video_download_options(Path("."), None, "best", include_subtitles=True)

        self.assertTrue(options["writesubtitles"])
        self.assertEqual(options["subtitleslangs"], ["ko", "ko-KR", "en", "en-US", "en-GB"])
        self.assertEqual(options["postprocessors"][0]["key"], "FFmpegEmbedSubtitle")

    def test_video_download_can_limit_quality_for_smaller_mp4(self):
        with patch("youtube_audio_extractor.extractor.require_ffmpeg", return_value="ffmpeg"):
            options = video_download_options(Path("."), None, "720")

        self.assertIn("height<=720", options["format"])
        self.assertIn("vcodec^=avc1", options["format"])
        self.assertNotIn("bestvideo[height<=720]+bestaudio", options["format"])
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertEqual(options["check_formats"], "selected")

    def test_remuxes_m4a_without_reencoding_for_player_compatibility(self):
        with tempfile.TemporaryDirectory() as temp:
            audio_path = Path(temp) / "audio.m4a"
            audio_path.write_bytes(b"dash-m4a")

            class Completed:
                returncode = 0
                stderr = ""

            def fake_run(command, **_kwargs):
                self.assertEqual(command[0], "ffmpeg")
                self.assertIn("-map", command)
                self.assertIn("0", command)
                self.assertIn("-c", command)
                self.assertIn("copy", command)
                self.assertIn("+faststart", command)
                Path(command[-1]).write_bytes(b"plain-m4a")
                return Completed()

            with (
                patch("youtube_audio_extractor.extractor.require_ffmpeg", return_value="ffmpeg"),
                patch("youtube_audio_extractor.extractor.subprocess.run", side_effect=fake_run),
            ):
                result = remux_m4a_for_compatibility(audio_path)

            self.assertEqual(result, audio_path)
            self.assertEqual(audio_path.read_bytes(), b"plain-m4a")
            self.assertFalse((Path(temp) / "audio.compat.m4a").exists())

    def test_parses_actual_video_quality_from_ffmpeg_output(self):
        self.assertEqual(
            parse_video_quality_from_ffmpeg_output(
                "Stream #0:0: Video: vp9, yuv420p, 3840x2160, 59.94 fps, 59.94 tbr"
            ),
            "3840x2160, 59.94fps, vp9",
        )

    def test_parses_embedded_subtitle_languages_from_ffmpeg_output(self):
        self.assertEqual(
            parse_subtitle_languages_from_ffmpeg_output(
                "Stream #0:2[0x3](eng): Subtitle: mov_text (tx3g / 0x67337874), 0 kb/s\n"
                "Stream #0:3[0x4](kor): Subtitle: subrip"
            ),
            ["en", "ko"],
        )

    def test_stream_language_probe_does_not_treat_handler_name_as_language(self):
        probe = {
            "streams": [
                {"codec_type": "audio", "tags": {"handler_name": "ISO Media file produced by Google Inc."}},
                {"codec_type": "subtitle", "tags": {"handler_name": "SubtitleHandler"}},
            ]
        }
        with patch("youtube_audio_extractor.extractor.ffprobe_json", return_value=probe):
            self.assertEqual(subtitle_stream_languages(Path("video.mkv")), ["und"])

    def test_renames_subtitle_sidecars_to_match_video(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            video = output_dir / "Channel - Title.mp4"
            video.write_bytes(b"video")
            subtitle = output_dir / "video.en.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

            renamed = rename_subtitle_sidecars([subtitle], video)

            self.assertEqual([path.name for path in renamed], ["Channel - Title.en.srt"])
            self.assertTrue((output_dir / "Channel - Title.en.srt").exists())

    def test_extraction_leaves_only_audio_in_output_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)

            def fake_download_cover(_url, cover_dir):
                cover_path = cover_dir / "cover.jpg"
                cover_path.write_bytes(b"cover")
                return file_record(cover_path, "image/jpeg")

            def fake_download_audio(_url, audio_dir, _progress, _format):
                audio_path = audio_dir / "audio.m4a"
                audio_path.write_bytes(b"audio")
                return file_record(audio_path, "audio/mp4")

            def fake_embed(_audio_path, _metadata, cover_file):
                self.assertIsNotNone(cover_file)
                self.assertNotEqual(Path(cover_file.path).parent, output_dir)
                self.assertTrue(Path(cover_file.path).exists())
                return EmbedReport(True, "m4a", ["title", "artist", "cover"])

            with (
                patch(
                    "youtube_audio_extractor.extractor.fetch_video_info",
                    return_value={
                        "id": "abc123",
                        "title": "Artist - Title",
                        "thumbnail": "https://i.ytimg.com/vi/x/maxresdefault.jpg",
                    },
                ),
                patch("youtube_audio_extractor.extractor.download_cover", side_effect=fake_download_cover),
                patch("youtube_audio_extractor.extractor.download_audio", side_effect=fake_download_audio),
                patch("youtube_audio_extractor.extractor.embed_audio_metadata", side_effect=fake_embed),
            ):
                result = extract_youtube("https://youtu.be/abc123", output_dir, audio_format="m4a")

            self.assertEqual(result.audio.name, "Artist - Title.m4a")
            self.assertIsNone(result.cover)
            self.assertIsNone(result.metadata_file)
            self.assertEqual([path.name for path in output_dir.iterdir()], ["Artist - Title.m4a"])

    def test_video_extraction_renames_and_reports_subtitles(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)

            def fake_download_video(_url, video_dir, _progress, _quality, include_subtitles=False):
                self.assertTrue(include_subtitles)
                video_path = video_dir / "video.mp4"
                video_path.write_bytes(b"video")
                subtitle_path = video_dir / "video.en.srt"
                subtitle_path.write_text("subtitle", encoding="utf-8")
                return file_record(video_path, "video/mp4"), ["en", "ko"], [subtitle_path], {}

            with (
                patch(
                    "youtube_audio_extractor.extractor.fetch_video_info",
                    return_value={
                        "id": "abc123",
                        "title": "A Video",
                        "channel": "Channel Name",
                    },
                ),
                patch("youtube_audio_extractor.extractor.download_video", side_effect=fake_download_video),
                patch("youtube_audio_extractor.extractor.fetch_selected_video_info", return_value=None),
            ):
                result = extract_youtube_video(
                    "https://youtu.be/abc123",
                    output_dir,
                    include_subtitles=True,
                )

            self.assertEqual(result.video.name, "Channel Name - A Video.mp4")
            self.assertEqual(result.subtitle_languages, ["en"])
            self.assertEqual([item.name for item in result.subtitle_files], ["Channel Name - A Video.en.srt"])
            self.assertIsNone(result.video_quality)
            self.assertIsNone(result.video_quality_source)
            self.assertFalse(result.subtitles_embedded)
            self.assertTrue(result.subtitles_requested)
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["Channel Name - A Video.en.srt", "Channel Name - A Video.mp4"],
            )

    def test_video_extraction_reports_downloaded_format_when_file_probe_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)

            def fake_download_video(_url, video_dir, _progress, _quality, include_subtitles=False):
                video_path = video_dir / "video.mkv"
                video_path.write_bytes(b"video")
                downloaded_info = {
                    "requested_formats": [
                        {"vcodec": "vp9", "width": 3840, "height": 2160, "fps": 60},
                        {"acodec": "opus", "vcodec": "none"},
                    ]
                }
                return file_record(video_path, "video/x-matroska"), [], [], downloaded_info

            with (
                patch(
                    "youtube_audio_extractor.extractor.fetch_video_info",
                    return_value={
                        "id": "abc123",
                        "title": "A Video",
                        "channel": "Channel Name",
                        "width": 1920,
                        "height": 1080,
                        "fps": 60,
                        "vcodec": "vp9",
                    },
                ),
                patch("youtube_audio_extractor.extractor.download_video", side_effect=fake_download_video),
                patch("youtube_audio_extractor.extractor.video_quality_from_file", return_value=None),
            ):
                result = extract_youtube_video("https://youtu.be/abc123", output_dir)

            self.assertEqual(result.video_quality, "3840x2160, 60fps, vp9")
            self.assertEqual(result.video_quality_source, "downloaded")

    def test_video_extraction_does_not_guess_quality_from_prefetch_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)

            def fake_download_video(_url, video_dir, _progress, _quality, include_subtitles=False):
                video_path = video_dir / "video.mkv"
                video_path.write_bytes(b"video")
                return file_record(video_path, "video/x-matroska"), [], [], {}

            with (
                patch(
                    "youtube_audio_extractor.extractor.fetch_video_info",
                    return_value={
                        "id": "abc123",
                        "title": "A Video",
                        "channel": "Channel Name",
                        "width": 1920,
                        "height": 1080,
                        "fps": 60,
                        "vcodec": "vp9",
                    },
                ),
                patch("youtube_audio_extractor.extractor.download_video", side_effect=fake_download_video),
                patch("youtube_audio_extractor.extractor.video_quality_from_file", return_value=None),
                patch("youtube_audio_extractor.extractor.fetch_selected_video_info", return_value=None),
            ):
                result = extract_youtube_video("https://youtu.be/abc123", output_dir)

            self.assertIsNone(result.video_quality)
            self.assertIsNone(result.video_quality_source)

    def test_video_extraction_rechecks_selected_format_when_file_probe_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)

            def fake_download_video(_url, video_dir, _progress, _quality, include_subtitles=False):
                video_path = video_dir / "video.mkv"
                video_path.write_bytes(b"video")
                return file_record(video_path, "video/x-matroska"), [], [], {}

            with (
                patch(
                    "youtube_audio_extractor.extractor.fetch_video_info",
                    return_value={
                        "id": "abc123",
                        "title": "A Video",
                        "channel": "Channel Name",
                        "width": 1920,
                        "height": 1080,
                        "fps": 60,
                        "vcodec": "vp9",
                    },
                ),
                patch("youtube_audio_extractor.extractor.download_video", side_effect=fake_download_video),
                patch("youtube_audio_extractor.extractor.video_quality_from_file", return_value=None),
                patch(
                    "youtube_audio_extractor.extractor.fetch_selected_video_info",
                    return_value={
                        "requested_formats": [
                            {"vcodec": "vp9", "width": 3840, "height": 2160, "fps": 60},
                            {"acodec": "opus", "vcodec": "none"},
                        ]
                    },
                ),
            ):
                result = extract_youtube_video("https://youtu.be/abc123", output_dir)

            self.assertEqual(result.video_quality, "3840x2160, 60fps, vp9")
            self.assertEqual(result.video_quality_source, "selected")


if __name__ == "__main__":
    unittest.main()
