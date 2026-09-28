from __future__ import annotations

from pathlib import Path

from wordlink.vocabulary.policy import VocabularyPolicy


def test_initial_ledgers_do_not_invent_game_acceptance() -> None:
    directory = Path(__file__).resolve().parents[1] / "data"
    policy = VocabularyPolicy.from_directory(directory)
    assert not policy.confirmed
    assert not policy.rejected
    assert policy.status("CAT") == "unknown"


def test_observed_fixture_verdicts_load_and_rejection_wins_conflicts(tmp_path: Path) -> None:
    # Simulated test verdicts are confined to a temporary directory.
    (tmp_path / "accepted.txt").write_text("# test fixture\n cat \nDOG\nDOG\nCAN'T\n", encoding="utf-8")
    (tmp_path / "rejected.txt").write_text("dog\nRAT\n", encoding="utf-8")
    policy = VocabularyPolicy.from_directory(tmp_path)
    assert policy.status(" cat ") == "confirmed"
    assert policy.status("DOG") == "rejected"
    assert policy.status("rat") == "rejected"
    assert policy.status("STONE") == "unknown"
    assert policy.status("CAN'T") == "unknown"
    assert policy.status("ß") == "unknown"


def test_ledger_reads_persisted_verdicts_without_mutating_files(tmp_path: Path) -> None:
    accepted = tmp_path / "accepted.txt"
    rejected = tmp_path / "rejected.txt"
    accepted.write_text("# explicitly supplied fixture verdict\nCAT\n", encoding="utf-8")
    rejected.write_text("RAT\n", encoding="utf-8")
    before = (accepted.read_bytes(), rejected.read_bytes())
    first = VocabularyPolicy.from_directory(tmp_path)
    second = VocabularyPolicy.from_directory(tmp_path)
    assert first == second
    assert first.status("CAT") == second.status("CAT") == "confirmed"
    assert first.status("RAT") == second.status("RAT") == "rejected"
    assert (accepted.read_bytes(), rejected.read_bytes()) == before


def test_missing_ledgers_remain_unknown_and_no_files_are_created(tmp_path: Path) -> None:
    directory = tmp_path / "not-created"
    policy = VocabularyPolicy.from_directory(directory)
    assert policy.status("CAT") == "unknown"
    assert not directory.exists()


def test_common_words_are_unconfirmed_and_rejection_overrides_their_band(tmp_path: Path) -> None:
    (tmp_path / "common.txt").write_text("cat\n dog \nRAT\n# test fixture\nCAN'T\n", encoding="utf-8")
    (tmp_path / "accepted.txt").write_text("DOG\n", encoding="utf-8")
    (tmp_path / "rejected.txt").write_text("RAT\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    policy = VocabularyPolicy.from_directory(tmp_path)
    assert policy.common_words == frozenset({"CAT", "DOG", "RAT"})
    assert policy.is_common(" cat ")
    assert policy.status("CAT") == "unknown"
    assert policy.confidence_band("CAT") == "B"
    assert policy.status("DOG") == "confirmed"
    assert policy.confidence_band("DOG") == "A"
    assert policy.is_common("RAT")
    assert policy.status("RAT") == "rejected"
    assert policy.confidence_band("RAT") == "C"
    assert policy.status("AGELONG") == "unknown"
    assert policy.confidence_band("AGELONG") == "C"
    assert not policy.is_common("CAN'T")
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_missing_common_list_preserves_confirmed_and_unknown_behavior(tmp_path: Path) -> None:
    (tmp_path / "accepted.txt").write_text("CAT\n", encoding="utf-8")
    policy = VocabularyPolicy.from_directory(tmp_path)
    assert not policy.common_words
    assert not policy.is_common("CAT")
    assert policy.status("CAT") == "confirmed"
    assert policy.confidence_band("CAT") == "A"
    assert policy.status("DOG") == "unknown"
    assert policy.confidence_band("DOG") == "C"
    assert not (tmp_path / "common.txt").exists()
