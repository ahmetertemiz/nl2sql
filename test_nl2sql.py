"""API anahtarı gerektirmeyen testler. Çalıştır: python -m pytest -q"""
import time
from contextlib import closing
from pathlib import Path

import pytest

import seed_db
from nl2sql import QueryTimeout, UnsafeSQL, get_schema, list_columns, parse_llm_json, response_text, run_sql, validate_sql


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    return seed_db.build(tmp_path_factory.mktemp("db") / "shop.db")


def test_schema_lists_all_tables(db):
    schema = get_schema(db)
    for table in ("customers", "products", "orders", "order_items"):
        assert f"CREATE TABLE {table}" in schema


def test_select_runs(db):
    df = run_sql(db, "SELECT category, COUNT(*) AS adet FROM products GROUP BY category;")
    assert len(df) == 5 and df["adet"].sum() == 14


def test_cte_allowed(db):
    df = run_sql(db, "WITH t AS (SELECT * FROM orders) SELECT COUNT(*) AS n FROM t")
    assert df["n"][0] == 1500


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders",
    "SELECT 1; DELETE FROM orders",
    "WITH t AS (SELECT 1) DELETE FROM orders",
    "UPDATE products SET price = 0",
    "PRAGMA table_info(orders)",
    "",
])
def test_unsafe_sql_rejected(sql):
    with pytest.raises(UnsafeSQL):
        validate_sql(sql)


def test_keyword_inside_string_is_fine(db):
    assert len(run_sql(db, "SELECT * FROM products WHERE name = 'update'")) == 0


# --- İzin listesi (allowlist) ---------------------------------------------
# Senaryo: model müşterinin şehrini ve siparişleri görebilir ama ADINI göremez.
ALLOWED = {"customers": ["id", "city"], "orders": ["id", "customer_id", "status"]}


def test_list_columns(db):
    cols = list_columns(db)
    assert set(cols) == {"customers", "products", "orders", "order_items"}
    assert cols["customers"] == ["id", "name", "city", "signup_date"]


def test_filtered_schema_hides_columns_and_tables(db):
    schema = get_schema(db, ALLOWED)
    assert "city" in schema and "CREATE TABLE orders" in schema
    assert "name" not in schema and "signup_date" not in schema   # gizli sütunlar
    assert "products" not in schema and "order_items" not in schema  # gizli tablolar
    assert "tamamlandi | iptal | iade" in schema                    # yorum korunur
    assert "REFERENCES customers(id)" in schema


def test_allowed_query_runs(db):
    df = run_sql(db, "SELECT c.city, COUNT(*) AS n FROM orders o JOIN customers c "
                     "ON c.id = o.customer_id WHERE o.status = 'iade' GROUP BY c.city", ALLOWED)
    assert df["n"].sum() == 67


def test_count_star_and_case_insensitive_names_allowed(db):
    assert run_sql(db, "SELECT COUNT(*) AS n FROM customers", ALLOWED)["n"][0] == 200
    assert len(run_sql(db, "SELECT CITY FROM Customers", ALLOWED)) == 200


@pytest.mark.parametrize("sql", [
    "SELECT name FROM customers",                                   # gizli sütun
    "SELECT * FROM customers",                                      # * gizli sütunu da açar
    "SELECT c.name AS x FROM customers c",                          # takma adla gizleme
    "WITH t AS (SELECT name FROM customers) SELECT * FROM t",       # CTE içinde
    "SELECT city FROM customers WHERE name LIKE 'A%'",              # yalnızca WHERE'de
    "SELECT COUNT(*) FROM products",                                # gizli tablo
    "SELECT sql FROM sqlite_master",                                # şemayı sızdırma
    "SELECT name FROM pragma_table_info('customers')",              # pragma fonksiyonu
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3) "
    "SELECT name FROM customers",                                   # özyinelemeli CTE kılıfı
])
def test_disallowed_access_rejected(db, sql):
    with pytest.raises(UnsafeSQL, match="izin verilmeyen"):
        run_sql(db, sql, ALLOWED)


def test_recursive_cte_allowed_with_allowlist(db):
    # Meşru kullanım: 1..5 serisi üretmek (ör. tarih serisi) gerçek tablo okumaz
    sql = "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 5) SELECT n FROM r"
    assert list(run_sql(db, sql, ALLOWED)["n"]) == [1, 2, 3, 4, 5]


