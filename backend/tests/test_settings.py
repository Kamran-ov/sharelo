import pytest

from sharelo.dburl import parse_database_url


def test_database_url_is_parsed():
    cfg = parse_database_url("postgres://me:p%40ss@example.test:5433/mydb")
    assert (cfg["NAME"], cfg["USER"], cfg["PASSWORD"], cfg["HOST"], cfg["PORT"]) == (
        "mydb",
        "me",
        "p@ss",
        "example.test",
        "5433",
    )
    assert cfg["ENGINE"] == "django.db.backends.postgresql"


def test_database_url_rejects_non_postgres_scheme():
    with pytest.raises(ValueError):
        parse_database_url("sqlite:///x")
