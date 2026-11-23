"""Veritabanı katmanı (db.py): örnek veritabanı davranışı değişmedi, bağlantı adresi hiçbir yerde görünmüyor,
PostgreSQL'de şema ve sorgu okuma çalışıyor. PostgreSQL testleri sunucu başlatılamazsa atlanır."""
import json
import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import nl2sql
import seed_db
from db import Database, QueryError
from errors import DatabaseError

GOLDEN = json.loads((Path(__file__).parent / "testdata" / "demo_golden.json").read_text(encoding="utf-8"))

SECRET = "S3cr3tPw_9f"
HOST = "db-host-that-does-not-exist.invalid"
BAD_URL = f"postgresql://report_user:{SECRET}@{HOST}:5432/sales"


# --- Örnek veritabanı: modele giden metin birebir aynı -----------------------------------

@pytest.mark.parametrize("lang", ["tr", "en"])
def test_demo_schema_and_prompt_unchanged(lang):
    """SQLAlchemy katmanına geçmeden önce kaydedilen çıktılarla karşılaştır (testdata/demo_golden.json)."""
    path = seed_db.DB_PATHS[lang]
    if not path.exists():
        seed_db.build(path, lang=lang)
    cols = nl2sql.list_columns(path)
    assert cols == GOLDEN[f"{lang}_columns"]
    assert nl2sql.get_schema(path) == GOLDEN[f"{lang}_none"]
    assert nl2sql.get_schema(path, cols) == GOLDEN[f"{lang}_all"]
    subset = {"customers": ["id", "city"], "orders": ["id", "customer_id", "status"],
              "order_items": ["order_id", "quantity"]}
    values = {"orders": ["status"], "customers": ["city"]}
    assert nl2sql.get_schema(path, subset, values) == GOLDEN[f"{lang}_subset"]
    assert nl2sql.get_schema(path, None, {"products": ["category"]}) == GOLDEN[f"{lang}_values_none_allowed"]


def test_sqlite_url_behaves_like_path(tmp_path):
    path = seed_db.build(tmp_path / "shop.db")
    via_url = Database.from_url(f"sqlite:///{path.as_posix()}")
    assert via_url.kind == "sqlite" and via_url.dialect == "sqlite"
    assert nl2sql.get_schema(via_url) == nl2sql.get_schema(path)
    df = nl2sql.run_sql(via_url, "SELECT COUNT(*) AS n FROM customers", {"customers": ["id"]})
    assert df["n"][0] == 200


def test_from_env_empty_means_demo(monkeypatch):
    monkeypatch.delenv("NL2SQL_DATABASE_URL", raising=False)
    assert Database.from_env() is None
    monkeypatch.setenv("NL2SQL_DATABASE_URL", "   ")
    assert Database.from_env() is None


# --- Bağlantı adresi hiçbir yerde görünmez --------------------------------------------------

def _assert_hidden(text: str):
    for part in (SECRET, HOST, "report_user", BAD_URL):
        assert part not in text


def test_unreachable_server_error_hides_address(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(DatabaseError) as info:
        Database.from_url(BAD_URL)
    exc = info.value
    assert exc.key == "err_db_connect" and exc.__cause__ is None and exc.__suppress_context__
    for lang in ("en", "tr"):
        _assert_hidden(exc.localized(lang))
    _assert_hidden(str(exc) + repr(exc))
    _assert_hidden(caplog.text)


@pytest.mark.parametrize("url, key", [
    (f"not a url {SECRET}", "err_db_url"),
    (f"mysql://report_user:{SECRET}@{HOST}/sales", "err_db_unsupported"),
    (f"sqlite:///{HOST}/{SECRET}.db", "err_db_connect"),
])
def test_bad_urls_hide_address(url, key):
    with pytest.raises(DatabaseError) as info:
        Database.from_url(url)
    assert info.value.key == key
    _assert_hidden(str(info.value) + info.value.localized("tr"))


def test_repr_and_scrub_hide_address():
    db = Database(engine=None, kind="postgresql", secrets=(BAD_URL, SECRET, "report_user", HOST))
    assert repr(db) == "<Database postgresql>"
    msg = db.scrub(f'password authentication failed for user "report_user" at {HOST} ({SECRET})')
    _assert_hidden(msg)
    assert "password authentication failed" in msg


def test_app_shows_generic_error_for_bad_database(monkeypatch):
    monkeypatch.setenv("NL2SQL_DATABASE_URL", BAD_URL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Could not connect to the database" in e.value for e in at.error)
    shown = " ".join(str(getattr(el, "value", "")) for el in
                     [*at.error, *at.markdown, *at.caption, *at.info, *at.title, *at.code, *at.warning])
    _assert_hidden(shown)


# --- PostgreSQL: şema, değer ipuçları, sorgu ---------------------------------------------------

@pytest.fixture(scope="module")
def pg(pg_url):
    return Database.from_url(pg_url)


def test_pg_columns_and_schema(pg):
    assert pg.kind == "postgresql" and pg.dialect == "postgres" and pg.schema == "public"
    assert pg.columns() == GOLDEN["tr_columns"]                # aynı tablo ve sütunlar
    schema = nl2sql.get_schema(pg, {"orders": ["id", "customer_id", "status"], "customers": ["id", "city"]},
                               {"orders": ["status"]})
    assert "CREATE TABLE customers (\n    id INTEGER PRIMARY KEY,\n    city TEXT NOT NULL\n)" in schema
    assert "customer_id INTEGER NOT NULL REFERENCES customers(id)" in schema
    assert "status TEXT NOT NULL  -- tamamlandi | iptal | iade; values: 'iade', 'iptal', 'tamamlandi'" in schema
    assert "name" not in schema and "products" not in schema   # izinsiz tablo ve sütun adı da yok


def test_pg_full_schema_and_types(pg):
    schema = nl2sql.get_schema(pg)
    assert "signup_date DATE NOT NULL" in schema and "price NUMERIC(10, 2) NOT NULL  -- TL" in schema


def test_pg_run_sql_and_query_error_hides_address(pg):
    df = nl2sql.run_sql(pg, "SELECT city, COUNT(*) AS n FROM customers GROUP BY city ORDER BY city",
                        {"customers": ["id", "city"]})
    assert df["n"].sum() == 200
    with pytest.raises(QueryError) as info:
        nl2sql.run_sql(pg, "SELECT nope FROM customers", {"customers": ["id", "city"]})
    assert "nope" in str(info.value) and "[SQL:" not in str(info.value)


def test_pg_like_with_percent_and_colon_literal(pg):
    df = nl2sql.run_sql(pg, "SELECT COUNT(*) AS n FROM customers WHERE name LIKE 'A%' OR city = 'x:y'")
    assert df["n"][0] > 0