def test_cte_named_like_hidden_table_reads_only_allowed_data(db):
    # CTE'ye gizli tablonun adı verilse de gerçek products tablosu okunmaz; dönen şehirlerdir
    df = run_sql(db, "WITH products AS (SELECT city AS name FROM customers) "
                     "SELECT DISTINCT name FROM products", ALLOWED)
    assert "İstanbul" in set(df["name"]) and "Kahve Makinesi" not in set(df["name"])


def test_no_allowlist_means_everything(db):
    assert len(run_sql(db, "SELECT name FROM customers")) == 200


# --- Kategorik sütun değerleri ----------------------------------------------
def test_category_values_are_listed(db):
    schema = get_schema(db, {"products": ["id", "category"]}, {"products": ["category"]})
    assert "değerler: 'Aksesuar', 'Elektronik', 'Ev', 'Kitap', 'Spor'" in schema


def test_values_appended_to_existing_comment(db):
    schema = get_schema(db, ALLOWED, {"orders": ["status"]})
    assert "-- tamamlandi | iptal | iade; değerler: 'iade', 'iptal', 'tamamlandi'" in schema


def test_high_cardinality_values_not_sent(db):
    # Ad gibi kişiye özgü bir sütun yanlışlıkla işaretlense bile (200 müşteri, onlarca farklı ad)
    schema = get_schema(db, {"customers": ["id", "name"]}, {"customers": ["name"]})
    assert "gösterilmedi" in schema and "Yılmaz" not in schema


def test_values_only_for_allowed_columns(db):
    # İzin listesinde olmayan bir sütunun değerleri istenirse hiçbir şey gönderilmez
    schema = get_schema(db, {"customers": ["id"]}, {"customers": ["city"]})
    assert "city" not in schema and "İstanbul" not in schema


def test_no_value_columns_means_no_data_in_schema(db):
    schema = get_schema(db, {"customers": ["id", "city"]})
    assert "İstanbul" not in schema and "değerler" not in schema


def test_values_without_allowlist(db):
    # Değerlendirme gibi izin listesi olmayan kullanım: tüm sütunlar + istenen değerler
    schema = get_schema(db, None, {"customers": ["city"]})
    assert "'İstanbul'" in schema and "signup_date" in schema


def test_quote_in_value_is_escaped(tmp_path):
    import sqlite3
    path = tmp_path / "q.db"
    with closing(sqlite3.connect(path)) as con:
        con.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, kind TEXT);"
                          "INSERT INTO t (kind) VALUES ('O''Brien'), ('normal');")
        con.commit()
    assert "'O''Brien'" in get_schema(path, {"t": ["kind"]}, {"t": ["kind"]})


# --- Süre sınırı --------------------------------------------------------------
# 100 milyon satır üreten özyinelemeli sorgu: süre sınırı olmasa dakikalarca sürer.
SLOW_SQL = ("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 100000000) "
            "SELECT COUNT(*) AS n FROM r")


def test_slow_query_is_stopped(db):
    start = time.monotonic()
    with pytest.raises(QueryTimeout, match="0.3 saniyede"):
        run_sql(db, SLOW_SQL, timeout=0.3)
    assert time.monotonic() - start < 2  # gerçekten erken kesildi


def test_slow_query_is_stopped_with_allowlist_too(db):
    with pytest.raises(QueryTimeout):
        run_sql(db, SLOW_SQL, ALLOWED, timeout=0.3)


def test_normal_query_unaffected_by_timeout(db):
    assert run_sql(db, "SELECT COUNT(*) AS n FROM order_items", timeout=0.5)["n"][0] > 0


def test_response_text_skips_thinking_blocks():
    from types import SimpleNamespace as Block
    content = [Block(type="thinking", thinking="..."), Block(type="text", text='{"sql": "SELECT 1"}')]
    assert response_text(content) == '{"sql": "SELECT 1"}'


def test_parse_json_in_code_fence():
    out = parse_llm_json('```json\n{"sql": "SELECT 1", "explanation": "x", "chart": "pie"}\n```')
    assert out["sql"] == "SELECT 1" and out["chart"] == "none"
