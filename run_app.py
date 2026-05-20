from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"


def main() -> int:
    try:
        if getattr(sys, "frozen", False):
            os.chdir(Path(sys.executable).resolve().parent)
        else:
            os.chdir(PROJECT_ROOT)
            sys.path.insert(0, str(SRC_ROOT))

        from youtube_audio_extractor.desktop_app import main as gui_main

        return gui_main()
    except Exception:
        show_startup_error(traceback.format_exc())
        return 1


def show_startup_error(message: str) -> None:
    log_path = PROJECT_ROOT / "app-error.log"
    log_path.write_text(message, encoding="utf-8")

    text = f"앱을 시작하지 못했습니다.\n\n{message}\n\nLog: {log_path}"
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, "YTET", 0x10)
            return
        except Exception:
            pass
    print(text, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
