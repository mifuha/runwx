from runwx.main import greet


def test_greet():
    result = greet("Miha")
    assert result == "Hello, Miha"