"""PostgreSQL güvenlik katmanları. Sunucu başlatılamazsa hepsi ATLANIR (bkz. conftest.py).

test_nl2sql.py'deki gizli sütun testlerinin hepsi burada PostgreSQL'de de koşar; ek olarak
sistem tabloları, fonksiyonlar, salt-okunur transaction, süre sınırı, EXPLAIN katmanı ve
yazma yetkisi uyarısı denetlenir.
"""
import time

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import nl2sql
from db import Database, QueryError
from errors import QueryTimeout, UnsafeSQL
from nl2sql import check_access, get_schema, list_columns, run_sql, validate_sql
from test_nl2sql import (ALLOWED, ALLOWED_ACCESS, FULL_CUSTOMERS, HIDDEN_ACCESS,
                         SLOW_SQL)

DISALLOWED = [  # test_nl2sql.test_disallowed_access_rejected ile aynı liste
    "SELECT name FROM customers",
    "SELECT * FROM customers",
    "SELECT c.name AS x FROM customers c",
    "WITH t AS (SELECT name FROM customers) SELECT * FROM t",
    "SELECT city FROM customers WHERE name LIKE 'A%'",
    "SELECT COUNT(*) FROM products",
    "SELECT sql FROM sqlite_master",
    "SELECT name FROM pragma_table_info('customers')",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT name FROM customers",
]

SYSTEM_ACCESS = {
    "pg_catalog tablosu": "SELECT usename FROM pg_catalog.pg_user",
    "nitelendirilmemiş katalog": "SELECT rolname FROM pg_roles",
    "pg_tables": "SELECT tablename FROM pg_tables",
    "information_schema": "SELECT column_name FROM information_schema.columns",
    "başka şema": "SELECT city FROM other_schema.customers",
    "katalog.şema.tablo": "SELECT city FROM otherdb.public.customers",
    "alt sorguda katalog": "SELECT city FROM customers WHERE id IN (SELECT oid::int FROM pg_class)",
    "dosya okuma": "SELECT pg_read_file('postgresql.conf')",
    "ayar okuma": "SELECT current_setting('data_directory')",
    "ayar değiştirme": "SELECT set_config('statement_timeout', '0', false)",
    "sürüm": "SELECT version()",
    "kullanıcı adı": "SELECT current_user",
    "veritabanı adı": "SELECT current_database()",
    "başka sorgu çalıştırma": "SELECT query_to_xml('select * from pg_user', true, true, '')",
    "bekletme": "SELECT pg_sleep(10)",
}


@pytest.fixture(scope="module")
def pg(pg_url):
    return Database.from_url(pg_url)


@pytest.fixture(scope="module")
def pg_readonly_url(pg_server, pg_url):
    """Yalnızca SELECT yetkisi olan bir kullanıcıyla aynı veritabanının adresi."""
    import psycopg
    from sqlalchemy.engine import make_url

    with psycopg.connect(pg_url, autocommit=True) as admin:
        admin.execute("DROP ROLE IF EXISTS nl2sql_ro")
        admin.execute("CREATE ROLE nl2sql_ro LOGIN PASSWORD 'ro_pass_123'")
        admin.execute("GRANT USAGE ON SCHEMA public TO nl2sql_ro")
        admin.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl2sql_ro")
        admin.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    url = make_url(pg_url).set(username="nl2sql_ro", password="ro_pass_123")
    yield url.render_as_string(hide_password=False)
    with psycopg.connect(pg_url, autocommit=True) as admin:
        admin.execute("DROP OWNED BY nl2sql_ro")
        admin.execute("DROP ROLE IF EXISTS nl2sql_ro")


# --- test_nl2sql.py'deki gizli sütun testleri, PostgreSQL'de ---------------------------------

def test_pg_filtered_schema_hides_columns_and_tables(pg):
    schema = get_schema(pg, ALLOWED)
    assert "city" in schema and "CREATE TABLE orders" in schema
    assert "name" not in schema and "signup_date" not in schema
    assert "products" not in schema and "order_items" not in schema
    assert "tamamlandi | iptal | iade" in schema
    assert "REFERENCES customers(id)" in schema


def test_pg_allowed_query_runs(pg):
    df = run_sql(pg, "SELECT c.city, COUNT(*) AS n FROM orders o JOIN customers c "
                     "ON c.id = o.customer_id WHERE o.status = 'iade' GROUP BY c.city", ALLOWED)
    assert df["n"].sum() == 67


def test_pg_count_star_and_case_insensitive_names_allowed(pg):
    assert run_sql(pg, "SELECT COUNT(*) AS n FROM customers", ALLOWED)["n"][0] == 200
    assert len(run_sql(pg, "SELECT CITY FROM Customers", ALLOWED)) == 200


@pytest.mark.parametrize("sql", DISALLOWED)
def test_pg_disallowed_access_rejected(pg, sql):
    with pytest.raises(UnsafeSQL, match="not allowed"):
        run_sql(pg, sql, ALLOWED)


