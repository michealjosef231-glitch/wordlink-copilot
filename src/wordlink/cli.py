from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import cv2

from wordlink.model import Board, FoundWord
from wordlink.capture.sources import CaptureError
from wordlink.overlay import save_overlay
from wordlink.paths import DATA_DIR
from wordlink.solver.ranking import rank_words
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy


def dictionary_trie() -> Trie:
    path = DATA_DIR / "words.txt"
    if not path.exists():
        raise ValueError(f"Missing local dictionary: {path}")
    return Trie(path.read_text(encoding="utf-8").splitlines())


def solve_board(board: Board, trie: Trie, policy: VocabularyPolicy) -> dict:
    start = perf_counter()
    found = find_words(board, trie)
    search_ms = (perf_counter() - start) * 1000
    start = perf_counter()
    ranked = rank_words(found, policy)
    return {
        "board": asdict(board), "legal_paths": [asdict(word) for word in found],
        "recommendations": [asdict(word) for word in ranked],
        "timings_ms": {"search": search_ms, "ranking": (perf_counter() - start) * 1000},
        "scoring": "uncalibrated: proxy utility, not game points",
        "dictionary": "ENABLE candidates; unknown game acceptance until recorded in the ledger",
    }


def print_summary(result: dict, top: int = 3) -> None:
    board = result["board"]
    for row in range(4):
        print(" ".join(board["letters"][row * 4:row * 4 + 4]))
    print(f"\n{len(result['recommendations'])} words / {len(result['legal_paths'])} legal paths")
    for candidate in result["recommendations"][:top]:
        found = candidate["found"]
        path = " -> ".join(f"r{index // 4 + 1}c{index % 4 + 1}" for index in found["path"])
        print(f"{found['word']:16} {candidate['status']:10} proxy utility {candidate['utility']:.2f}  {path}")
    print("Scores are uncalibrated; game acceptance is unknown for ordinary dictionary words.")
    print("Timings (ms): " + json.dumps(result["timings_ms"]))


def write_json(path: Path | None, result: dict) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Word Link live assistant and screenshot analyzer")
    sub = parser.add_subparsers(dest="command", required=True)
    screenshot = sub.add_parser("screenshot", help="Read and solve one screenshot")
    screenshot.add_argument("image", type=Path)
    screenshot.add_argument("--json", type=Path)
    screenshot.add_argument("--overlay", type=Path)
    screenshot.add_argument("--top", type=int, default=3)
    screenshot.add_argument("--allow-uncertain", action="store_true", help="Include flagged reads for offline inspection")
    manual = sub.add_parser("board", help="Solve a manually entered 4x4 board")
    manual.add_argument("letters", help="16 A-Z tiles; use 16 space-separated tokens when a tile is Qu")
    manual.add_argument("--dots", required=True, help="16 space-separated integer dot counts")
    manual.add_argument("--json", type=Path)
    manual.add_argument("--top", type=int, default=3)
    video = sub.add_parser("video", help="Analyze settled boards in a local recording")
    video.add_argument("recording", type=Path)
    video.add_argument("--json", type=Path, required=True)
    video.add_argument("--overlays", type=Path)
    video.add_argument("--sample-fps", type=float, default=4)
    video.add_argument("--start", type=float, default=0)
    video.add_argument("--stop", type=float)
    ui = sub.add_parser("ui", help="Open the desktop assistant")
    ui.add_argument("image", type=Path, nargs="?")
    windows = sub.add_parser("windows", help="List available Mac mirror windows")
    windows.add_argument("--json", action="store_true")
    live = sub.add_parser("live", help="Open automatic reading of a mirror window or local replay")
    source = live.add_mutually_exclusive_group()
    source.add_argument("--window-id", type=int)
    source.add_argument("--recording", type=Path)
    live.add_argument("--start", type=float, default=0, help="Recording replay start in seconds")
    live.add_argument("--loop", action="store_true", help="Repeat the recording replay")
    args = parser.parse_args(argv)
    try:
        if args.command == "windows":
            from wordlink.capture.macos import list_windows, screen_recording_allowed
            available = list_windows()
            if args.json:
                print(json.dumps({"screen_recording_allowed": screen_recording_allowed(),
                                  "windows": [asdict(window) for window in available]}, indent=2))
            else:
                for window in available:
                    print(f"{window.window_id}\t{window.app}\t{window.title}")
                if not screen_recording_allowed():
                    print("Screen Recording permission is needed to read another app's window.")
            return 0
        if args.command in {"ui", "live"}:
            from wordlink.ui.app import launch
            if args.command == "ui":
                launch(args.image)
            else:
                selected = None
                if args.recording:
                    from wordlink.capture.replay import ReplaySource
                    selected = ReplaySource(args.recording, start=args.start, loop=args.loop)
                elif args.start != 0 or args.loop:
                    raise ValueError("--start and --loop require --recording")
                elif args.window_id is not None:
                    from wordlink.capture.macos import MacWindowSource
                    selected = MacWindowSource(args.window_id)
                launch(live_source=selected)
            return 0
        start = perf_counter()
        trie = dictionary_trie()
        policy = VocabularyPolicy.from_directory(DATA_DIR)
        setup_ms = (perf_counter() - start) * 1000
        if args.command == "video":
            from wordlink.capture.analyze import analyze_recording
            result = analyze_recording(args.recording, trie, policy, args.sample_fps,
                                       args.start, args.stop, args.overlays)
            result["dictionary_setup_ms"] = setup_ms
            write_json(args.json, result)
            print(f"Saved {len(result['boards'])} stable board reads to {args.json}")
            return 0
        if args.command == "screenshot":
            from wordlink.vision.board import recognize
            read = recognize(args.image)
            if read.warnings and not args.allow_uncertain:
                raise ValueError("Recognition needs review: " + "; ".join(read.warnings))
            result = solve_board(read.board, trie, policy)
            result["recognition"] = asdict(read)
            result["timings_ms"]["recognition"] = read.elapsed_ms
            if args.overlay and result["recommendations"]:
                recommendation = result["recommendations"][0]["found"]
                found = FoundWord(recommendation["word"], tuple(recommendation["path"]), recommendation["dot_sum"])
                image = cv2.imread(str(args.image))
                save_overlay(args.overlay, image, read.board, found)
        else:
            tokens = args.letters.upper().split()
            letters = tuple(tokens) if len(tokens) == 16 else tuple("".join(tokens))
            dots = tuple(int(value) for value in args.dots.split())
            result = solve_board(Board(letters, dots), trie, policy)
        result["timings_ms"]["dictionary_setup"] = setup_ms
        write_json(args.json, result)
        print_summary(result, max(1, args.top))
        return 0
    except (ValueError, OSError, CaptureError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
