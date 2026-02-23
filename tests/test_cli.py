from runwx.main import main

def test_main_cli_smoke(tmp_path, capsys):
    # run demo mode without DB
    main([])
    out = capsys.readouterr().out
    assert "Enriched:" in out