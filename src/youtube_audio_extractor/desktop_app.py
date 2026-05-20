from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import BooleanVar, Tk, filedialog, messagebox
from tkinter import StringVar
from tkinter import ttk
from typing import Any

from .extractor import ExtractorError, extract_youtube, extract_youtube_video


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = app_root()
DEFAULT_OUTPUT_DIR = Path.home() / "Music" / "YTET"
FORMAT_OPTIONS = [
    ("M4A (AAC) - 기본 추천", "m4a"),
    ("Original Opus - 최고 효율/작은 용량", "original"),
    ("MP3 - 구형 호환", "mp3"),
]
MEDIA_OPTIONS = [
    ("음원", "audio"),
    ("영상", "video"),
]
VIDEO_QUALITY_OPTIONS = [
    ("원본 최고품질 · MKV · 4K/8K", "best"),
    ("1080p MP4 · 호환 우선", "1080"),
    ("720p MP4 · 저용량", "720"),
    ("480p MP4 · 최소용량", "480"),
]
AUDIO_FORMAT_DETAILS = {
    "m4a": "M4A(AAC) · 50-90MB/시간 · 기본 추천",
    "original": "Original Opus · 40-80MB/시간 · 최고 효율 · 일부 플레이어 코덱 필요",
    "mp3": "MP3 · 60-120MB/시간 · 구형 기기 호환 · 용량 효율 낮음",
}
VIDEO_QUALITY_DETAILS = {
    "best": "최고 해상도 · AV1/VP9 가능 · 파일 용량 큼",
    "1080": "호환 우선 · 4K→1080p · H.264/AAC 우선",
    "720": "저용량 · 작은 글자 약함 · 모바일 보관",
    "480": "최소용량 · 큰 화면 약함 · 확인용",
}


