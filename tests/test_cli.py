from runwx.main import main

def test_main_cli_smoke(tmp_path, capsys):
    # run demo mode without DB
    main([])
    out = capsys.readouterr().out
    assert "Enriched:" in out


def test_main_cli_quiet_suppresses_stdout(capsys):
    main(["run", "--quiet"])
    out = capsys.readouterr().out
    assert out == ""
