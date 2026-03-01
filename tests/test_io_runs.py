from runwx.io_runs import load_runs_csv


def test_load_runs_csv_happy_path(tmp_path):
    csv_text = (
        "started_at,duration_s,distance_m\n"
        "2026-02-01T10:00:00+00:00,3600,10000\n"
        "2026-02-01T12:00:00+00:00,1800,5000\n"
    )
    path = tmp_path / "runs.csv"
    path.write_text(csv_text, encoding="utf-8")

    runs = load_runs_csv(path)

    assert len(runs) == 2
    assert runs[0].duration_s == 3600
    assert runs[1].distance_m == 5000


def test_load_runs_csv_missing_column(tmp_path):
    csv_text = (
        "started_at,duration_s\n"
        "2026-02-01T10:00:00+00:00,3600\n"
    )
    path = tmp_path / "runs_bad.csv"
    path.write_text(csv_text, encoding="utf-8")

    try:
        load_runs_csv(path)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Missing run CSV columns" in str(e)