@pytest.mark.parametrize("sql", HIDDEN_ACCESS.values(), ids=HIDDEN_ACCESS.keys())
def test_pg_parser_rejects_hidden_access(pg, sql):
    with pytest.raises(UnsafeSQL, match="not allowed"):
        check_access(sql, ALLOWED, list_columns(pg), dialect="postgres", db_schema="public")


def test_pg_parser_names_the_hidden_column(pg):
    cols = list_columns(pg)
    with pytest.raises(UnsafeSQL, match=r"customers\.name"):
        check_access("SELECT c.name AS x FROM customers c", ALLOWED, cols, "postgres", "public")
    with pytest.raises(UnsafeSQL, match=r"\* cannot be used"):
        check_access("SELECT * FROM customers", ALLOWED, cols, "postgres", "public")


@pytest.mark.parametrize("sql", ALLOWED_ACCESS.values(), ids=ALLOWED_ACCESS.keys())
def test_pg_same_shapes_with_allowed_columns_run(pg, sql):
    allowed = FULL_CUSTOMERS if "*" in sql else ALLOWED
    check_access(sql, allowed, list_columns(pg), dialect="postgres", db_schema="public")
    assert len(run_sql(pg, sql, allowed)) > 0


def test_pg_star_on_table_with_hidden_column_rejected_even_if_others_open(pg):
    with pytest.raises(UnsafeSQL):
        run_sql(pg, "SELECT o.* FROM orders o", FULL_CUSTOMERS)
    assert len(run_sql(pg, "SELECT c.* FROM customers c JOIN orders o ON o.customer_id = c.id",
                       FULL_CUSTOMERS)) > 0


def test_pg_recursive_cte_allowed_with_allowlist(pg):
    sql = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 5) SELECT n FROM r"
    assert list(run_sql(pg, sql, ALLOWED)["n"]) == [1, 2, 3, 4, 5]


def test_pg_cte_named_like_hidden_table_reads_only_allowed_data(pg):
    df = run_sql(pg, "WITH products AS (SELECT city AS name FROM customers) "
                     "SELECT DISTINCT name FROM products", ALLOWED)
    assert "İstanbul" in set(df["name"]) and "Kahve Makinesi" not in set(df["name"])


def test_pg_values_only_for_allowed_columns(pg):
    schema = get_schema(pg, {"customers": ["id"]}, {"customers": ["city"]})
    assert "city" not in schema and "İstanbul" not in schema
    schema = get_schema(pg, {"customers": ["id", "name"]}, {"customers": ["name"]})
    assert "not shown" in schema and "Yılmaz" not in schema


# --- PostgreSQL'e özgü: sistem tabloları ve fonksiyonlar --------------------------------------

@pytest.mark.parametrize("sql", SYSTEM_ACCESS.values(), ids=SYSTEM_ACCESS.keys())
def test_pg_system_tables_and_functions_rejected(pg, sql):
    with pytest.raises(UnsafeSQL, match="not allowed"):
        run_sql(pg, sql, FULL_CUSTOMERS)


def test_pg_schema_qualified_allowed_table_runs(pg):
    assert len(run_sql(pg, "SELECT city FROM public.customers", ALLOWED)) == 200


def test_pg_safe_functions_run(pg):
    sql = ("SELECT date_trunc('month', o.order_date) AS ay, COUNT(*) AS n, "
           "to_char(MIN(o.order_date), 'YYYY-MM') AS ilk, EXTRACT(YEAR FROM MIN(o.order_date)) AS yil "
           "FROM orders o WHERE o.order_date >= DATE '2026-11-20' - INTERVAL '3 months' GROUP BY 1 ORDER BY 1")
    allowed = {"orders": ["id", "order_date"]}
    assert len(run_sql(pg, sql, allowed)) >= 3


@pytest.mark.parametrize("sql", [
    "SELECT * INTO kopya FROM customers",
    "WITH x AS (DELETE FROM orders RETURNING id) SELECT * FROM x",
    "SELECT 1; TRUNCATE orders",
])
def test_pg_modifying_sql_rejected_before_database(sql):
    with pytest.raises(UnsafeSQL):
        validate_sql(sql, dialect="postgres")


def test_pg_extra_keywords_do_not_affect_sqlite_validation():
    assert validate_sql("SELECT 1 AS into_x, 'copy' AS c") and validate_sql("SELECT lock FROM t")


# --- Veritabanı katmanı: salt-okunur, süre sınırı, EXPLAIN ----------------------------------

def test_pg_transaction_is_read_only(pg):
    with pytest.raises(QueryError, match="read-only"):
        pg._pg_query("INSERT INTO customers VALUES (999, 'x', 'y', DATE '2026-01-01')", 5)
    assert run_sql(pg, "SELECT COUNT(*) AS n FROM customers")["n"][0] == 200


