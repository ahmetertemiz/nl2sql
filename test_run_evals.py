"""Değerlendirme scriptinin testleri — API anahtarı gerektirmez (sahte model kullanır)."""
from pathlib import Path

import pandas as pd
import pytest

import seed_db
from evals.run_evals import (LEVELS, evaluate_one, evaluate_repeated, load_questions,
                             results_match, side_by_side, summarize)
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


HOLDOUT = load_questions(Path(__file__).parent / "evals" / "holdout.yaml")


def test_holdout_shape():
    assert len(HOLDOUT) == 20 and len({q["id"] for q in HOLDOUT}) == 20
    assert not {q["id"] for q in HOLDOUT} & {q["id"] for q in QUESTIONS}  # id'ler çakışmasın
    assert sum(q["referans_sql"] is None for q in HOLDOUT) == 3
    assert {"pencere", "ayni-ad", "iki-adim", "belirsiz", "yazim-hatasi"} <= {q["kategori"] for q in HOLDOUT}


HOLDOUT_V1_FINGERPRINT = "d6e6f7f17ff463e5ab7fa5927d14fab25e6f10a8563e37772201c8d7e308433d"


HOLDOUT_V2 = load_questions(Path(__file__).parent / "evals" / "holdout_v2.yaml")


def test_holdout_v2_ids_and_gold(db):
    # Şablon boş başlar; sorular eklendikçe aynı kurallar geçerli
    assert isinstance(HOLDOUT_V2, list)
    ids = [q["id"] for q in HOLDOUT_V2]
    assert len(ids) == len(set(ids)) and all(i >= 201 for i in ids)
    for item in HOLDOUT_V2:
        assert evaluate_one(item, db, fake_model(item["referans_sql"] or ""))["gecti"], item["id"]


