from runwx.io_weather import load_weather_csv


def test_load_weather_csv_happy_path(tmp_path):
    csv_text = (
        "observed_at,temp_c,wind_mps,precipitation_mm\n"
        "2026-02-01T10:20:00+00:00,6.5,4.2,0.0\n"
        "2026-02-01T11:50:00+00:00,7.1,3.8,0.2\n"
    )
    path = tmp_path / "weather.csv"
    path.write_text(csv_text, encoding="utf-8")

    obs = load_weather_csv(path)

    assert len(obs) == 2
    assert obs[0].temp_c == 6.5
    assert obs[1].precipitation_mm == 0.2


def test_load_weather_csv_invalid_row(tmp_path):
    csv_text = (
        "observed_at,temp_c,wind_mps,precipitation_mm\n"
        "not-a-date,6.5,4.2,0.0\n"
    )
    path = tmp_path / "weather_bad.csv"
    path.write_text(csv_text, encoding="utf-8")

    try:
        load_weather_csv(path)
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "Invalid weather CSV row" in str(e)