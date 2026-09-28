"""Measure the full local pipeline against independently labeled recording crops."""
import json
import statistics
from pathlib import Path
from time import perf_counter

from wordlink.cli import dictionary_trie
from wordlink.paths import DATA_DIR, FIXTURES_DIR, ROOT
from wordlink.solver.ranking import rank_words
from wordlink.solver.search import find_words
from wordlink.vocabulary.policy import VocabularyPolicy
from wordlink.vision.board import recognize


def main():
    cases = json.loads((FIXTURES_DIR / "boards/labels.json").read_text())["boards"]
    started = perf_counter()
    trie = dictionary_trie()
    setup_ms = (perf_counter() - started) * 1000
    policy = VocabularyPolicy.from_directory(DATA_DIR)
    cold_start = perf_counter()
    recognize(FIXTURES_DIR / "boards" / cases[0]["file"])
    first_recognition_ms = (perf_counter() - cold_start) * 1000
    rows = []
    for case in cases:
        letters = tuple("".join(case["letters"]))
        dots = tuple(value for row in case["dots"] for value in row)
        recognition_times, full_times = [], []
        for _ in range(5):
            started = perf_counter()
            read = recognize(FIXTURES_DIR / "boards" / case["file"])
            assert read.board.letters == letters
            assert read.board.dots == dots
            assert not read.warnings
            found = find_words(read.board, trie)
            ranked = rank_words(found, policy)
            recognition_times.append(read.elapsed_ms)
            full_times.append((perf_counter() - started) * 1000)
            for word in found:
                assert len(word.path) == len(set(word.path))
                assert "".join(letters[index] for index in word.path) == word.word
                assert sum(dots[index] for index in word.path) == word.dot_sum
                assert all(max(abs(a // 4 - b // 4), abs(a % 4 - b % 4)) == 1
                           for a, b in zip(word.path, word.path[1:]))
        rows.append({"fixture": case["file"], "letters_correct": 16, "dots_correct": 16,
                     "recognition_median_ms": statistics.median(recognition_times),
                     "pipeline_median_ms": statistics.median(full_times),
                     "pipeline_max_ms": max(full_times), "unique_words": len(ranked),
                     "legal_paths": len(found), "top_three": [candidate.found.word for candidate in ranked[:3]]})
    output = {"scope": "four independently labeled board crops, five warmed repetitions per board",
              "dictionary_words": len(trie), "dictionary_setup_ms": setup_ms,
              "first_recognition_ms": first_recognition_ms, "boards": rows,
              "scoring": "uncalibrated proxies", "game_acceptance": "unknown"}
    (ROOT / "artifacts/validation.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