def test_holdout_v1_is_frozen():
    # Donduruldu (2026-11-21): soru, referans veya alan değişirse bu parmak izi tutmaz.
    # Yorum satırları (#) parmak izine girmez; not eklemek serbest.
    import hashlib
    import json
    digest = hashlib.sha256(json.dumps(HOLDOUT, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert digest == HOLDOUT_V1_FINGERPRINT, "holdout.yaml v1 donduruldu; yeni sorular holdout_v2.yaml'a"


@pytest.mark.parametrize("item", HOLDOUT, ids=[str(q["id"]) for q in HOLDOUT])
def test_holdout_gold_sql_passes_itself(db, item):
    assert evaluate_one(item, db, fake_model(item["referans_sql"] or ""))["gecti"]


def test_grouping_by_name_fails_same_name_questions(db):
    # Aynı adı taşıyan müşteriler: ada göre gruplamak / saymak yanlış cevap verir
    q108 = next(q for q in HOLDOUT if q["id"] == 108)
    by_name = ("SELECT c.name, COUNT(*) AS n FROM orders o JOIN customers c ON c.id = o.customer_id "
               "GROUP BY c.name ORDER BY n DESC LIMIT 1")
    assert not evaluate_one(q108, db, fake_model(by_name))["gecti"]
    q109 = next(q for q in HOLDOUT if q["id"] == 109)
    distinct_name = ("SELECT COUNT(DISTINCT c.name) FROM orders o JOIN customers c "
                     "ON c.id = o.customer_id WHERE o.status = 'iade'")
    assert not evaluate_one(q109, db, fake_model(distinct_name))["gecti"]


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


@pytest.mark.parametrize("wrong_sql", [
    # LEFT JOIN + tarih filtresi WHERE'de: eşleşmeyen satırların tarihi NULL, hepsi elenir -> 0
    "SELECT COUNT(*) FROM customers c LEFT JOIN orders o ON o.customer_id = c.id "
    "WHERE o.id IS NULL AND strftime('%Y-%m', o.order_date) = '2026-10'",
    # Ters mantık: o ay sipariş VERENLER -> 119
    "SELECT COUNT(DISTINCT customer_id) FROM orders WHERE strftime('%Y-%m', order_date) = '2026-10'",
    # Yalnızca tamamlanan siparişler sayılmış (soru "durum önemli değil" diyor) -> 86
    "SELECT COUNT(*) FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o "
    "WHERE o.customer_id = c.id AND strftime('%Y-%m', o.order_date) = '2026-10' "
    "AND o.status = 'tamamlandi')",
], ids=["filtre-WHERE'de", "ters-mantik", "yalnizca-tamamlanan"])
def test_common_mistakes_fail_q9(db, wrong_sql):
    item = next(q for q in QUESTIONS if q["id"] == 9)
    assert run_sql(db, item["referans_sql"]).iloc[0, 0] == 81
    assert not evaluate_one(item, db, fake_model(wrong_sql))["gecti"]


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


def test_summary_by_difficulty_and_unstable():
    records = [{"id": 1, "zorluk": "kolay", "gecen": 3, "kosu": 3, "kararsiz": False},
               {"id": 2, "zorluk": "kolay", "gecen": 1, "kosu": 3, "kararsiz": True},
               {"id": 3, "zorluk": "zor", "gecen": 0, "kosu": 3, "kararsiz": False}]
    s = summarize(records)
    assert s["toplam"] == {"gecen": 4, "toplam": 9, "yuzde": 44.4}
    assert s["zorluk"]["kolay"] == {"gecen": 4, "toplam": 6, "yuzde": 66.7}
    assert s["zorluk"]["orta"]["toplam"] == 0
    assert s["kararsiz"] == [2] and s["hep_kalan"] == [3]


def test_assumption_stats():
    records = [  # beklenmeyen: 3 deneme hep boş + 3 denemede 1 dolu -> 5/6 boş
        {"id": 1, "varsayim_beklenir": False, "varsayim_dolu": [False, False, False], "varsayim_tutarsiz": False},
        {"id": 2, "varsayim_beklenir": False, "varsayim_dolu": [True, False, False], "varsayim_tutarsiz": True},
        # beklenen: 3 denemenin 2'si dolu -> 2/3 dolu
        {"id": 3, "varsayim_beklenir": True, "varsayim_dolu": [True, True, False], "varsayim_tutarsiz": True},
        {"id": 4, "varsayim_beklenir": None, "varsayim_dolu": [True], "varsayim_tutarsiz": False},  # etiketsiz
    ]
    from evals.run_evals import assumption_stats
    s = assumption_stats(records)
    assert s["bos_beklenmeyende"] == {"sayi": 5, "toplam": 6, "yuzde": 83.3}
    assert s["dolu_beklenende"] == {"sayi": 2, "toplam": 3, "yuzde": 66.7}
    assert s["tutarsiz"] == [2, 3]


def test_assumption_stats_none_without_labels():
    from evals.run_evals import assumption_stats
    assert assumption_stats([{"id": 1, "varsayim_dolu": [True]}]) is None


def test_repeated_run_records_assumption_flags(db):
    item = {"id": 1, "soru": "?", "referans_sql": "SELECT 1", "zorluk": "kolay", "kategori": "x",
            "sirali": False, "varsayim_beklenir": False}
    lists = iter([[], ["gereksiz"], []])

    def model(question, db_path, today):
        return {"sql": "SELECT 1", "explanation": "", "assumptions": next(lists),
                "df": run_sql(db_path, "SELECT 1"), "error": None}

    r = evaluate_repeated(item, db, runs=3, answer_fn=model)
    assert r["varsayim_dolu"] == [False, True, False] and r["varsayim_tutarsiz"]


def test_every_question_has_assumption_label():
    assert all(isinstance(q.get("varsayim_beklenir"), bool) for q in QUESTIONS)
    assert not any(q["varsayim_beklenir"] for q in QUESTIONS if q["referans_sql"] is None)


# --- Göreli tolerans --------------------------------------------------------------
def test_rounded_correct_answer_passes():
    # 14.917163 doğru cevap; model ROUND(..., 1) ile 14.9 döndürürse yine doğru sayılmalı
    gold = pd.DataFrame({"buyume": [14.917163]})
    assert results_match(gold, pd.DataFrame({"x": [14.9]}))
    assert results_match(gold, pd.DataFrame({"x": [14.92]}))
    assert not results_match(gold, pd.DataFrame({"x": [15.1]}))   # %1.2 fark: yanlış


def test_rounded_rows_with_text_still_match_unordered():
    gold = pd.DataFrame({"ay": ["2026-09", "2026-10"], "ciro": [1174815.2, 1350064.3]})
    pred = pd.DataFrame({"ay": ["2026-10", "2026-09"], "ciro": [1350064.0, 1174815.0]})  # ROUND(..., 0)
    assert results_match(gold, pred)


def test_integer_counts_must_be_exact():
    # Sayımlarda tolerans yok: 1093 yerine 1090 yanlış (fark %0.3 olsa da)
    gold = pd.DataFrame({"n": [1093, 407]})
    assert not results_match(gold, pd.DataFrame({"n": [1090, 407]}))
    assert results_match(gold, pd.DataFrame({"n": [407.0, 1093.0]}))


def test_rounded_q105_passes_end_to_end(db):
    item = next(q for q in HOLDOUT if q["id"] == 105)
    rounded = ("WITH m AS (SELECT strftime('%Y-%m', o.order_date) AS ay, "
               "SUM(oi.quantity * oi.unit_price) AS ciro FROM orders o JOIN order_items oi "
               "ON oi.order_id = o.id WHERE o.status = 'tamamlandi' GROUP BY ay) "
               "SELECT ROUND(100.0 * (e.ciro - s.ciro) / s.ciro, 1) AS buyume "
               "FROM m e, m s WHERE e.ay = '2026-10' AND s.ay = '2026-09'")
    assert run_sql(db, rounded).iloc[0, 0] == 14.9
    assert evaluate_one(item, db, fake_model(rounded))["gecti"]


# --- kabul_edilen ve ilk_satir ------------------------------------------------------
BASKET = {"id": 1, "soru": "ortalama sepet?", "zorluk": "orta", "kategori": "belirsiz", "sirali": False,
          "referans_sql": "SELECT AVG(a) FROM (SELECT SUM(quantity) a FROM order_items GROUP BY order_id)"}
COMPLETED_BASKET = ("SELECT AVG(a) FROM (SELECT SUM(oi.quantity) a FROM orders o JOIN order_items oi "
                    "ON oi.order_id = o.id WHERE o.status = 'tamamlandi' GROUP BY o.id)")


def test_alternative_reference_accepts_other_interpretation(db):
    assert not evaluate_one(BASKET, db, fake_model(COMPLETED_BASKET))["gecti"]   # alan yokken kalır
    item = {**BASKET, "kabul_edilen": [COMPLETED_BASKET]}
    r = evaluate_one(item, db, fake_model(COMPLETED_BASKET))
    assert r["gecti"] and r["eslesme"] == "kabul_edilen[0]"
    assert evaluate_one(item, db, fake_model(BASKET["referans_sql"]))["eslesme"] == "referans"


def test_alternative_reference_still_rejects_wrong_answer(db):
    item = {**BASKET, "kabul_edilen": [COMPLETED_BASKET]}
    wrong = "SELECT AVG(quantity) FROM order_items"            # kalem başına, sepet değil
    assert not evaluate_one(item, db, fake_model(wrong))["gecti"]


TOP_MONTH = {"id": 2, "soru": "masa lambası en çok hangi ay?", "zorluk": "orta", "kategori": "x",
             "sirali": False,
             "referans_sql": "SELECT strftime('%Y-%m', o.order_date) ay, SUM(oi.quantity) n "
                             "FROM order_items oi JOIN orders o ON o.id = oi.order_id "
                             "WHERE oi.product_id = 10 AND o.status = 'tamamlandi' "
                             "GROUP BY ay ORDER BY n DESC LIMIT 1"}
ALL_MONTHS = TOP_MONTH["referans_sql"].replace(" LIMIT 1", "")
ALL_MONTHS_WRONG_ORDER = ALL_MONTHS.replace("ORDER BY n DESC", "ORDER BY n ASC")


def test_first_row_accepts_full_sorted_list(db):
    assert not evaluate_one(TOP_MONTH, db, fake_model(ALL_MONTHS))["gecti"]       # alan yokken kalır
    item = {**TOP_MONTH, "ilk_satir": True}
    r = evaluate_one(item, db, fake_model(ALL_MONTHS))
    assert r["gecti"] and r["eslesme"] == "referans (ilk satır)"


def test_first_row_rejects_list_with_wrong_first_row(db):
    item = {**TOP_MONTH, "ilk_satir": True}
    assert not evaluate_one(item, db, fake_model(ALL_MONTHS_WRONG_ORDER))["gecti"]


def test_first_row_only_applies_to_single_row_gold(db):
    # Referans birden çok satır döndürüyorsa ilk_satir hiçbir şeyi gevşetmez
    item = {**TOP_MONTH, "referans_sql": ALL_MONTHS, "ilk_satir": True}
    assert not evaluate_one(item, db, fake_model(ALL_MONTHS + " LIMIT 1"))["gecti"]


# --- Tekrarlı koşu ----------------------------------------------------------------
def test_repeated_runs_detect_unstable_question(db):
    item = {"id": 1, "soru": "?", "referans_sql": "SELECT COUNT(*) FROM customers",
            "zorluk": "kolay", "kategori": "x", "sirali": False}
    answers = iter(["SELECT COUNT(*) FROM customers", "SELECT COUNT(*) FROM orders",
                    "SELECT COUNT(*) FROM customers"])

    def flaky(question, db_path, today):  # her çağrıda sıradaki SQL'i "üretir"
        return fake_model(next(answers))(question, db_path, today)

    r = evaluate_repeated(item, db, runs=3, answer_fn=flaky)
    assert r["gecen"] == 2 and r["kosu"] == 3 and r["kararsiz"]
    assert [a["gecti"] for a in r["denemeler"]] == [True, False, True]


def test_side_by_side_shows_both_queries():
    text = side_by_side("select a from t", "select b from t")
    assert "ÜRETİLEN" in text and "REFERANS" in text
    assert "SELECT a" in text and "SELECT b" in text


def test_each_set_uses_its_own_database():
    from evals import run_evals
    import seed_db
    assert run_evals.db_for("questions") == seed_db.DB_PATHS["tr"]
    assert run_evals.db_for("holdout_v2") == seed_db.DB_PATHS["tr"]
    assert run_evals.db_for("questions_en") == seed_db.DB_PATHS["en"]


def test_english_set_mirrors_turkish_set():
    from evals import run_evals
    tr = run_evals.load_questions(run_evals.SETS["questions"])
    en = run_evals.load_questions(run_evals.SETS["questions_en"])
    assert [q["id"] for q in en] == [q["id"] for q in tr]
    for a, b in zip(tr, en):
        for key in ("zorluk", "kategori", "sirali", "varsayim_beklenir"):
            assert a.get(key) == b.get(key), (a["id"], key)
        assert (a["referans_sql"] is None) == (b["referans_sql"] is None)
        assert "tamamlandi" not in (b["referans_sql"] or "")


# --- PostgreSQL: referans SQL'ler ve --postgres ----------------------------------------------

def test_references_pick_postgres_fields_only_on_postgres():
    from evals.run_evals import references
    item = {"referans_sql": "S", "referans_sql_postgres": "P", "kabul_edilen": ["A"]}
    assert references(item) == [("referans", "S"), ("kabul_edilen[0]", "A")]
    assert references(item, "postgres") == [("referans", "P"), ("kabul_edilen[0]", "A")]
    assert references({"referans_sql": "S"}, "postgres") == [("referans", "S")]   # alan yoksa aynısı


def test_every_questions_reference_gives_same_result_on_postgres(pg_url, tmp_path):
    """questions.yaml: her referans (ve kabul_edilen) PostgreSQL'de SQLite ile aynı sonucu vermeli."""
    from db import Database
    from evals.run_evals import QUESTIONS, load_questions, references, results_match
    from nl2sql import run_sql

    lite = seed_db.build(tmp_path / "shop.db")
    pg = Database.from_url(pg_url)
    checked = 0
    for item in load_questions(QUESTIONS):
        if item["referans_sql"] is None:
            continue
        for (label, lite_sql), (_, pg_sql) in zip(references(item), references(item, "postgres")):
            gold, got = run_sql(lite, lite_sql), run_sql(pg, pg_sql)
            assert results_match(gold, got, item["sirali"]), (item["id"], label)
            checked += 1
    assert checked >= 18


def test_postgres_numeric_comes_back_as_float(pg_url):
    from db import Database
    from nl2sql import run_sql
    df = run_sql(Database.from_url(pg_url), "SELECT category, SUM(price) AS toplam FROM products GROUP BY category")
    assert df["toplam"].dtype == "float64"
