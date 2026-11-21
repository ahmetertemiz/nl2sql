"""Arayüz testleri: model yalnızca Gönder'e (veya örnek soruya) basılınca çağrılmalı.

Gerçek model çağrısı yapılmaz: nl2sql.answer sahte bir fonksiyonla değiştirilir
ve kaç kez çağrıldığı sayılır. API anahtarı gerektirmez.
"""
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


def test_example_button_calls_model(calls):
    at = open_app()
    example = next(b for b in at.button if b.label.startswith("Aylara"))
    example.click().run()
    assert [c["question"] for c in calls] == ["Aylara göre toplam ciro nasıl değişti?"]
    assert at.text_input(key="question").value == "Aylara göre toplam ciro nasıl değişti?"
