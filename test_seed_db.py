"""İki dilli örnek veri: Türkçe üretim değişmemeli, İngilizce aynı dağılımı taşımalı."""
import hashlib
import sqlite3

import pytest

import seed_db
from nl2sql import build_system_prompt, completed_status

# Türkçe veritabanının tam dökümünün (şema + tüm satırlar) parmak izi. Değişirse evals/
# altındaki referans SQL'lerin beklediği sayılar da değişir: bilerek yapılmadıysa hatadır.
TR_DUMP_SHA256 = "d7c80b2bdc133d12b6c62de87a763eb75b36b5cd28f6cea395f6ded7cdb238b7"


def dump(path) -> list[str]:
    with sqlite3.connect(path) as con:
        return list(con.iterdump())


@pytest.fixture(scope="module")
def dbs(tmp_path_factory):
    d = tmp_path_factory.mktemp("seed")
    return seed_db.build(d / "tr.db", lang="tr"), seed_db.build(d / "en.db", lang="en")


def q(path, sql):
    with sqlite3.connect(path) as con:
        return con.execute(sql).fetchall()


def test_turkish_build_is_unchanged(dbs):
    digest = hashlib.sha256("\n".join(dump(dbs[0])).encode("utf-8")).hexdigest()
    assert digest == TR_DUMP_SHA256


def test_same_structure_in_both_languages(dbs):
    tr, en = dbs
    for sql in ("SELECT id, customer_id, order_date FROM orders",
                "SELECT id, order_id, product_id, quantity FROM order_items",
                "SELECT id, signup_date FROM customers"):
        assert q(tr, sql) == q(en, sql)
    # Durumlar aynı sırayla eşlenir: tamamlandi->completed, iptal->cancelled, iade->returned
    pairs = q(tr, "SELECT status FROM orders ORDER BY id"), q(en, "SELECT status FROM orders ORDER BY id")
    mapping = dict(zip(seed_db.LOCALES["tr"]["statuses"], seed_db.LOCALES["en"]["statuses"]))
    assert [mapping[a[0]] for a in pairs[0]] == [b[0] for b in pairs[1]]


def test_english_content(dbs):
    en = dbs[1]
    assert {r[0] for r in q(en, "SELECT DISTINCT status FROM orders")} == {"completed", "cancelled", "returned"}
    assert {r[0] for r in q(en, "SELECT DISTINCT category FROM products")} == {
        "Electronics", "Sports", "Home", "Books", "Accessories"}
    assert "London" in {r[0] for r in q(en, "SELECT DISTINCT city FROM customers")}
    schema = q(en, "SELECT sql FROM sqlite_master WHERE name = 'products'")[0][0]
    assert "-- USD" in schema


def test_locale_lists_have_equal_lengths():
    tr, en = seed_db.LOCALES["tr"], seed_db.LOCALES["en"]
    for key in ("first", "last", "cities", "products", "statuses"):
        assert len(tr[key]) == len(en[key]), key
    assert [c for _, c, _ in tr["products"]].count("Elektronik") == \
           [c for _, c, _ in en["products"]].count("Electronics")


def test_completed_status_is_read_from_database(dbs, tmp_path):
    assert completed_status(dbs[0]) == "tamamlandi"
    assert completed_status(dbs[1]) == "completed"
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert completed_status(empty) is None


def test_revenue_rule_uses_database_value():
    assert "count only orders with status = 'completed' in revenue" in build_system_prompt("s", "t", "completed")
    assert "status = 'tamamlandi'" in build_system_prompt("s", "t", "tamamlandi")
    no_value = build_system_prompt("s", "t", None)
    assert "count only completed orders in revenue" in no_value and "status = '" not in no_value
