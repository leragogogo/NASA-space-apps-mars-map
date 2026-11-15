from app.graph.cli import main
from app.graph.contracts import GraphData


def test_fake_small_builds_then_reuses(tmp_path, capsys):
    out = tmp_path / "g.npz"
    assert main(["--fake", "--small", "--out", str(out)]) == 0
    assert "built:" in capsys.readouterr().out and GraphData.load(out).n_edges > 0
    assert main(["--fake", "--small", "--out", str(out)]) == 0
    assert "up to date" in capsys.readouterr().out
    assert main(["--fake", "--small", "--out", str(out), "--force"]) == 0
    assert "built:" in capsys.readouterr().out


def test_without_fake_reports_missing_data_and_the_fix(tmp_path, capsys):
    assert main(["--out", str(tmp_path / "g.npz"), "--data-dir", str(tmp_path / "nothing")]) == 2
    err = capsys.readouterr().err
    assert "cannot build the graph" in err and "download_data.py" in err
