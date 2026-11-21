"""Değerlendirme scriptinin testleri — API anahtarı gerektirmez (sahte model kullanır)."""
from pathlib import Path

import pandas as pd
import pytest

import seed_db
from evals.run_evals import (LEVELS, evaluate_one, load_questions, results_match, side_by_side,
                             summarize)
from nl2sql import run_sql


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    return seed_db.build(tmp_path_factory.mktemp("db") / "shop.db")


GOLD = pd.DataFrame({"sehir": ["Ankara", "İzmir"], "ciro": [100.0, 250.5]})


def test_column_names_and_order_do_not_matter():
    pred = pd.DataFrame({"toplam": [250.5, 100], "city": ["İzmir", "Ankara"]})
    assert results_match(GOLD, pred)


def test_extra_column_is_allowed():
    assert results_match(GOLD, GOLD.assign(id=[1, 2]))


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
        return {"sql": sql, "explanation": "", "df": df, "error": None}
    return answer_fn


# --- Soru seti ------------------------------------------------------------------
QUESTIONS = load_questions()


def test_question_set_shape():
    assert len(QUESTIONS) == 20 and len({q["id"] for q in QUESTIONS}) == 20
    assert {q["zorluk"] for q in QUESTIONS} == set(LEVELS)
    assert sum(q["referans_sql"] is None for q in QUESTIONS) == 2   # cevaplanamaz sorular
    kinds = {q["kategori"] for q in QUESTIONS}
    assert {"filtreleme", "gruplama", "join", "tarih", "oran", "cevaplanamaz"} <= kinds


@pytest.mark.parametrize("item", QUESTIONS, ids=[str(q["id"]) for q in QUESTIONS])
def test_gold_sql_passes_itself(db, item):
    assert evaluate_one(item, db, fake_model(item["referans_sql"] or ""))["gecti"]


def test_inner_join_that_drops_unsold_products_fails(db):
    # Satış kalemlerinden başlayan (INNER JOIN) sorgu, o gün hiç satılmayan ürünleri göremez
    item = next(q for q in QUESTIONS if q["id"] == 15)
    gold = run_sql(db, item["referans_sql"])
    assert len(gold) == 4 and (gold["adet"] == 0).sum() == 2
    inner = ("SELECT p.name, SUM(oi.quantity) AS adet FROM order_items oi "
             "JOIN orders o ON o.id = oi.order_id JOIN products p ON p.id = oi.product_id "
             "WHERE o.status = 'tamamlandi' AND o.order_date = '2026-10-02' "
             "GROUP BY p.id HAVING adet < 3")
    assert not evaluate_one(item, db, fake_model(inner))["gecti"]


def test_wrong_sql_and_sql_for_unanswerable_fail(db):
    count_q = {"id": 1, "soru": "?", "referans_sql": "SELECT COUNT(*) FROM customers",
               "zorluk": "kolay", "kategori": "x", "sirali": False}
    assert not evaluate_one(count_q, db, fake_model("SELECT COUNT(*) FROM orders"))["gecti"]
    unanswerable = {**count_q, "referans_sql": None}
    assert not evaluate_one(unanswerable, db, fake_model("SELECT name FROM customers"))["gecti"]


def test_model_exception_counts_as_failure(db):
    def boom(question, db_path, today):
        raise RuntimeError("ağ hatası")
    item = {"id": 1, "soru": "?", "referans_sql": "SELECT 1", "zorluk": "kolay",
            "kategori": "x", "sirali": False}
    result = evaluate_one(item, db, boom)
    assert not result["gecti"] and "ağ hatası" in result["neden"]


def test_summary_by_difficulty():
    rows = [{"gecti": True, "zorluk": "kolay"}, {"gecti": False, "zorluk": "kolay"},
            {"gecti": True, "zorluk": "zor"}]
    s = summarize(rows)
    assert s["toplam"] == {"gecen": 2, "toplam": 3, "yuzde": 66.7}
    assert s["zorluk"]["kolay"]["yuzde"] == 50.0 and s["zorluk"]["orta"]["toplam"] == 0


def test_side_by_side_shows_both_queries():
    text = side_by_side("select a from t", "select b from t")
    assert "ÜRETİLEN" in text and "REFERANS" in text
    assert "SELECT a" in text and "SELECT b" in text
