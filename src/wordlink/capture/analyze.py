from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from wordlink.capture.video import SettleDetector, iter_frames, video_info
from wordlink.overlay import save_overlay
from wordlink.solver.ranking import rank_words
from wordlink.solver.search import find_words
from wordlink.solver.trie import Trie
from wordlink.vocabulary.policy import VocabularyPolicy
from wordlink.vision.board import recognize
from wordlink.vision.tiles import detect_tiles


def analyze_recording(path: Path, trie: Trie, policy: VocabularyPolicy, sample_fps: float = 4,
                      start: float = 0, stop: float | None = None,
                      overlay_dir: Path | None = None) -> dict:
    info = video_info(path)
    detector = SettleDetector()
    reads, seen, failures = [], set(), []
    sampled = unstable = uncertain = duplicate = 0
    started = perf_counter()
    next_progress = start + 10
    for timestamp, frame in iter_frames(path, sample_fps, start, stop):
        sampled += 1
        if timestamp >= next_progress:
            print(f"Recording {timestamp:.1f}s: {len(reads)} unique settled boards", flush=True)
            next_progress = timestamp + 10
        try:
            boxes = detect_tiles(frame)
        except ValueError as exc:
            if len(failures) < 5:
                failures.append({"timestamp": timestamp, "reason": str(exc)})
            detector = SettleDetector()
            unstable += 1
            continue
        x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x2, y2 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        if not detector.update(frame[y1:y2, x1:x2]):
            continue
        try:
            read = recognize(frame)
        except ValueError as exc:
            if len(failures) < 5:
                failures.append({"timestamp": timestamp, "reason": str(exc)})
            detector = SettleDetector()
            unstable += 1
            continue
        signature = (read.board.letters, read.board.dots)
        if signature in seen:
            duplicate += 1
            continue
        seen.add(signature)
        result = {"timestamp": timestamp, "recognition": asdict(read), "recommendations": []}
        if read.warnings:
            result["status"] = "needs review"
            uncertain += 1
        else:
            result["status"] = "solved"
            solving = perf_counter()
            found = find_words(read.board, trie)
            ranked = rank_words(found, policy)
            result.update({"legal_paths": [asdict(word) for word in found],
                           "recommendations": [asdict(word) for word in ranked],
                           "solve_and_rank_ms": (perf_counter() - solving) * 1000})
            if overlay_dir and ranked:
                overlay = overlay_dir / f"board_{timestamp:07.3f}.png"
                save_overlay(overlay, frame, read.board, ranked[0].found)
                result["overlay"] = str(overlay)
        reads.append(result)
    return {
        "video": {**asdict(info), "duration_seconds": info.duration, "source": str(path)},
        "sampling": {"fps": sample_fps, "quiet_frames": 3, "start": start, "stop": stop},
        "counts": {"sampled": sampled, "missing_or_moving_tiles": unstable,
                   "uncertain_unique_boards": uncertain, "duplicate_settled_boards": duplicate},
        "elapsed_seconds": perf_counter() - started, "diagnostic_examples": failures,
        "accuracy": "Only independently annotated fixtures establish accuracy; other reads are unverified",
        "scoring": "Uncalibrated proxy utility; game dictionary acceptance is unknown",
        "boards": reads,
    }
