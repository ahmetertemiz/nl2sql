"""Arayüz testleri: model yalnızca Gönder'e (veya örnek soruya) basılınca çağrılmalı.

Gerçek model çağrısı yapılmaz: nl2sql.answer sahte bir fonksiyonla değiştirilir
ve kaç kez çağrıldığı sayılır. API anahtarı gerektirmez.
"""
import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import nl2sql


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake_answer(question, db_path, today, allowed=None, value_columns=None, **_):
        log.append({"question": question, "allowed": allowed, "value_columns": value_columns})
        return {"sql": "SELECT 1 AS n", "explanation": "sahte", "chart": "none", "x": None, "y": None,
                "df": pd.DataFrame({"n": [1]}), "error": None}

    monkeypatch.setattr(nl2sql, "answer", fake_answer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    return log


def open_app() -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.multiselect(key="cols_customers").set_value(["id", "city"]).run()
    return at


def submit_button(at: AppTest):
    return next(b for b in at.button if b.label == "Gönder")


def test_typing_does_not_call_model(calls):
    at = open_app()
    at.text_input(key="question").input("İstanbul'da kaç müşteri var?").run()
    assert calls == []


def test_submit_calls_model_once(calls):
    at = open_app()
    at.text_input(key="question").input("İstanbul'da kaç müşteri var?")
    submit_button(at).click().run()
    assert len(calls) == 1 and calls[0]["allowed"] == {"customers": ["id", "city"]}
    assert len(at.dataframe) == 1 and not at.exception


def test_sidebar_change_does_not_call_model_and_marks_result_stale(calls):
    at = open_app()
    at.text_input(key="question").input("İstanbul'da kaç müşteri var?")
    submit_button(at).click().run()
    assert not any("önceki" in w.value for w in at.warning)

    at.multiselect(key="value_cols").set_value(["customers.city"]).run()
    assert len(calls) == 1                                   # yeniden çağrılmadı
    assert any("önceki soru veya ayarlarla" in w.value for w in at.warning)
    assert len(at.dataframe) == 1                            # eski sonuç hâlâ görünür

    submit_button(at).click().run()                          # yeniden gönderince güncel ayarlar gider
    assert len(calls) == 2 and calls[1]["value_columns"] == {"customers": ["city"]}
    assert not any("önceki" in w.value for w in at.warning)


def test_chart_is_drawn_with_altair_in_sql_order(monkeypatch):
    df = pd.DataFrame({"urun": ["Powerbank", "Akıllı Saat"], "adet": [87, 62]})
    monkeypatch.setattr(nl2sql, "answer", lambda *a, **k: {
        "sql": "SELECT 1", "explanation": "", "chart": "bar", "x": "urun", "y": "adet",
        "df": df, "error": None})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = open_app()
    at.text_input(key="question").input("En çok satanlar?")
    submit_button(at).click().run()
    assert not at.exception
    charts = at.get("vega_lite_chart")
    assert len(charts) == 1
    spec = json.loads(charts[0].proto.spec)
    assert spec["encoding"]["x"]["sort"] is None   # alfabetik değil, SQL sırası


def test_sql_shown_formatted_but_run_unchanged(monkeypatch):
    raw = "select city, count(*) as n from customers group by city"
    seen = []

    def fake_answer(question, db_path, today, allowed=None, value_columns=None, **_):
        df = nl2sql.run_sql(db_path, raw, allowed)   # çalıştırılan: modelin ham metni
        seen.append(raw)
        return {"sql": raw, "explanation": "", "chart": "none", "x": None, "y": None,
                "df": df, "error": None}

    monkeypatch.setattr(nl2sql, "answer", fake_answer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = open_app()
    at.text_input(key="question").input("Şehirlere göre müşteri?")
    submit_button(at).click().run()
    shown = at.main.code[0].value   # kenar çubuğundaki şema da bir kod bloğu; ana alandakini al
    assert shown.startswith("SELECT city,") and "\nFROM customers" in shown
    assert seen == [raw]


@pytest.fixture
def comments(monkeypatch, calls):
    log = []

    def fake_interpret(question, sql, df, **_):
        log.append({"question": question, "sql": sql, "rows": len(df)})
        return "Sahte yorum: tek satır var."

    monkeypatch.setattr(nl2sql, "interpret_result", fake_interpret)
    return log


def asked(at: AppTest) -> AppTest:
    at.text_input(key="question").input("İstanbul'da kaç müşteri var?")
    submit_button(at).click().run()
    return at


def test_interpret_off_by_default_no_button_no_call(calls, comments):
    at = asked(open_app())
    assert not any(b.label == "Yorumla" for b in at.button)
    assert comments == []


def test_interpret_on_shows_warning_and_button_and_calls_once(calls, comments):
    at = open_app()
    at.toggle(key="interpret_on").set_value(True).run()
    assert any("modele gönderilir" in w.value for w in at.sidebar.warning)
    at = asked(at)
    assert comments == []                                    # düğmeye basılmadan çağrı yok
    next(b for b in at.button if b.label == "Yorumla").click().run()
    assert len(comments) == 1 and comments[0]["question"] == "İstanbul'da kaç müşteri var?"
    assert len(calls) == 1                                   # sorgu yeniden çalışmadı
    assert any("Sahte yorum" in s.value for s in at.success)
    assert next(b for b in at.button if b.label == "Yorumla").disabled  # ikinci kez ücret yok


def test_interpret_error_is_shown_and_retry_allowed(calls, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("ağ hatası")
    monkeypatch.setattr(nl2sql, "interpret_result", broken)
    at = open_app()
    at.toggle(key="interpret_on").set_value(True).run()
    at = asked(at)
    next(b for b in at.button if b.label == "Yorumla").click().run()
    assert any("ağ hatası" in e.value for e in at.error)
    assert not next(b for b in at.button if b.label == "Yorumla").disabled


def test_new_question_clears_old_comment(calls, comments):
    at = open_app()
    at.toggle(key="interpret_on").set_value(True).run()
    at = asked(at)
    next(b for b in at.button if b.label == "Yorumla").click().run()
    at.text_input(key="question").input("Başka bir soru")
    submit_button(at).click().run()
    assert not any("Sahte yorum" in s.value for s in at.success)
    assert not next(b for b in at.button if b.label == "Yorumla").disabled


def test_example_button_calls_model(calls):
    at = open_app()
    example = next(b for b in at.button if b.label.startswith("Aylara"))
    example.click().run()
    assert [c["question"] for c in calls] == ["Aylara göre toplam ciro nasıl değişti?"]
    assert at.text_input(key="question").value == "Aylara göre toplam ciro nasıl değişti?"