class MainWindow:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_output_dir = DEFAULT_OUTPUT_DIR
        self.media_buttons: list[ttk.Radiobutton] = []

        self.url_var = StringVar()
        self.output_var = StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.media_var = StringVar(value=MEDIA_OPTIONS[0][1])
        self.format_var = StringVar(value=FORMAT_OPTIONS[0][0])
        self.include_subtitles_var = BooleanVar(value=False)
        self.include_multi_audio_var = BooleanVar(value=False)
        self.selection_help_var = StringVar()
        self.status_var = StringVar(value="URL과 저장 폴더를 입력한 뒤 추출을 누르세요.")
        self.result_var = StringVar(value="-")

        self.root.title("YTET")
        self.root.minsize(860, 650)
        self._build_ui()
        self.root.after(100, self._poll_events)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(16, 8))
        style.configure("TEntry", padding=(8, 7))
        style.configure("TCombobox", padding=(8, 7))
        style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Mode.Toolbutton", font=("Segoe UI", 11, "bold"), padding=(22, 12))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(20, 9))

        frame = ttk.Frame(self.root, padding=28)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        title = ttk.Label(frame, text="YTET", font=("Segoe UI", 24, "bold"))
        title.grid(row=0, column=0, sticky="w")

        ttk.Label(frame, text="YouTube URL").grid(row=1, column=0, sticky="w", pady=(24, 6))
        self.url_input = ttk.Entry(frame, textvariable=self.url_var)
        self.url_input.grid(row=2, column=0, sticky="ew", ipady=5)

        ttk.Label(frame, text="저장 폴더").grid(row=3, column=0, sticky="w", pady=(18, 6))
        output_row = ttk.Frame(frame)
        output_row.grid(row=4, column=0, sticky="ew")
        output_row.columnconfigure(0, weight=1)
        self.output_input = ttk.Entry(output_row, textvariable=self.output_var)
        self.output_input.grid(row=0, column=0, sticky="ew", ipady=5)
        self.browse_button = ttk.Button(output_row, text="폴더 선택", command=self.choose_output_dir)
        self.browse_button.grid(row=0, column=1, padx=(8, 0))

        ttk.Label(frame, text="추출 유형").grid(row=5, column=0, sticky="w", pady=(22, 6))
        media_row = ttk.Frame(frame)
        media_row.grid(row=6, column=0, sticky="ew")
        media_row.columnconfigure(0, weight=1)
        media_row.columnconfigure(1, weight=1)
        self.media_buttons = []
        for index, (label, value) in enumerate(MEDIA_OPTIONS):
            button = ttk.Radiobutton(
                media_row,
                text=label,
                value=value,
                variable=self.media_var,
                command=self.on_media_changed,
                style="Mode.Toolbutton",
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0, 8) if index == 0 else (8, 0), ipady=3)
            self.media_buttons.append(button)

        controls = ttk.Frame(frame)
        controls.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        controls.columnconfigure(0, weight=1)
        self.format_select = ttk.Combobox(
            controls,
            textvariable=self.format_var,
            values=[label for label, _value in FORMAT_OPTIONS],
            state="readonly",
        )
        self.format_select.grid(row=0, column=0, sticky="ew", ipady=5)
        self.format_select.bind("<<ComboboxSelected>>", self.on_format_changed)
        self.extract_button = ttk.Button(controls, text="추출", command=self.start_extract, style="Accent.TButton")
        self.extract_button.grid(row=0, column=1, padx=(10, 0))

        self.video_options_frame = ttk.Frame(frame)
        self.video_options_frame.grid(row=8, column=0, sticky="w", pady=(12, 0))
        self.subtitle_check = ttk.Checkbutton(
            self.video_options_frame,
            text="자막 포함",
            variable=self.include_subtitles_var,
        )
        self.subtitle_check.grid(row=0, column=0, sticky="w")
        self.multi_audio_check = ttk.Checkbutton(
            self.video_options_frame,
            text="다중 오디오 포함",
            variable=self.include_multi_audio_var,
        )
        self.multi_audio_check.grid(row=0, column=1, sticky="w", padx=(18, 0))

        self.selection_help_label = ttk.Label(
            frame,
            textvariable=self.selection_help_var,
            wraplength=780,
            justify="left",
        )
        self.selection_help_label.grid(row=9, column=0, sticky="ew", pady=(10, 0))

        self.progress = ttk.Progressbar(frame, maximum=100, mode="determinate")
        self.progress.grid(row=10, column=0, sticky="ew", pady=(22, 0), ipady=3)

        self.status_label = ttk.Label(frame, textvariable=self.status_var, wraplength=740)
        self.status_label.grid(row=11, column=0, sticky="ew", pady=(12, 0))

        result_box = ttk.LabelFrame(frame, text="결과", padding=16)
        result_box.grid(row=12, column=0, sticky="nsew", pady=(20, 0))
        result_box.columnconfigure(0, weight=1)
        frame.rowconfigure(12, weight=1)
        self.result_label = ttk.Label(result_box, textvariable=self.result_var, wraplength=740)
        self.result_label.grid(row=0, column=0, sticky="nw")
        self.open_folder_button = ttk.Button(
            result_box,
            text="저장 폴더 열기",
            command=self.open_output_dir,
            state="disabled",
        )
        self.open_folder_button.grid(row=1, column=0, sticky="w", pady=(14, 0))

        self.url_input.focus_set()
        self.update_video_option_visibility()
        self.update_selection_help()

    def on_media_changed(self, _event: object | None = None) -> None:
        if self.selected_media() == "video":
            self.format_select.configure(values=[label for label, _value in VIDEO_QUALITY_OPTIONS], state="readonly")
            self.format_var.set(VIDEO_QUALITY_OPTIONS[0][0])
        else:
            self.format_select.configure(values=[label for label, _value in FORMAT_OPTIONS], state="readonly")
            self.format_var.set(FORMAT_OPTIONS[0][0])
        self.update_video_option_visibility()
        self.update_selection_help()

    def on_format_changed(self, _event: object | None = None) -> None:
        self.update_selection_help()

    def update_selection_help(self) -> None:
        if self.selected_media() == "video":
            self.selection_help_var.set(VIDEO_QUALITY_DETAILS.get(self.selected_video_quality(), ""))
        else:
            self.selection_help_var.set(AUDIO_FORMAT_DETAILS.get(self.selected_format(), ""))

    def update_video_option_visibility(self) -> None:
        if self.selected_media() == "video":
            self.video_options_frame.grid()
        else:
            self.video_options_frame.grid_remove()

    def choose_output_dir(self) -> None:
        initial = self.output_var.get().strip() or str(DEFAULT_OUTPUT_DIR)
        selected = filedialog.askdirectory(title="저장 폴더 선택", initialdir=initial)
        if selected:
            self.output_var.set(selected)

    def start_extract(self) -> None:
        url = self.url_var.get().strip()
        output_text = self.output_var.get().strip()
        if not url:
            self.show_error("YouTube URL을 입력하세요.")
            return
        if not output_text:
            self.show_error("저장 폴더를 입력하거나 선택하세요.")
            return

        output_dir = Path(output_text).expanduser()
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        self.last_output_dir = output_dir

        self.set_busy(True)
        self.progress.configure(value=0)
        self.status_var.set("작업을 준비하는 중")
        self.result_var.set("-")
        self.open_folder_button.configure(state="disabled")

        media_type = self.selected_media()
        format_or_quality = self.selected_video_quality() if media_type == "video" else self.selected_format()
        include_subtitles = self.include_subtitles_var.get() if media_type == "video" else False
        include_multi_audio = self.include_multi_audio_var.get() if media_type == "video" else False
        self.worker = threading.Thread(
            target=self._run_extract,
            args=(url, output_dir, media_type, format_or_quality, include_subtitles, include_multi_audio),
            daemon=True,
        )
        self.worker.start()

    def _run_extract(
        self,
        url: str,
        output_dir: Path,
        media_type: str,
        format_or_quality: str,
        include_subtitles: bool,
        include_multi_audio: bool,
    ) -> None:
        def on_progress(payload: dict[str, Any]) -> None:
            self.events.put(("progress", payload))

        try:
            if media_type == "video":
                result = extract_youtube_video(
                    url,
                    output_dir,
                    on_progress,
                    format_or_quality,
                    include_subtitles=include_subtitles,
                    include_multi_audio=include_multi_audio,
                )
            else:
                result = extract_youtube(url, output_dir, on_progress, format_or_quality)
            self.events.put(("finished", result.to_dict()))
        except Exception as exc:
            detail = str(exc)
            if not isinstance(exc, ExtractorError):
                detail = f"{detail}\n\n{traceback.format_exc()}"
            self.events.put(("failed", detail))

    def selected_media(self) -> str:
        selected = self.media_var.get()
        if selected in {value for _label, value in MEDIA_OPTIONS}:
            return selected
        return "audio"

    def selected_format(self) -> str:
        selected = self.format_var.get()
        for label, value in FORMAT_OPTIONS:
            if label == selected:
                return value
        return "m4a"

    def selected_video_quality(self) -> str:
        selected = self.format_var.get()
        for label, value in VIDEO_QUALITY_OPTIONS:
            if label == selected:
                return value
        return "best"

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "progress":
                self.on_progress(payload)
            elif event == "finished":
                self.on_finished(payload)
            elif event == "failed":
                self.on_failed(str(payload))
        self.root.after(100, self._poll_events)

    def on_progress(self, payload: dict[str, Any]) -> None:
        percent = int(payload.get("percent") or 0)
        stage = str(payload.get("stage") or "running")
        message = str(payload.get("message") or "처리 중")
        self.progress.configure(value=percent)
        self.status_var.set(f"{stage}: {message}")

    def on_finished(self, result: dict[str, Any]) -> None:
        metadata = result["metadata"]
        self.progress.configure(value=100)
        self.status_var.set("완료")
        if "video" in result:
            video = result["video"]
            subtitle_languages = result.get("subtitle_languages") or []
            subtitle_files = result.get("subtitle_files") or []
            audio_languages = result.get("audio_languages") or []
            video_quality = result.get("video_quality") or "자동 선택"
            video_format = video_format_label(video["name"], video.get("mime_type"))
            subtitles_requested = bool(result.get("subtitles_requested"))
            multi_audio_requested = bool(result.get("multi_audio_requested"))
            subtitle_text = ", ".join(subtitle_languages) if subtitle_languages else "등록 자막 없음"
            subtitle_file_text = ", ".join(item["name"] for item in subtitle_files) if subtitle_files else "없음"
            if not subtitles_requested:
                subtitle_text = "선택 안 함"
                subtitle_file_text = "선택 안 함"
            audio_text = ", ".join(audio_languages) if audio_languages else "기본 오디오"
            if not multi_audio_requested:
                audio_text = "기본 오디오"
            lines = [
                f"파일: {video['name']}",
                f"제목: {metadata['title']}",
                f"Channel: {metadata['channel'] or metadata['artist']}",
                f"형식: {video_format}",
                f"화질/코덱: {video_quality}",
                f"용량: {format_file_size(video.get('bytes'))}",
                f"오디오: {audio_text}",
                f"자막: {subtitle_text}",
                f"자막 파일: {subtitle_file_text}",
                f"저장 위치: {video['path']}",
            ]
        else:
            audio = result["audio"]
            lines = [
                f"파일: {audio['name']}",
                f"제목: {metadata['title']}",
                f"Artist: {metadata['artist']}",
                f"용량: {format_file_size(audio.get('bytes'))}",
                f"저장 위치: {audio['path']}",
            ]
        self.result_var.set("\n".join(lines))
        self.open_folder_button.configure(state="normal")
        self.set_busy(False)

    def on_failed(self, message: str) -> None:
        self.show_error(message)
        self.set_busy(False)

    def open_output_dir(self) -> None:
        open_in_file_manager(self.last_output_dir)

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        readonly = "disabled" if busy else "readonly"
        self.extract_button.configure(state=state)
        self.url_input.configure(state=state)
        self.output_input.configure(state=state)
        self.browse_button.configure(state=state)
        for button in self.media_buttons:
            button.configure(state=state)
        self.subtitle_check.configure(state=state)
        self.multi_audio_check.configure(state=state)
        if busy:
            self.format_select.configure(state="disabled")
        else:
            self.format_select.configure(state=readonly)

    def show_error(self, message: str) -> None:
        self.progress.configure(value=0)
        self.status_var.set("실패")
        self.result_var.set(message)
        messagebox.showerror("추출 실패", message)


def open_in_file_manager(path: Path) -> None:
    target = str(path)
    if sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def video_format_label(name: str, mime_type: str | None = None) -> str:
    extension = Path(name).suffix.lower()
    labels = {
        ".mkv": "MKV",
        ".mp4": "MP4",
        ".webm": "WebM",
        ".mov": "MOV",
        ".m4v": "MP4",
    }
    label = labels.get(extension, extension.lstrip(".").upper() or "알 수 없음")
    if extension:
        return f"{label} ({extension})"
    if mime_type:
        return mime_type
    return label


def format_file_size(value: Any) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "알 수 없음"
    if size < 0:
        return "알 수 없음"

    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(size)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    if unit == "B":
        return f"{int(amount)} {unit}"
    return f"{amount:.1f} {unit}"


def main() -> int:
    root = Tk()
    MainWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