def test_pg_slow_query_is_stopped(pg):
    start = time.monotonic()
    with pytest.raises(QueryTimeout, match="within 0.3 seconds"):
        run_sql(pg, SLOW_SQL, ALLOWED, timeout=0.3)
    assert time.monotonic() - start < 3
    assert run_sql(pg, "SELECT COUNT(*) AS n FROM order_items")["n"][0] > 0  # bağlantı sağlam


def test_pg_explain_layer_alone_rejects_unallowed_table(pg):
    """check_access'i atlayıp doğrudan veritabanı katmanını çağır: plan kontrolü tek başına yakalamalı."""
    with pytest.raises(UnsafeSQL, match="public.products"):
        pg.execute("SELECT COUNT(*) FROM products", ALLOWED, 5, 10)
    with pytest.raises(UnsafeSQL, match="pg_catalog"):
        pg.execute("SELECT rolname FROM pg_roles", None, 5, 10)   # izin listesi yokken bile katalog kapalı
    assert len(pg.execute("SELECT city FROM customers", ALLOWED, 5, 10)) == 10


# --- Yazma yetkisi uyarısı ----------------------------------------------------------------------

def test_superuser_has_write_privileges(pg):
    assert "superuser" in pg.write_privileges()


def test_readonly_user_has_none_and_still_works(pg_readonly_url):
    ro = Database.from_url(pg_readonly_url)
    assert ro.write_privileges() == []
    assert run_sql(ro, "SELECT COUNT(*) AS n FROM customers", ALLOWED)["n"][0] == 200


def _app(monkeypatch, url):
    monkeypatch.setenv("NL2SQL_DATABASE_URL", url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    return at


def test_app_warns_when_user_can_write(monkeypatch, pg_url):
    at = _app(monkeypatch, pg_url)
    assert not at.exception
    assert any("can modify data" in e.value and "superuser" in e.value for e in at.error)
    assert any("own database (postgresql)" in c.value for c in at.caption)
    assert not any(b.label.startswith("Which 5 products") for b in at.button)  # örnek sorular yok


def test_app_no_warning_for_readonly_user_and_question_uses_it(monkeypatch, pg_readonly_url):
    seen = []

    def fake_answer(question, db_path, today, allowed=None, glossary=None, **_):
        seen.append((type(db_path).__name__, allowed, today, glossary))
        df = nl2sql.run_sql(db_path, "SELECT COUNT(*) AS n FROM customers", allowed)
        return {"sql": "SELECT 1", "explanation": "", "chart": "none", "x": None, "y": None,
                "df": df, "error": None}

    monkeypatch.setattr(nl2sql, "answer", fake_answer)
    at = _app(monkeypatch, pg_readonly_url)
    assert not at.exception and not at.error
    at.text_input(key="question").input("How many customers?")
    next(b for b in at.button if b.label == "Send").click().run()
    from datetime import date
    assert seen and seen[0][0] == "Database"
    assert seen[0][2] == date.today().isoformat()      # dış veritabanında gerçek tarih
    assert seen[0][3] == ""                            # NL2SQL_GLOSSARY yok: örnek sözlük gönderilmez
    assert pd.DataFrame(at.dataframe[0].value)["n"][0] == 200


def test_readme_readonly_user_sql_works(pg_url):
    """README'deki salt-okunur kullanıcı SQL'i olduğu gibi çalışmalı ve gerçekten salt-okunur olmalı."""
    import re
    from pathlib import Path

    import psycopg
    from sqlalchemy.engine import make_url

    readme = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")
    section = readme.split("### 1. Create a read-only user (PostgreSQL)", 1)[1]
    sql = re.search(r"```sql\n(.*?)```", section, re.DOTALL).group(1)
    db_name = make_url(pg_url).database
    with psycopg.connect(pg_url, autocommit=True) as admin:
        if admin.execute("SELECT 1 FROM pg_roles WHERE rolname = 'nl2sql_reader'").fetchone():
            admin.execute("DROP OWNED BY nl2sql_reader")  # önceki yarım kalmış çalıştırmadan
            admin.execute("DROP ROLE nl2sql_reader")
        for statement in sql.replace("mydb", db_name).split(";"):
            body = "\n".join(l for l in statement.splitlines() if not l.strip().startswith("--")).strip()
            if body:
                admin.execute(body)
    try:
        url = make_url(pg_url).set(username="nl2sql_reader", password="change-me")
        reader = Database.from_url(url.render_as_string(hide_password=False))
        assert reader.write_privileges() == []
        everything = {"customers": ["id", "name", "city", "signup_date"]}
        assert len(run_sql(reader, "SELECT city FROM customers", everything)) == 200
        with pytest.raises(QueryError, match="permission denied"):   # sütun düzeyinde GRANT
            run_sql(reader, "SELECT name FROM customers", everything)
    finally:
        with psycopg.connect(pg_url, autocommit=True) as admin:
            admin.execute("DROP OWNED BY nl2sql_reader")
            admin.execute("DROP ROLE IF EXISTS nl2sql_reader")
