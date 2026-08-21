import unittest
from unittest.mock import MagicMock, patch

from youtube_audio_extractor.updater import (
    check_yt_dlp_update,
    get_installed_yt_dlp_version,
    is_newer_version,
    parse_version_tuple,
    reload_yt_dlp,
    update_yt_dlp,
)


class UpdaterTests(unittest.TestCase):
    def test_parse_version_tuple(self):
        self.assertEqual(parse_version_tuple("2026.08.19"), (2026, 8, 19))
        self.assertEqual(parse_version_tuple("v2026.3.17"), (2026, 3, 17))
        self.assertEqual(parse_version_tuple("2026.8.19.1"), (2026, 8, 19, 1))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("2026.8.19", "2026.3.17"))
        self.assertTrue(is_newer_version("2026.08.19", "2026.03.17"))
        self.assertFalse(is_newer_version("2026.3.17", "2026.8.19"))
        self.assertFalse(is_newer_version("2026.8.19", "2026.8.19"))
        self.assertFalse(is_newer_version("2026.08.19", "2026.8.19"))
        self.assertTrue(is_newer_version("2026.8.19", None))
        self.assertTrue(is_newer_version("2026.8.19", "알 수 없음"))
        self.assertFalse(is_newer_version(None, "2026.8.19"))

    def test_get_installed_yt_dlp_version(self):
        version = get_installed_yt_dlp_version()
        self.assertIsNotNone(version)
        self.assertIn("2026", version)

    def test_check_yt_dlp_update(self):
        with patch("youtube_audio_extractor.updater.get_latest_yt_dlp_version", return_value="2099.1.1"):
            info = check_yt_dlp_update()
            self.assertTrue(info["update_available"])
            self.assertEqual(info["latest"], "2099.1.1")

        with patch("youtube_audio_extractor.updater.get_latest_yt_dlp_version", return_value="2020.1.1"):
            info = check_yt_dlp_update()
            self.assertFalse(info["update_available"])

    def test_update_yt_dlp_success(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed yt-dlp"
        mock_proc.stderr = ""

        progress_messages = []

        with (
            patch("youtube_audio_extractor.updater.run_subprocess_hidden", return_value=mock_proc) as mock_run,
            patch("youtube_audio_extractor.updater.get_installed_yt_dlp_version", side_effect=["2026.3.17", "2026.8.19"]),
            patch("youtube_audio_extractor.updater.reload_yt_dlp") as mock_reload,
        ):
            success, msg = update_yt_dlp(progress_callback=progress_messages.append)
            self.assertTrue(success)
            self.assertIn("v2026.8.19", msg)
            mock_run.assert_called_once()
            mock_reload.assert_called_once()
            self.assertTrue(any("업그레이드" in m for m in progress_messages))

    def test_update_yt_dlp_failure(self):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "Network error: Connection refused"

        with patch("youtube_audio_extractor.updater.run_subprocess_hidden", return_value=mock_proc):
            success, msg = update_yt_dlp()
            self.assertFalse(success)
            self.assertIn("Connection refused", msg)


if __name__ == "__main__":
    unittest.main()
