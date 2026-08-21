from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
GITHUB_RELEASES_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"


def run_subprocess_hidden(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs.setdefault("startupinfo", startupinfo)
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


def get_installed_yt_dlp_version() -> str | None:
    try:
        import yt_dlp.version

        return str(yt_dlp.version.__version__)
    except Exception:
        pass

    try:
        return str(importlib.metadata.version("yt-dlp"))
    except Exception:
        return None


def parse_version_tuple(v_str: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in v_str.strip().lstrip("v").replace("-", ".").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def is_newer_version(latest: str | None, current: str | None) -> bool:
    if not latest:
        return False
    if not current or current == "알 수 없음":
        return True
    try:
        from packaging import version

        return version.parse(latest) > version.parse(current)
    except Exception:
        return parse_version_tuple(latest) > parse_version_tuple(current)


def get_latest_yt_dlp_version(timeout: float = 4.0) -> str | None:
    # 1. Try PyPI JSON API
    try:
        req = Request(PYPI_URL, headers={"User-Agent": "YTET-Updater/1.0"})
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            version_str = data.get("info", {}).get("version")
            if version_str:
                return str(version_str)
    except Exception:
        pass

    # 2. Fallback to GitHub Releases API
    try:
        req = Request(GITHUB_RELEASES_URL, headers={"User-Agent": "YTET-Updater/1.0"})
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            tag_name = data.get("tag_name")
            if tag_name:
                return str(tag_name).lstrip("v")
    except Exception:
        pass

    return None


def check_yt_dlp_update(timeout: float = 4.0) -> dict[str, Any]:
    installed = get_installed_yt_dlp_version()
    latest = get_latest_yt_dlp_version(timeout=timeout)
    update_available = is_newer_version(latest, installed) if latest else False

    return {
        "installed": installed or "알 수 없음",
        "latest": latest or "조회 실패",
        "update_available": update_available,
    }


def reload_yt_dlp() -> None:
    for mod_name in list(sys.modules.keys()):
        if mod_name == "yt_dlp" or mod_name.startswith("yt_dlp.") or mod_name == "yt_dlp_ejs" or mod_name.startswith("yt_dlp_ejs."):
            del sys.modules[mod_name]
    importlib.invalidate_caches()


def find_python_executable() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for venv_name in [".venv-win", ".venv", "venv"]:
            candidate = exe_dir / venv_name / "Scripts" / "python.exe"
            if candidate.is_file():
                return str(candidate)
            candidate_posix = exe_dir / venv_name / "bin" / "python"
            if candidate_posix.is_file():
                return str(candidate_posix)
    return sys.executable


def update_yt_dlp(progress_callback: Callable[[str], None] | None = None) -> tuple[bool, str]:
    if progress_callback:
        progress_callback("최신 yt-dlp 패키지 확인 중...")

    old_version = get_installed_yt_dlp_version() or "알 수 없음"
    python_exe = find_python_executable()

    if progress_callback:
        progress_callback("pip를 통해 yt-dlp 및 플러그인을 업그레이드하는 중...")

    cmd = [
        python_exe,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "yt-dlp[default]",
        "yt-dlp-ejs",
    ]

    try:
        result = run_subprocess_hidden(cmd, timeout=120)
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or f"반환 코드: {result.returncode}"
            return False, f"yt-dlp 업그레이드 실패: {error_msg}"

        reload_yt_dlp()
        new_version = get_installed_yt_dlp_version() or "알 수 없음"

        if progress_callback:
            progress_callback(f"업데이트 완료 (v{new_version})")

        return True, f"yt-dlp가 v{new_version} (으)로 업데이트되었습니다. (이전: v{old_version})"
    except subprocess.TimeoutExpired:
        return False, "yt-dlp 업그레이드 시간이 초과되었습니다 (120초)."
    except Exception as exc:
        return False, f"yt-dlp 업데이트 중 오류 발생: {exc}"


def check_yt_dlp_update_async(
    on_complete: Callable[[dict[str, Any]], None],
    timeout: float = 4.0,
) -> threading.Thread:
    def _worker() -> None:
        info = check_yt_dlp_update(timeout=timeout)
        on_complete(info)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def update_yt_dlp_async(
    on_complete: Callable[[bool, str], None],
    progress_callback: Callable[[str], None] | None = None,
) -> threading.Thread:
    def _worker() -> None:
        success, message = update_yt_dlp(progress_callback=progress_callback)
        on_complete(success, message)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread
