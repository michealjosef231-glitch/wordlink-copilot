import sys
from dataclasses import dataclass
from types import SimpleNamespace

from wordlink.cli import main


def test_live_cli_passes_replay_source_without_opening_or_loading_dictionary(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setitem(sys.modules, "wordlink.ui.app", SimpleNamespace(launch=lambda **kw: launched.append(kw)))
    path = tmp_path / "recording.mp4"
    assert main(["live", "--recording", str(path), "--start", "10", "--loop"]) == 0
    source = launched[0]["live_source"]
    assert source.path == path and source.start == 10 and source.loop
    assert source._capture is None
    source.close()


def test_live_cli_rejects_replay_options_without_a_recording(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "wordlink.ui.app", SimpleNamespace(launch=lambda **kw: None))
    assert main(["live", "--start", "10"]) == 2
    assert "require --recording" in capsys.readouterr().err


def test_windows_cli_exposes_permission_and_only_selected_metadata(monkeypatch, capsys):
    @dataclass
    class Window:
        window_id: int
        app: str
        title: str
        pid: int
        bounds: tuple
    monkeypatch.setitem(sys.modules, "wordlink.capture.macos", SimpleNamespace(
        list_windows=lambda: [Window(23, "QuickTime Player", "Movie Recording", 123, (0, 0, 512, 732))],
        screen_recording_allowed=lambda: False,
    ))
    assert main(["windows", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"screen_recording_allowed": false' in output
    assert '"window_id": 23' in output
