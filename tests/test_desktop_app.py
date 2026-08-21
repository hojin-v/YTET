import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# If tkinter is not available (e.g. headless Linux CI), mock it before importing desktop_app
if "tkinter" not in sys.modules:
    try:
        import tkinter
    except ModuleNotFoundError:
        tkinter_mock = MagicMock()
        sys.modules["tkinter"] = tkinter_mock
        sys.modules["tkinter.ttk"] = MagicMock()
        sys.modules["tkinter.filedialog"] = MagicMock()
        sys.modules["tkinter.messagebox"] = MagicMock()

from youtube_audio_extractor.desktop_app import (
    DEFAULT_AUDIO_OUTPUT_DIR,
    DEFAULT_VIDEO_OUTPUT_DIR,
    DEFAULT_YTET_DIR,
)


class DesktopAppDirectoryTests(unittest.TestCase):
    def test_default_directories(self):
        self.assertEqual(DEFAULT_YTET_DIR, Path.home() / "YTET")
        self.assertEqual(DEFAULT_AUDIO_OUTPUT_DIR, Path.home() / "YTET" / "Music")
        self.assertEqual(DEFAULT_VIDEO_OUTPUT_DIR, Path.home() / "YTET" / "Video")


if __name__ == "__main__":
    unittest.main()

