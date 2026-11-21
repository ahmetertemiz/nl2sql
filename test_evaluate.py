"""Değerlendirme scriptinin testleri — API anahtarı gerektirmez (sahte model kullanır)."""
import json
from pathlib import Path

import pandas as pd
import pytest

import seed_db
from evaluate import EVAL_SET, evaluate_one, results_match
from nl2sql import run_sql


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    return seed_db.build(tmp_path_factory.mktemp("db") / "shop.db")


GOLD = pd.DataFrame({"sehir": ["Ankara", "İzmir"], "ciro": [100.0, 250.5]})


def test_column_names_and_order_do_not_matter():
    pred = pd.DataFrame({"toplam": [250.5, 100], "city": ["İzmir", "Ankara"]})
    assert results_match(GOLD, pred)


def test_extra_column_is_allowed():
    pred = GOLD.assign(id=[1, 2])
    assert results_match(GOLD, pred)


def test_tiny_float_difference_is_ignored():
    pred = pd.DataFrame({"sehir": ["Ankara", "İzmir"], "ciro": [100.0000001, 250.5]})
    assert results_match(GOLD, pred)


def test_wrong_value_missing_row_and_missing_column_fail():
    assert not results_match(GOLD, pd.DataFrame({"sehir": ["Ankara", "İzmir"], "ciro": [100.0, 999]}))
    assert not results_match(GOLD, GOLD.head(1))
    assert not results_match(GOLD, GOLD[["sehir"]])


def test_values_swapped_between_rows_fail():
    # Sütunlar tek tek aynı değerleri içeriyor ama satır eşleşmesi yanlış
    pred = pd.DataFrame({"sehir": ["Ankara", "İzmir"], "ciro": [250.5, 100.0]})
    assert not results_match(GOLD, pred)


def test_row_order_matters_only_when_ordered():
    reversed_ = GOLD.iloc[::-1].reset_index(drop=True)
    assert results_match(GOLD, reversed_, ordered=False)
    assert not results_match(GOLD, reversed_, ordered=True)


def fake_model(sql: str):
    """answer() ile aynı biçimde sonuç döndüren, verilen SQL'i 'üreten' sahte model."""
    def answer_fn(question, db_path, today):
        df = run_sql(db_path, sql) if sql else None
        return {"sql": sql, "df": df, "error": None}
    return answer_fn


def test_eval_set_ids_unique_and_gold_passes_itself(db):
    items = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    assert len(items) == 21 and len({i["id"] for i in items}) == len(items)
    for item in items:
        result = evaluate_one(item, db, fake_model(item["gold_sql"] or ""))
        assert result["passed"], item["id"]


def test_inner_join_that_drops_unsold_products_fails_q21(db):
    # Satış kalemlerinden başlayan (INNER JOIN) sorgu, o gün hiç satılmayan ürünleri göremez
    item = next(i for i in json.loads(EVAL_SET.read_text(encoding="utf-8")) if i["id"] == 21)
    gold = run_sql(db, item["gold_sql"])
    assert len(gold) == 4 and (gold["satis_adedi"] == 0).sum() == 2
    inner = ("SELECT p.name, SUM(oi.quantity) AS adet FROM order_items oi "
             "JOIN orders o ON o.id = oi.order_id JOIN products p ON p.id = oi.product_id "
             "WHERE o.status = 'tamamlandi' AND o.order_date = '2026-10-02' "
             "GROUP BY p.id HAVING adet < 3")
    assert len(run_sql(db, inner)) == 2
    assert not evaluate_one(item, db, fake_model(inner))["passed"]


def test_wrong_sql_and_sql_for_unanswerable_fail(db):
    count_q = {"id": 1, "question": "?", "gold_sql": "SELECT COUNT(*) FROM customers", "ordered": False}
    assert not evaluate_one(count_q, db, fake_model("SELECT COUNT(*) FROM orders"))["passed"]
    unanswerable = {"id": 2, "question": "?", "gold_sql": None, "ordered": False}
    assert not evaluate_one(unanswerable, db, fake_model("SELECT name FROM customers"))["passed"]


def test_model_exception_counts_as_failure(db):
    def boom(question, db_path, today):
        raise RuntimeError("ağ hatası")
    item = {"id": 1, "question": "?", "gold_sql": "SELECT 1", "ordered": False}
    result = evaluate_one(item, db, boom)
    assert not result["passed"] and "ağ hatası" in result["reason"]
