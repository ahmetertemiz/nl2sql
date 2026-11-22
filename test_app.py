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


def open_app(lang: str = "tr") -> AppTest:
    """Eski testler Türkçe metinleri denetler; varsayılan dil (en) ayrı testlerde."""
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["lang"] = lang
    at.run()
    clear_all(at)
    at.multiselect(key="cols_customers").set_value(["id", "city"]).run()
    return at


def clear_all(at: AppTest) -> AppTest:
    """İlk açılışta her şey seçili; testler dar bir izinle başlasın diye önce hepsini kapat."""
    next(b for b in at.sidebar.button if b.label in ("Tümünü kapat", "Clear all")).click().run()
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
    assert not any("yapay zeka" in c.value.lower() for c in at.main.caption)
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
    assert any("Yapay zeka tarafından üretildi; sayıları tabloyla karşılaştır." == c.value
               for c in at.main.caption)
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


def _answer_with(assumptions):
    return lambda *a, **k: {"sql": "SELECT 1", "explanation": "x", "assumptions": assumptions,
                            "chart": "none", "x": None, "y": None,
                            "df": pd.DataFrame({"n": [1]}), "error": None}


def test_assumptions_shown_above_result(monkeypatch):
    monkeypatch.setattr(nl2sql, "answer", _answer_with(["Yalnızca tamamlanan siparişler sayıldı",
                                                        "Kasım dahil alındı"]))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = asked(open_app())
    texts = [m.value for m in at.main.markdown]
    assert "**Varsayımlar**" in texts
    assert "- Yalnızca tamamlanan siparişler sayıldı\n- Kasım dahil alındı" in texts


def test_no_assumptions_no_heading(monkeypatch):
    monkeypatch.setattr(nl2sql, "answer", _answer_with([]))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    at = asked(open_app())
    assert "**Varsayımlar**" not in [m.value for m in at.main.markdown]


def test_example_button_calls_model(calls):
    at = open_app()
    example = next(b for b in at.button if b.label.startswith("Aylara"))
    example.click().run()
    assert [c["question"] for c in calls] == ["Aylara göre toplam ciro nasıl değişti?"]
    assert at.text_input(key="question").value == "Aylara göre toplam ciro nasıl değişti?"


# --- Yayın hazırlığı: sabit demo tarihi, günlük sınır, ziyaretçinin kendi anahtarı ---

@pytest.fixture
def key_calls(monkeypatch):
    """calls gibi, ama today ve api_key de kaydedilir; günlük sayaç her testte sıfırdan başlar."""
    import quota

    log = []

    def fake_answer(question, db_path, today, allowed=None, value_columns=None, api_key=None, **_):
        log.append({"today": today, "api_key": api_key})
        return {"sql": "SELECT 1 AS n", "explanation": "sahte", "chart": "none", "x": None, "y": None,
                "df": pd.DataFrame({"n": [1]}), "error": None}

    monkeypatch.setattr(nl2sql, "answer", fake_answer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    monkeypatch.delenv("NL2SQL_DAILY_LIMIT", raising=False)
    quota.reset()
    yield log
    quota.reset()


def test_today_is_fixed_to_seed_date_not_real_date(key_calls):
    asked(open_app())
    assert key_calls == [{"today": "2026-11-20", "api_key": None}]


def test_daily_limit_blocks_shared_key(key_calls, monkeypatch):
    monkeypatch.setenv("NL2SQL_DAILY_LIMIT", "1")
    at = asked(open_app())
    assert len(key_calls) == 1
    submit_button(at).click().run()                          # ikinci çağrı: hak doldu
    assert len(key_calls) == 1
    assert any("demo hakkı doldu" in w.value for w in at.warning)


def test_own_key_is_passed_and_bypasses_limit(key_calls, monkeypatch):
    monkeypatch.setenv("NL2SQL_DAILY_LIMIT", "1")
    at = asked(open_app())
    at.text_input(key="user_key").input("sk-ant-ziyaretci").run()
    submit_button(at).click().run()
    assert [c["api_key"] for c in key_calls] == [None, "sk-ant-ziyaretci"]
    assert not any("demo hakkı doldu" in w.value for w in at.warning)


def test_no_server_key_asks_for_own_key_then_works(key_calls, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    at = open_app()
    assert any("API anahtarı yok" in e.value for e in at.error)
    at.text_input(key="user_key").input("sk-ant-ziyaretci").run()
    assert not at.error
    asked(at)
    assert key_calls[-1]["api_key"] == "sk-ant-ziyaretci"


def _retrying_answer(log):
    """SQL'i ilk denemede hata veren, ikinci model çağrısı için hak isteyen sahte answer."""
    def fake(question, db_path, today, allow_retry=None, **_):
        retried = allow_retry()
        log.append(retried)
        return {"sql": "SELECT 1 AS n" if retried else "SELECT nope", "explanation": "", "chart": "none",
                "x": None, "y": None, "df": pd.DataFrame({"n": [1]}) if retried else None,
                "error": None if retried else "no such column: nope"}
    return fake


def test_retry_also_uses_daily_quota(key_calls, monkeypatch):
    import quota

    log = []
    monkeypatch.setattr(nl2sql, "answer", _retrying_answer(log))
    monkeypatch.setenv("NL2SQL_DAILY_LIMIT", "2")
    at = asked(open_app())
    assert log == [True]                                     # ilk çağrı + yeniden deneme = 2 hak
    assert not quota.take(2)                                 # hak kalmadı
    quota.reset()


def test_retry_skipped_when_quota_runs_out(key_calls, monkeypatch):
    log = []
    monkeypatch.setattr(nl2sql, "answer", _retrying_answer(log))
    monkeypatch.setenv("NL2SQL_DAILY_LIMIT", "1")
    at = asked(open_app())
    assert log == [False]                                    # tek hak ilk çağrıya gitti
    assert any("no such column: nope" in e.value for e in at.error)   # ilk hata gösterildi


def test_daily_limit_also_covers_interpret(key_calls, comments, monkeypatch):
    monkeypatch.setenv("NL2SQL_DAILY_LIMIT", "1")
    at = open_app()
    at.toggle(key="interpret_on").set_value(True).run()
    at = asked(at)                                           # tek hak soruya gitti
    next(b for b in at.button if b.label == "Yorumla").click().run()
    assert comments == []
    assert any("demo hakkı doldu" in w.value for w in at.warning)


# --- İki dil: varsayılan İngilizce, Türkçe seçilebilir ---

def test_default_language_is_english(calls):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert at.selectbox(key="lang").value == "en"
    assert at.title[0].value == "Ask Your Data in Plain Language"


def test_all_columns_selected_on_first_open(calls):
    import seed_db
    from nl2sql import list_columns

    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    expected = list_columns(seed_db.DB_PATHS["en"])
    for table, cols in expected.items():
        assert at.multiselect(key=f"cols_{table}").value == cols
    assert not at.info                                       # "sütun seç" uyarısı yok
    next(b for b in at.button if b.label.startswith("Which 5 products")).click().run()
    assert len(calls) == 1 and calls[0]["allowed"] == expected


def test_clear_all_and_single_removal_stay_off(calls):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    at.multiselect(key="cols_customers").unselect("name").run()
    at.run()                                                 # yeniden çalışınca geri seçilmez
    assert "name" not in at.multiselect(key="cols_customers").value
    clear_all(at)
    at.run()
    assert all(not m.value for m in at.sidebar.multiselect)
    assert any("select the columns" in i.value for i in at.info)
    assert not any(b.label.startswith("Which 5 products") for b in at.button)
    at.selectbox(key="lang").set_value("tr").run()            # dil değişince de kapalı kalır
    assert all(not m.value for m in at.sidebar.multiselect)


def test_switching_language_changes_texts(calls):
    at = open_app("en")
    assert any(b.label == "Send" for b in at.button)
    at.selectbox(key="lang").set_value("tr").run()
    assert any(b.label == "Gönder" for b in at.button)
    assert at.title[0].value == "Doğal Dille SQL"
    assert calls == []                                       # dil değişimi model çağırmaz


def test_english_ai_note_and_assumptions_heading(calls, comments, monkeypatch):
    monkeypatch.setattr(nl2sql, "answer", _answer_with(["Only completed orders were counted."]))
    at = open_app("en")
    at.toggle(key="interpret_on").set_value(True).run()
    at.text_input(key="question").input("How many customers?")
    next(b for b in at.button if b.label == "Send").click().run()
    assert "**Assumptions**" in [m.value for m in at.main.markdown]
    next(b for b in at.button if b.label == "Interpret").click().run()
    assert any(c.value == "AI-generated; compare the numbers with the table." for c in at.main.caption)


def test_changing_language_marks_result_stale(calls):
    at = asked(open_app("tr"))
    at.selectbox(key="lang").set_value("en").run()
    assert any("earlier question or settings" in w.value for w in at.warning)


def test_each_language_opens_its_own_database(monkeypatch):
    seen = []

    def fake_answer(question, db_path, today, **_):
        seen.append(db_path.name)
        return {"sql": "SELECT 1", "explanation": "", "chart": "none", "x": None, "y": None,
                "df": pd.DataFrame({"n": [1]}), "error": None}

    monkeypatch.setattr(nl2sql, "answer", fake_answer)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-no-calls")
    asked(open_app("tr"))
    at = open_app("en")
    at.text_input(key="question").input("How many customers?")
    next(b for b in at.button if b.label == "Send").click().run()
    assert seen == ["shop.db", "shop_en.db"]


def test_multiselect_placeholders_are_translated(calls):
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["lang"] = "tr"
    at.run()
    clear_all(at)
    assert at.multiselect(key="cols_customers").proto.placeholder == "Sütun seç"
    assert at.multiselect(key="value_cols").proto.placeholder == "Önce yukarıdan sütun seç"
    at.multiselect(key="cols_customers").set_value(["city"]).run()
    assert at.multiselect(key="value_cols").proto.placeholder == "Sütun seç"
    at.selectbox(key="lang").set_value("en").run()
    assert at.multiselect(key="cols_orders").proto.placeholder == "Choose columns"
