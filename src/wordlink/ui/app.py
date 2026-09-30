"""Read screenshots, recordings, and selected mirror windows without game input."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from queue import Empty, SimpleQueue
from sys import platform
from threading import Event
from time import monotonic, perf_counter
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Sequence

from PIL import Image, ImageTk

from wordlink.capture.sources import FrameSource
from wordlink.model import Board, Box, Recognition
from wordlink.paths import DATA_DIR
from wordlink.solver.ranking import RankedWord, rank_words
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy
from wordlink.vision.board import recognize

if TYPE_CHECKING:
    from wordlink.capture.live import LiveAssistant, LiveUpdate
    from wordlink.capture.macos import WindowInfo


BACKGROUND = "#0c121c"
PANEL = "#131d2b"
SURFACE = "#1b293b"
BORDER = "#293a50"
TEXT = "#ecf2ff"
MUTED = "#99abc3"
BLUE = "#4b9cff"
YELLOW = "#ffe079"
GREEN = "#7cdeb2"
LIVE_MAX_FRAME_AGE = 1.5


def live_ready_is_fresh(state: str, captured_at: float | None, now: float) -> bool:
    """A stalled capture must never leave an actionable word on screen."""
    if state != "ready" or captured_at is None:
        return False
    if not isfinite(captured_at) or not isfinite(now):
        return False
    return 0 <= now - captured_at <= LIVE_MAX_FRAME_AGE


def parse_board_entries(
    letters: Sequence[str], dots: Sequence[str], boxes: Sequence[Box] = ()
) -> Board:
    """Validate all editable tiles before starting a solve."""
    if len(letters) != 16 or len(dots) != 16:
        raise ValueError("Enter a letter and dot count for all 16 tiles.")
    parsed_letters: list[str] = []
    parsed_dots: list[int] = []
    for index, (letter, count) in enumerate(zip(letters, dots), start=1):
        normalized = letter.strip().upper()
        if len(normalized) != 1 or not ("A" <= normalized <= "Z"):
            raise ValueError(f"Tile {index}: enter one letter from A to Z.")
        cleaned_count = count.strip()
        if not cleaned_count.isascii() or not cleaned_count.isdigit():
            raise ValueError(f"Tile {index}: enter a whole dot count from 0 to 10.")
        parsed_count = int(cleaned_count)
        if not 0 <= parsed_count <= 10:
            raise ValueError(f"Tile {index}: the dot count must be from 0 to 10.")
        parsed_letters.append(normalized)
        parsed_dots.append(parsed_count)
    return Board(tuple(parsed_letters), tuple(parsed_dots), tuple(boxes))


def crop_bounds(image_size: tuple[int, int], boxes: Sequence[Box]) -> tuple[int, int, int, int]:
    """Find a padded board crop, clipped to the actual screenshot."""
    width, height = image_size
    if not boxes:
        return 0, 0, width, height
    padding = max(4, round(min(min(box[2], box[3]) for box in boxes) * 0.12))
    left = max(0, min(box[0] for box in boxes) - padding)
    top = max(0, min(box[1] for box in boxes) - padding)
    right = min(width, max(box[0] + box[2] for box in boxes) + padding)
    bottom = min(height, max(box[1] + box[3] for box in boxes) + padding)
    if left >= right or top >= bottom:
        return 0, 0, width, height
    return left, top, right, bottom


@dataclass(frozen=True)
class AnalysisOutcome:
    image: Image.Image | None
    board: Board | None
    recognition: Recognition | None
    ranked_words: tuple[RankedWord, ...]
    elapsed_ms: float
    solve_ms: float
    vocabulary_count: int
    error: str | None = None
    edited: bool = False


@dataclass(frozen=True)
class LivePreparation:
    source: FrameSource
    trie: Trie
    policy: VocabularyPolicy


class WordLinkApp:
    """Tk widgets stay on the main thread; worker results travel through a queue."""

    def __init__(self, root: tk.Tk, image_path: Path | None = None, live_source: FrameSource | None = None) -> None:
        self.root = root
        self.closed = False
        self.busy = False
        self.board: Board | None = None
        self.ranked_words: tuple[RankedWord, ...] = ()
        self.selected_index = 0
        self.last_result: AnalysisOutcome | None = None
        self.source_path: Path | None = None
        self._image: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._recognition: Recognition | None = None
        self._trie: Trie | None = None
        self._policy: VocabularyPolicy | None = None
        self._vocabulary_count = 0
        self._generation = 0
        self._cancel = Event()
        self._future: Future[AnalysisOutcome | LivePreparation] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wordlink-analysis")
        self._outbox: SimpleQueue[tuple[int, AnalysisOutcome | LivePreparation | None, str | None]] = SimpleQueue()
        self._poll_id: str | None = None
        self._render_id: str | None = None
        self._initial_id: str | None = None
        self._full_screenshot = False
        self._live_controller: LiveAssistant | None = None
        self._pending_source: FrameSource | None = None
        self._live_requested = False
        self._live_label = ""
        self._live_state = "stopped"
        self._live_frame_at: float | None = None
        self._updating_entries = False
        self._windows: dict[str, WindowInfo] = {}
        self._capture_help: tk.Toplevel | None = None
        self._permission_var = tk.StringVar(root, "")

        self.status_var = tk.StringVar(root, "READY")
        self.source_var = tk.StringVar(root, "Open a screenshot to begin")
        self.processing_var = tk.StringVar(root, "No screenshot analyzed yet")
        self.best_word_var = tk.StringVar(root, "—")
        self.result_title_var = tk.StringVar(root, "BEST CANDIDATE")
        self.dictionary_var = tk.StringVar(root, "Dictionary: UNKNOWN")
        self.utility_var = tk.StringVar(root, "—")
        self.dot_total_var = tk.StringVar(root, "—")
        self.tracing_var = tk.StringVar(root, "—")
        self.path_var = tk.StringVar(root, "Your numbered path will appear on the board.")
        self.warning_var = tk.StringVar(root, "Review the detected letters and dots before relying on a result.")
        self.review_var = tk.StringVar(root, "16 tiles · letter / dot count")
        self.view_var = tk.StringVar(root, "Full screenshot")
        self.window_var = tk.StringVar(root, "Choose an existing mirror window")
        self.live_source_var = tk.StringVar(root, "Select a mirrored screen window, or replay a recording.")
        self.letter_vars = [tk.StringVar(root, "") for _ in range(16)]
        self.dot_vars = [tk.StringVar(root, "0") for _ in range(16)]
        self.tile_frames: list[tk.Frame] = []
        self.alternative_buttons: list[tk.Button] = []

        root.title("Word Link Copilot — Screen Assistant")
        root.configure(bg=BACKGROUND)
        root.geometry(f"1240x{min(950, max(760, root.winfo_screenheight() - 110))}")
        root.minsize(1020, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        self._build_header()
        self._build_live_controls()
        self._build_content()
        self._build_footer()
        root.bind("<Control-o>", self._open_shortcut)
        root.bind("<Command-o>", self._open_shortcut)
        root.bind("<Control-Return>", self._solve_shortcut)
        root.bind("<Command-Return>", self._solve_shortcut)
        for variable in (*self.letter_vars, *self.dot_vars):
            variable.trace_add("write", self._on_manual_edit)
        self._poll_id = root.after(50, self._poll)
        if live_source is not None:
            self._initial_id = root.after(0, lambda: self.start_live(live_source))
        elif image_path is not None:
            self._initial_id = root.after(0, lambda: self.open_image(image_path))

    def _label(self, parent: tk.Misc, text: str = "", **options: object) -> tk.Label:
        defaults: dict[str, object] = {"text": text, "bg": PANEL, "fg": TEXT, "font": ("Helvetica", 11), "anchor": "w"}
        defaults.update(options)
        return tk.Label(parent, **defaults)

    def _button(self, parent: tk.Misc, text: str, command: object, primary: bool = False, **options: object) -> tk.Button:
        defaults: dict[str, object] = {
            "text": text, "command": command, "bg": BLUE if primary else SURFACE,
            "fg": BACKGROUND if primary or platform == "darwin" else TEXT,
            "activebackground": "#75b4ff" if primary else BORDER,
            "activeforeground": BACKGROUND if primary or platform == "darwin" else TEXT,
            "disabledforeground": "#61758f",
            "relief": "flat", "borderwidth": 0, "highlightthickness": 1,
            "highlightbackground": BLUE if primary else BORDER, "highlightcolor": YELLOW,
            "font": ("Helvetica", 11, "bold"), "padx": 15, "pady": 9, "cursor": "hand2",
        }
        defaults.update(options)
        return tk.Button(parent, **defaults)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=BACKGROUND, padx=26, pady=19)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        tk.Label(header, text="W", bg=BLUE, fg=BACKGROUND, font=("Helvetica", 23, "bold"), width=2).grid(row=0, column=0, rowspan=2, padx=(0, 13))
        tk.Label(header, text="wordlink / copilot", bg=BACKGROUND, fg=TEXT, font=("Helvetica", 19, "bold"), anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(header, text="LOCAL SCREEN ASSISTANT", bg=BACKGROUND, fg=MUTED, font=("Helvetica", 8, "bold"), anchor="w").grid(row=1, column=1, sticky="w", pady=(3, 0))
        self.status_label = tk.Label(header, textvariable=self.status_var, bg=SURFACE, fg=GREEN, font=("Helvetica", 9, "bold"), padx=12, pady=8)
        self.status_label.grid(row=0, column=2, rowspan=2, padx=(15, 20))
        self._button(header, "Open screenshot…", self.open_dialog, primary=True).grid(row=0, column=3, rowspan=2)

    def _build_live_controls(self) -> None:
        controls = tk.Frame(self.root, bg=BACKGROUND, padx=26, pady=10)
        controls.grid(row=1, column=0, sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        tk.Label(controls, text="MIRROR WINDOW", bg=BACKGROUND, fg=MUTED, font=("Helvetica", 9, "bold")).grid(row=0, column=0, padx=(0, 12))
        self.window_menu = tk.OptionMenu(controls, self.window_var, "Choose an existing mirror window", command=self._window_selected)
        menu_ink = BACKGROUND if platform == "darwin" else TEXT
        self.window_menu.configure(bg=SURFACE, fg=menu_ink, activebackground=BORDER, activeforeground=menu_ink, relief="flat", highlightbackground=BORDER, highlightcolor=YELLOW, font=("Helvetica", 10), width=30)
        self.window_menu["menu"].configure(bg=SURFACE, fg=menu_ink, activebackground=BORDER, activeforeground=menu_ink)
        self.window_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._button(controls, "Refresh", self.refresh_windows, font=("Helvetica", 10), padx=10, pady=7).grid(row=0, column=2, padx=(0, 8))
        self.start_live_button = self._button(controls, "Start live", self.start_selected_window, primary=True, font=("Helvetica", 10), padx=12, pady=7)
        self.start_live_button.grid(row=0, column=3, padx=(0, 8))
        self.stop_live_button = self._button(controls, "Stop", self.stop_live, state="disabled", font=("Helvetica", 10), padx=12, pady=7)
        self.stop_live_button.grid(row=0, column=4, padx=(0, 8))
        self._button(controls, "Replay recording…", self.open_replay, font=("Helvetica", 10), padx=11, pady=7).grid(row=0, column=5, padx=(0, 8))
        self._button(controls, "Capture help", self.show_capture_help, font=("Helvetica", 10), padx=11, pady=7).grid(row=0, column=6)
        tk.Label(controls, textvariable=self.live_source_var, bg=BACKGROUND, fg=MUTED, font=("Helvetica", 10), anchor="w", justify="left", wraplength=1120).grid(row=1, column=0, columnspan=7, sticky="ew", pady=(10, 4))

    def _build_content(self) -> None:
        content = tk.Frame(self.root, bg=BACKGROUND, padx=26)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, minsize=350)
        content.grid_rowconfigure(0, weight=1)
        left = tk.Frame(content, bg=PANEL, padx=18, pady=16, highlightbackground=BORDER, highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)
        toolbar = tk.Frame(left, bg=PANEL)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(0, weight=1)
        self._label(toolbar, textvariable=self.source_var, fg=MUTED, font=("Helvetica", 10)).grid(row=0, column=0, sticky="w")
        self.view_button = self._button(toolbar, "", self.toggle_view, textvariable=self.view_var, font=("Helvetica", 9), padx=9, pady=6, state="disabled")
        self.view_button.grid(row=0, column=1, padx=(10, 0))
        self.canvas = tk.Canvas(left, bg="#09111b", height=390, highlightbackground=BORDER, highlightthickness=1)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._schedule_render)
        review_header = tk.Frame(left, bg=PANEL)
        review_header.grid(row=2, column=0, sticky="ew", pady=(16, 10))
        review_header.grid_columnconfigure(0, weight=1)
        self._label(review_header, "REVIEW BOARD", font=("Helvetica", 9, "bold"), fg=MUTED).grid(row=0, column=0, sticky="w")
        self._label(review_header, textvariable=self.review_var, font=("Helvetica", 9), fg=MUTED).grid(row=0, column=1, sticky="e")
        editors = tk.Frame(left, bg=PANEL)
        editors.grid(row=3, column=0, sticky="ew")
        for column in range(4):
            editors.grid_columnconfigure(column, weight=1, uniform="tile")
        for index in range(16):
            cell = tk.Frame(editors, bg=SURFACE, padx=6, pady=6, highlightbackground=BORDER, highlightthickness=1)
            cell.grid(row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3)
            cell.grid_columnconfigure(1, weight=1)
            self.tile_frames.append(cell)
            tk.Label(cell, text=f"{index + 1:02}", bg=SURFACE, fg="#7f95b1", font=("Helvetica", 8)).grid(row=0, column=0, padx=(0, 4))
            entry = tk.Entry(cell, textvariable=self.letter_vars[index], width=2, justify="center", bg="#101b29", fg=TEXT, insertbackground=YELLOW, font=("Helvetica", 15, "bold"), relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE)
            entry.grid(row=0, column=1, sticky="ew")
            tk.Label(cell, text="/", bg=SURFACE, fg=MUTED, font=("Helvetica", 10)).grid(row=0, column=2, padx=4)
            spin = tk.Spinbox(cell, textvariable=self.dot_vars[index], from_=0, to=10, width=2, justify="center", bg="#101b29", fg=TEXT, insertbackground=YELLOW, buttonbackground=SURFACE, font=("Helvetica", 10), relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE)
            spin.grid(row=0, column=3)
        self.solve_button = self._button(left, "Solve edited board", self.solve_corrected, primary=True)
        self.solve_button.grid(row=4, column=0, sticky="ew", pady=(12, 0))

        right_shell = tk.Frame(content, bg=PANEL, width=370, highlightbackground=BORDER, highlightthickness=1)
        right_shell.grid(row=0, column=1, sticky="nsew")
        right_shell.grid_rowconfigure(0, weight=1)
        right_shell.grid_columnconfigure(0, weight=1)
        self.results_canvas = tk.Canvas(right_shell, bg=PANEL, width=350, highlightthickness=0)
        self.results_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(right_shell, orient="vertical", command=self.results_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        right = tk.Frame(self.results_canvas, bg=PANEL, padx=20, pady=20)
        window = self.results_canvas.create_window(0, 0, anchor="nw", window=right)
        right.bind("<Configure>", lambda _event: self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all")))
        self.results_canvas.bind("<Configure>", lambda event: self.results_canvas.itemconfigure(window, width=event.width))
        right.grid_columnconfigure(0, weight=1)
        result_header = tk.Frame(right, bg=PANEL)
        result_header.grid(row=0, column=0, sticky="ew")
        result_header.grid_columnconfigure(0, weight=1)
        self._label(result_header, textvariable=self.result_title_var, fg=MUTED, font=("Helvetica", 9, "bold")).grid(row=0, column=0, sticky="w")
        self.best_button = self._button(result_header, "Show best", lambda: self.select_candidate(0), state="disabled", font=("Helvetica", 9), padx=8, pady=4)
        self.best_button.grid(row=0, column=1, padx=(8, 0))
        self.best_label = self._label(right, textvariable=self.best_word_var, font=("Helvetica", 36, "bold"), fg=TEXT, pady=10)
        self.best_label.grid(row=1, column=0, sticky="ew")
        self.dictionary_label = self._label(right, textvariable=self.dictionary_var, fg=YELLOW, font=("Helvetica", 10, "bold"))
        self.dictionary_label.grid(row=2, column=0, sticky="w", pady=(0, 16))
        metrics = tk.Frame(right, bg=SURFACE, padx=12, pady=11)
        metrics.grid(row=3, column=0, sticky="ew")
        metrics.grid_columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate((("Utility proxy", self.utility_var), ("Tile dot total", self.dot_total_var), ("Estimated tracing", self.tracing_var))):
            self._label(metrics, label, bg=SURFACE, fg=MUTED, font=("Helvetica", 10)).grid(row=row, column=0, sticky="w", pady=4)
            self._label(metrics, textvariable=variable, bg=SURFACE, fg=YELLOW if row == 0 else TEXT, font=("Helvetica", 11, "bold"), anchor="e").grid(row=row, column=1, sticky="e", padx=(16, 0), pady=4)
        self._label(right, "Proxy values are NOT game points.\nTracing time is a model estimate.", fg=MUTED, font=("Helvetica", 9), justify="left").grid(row=4, column=0, sticky="w", pady=(9, 15))
        self._label(right, textvariable=self.path_var, fg=BLUE, wraplength=300, justify="left", font=("Helvetica", 10)).grid(row=5, column=0, sticky="ew", pady=(0, 22))
        self._label(right, "TOP 3 ALTERNATIVES", fg=MUTED, font=("Helvetica", 9, "bold")).grid(row=6, column=0, sticky="w", pady=(0, 10))
        self.alternatives_frame = tk.Frame(right, bg=PANEL)
        self.alternatives_frame.grid(row=7, column=0, sticky="ew")
        self.alternatives_frame.grid_columnconfigure(0, weight=1)
        self.empty_alternatives = self._label(self.alternatives_frame, "Candidate words will appear here.", fg=MUTED, font=("Helvetica", 10))
        self.empty_alternatives.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        self._label(right, "RECOGNITION REVIEW", fg=MUTED, font=("Helvetica", 9, "bold")).grid(row=8, column=0, sticky="w", pady=(22, 10))
        tk.Message(right, textvariable=self.warning_var, bg=SURFACE, fg=YELLOW, font=("Helvetica", 10), width=300, padx=12, pady=10).grid(row=9, column=0, sticky="ew")
        right.grid_rowconfigure(10, weight=1)
        self._label(right, textvariable=self.processing_var, fg=MUTED, font=("Helvetica", 9), wraplength=300, justify="left").grid(row=11, column=0, sticky="ew", pady=(18, 0))
        self._bind_result_scrolling(right)
        self.results_canvas.bind("<MouseWheel>", self._scroll_results)

    def _bind_result_scrolling(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._scroll_results, add="+")
        for child in widget.winfo_children():
            self._bind_result_scrolling(child)

    def _scroll_results(self, event: tk.Event) -> str:
        if event.delta:
            steps = max(1, abs(event.delta) // 120) if abs(event.delta) >= 120 else max(1, abs(event.delta))
            self.results_canvas.yview_scroll(-steps if event.delta > 0 else steps, "units")
        return "break"

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=BACKGROUND, padx=27, pady=14)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, text="Selected screen reading · Suggestions only · No gameplay actions", bg=BACKGROUND, fg=MUTED, font=("Helvetica", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="Open: ⌘/Ctrl O   ·   Solve edits: ⌘/Ctrl Enter", bg=BACKGROUND, fg="#697f9d", font=("Helvetica", 9)).grid(row=0, column=1, sticky="e")

    def refresh_windows(self) -> None:
        if self.closed:
            return
        from wordlink.capture.macos import list_windows

        selected = self._windows.get(self.window_var.get())
        try:
            windows = list_windows()
        except Exception as error:
            self.live_source_var.set(f"Could not list mirror windows: {error}")
            return
        windows = sorted(windows, key=lambda item: ("quicktime" not in item.app.lower(), item.app.lower(), item.title.lower(), item.window_id))
        self._windows = {
            f"{item.app} — {item.title or 'Untitled'} [{item.window_id}]": item
            for item in windows
        }
        menu = self.window_menu["menu"]
        menu.delete(0, "end")
        for label in self._windows:
            menu.add_command(label=label, command=lambda value=label: self._choose_window(value))
        preserved = next((label for label, item in self._windows.items() if selected and item.window_id == selected.window_id), None)
        if preserved:
            self.window_var.set(preserved)
        elif self._windows:
            # Window discovery is not source selection. Require a deliberate
            # choice so another app (such as a browser) is never captured by
            # pressing Start immediately after Refresh.
            self.window_var.set("Choose an existing mirror window")
        else:
            self.window_var.set("No mirror windows found")
            menu.add_command(label="No mirror windows found", state="disabled")
        if not self._live_requested:
            self.live_source_var.set("Choose the window showing your iPad and press Start live." if self._windows else "No mirror window found. Open an iPad mirror in QuickTime Player, then Refresh. Capture help has setup steps.")

    def _choose_window(self, label: str) -> None:
        self.window_var.set(label)
        self._window_selected(label)

    def _window_selected(self, _label: str) -> None:
        if self._live_requested:
            self.stop_live("Source changed. Press Start live to read the selected window.")
        else:
            self.live_source_var.set("Selected window: " + self.window_var.get())

    def start_selected_window(self) -> None:
        if self.closed:
            return
        selected = self._windows.get(self.window_var.get())
        if selected is None:
            self.refresh_windows()
            selected = self._windows.get(self.window_var.get())
        if selected is None:
            self.show_capture_help()
            return
        from wordlink.capture.macos import MacWindowSource
        from wordlink.capture.sources import CapturePermissionError

        try:
            source = MacWindowSource(selected.window_id, label=f"{selected.app} — {selected.title or 'Untitled'}")
        except CapturePermissionError as error:
            self._show_live_issue("permission", str(error))
            self.show_capture_help()
            return
        except Exception as error:
            self._show_live_issue("disconnected", str(error))
            return
        self.start_live(source)

    def open_replay(self) -> None:
        if self.closed:
            return
        filename = filedialog.askopenfilename(parent=self.root, title="Replay a Word Link recording", filetypes=[("Video recordings", "*.mp4 *.mov *.m4v *.avi *.mkv"), ("All files", "*")])
        if not filename:
            return
        from wordlink.capture.replay import ReplaySource

        try:
            source = ReplaySource(Path(filename))
        except Exception as error:
            self._show_live_issue("error", f"Could not open recording: {error}")
            return
        self.start_live(source)

    def start_live(self, source: FrameSource) -> None:
        """Start a selected native/replay/injected source after local vocabulary warm-up."""
        if self.closed:
            source.close()
            return
        self.stop_live()
        self._live_requested = True
        self._pending_source = source
        self._live_label = source.label
        self._live_state = "waiting"
        self._live_frame_at = None
        self.source_path = None
        self._image = None
        self.board = None
        self._recognition = None
        self.last_result = None
        self._clear_entries()
        self._full_screenshot = False
        self.source_var.set(f"Live · {source.label}")
        self.live_source_var.set(f"Starting · {source.label} · Loading local vocabulary…")
        self.warning_var.set("Waiting for a clear, settled board. Suggestions disappear when the board moves or cannot be read reliably.")
        self._clear_suggestions()
        self.start_live_button.configure(state="disabled")
        self.stop_live_button.configure(state="normal")
        self._start_job("STARTING", self._prepare_live, source)

    def _prepare_live(self, source: FrameSource, cancellation: Event) -> LivePreparation:
        try:
            trie, policy = self._load_vocabulary(cancellation)
            if cancellation.is_set():
                raise CancelledError()
            return LivePreparation(source, trie, policy)
        except BaseException:
            source.close()
            raise

    def _activate_live(self, prepared: LivePreparation) -> None:
        if not self._live_requested or self.closed:
            prepared.source.close()
            return
        from wordlink.capture.live import LiveAssistant

        self._pending_source = None
        try:
            controller = LiveAssistant(prepared.source, prepared.trie, prepared.policy)
            self._live_controller = controller
            controller.start()
        except Exception as error:
            prepared.source.close()
            self._live_controller = None
            self._show_live_issue("error", f"Could not start screen reading: {error}")
            return
        self.status_var.set("WAITING")
        self.status_label.configure(fg=BLUE)
        self.live_source_var.set(f"Live · {self._live_label} · Waiting for a settled board…")
        self.processing_var.set("Live reading · local vocabulary ready")

    def stop_live(self, message: str = "Live reading stopped.") -> None:
        """Discard this session immediately; the controller releases its own source."""
        active = self._live_requested or self._pending_source is not None or self._live_controller is not None
        self._live_requested = False
        self._live_frame_at = None
        self._live_state = "stopped"
        controller, self._live_controller = self._live_controller, None
        pending, self._pending_source = self._pending_source, None
        if active:
            self._generation += 1
            self._cancel.set()
            if self._future is not None:
                self._future.cancel()
        if controller is not None:
            controller.stop(timeout=.5 if self.closed else 0)
        if pending is not None:
            pending.close()
        if active and not self.closed:
            self.busy = False
            self.solve_button.configure(state="normal")
            self.start_live_button.configure(state="normal")
            self.stop_live_button.configure(state="disabled")
            self.status_var.set("STOPPED")
            self.status_label.configure(fg=MUTED)
            self.live_source_var.set(f"{self._live_label} · {message}")
            self.warning_var.set(message)
            self._clear_suggestions()

    def _show_live_issue(self, state: str, message: str) -> None:
        self.stop_live()
        self._live_state = state
        self.status_var.set(state.upper())
        self.status_label.configure(fg=YELLOW)
        self.live_source_var.set(message)
        self.warning_var.set(message)
        self._clear_suggestions()

    def show_capture_help(self) -> None:
        if self.closed:
            return
        if self._capture_help is not None and self._capture_help.winfo_exists():
            self._capture_help.lift()
            self._refresh_permission_status()
            return
        dialog = tk.Toplevel(self.root)
        self._capture_help = dialog
        dialog.title("Mirror setup and Screen Recording")
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        dialog.geometry("570x520")
        dialog.resizable(False, False)
        body = tk.Frame(dialog, bg=PANEL, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        self._label(body, "Read the screen you choose", font=("Helvetica", 20, "bold")).pack(anchor="w", pady=(0, 16))
        self._label(body, "1. Connect your iPad to this Mac with USB and trust the Mac.\n\n2. In QuickTime Player, choose File → New Movie Recording. Next to the recording button, choose the iPad as the camera source. Keep the game visible.\n\n3. Return here, Refresh the window list, choose the mirror window, then Start live.", fg=MUTED, font=("Helvetica", 11), justify="left", wraplength=515).pack(anchor="w")
        self._label(body, "The app reads an existing window. It does not connect to or automatically detect a physical iPad.", fg=MUTED, font=("Helvetica", 10), justify="left", wraplength=515).pack(anchor="w", pady=(16, 15))
        self._label(body, textvariable=self._permission_var, fg=YELLOW, font=("Helvetica", 10), justify="left", wraplength=515).pack(anchor="w", pady=(0, 15))
        buttons = tk.Frame(body, bg=PANEL)
        buttons.pack(fill="x")
        self._button(buttons, "Request Screen Recording", self._request_permission, primary=True, font=("Helvetica", 10), padx=11).pack(side="left", padx=(0, 10))
        self._button(buttons, "Open macOS settings", self._open_permission_settings, font=("Helvetica", 10), padx=11).pack(side="left")
        self._refresh_permission_status()

    def _refresh_permission_status(self) -> None:
        from wordlink.capture.macos import screen_recording_allowed

        try:
            allowed = screen_recording_allowed()
            self._permission_var.set("Screen Recording access is allowed. Refresh the window list and start the selected mirror." if allowed else "Screen Recording access is needed for another app’s window. Grant access to the app or terminal running Copilot, then relaunch if macOS asks.")
        except Exception as error:
            self._permission_var.set(f"Could not check Screen Recording access: {error}")

    def _request_permission(self) -> None:
        from wordlink.capture.macos import request_screen_recording

        try:
            request_screen_recording()
            self._refresh_permission_status()
        except Exception as error:
            self._permission_var.set(f"Could not request access: {error}")

    def _open_permission_settings(self) -> None:
        from wordlink.capture.macos import open_screen_recording_settings

        try:
            open_screen_recording_settings()
        except Exception as error:
            self._permission_var.set(f"Could not open macOS settings: {error}")

    def _on_manual_edit(self, *_arguments: str) -> None:
        if self.closed or self._updating_entries:
            return
        if self._live_requested:
            self.stop_live("Live reading paused for manual edits.")
        if self.busy:
            self._generation += 1
            self._cancel.set()
            if self._future is not None:
                self._future.cancel()
            self.busy = False
            self.solve_button.configure(state="normal")
        self._clear_suggestions()
        self.status_var.set("EDITED")
        self.status_label.configure(fg=YELLOW)
        self.warning_var.set("Entries changed. Press Solve edited board to analyze your corrections.")

    def _clear_suggestions(self) -> None:
        self.ranked_words = ()
        self.selected_index = 0
        self._update_results()
        self._draw_preview()

    def _open_shortcut(self, _event: tk.Event) -> str:
        self.open_dialog()
        return "break"

    def _solve_shortcut(self, _event: tk.Event) -> str:
        self.solve_corrected()
        return "break"

    def open_dialog(self) -> None:
        if self.closed:
            return
        filename = filedialog.askopenfilename(parent=self.root, title="Open a Word Link screenshot", filetypes=[("Screenshot images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("All files", "*")])
        if filename:
            self.open_image(Path(filename))

    def open_image(self, path: Path) -> None:
        if self.closed:
            return
        self.stop_live("Live reading paused for a screenshot.")
        self.source_path = Path(path)
        self._image = None
        self.board = None
        self._recognition = None
        self._full_screenshot = False
        self.ranked_words = ()
        self.last_result = None
        self.source_var.set(f"Reading {self.source_path.name}…")
        self.warning_var.set("Reading the screenshot. You can open another image at any time.")
        self._updating_entries = True
        try:
            for variable in self.letter_vars:
                variable.set("")
            for variable in self.dot_vars:
                variable.set("0")
        finally:
            self._updating_entries = False
        for cell in self.tile_frames:
            cell.configure(highlightbackground=BORDER)
        self._update_results()
        self._draw_preview()
        self._start_job("ANALYZING", self._analyze_screenshot, self.source_path)

    def solve_corrected(self) -> None:
        if self.closed:
            return
        self.stop_live("Live reading paused for a manual solve.")
        if self.busy:
            return
        try:
            boxes = self.board.boxes if self.board is not None else ()
            board = parse_board_entries([variable.get() for variable in self.letter_vars], [variable.get() for variable in self.dot_vars], boxes)
        except ValueError as error:
            self.warning_var.set(str(error))
            self.status_var.set("CHECK ENTRIES")
            self.status_label.configure(fg=YELLOW)
            return
        self._start_job("SOLVING", self._solve_board, board, self._image)

    def _start_job(self, status: str, function: Callable[..., AnalysisOutcome | LivePreparation], *args: object) -> None:
        self._cancel.set()
        if self._future is not None:
            self._future.cancel()
        self._cancel = Event()
        self._generation += 1
        generation = self._generation
        self.busy = True
        self.status_var.set(status)
        self.status_label.configure(fg=BLUE)
        self.processing_var.set("Processing locally…")
        self.solve_button.configure(state="disabled")
        self._future = self._executor.submit(function, *args, self._cancel)

        def completed(future: Future[AnalysisOutcome | LivePreparation]) -> None:
            try:
                outcome = future.result()
            except CancelledError:
                return
            except Exception as error:
                self._outbox.put((generation, None, f"{type(error).__name__}: {error}"))
            else:
                self._outbox.put((generation, outcome, None))

        self._future.add_done_callback(completed)

    def _load_vocabulary(self, cancellation: Event) -> tuple[Trie, VocabularyPolicy]:
        if cancellation.is_set():
            raise CancelledError()
        if self._trie is None:
            word_file = DATA_DIR / "words.txt"
            if not word_file.is_file():
                raise FileNotFoundError(f"Local word list missing: {word_file}")
            words = [line.strip() for line in word_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
            trie = Trie(words)
            policy = VocabularyPolicy.from_directory(DATA_DIR)
            if cancellation.is_set():
                raise CancelledError()
            self._trie = trie
            self._policy = policy
            self._vocabulary_count = len(trie)
        assert self._policy is not None
        return self._trie, self._policy

    def _analyze_screenshot(self, path: Path, cancellation: Event) -> AnalysisOutcome:
        started = perf_counter()
        image: Image.Image | None = None
        recognition: Recognition | None = None
        solve_ms = 0.0
        try:
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            if cancellation.is_set():
                raise CancelledError()
            recognition = recognize(path)
            if recognition.warnings:
                return AnalysisOutcome(image, recognition.board, recognition, (),
                                       (perf_counter() - started) * 1000, 0, self._vocabulary_count)
            trie, policy = self._load_vocabulary(cancellation)
            solve_started = perf_counter()
            ranked = tuple(rank_words(find_words(recognition.board, trie, min_length=3), policy))
            solve_ms = (perf_counter() - solve_started) * 1000
            if cancellation.is_set():
                raise CancelledError()
            return AnalysisOutcome(image, recognition.board, recognition, ranked, (perf_counter() - started) * 1000, solve_ms, self._vocabulary_count)
        except CancelledError:
            raise
        except Exception as error:
            return AnalysisOutcome(image, recognition.board if recognition else None, recognition, (), (perf_counter() - started) * 1000, solve_ms, self._vocabulary_count, str(error))

    def _solve_board(self, board: Board, image: Image.Image | None, cancellation: Event) -> AnalysisOutcome:
        started = perf_counter()
        try:
            trie, policy = self._load_vocabulary(cancellation)
            solve_started = perf_counter()
            ranked = tuple(rank_words(find_words(board, trie, min_length=3), policy))
            solve_ms = (perf_counter() - solve_started) * 1000
            if cancellation.is_set():
                raise CancelledError()
            return AnalysisOutcome(image, board, None, ranked, (perf_counter() - started) * 1000, solve_ms, self._vocabulary_count, edited=True)
        except CancelledError:
            raise
        except Exception as error:
            return AnalysisOutcome(image, board, None, (), (perf_counter() - started) * 1000, 0, self._vocabulary_count, str(error), edited=True)

    def _poll(self) -> None:
        if self.closed:
            return
        while True:
            try:
                generation, outcome, error = self._outbox.get_nowait()
            except Empty:
                break
            if generation != self._generation:
                if isinstance(outcome, LivePreparation):
                    outcome.source.close()
                continue
            self.busy = False
            self.solve_button.configure(state="normal")
            if error is not None:
                if self._live_requested:
                    self._show_live_issue("error", error)
                else:
                    self.warning_var.set(error)
                    self.status_var.set("CHECK INPUT")
                    self.status_label.configure(fg=YELLOW)
            elif isinstance(outcome, LivePreparation):
                self._activate_live(outcome)
            elif isinstance(outcome, AnalysisOutcome):
                self._apply_result(outcome)
        if self._live_controller is not None:
            try:
                update = self._live_controller.poll()
            except Exception as error:
                self._show_live_issue("error", f"Screen reading failed: {error}")
            else:
                if update is not None:
                    self._apply_live_update(update)
        if self._live_requested and self._live_state == "ready" and not live_ready_is_fresh("ready", self._live_frame_at, monotonic()):
            self._live_state = "waiting"
            self.status_var.set("WAITING")
            self.status_label.configure(fg=YELLOW)
            self.live_source_var.set(f"{self._live_label} · Waiting for a fresh frame…")
            self.warning_var.set("The latest frame is stale. Suggestions are hidden until a fresh, settled board arrives.")
            self.board = None
            self._recognition = None
            self._clear_entries()
            self._clear_suggestions()
        self._poll_id = self.root.after(50, self._poll)

    def _clear_entries(self) -> None:
        self._updating_entries = True
        try:
            for variable in self.letter_vars:
                variable.set("")
            for variable in self.dot_vars:
                variable.set("0")
            for cell in self.tile_frames:
                cell.configure(highlightbackground=BORDER)
            self.review_var.set("Waiting for a readable board · letter / dot count")
        finally:
            self._updating_entries = False

    def _fill_entries(self, board: Board, recognition: Recognition | None) -> None:
        self._updating_entries = True
        try:
            for index, (letter, dots) in enumerate(zip(board.letters, board.dots)):
                self.letter_vars[index].set(letter)
                self.dot_vars[index].set(str(dots))
                uncertain = bool(recognition and (
                    recognition.tiles[index].confidence < 0.80
                    or any(warning.startswith(f"Tile {index + 1}:") for warning in recognition.warnings)
                ))
                self.tile_frames[index].configure(highlightbackground=YELLOW if uncertain else BORDER)
        finally:
            self._updating_entries = False

    def _apply_live_update(self, update: LiveUpdate) -> None:
        if not self._live_requested or self.closed:
            return
        old_state = self._live_state
        state = update.state
        frame = update.frame
        if frame is not None:
            self._image = Image.fromarray(frame.image[:, :, ::-1].copy())
            self._live_frame_at = frame.captured_at
            self.view_button.configure(state="normal")
        self._live_state = state
        self.source_var.set(self._live_label + (f" · {frame.media_time:.2f} s" if frame and frame.media_time is not None else " · Live"))
        self.live_source_var.set(f"{self._live_label} · {update.message}")
        self.status_var.set(state.upper())
        self.status_label.configure(fg=GREEN if state == "ready" else BLUE if state in ("waiting", "reading") else MUTED if state in ("ended", "stopped") else YELLOW)
        self.processing_var.set(f"Live frame {update.sequence} · {update.elapsed_ms:.0f} ms\nSolve + rank {update.solve_ms:.0f} ms\n{len(update.ranked_words):,} candidates · {self._vocabulary_count:,} local words")
        recognition = update.recognition
        if state == "ready" and live_ready_is_fresh(state, frame.captured_at if frame else None, monotonic()) and recognition is not None:
            same_result = old_state == "ready" and self.board == recognition.board and self.ranked_words == tuple(update.ranked_words)
            self.board = recognition.board
            self._recognition = recognition
            self.ranked_words = tuple(update.ranked_words)
            self.review_var.set("Live detected tiles · letter / dot count")
            self._fill_entries(self.board, recognition)
            self.warning_var.set("The board is settled. Review the letters if a suggestion looks wrong. Common-word membership does not establish game acceptance.")
            if not same_result:
                self.selected_index = 0
                self._update_results()
            self._draw_preview()
        else:
            if state == "ready":
                self._live_state = "waiting"
                self.status_var.set("WAITING")
                self.status_label.configure(fg=YELLOW)
                self.live_source_var.set(f"{self._live_label} · Waiting for a fresh readable board…")
                self.warning_var.set("Suggestions are hidden because this ready update lacks a fresh readable board.")
            else:
                self.warning_var.set(update.message)
            self.board = recognition.board if recognition else None
            self._recognition = recognition
            if self.board is not None:
                self._fill_entries(self.board, recognition)
            else:
                self._clear_entries()
            self._clear_suggestions()
        if state in ("permission", "disconnected", "ended", "error", "stopped"):
            controller, self._live_controller = self._live_controller, None
            if controller is not None:
                controller.stop(timeout=0)
            self._live_requested = False
            self._live_frame_at = None
            self.start_live_button.configure(state="normal")
            self.stop_live_button.configure(state="disabled")

    def _apply_result(self, outcome: AnalysisOutcome) -> None:
        self.last_result = outcome
        self._image = outcome.image
        self.board = outcome.board
        self._recognition = outcome.recognition
        self.ranked_words = outcome.ranked_words
        self.selected_index = 0
        self.view_button.configure(state="normal" if self._image else "disabled")
        self.view_var.set("Full screenshot" if not self._full_screenshot else "Board view")
        filename = self.source_path.name if self.source_path else "Manual board"
        self.source_var.set(filename)
        if self.board is not None:
            self._fill_entries(self.board, outcome.recognition)
        if outcome.error:
            self.status_var.set("REVIEW NEEDED")
            self.status_label.configure(fg=YELLOW)
            self.warning_var.set(f"Could not complete analysis: {outcome.error}\n\nYou can enter all 16 letters and dot counts below and solve the board manually.")
        else:
            warnings = list(outcome.recognition.warnings) if outcome.recognition else []
            needs_review = bool(warnings) and not outcome.edited
            self.status_var.set("REVIEW NEEDED" if needs_review else "ANALYZED")
            self.status_label.configure(fg=YELLOW if needs_review else GREEN)
            if needs_review:
                warnings.insert(0, "Suggestions are held until you review the detected entries and choose Solve edited board.")
            if outcome.edited:
                self.review_var.set("Edited entries · letter / dot count")
                warnings.insert(0, "Using your edited letters and dot counts. Recognition confidence does not apply to these entries.")
            else:
                self.review_var.set("16 tiles · letter / dot count")
                if outcome.recognition and outcome.recognition.tiles:
                    minimum = min(tile.confidence for tile in outcome.recognition.tiles)
                    warnings.insert(0, f"Lowest recognizer confidence: {minimum:.0%}. This is an estimate, not a measured accuracy.")
            warnings.append("Dictionary membership is unverified unless backed by a local confirmation record.")
            self.warning_var.set("\n\n".join(warnings[:4]))
        recognition_text = f"Recognition {outcome.recognition.elapsed_ms:.0f} ms · " if outcome.recognition else ""
        self.processing_var.set(f"Total {outcome.elapsed_ms:.0f} ms\n{recognition_text}Solve + rank {outcome.solve_ms:.0f} ms\n{len(outcome.ranked_words):,} candidates · {outcome.vocabulary_count:,} local words")
        self._update_results()
        self._draw_preview()

    def _update_results(self) -> None:
        for button in self.alternative_buttons:
            button.destroy()
        self.alternative_buttons.clear()
        self.empty_alternatives.grid_remove()
        if not self.ranked_words:
            self.result_title_var.set("BEST CANDIDATE")
            self.best_button.configure(state="disabled")
            self.best_word_var.set("—")
            self.dictionary_var.set("Dictionary: UNKNOWN")
            self.dictionary_label.configure(fg=YELLOW)
            self.utility_var.set("—")
            self.dot_total_var.set("—")
            self.tracing_var.set("—")
            held_for_review = bool(self._recognition and self._recognition.warnings)
            self.path_var.set("Review the detected entries and choose Solve edited board to show candidates." if held_for_review
                              else "No candidates yet." if self.board is None
                              else "No matching words in the local vocabulary. Review the board entries.")
            self.empty_alternatives.configure(text="Suggestions are held for review." if held_for_review
                                             else "Candidate words will appear here." if self.board is None
                                             else "No alternative candidates found.")
            self.empty_alternatives.grid(row=0, column=0, sticky="ew", pady=(4, 12))
            return
        for row, candidate in enumerate(self.ranked_words[1:4]):
            index = row + 1
            text = f"{candidate.found.word}    ·    utility {candidate.utility:.1f}\n{len(candidate.found.path)} letters  /  {candidate.found.dot_sum} dots  /  Band {candidate.confidence_band} · {candidate.status.upper()}"
            button = self._button(self.alternatives_frame, text, lambda selected=index: self.select_candidate(selected), anchor="w", justify="left", font=("Helvetica", 10), padx=11, pady=10)
            button.grid(row=row, column=0, sticky="ew", pady=(0, 7))
            self._bind_result_scrolling(button)
            self.alternative_buttons.append(button)
        if len(self.ranked_words) == 1:
            self.empty_alternatives.configure(text="This is the only candidate for this board.")
            self.empty_alternatives.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        self.select_candidate(self.selected_index)

    def select_candidate(self, index: int) -> None:
        if self.closed or not 0 <= index < len(self.ranked_words):
            return
        self.selected_index = index
        self.best_button.configure(state="normal" if index != 0 else "disabled")
        candidate = self.ranked_words[index]
        self.result_title_var.set("BEST CANDIDATE" if index == 0 else "SELECTED ALTERNATIVE")
        self.best_word_var.set(candidate.found.word)
        self.best_label.configure(font=("Helvetica", 36 if len(candidate.found.word) <= 10 else 25, "bold"))
        band_description = {"A": "confirmed", "B": "common word", "C": "dictionary word"}[candidate.confidence_band]
        self.dictionary_var.set(f"Dictionary: {candidate.status.upper()} · {band_description}")
        self.dictionary_label.configure(fg=GREEN if candidate.status == "confirmed" else YELLOW)
        self.utility_var.set(f"{candidate.utility:.1f}")
        self.dot_total_var.set(str(candidate.found.dot_sum))
        self.tracing_var.set(f"{candidate.estimated_seconds:.2f} s")
        self.path_var.set("Path: " + " → ".join(str(tile + 1) for tile in candidate.found.path))
        for offset, button in enumerate(self.alternative_buttons, start=1):
            button.configure(bg="#203b5b" if offset == index else SURFACE, highlightbackground=BLUE if offset == index else BORDER)
        self._draw_preview()

    def toggle_view(self) -> None:
        self._full_screenshot = not self._full_screenshot
        self.view_var.set("Board view" if self._full_screenshot else "Full screenshot")
        self._draw_preview()

    def _schedule_render(self, _event: tk.Event | None = None) -> None:
        if self.closed:
            return
        if self._render_id is not None:
            self.root.after_cancel(self._render_id)
        self._render_id = self.root.after(30, self._draw_preview)

    def _draw_preview(self) -> None:
        if self._render_id is not None:
            try:
                self.root.after_cancel(self._render_id)
            except tk.TclError:
                pass
        self._render_id = None
        if self.closed:
            return
        self.canvas.delete("all")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 2 or height < 2:
            return
        self._photo = None
        displayed_boxes: list[tuple[float, float, float, float]] = []
        use_image = self._image is not None and (self._full_screenshot or self.board is None or bool(self.board.boxes))
        if use_image and self._image is not None:
            bounds = (0, 0, *self._image.size) if self._full_screenshot else crop_bounds(self._image.size, self.board.boxes if self.board else ())
            cropped = self._image.crop(bounds)
            scale = min((width - 28) / cropped.width, (height - 30) / cropped.height)
            shown_width, shown_height = max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))
            resized = cropped.resize((shown_width, shown_height), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(resized, master=self.root)
            offset_x, offset_y = (width - shown_width) / 2, (height - shown_height) / 2
            self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self._photo)
            if self.board and self.board.boxes:
                for x, y, tile_width, tile_height in self.board.boxes:
                    displayed_boxes.append((offset_x + (x - bounds[0]) * scale, offset_y + (y - bounds[1]) * scale, tile_width * scale, tile_height * scale))
        else:
            size = min(width - 70, height - 70, 390)
            tile_size = size / 4
            offset_x, offset_y = (width - size) / 2, (height - size) / 2
            for index in range(16):
                x = offset_x + (index % 4) * tile_size
                y = offset_y + (index // 4) * tile_size
                displayed_boxes.append((x, y, tile_size, tile_size))
                self.canvas.create_rectangle(x + 3, y + 3, x + tile_size - 3, y + tile_size - 3, fill="#183761", outline="#2d5b91", width=1)
                letter = self.board.letters[index] if self.board else "·"
                self.canvas.create_text(x + tile_size / 2, y + tile_size / 2, text=letter, fill=TEXT if self.board else "#42668f", font=("Helvetica", max(15, int(tile_size * 0.30)), "bold"))
                if self.board:
                    self.canvas.create_text(x + tile_size / 2, y + tile_size * 0.78, text=f"{self.board.dots[index]} dots", fill=MUTED, font=("Helvetica", 8))
            caption = "Manual reconstruction" if self.board else "Waiting for the selected screen…" if self._live_requested else "Open a screenshot or enter a board below"
            self.canvas.create_text(width / 2, height - 16, text=caption, fill=MUTED, font=("Helvetica", 10))
        if displayed_boxes and self.ranked_words:
            path = self.ranked_words[self.selected_index].found.path
            points = [(displayed_boxes[index][0] + displayed_boxes[index][2] / 2, displayed_boxes[index][1] + displayed_boxes[index][3] / 2) for index in path]
            if len(points) > 1:
                coordinates = [value for point in points for value in point]
                self.canvas.create_line(*coordinates, fill=BLUE, width=7, capstyle="round", joinstyle="round", arrow="last", arrowshape=(14, 17, 6), tags=("path",))
            for step, index in enumerate(path, start=1):
                x, y, tile_width, tile_height = displayed_boxes[index]
                color = YELLOW if step == len(path) else BLUE
                self.canvas.create_rectangle(x + 2, y + 2, x + tile_width - 2, y + tile_height - 2, outline=color, width=2, tags=("path",))
                radius = max(7, min(12, tile_width * 0.16))
                marker_x, marker_y = x + radius + 5, y + radius + 5
                self.canvas.create_oval(marker_x - radius, marker_y - radius, marker_x + radius, marker_y + radius, fill=BACKGROUND, outline=YELLOW, width=2, tags=("path",))
                self.canvas.create_text(marker_x, marker_y, text=str(step), fill=YELLOW, font=("Helvetica", max(7, round(radius * 0.9)), "bold"), tags=("path",))
            self.canvas.create_text(10, 10, anchor="nw", text="NUMBERED MARKERS = PATH ORDER", fill=MUTED, font=("Helvetica", 8))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.stop_live()
        self._generation += 1
        self._cancel.set()
        if self._future is not None:
            self._future.cancel()
        for callback in (self._poll_id, self._render_id, self._initial_id):
            if callback is not None:
                try:
                    self.root.after_cancel(callback)
                except tk.TclError:
                    pass
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def create_app(root: tk.Tk, image_path: Path | None = None, live_source: FrameSource | None = None) -> WordLinkApp:
    return WordLinkApp(root, image_path, live_source)


def launch(image_path: Path | None = None, live_source: FrameSource | None = None) -> None:
    root = tk.Tk()
    create_app(root, image_path, live_source)
    root.mainloop()
