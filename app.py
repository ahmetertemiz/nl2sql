"""Doğal dille SQL — Streamlit arayüzü. Çalıştır: streamlit run app.py"""
import json
import os
from pathlib import Path

import streamlit as st

import quota
import seed_db
from charts import make_chart
from i18n import DEFAULT_LANG, LANGS, t
from nl2sql import INTERPRET_MAX_ROWS, answer, format_sql, get_schema, interpret_result, list_columns

DB_PATH = Path(__file__).parent / "shop.db"
TODAY = seed_db.TODAY.isoformat()  # örnek verinin bittiği gün; gerçek tarih değil (bkz. seed_db.py)
# Ortak anahtarla günde en fazla kaç model çağrısı yapılabilir. 0 = sınırsız (yerel kullanım).
DAILY_LIMIT = int(os.getenv("NL2SQL_DAILY_LIMIT", "0"))
MAX_QUESTION_CHARS = 500

# Dil, sayfa başlığından önce okunur; seçici kenar çubuğunun en üstünde (aşağıda).
lang = st.session_state.get("lang", DEFAULT_LANG)
EXAMPLES = t(lang, "examples")

st.set_page_config(page_title=t(lang, "page_title"), page_icon="🔎", layout="wide")

if not DB_PATH.exists():
    seed_db.build(DB_PATH)

COLUMNS = list_columns(DB_PATH)


def set_all(on: bool) -> None:
    for table, cols in COLUMNS.items():
        st.session_state[f"cols_{table}"] = cols if on else []
    if not on:
        st.session_state.value_cols = []


with st.sidebar:
    st.selectbox(t(lang, "language"), list(LANGS), format_func=LANGS.get, key="lang")
    st.header(t(lang, "sidebar_header"))
    st.caption(t(lang, "sidebar_caption"))
    with st.container(horizontal=True):
        st.button(t(lang, "select_all"), on_click=set_all, args=(True,), width="stretch")
        st.button(t(lang, "clear_all"), on_click=set_all, args=(False,), width="stretch")
    # Varsayılan: hiçbir şey açık değil. Kullanıcı bilerek seçmeli.
    allowed = {table: st.multiselect(table, cols, key=f"cols_{table}") for table, cols in COLUMNS.items()}
    allowed = {table: cols for table, cols in allowed.items() if cols}

    # Değerleri gösterilecek sütunlar yalnızca izinli sütunlar arasından seçilebilir.
    # İzin kaldırılan bir sütun bu listeden de düşer.
    value_options = [f"{table}.{col}" for table, cols in allowed.items() for col in cols]
    if "value_cols" in st.session_state:
        st.session_state.value_cols = [v for v in st.session_state.value_cols if v in value_options]
    picked = st.multiselect(t(lang, "value_cols_label"), value_options, key="value_cols",
                            help=t(lang, "value_cols_help"))
    value_columns: dict[str, list[str]] = {}
    for item in picked:
        table, col = item.split(".", 1)
        value_columns.setdefault(table, []).append(col)
    if value_columns:
        st.warning(t(lang, "value_cols_warning"), icon=":material/info:")

    # Varsayılan kapalı: açılınca sorgu SONUCU (gerçek satırlar) modele gider.
    interpret_on = st.toggle(t(lang, "interpret_toggle"), key="interpret_on",
                             help=t(lang, "interpret_help", rows=INTERPRET_MAX_ROWS))
    if interpret_on:
        st.warning(t(lang, "interpret_warning", rows=INTERPRET_MAX_ROWS), icon=":material/info:")

    with st.expander(t(lang, "schema_expander"), icon=":material/visibility:"):
        st.code(get_schema(DB_PATH, allowed, value_columns) or t(lang, "schema_empty"),
                language="sql")

    # Ziyaretçinin kendi anahtarı: günlük sınıra takılmaz, yalnızca bu oturumda tutulur.
    with st.expander(t(lang, "own_key_expander"), icon=":material/key:"):
        user_key = st.text_input(t(lang, "own_key_label"), type="password", key="user_key",
                                 help=t(lang, "own_key_help")).strip() or None

st.title(t(lang, "title"))
st.caption(t(lang, "subtitle"))
st.caption(t(lang, "data_date", today=TODAY))

if not user_key and not os.getenv("ANTHROPIC_API_KEY"):
    st.error(t(lang, "no_key"))
    st.stop()


def may_call_model() -> bool:
    """Kendi anahtarını giren sınırsız; ortak anahtar günlük sınıra tabi."""
    return bool(user_key) or quota.take(DAILY_LIMIT)


if not allowed:
    st.info(t(lang, "start_hint"), icon=":material/lock:")
    st.stop()

if "question" not in st.session_state:
    st.session_state.question = ""


def ask_example(example: str) -> None:
    st.session_state.question = example
    st.session_state.run_now = True


cols = st.columns(len(EXAMPLES))
for col, example in zip(cols, EXAMPLES):
    col.button(example, width="stretch", on_click=ask_example, args=(example,))

# Form: yazarken ya da kenar çubuğunda ayar değiştirirken model çağrılmaz.
# Model yalnızca Gönder'e (veya bir örnek soruya) basılınca çağrılır; her çağrı ücretli.
with st.form("ask_form", border=False):
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.text_input(t(lang, "question_label"), key="question", placeholder=EXAMPLES[0],
                      max_chars=MAX_QUESTION_CHARS)
        submitted = st.form_submit_button(t(lang, "submit"), icon=":material/send:", type="primary")

# Sonucun hangi ayarlarla üretildiğini hatırla: ayar (dil dahil) değişince eski sonuç uyarıyla gösterilir.
settings = json.dumps([allowed, value_columns, lang], sort_keys=True)
question = st.session_state.question.strip()
if (submitted or st.session_state.pop("run_now", False)) and question:
    if not may_call_model():
        st.warning(t(lang, "limit_reached"), icon=":material/hourglass_disabled:")
        st.stop()
    with st.spinner(t(lang, "generating")):
        try:
            result = answer(question, DB_PATH, today=TODAY, allowed=allowed,
                            value_columns=value_columns, api_key=user_key, lang=lang)
        except Exception as exc:
            st.error(t(lang, "model_failed", error=exc))
            st.stop()
    st.session_state.last = {"question": question, "settings": settings, "result": result}

last = st.session_state.get("last")
if last:
    result = last["result"]
    if last["settings"] != settings or last["question"] != question:
        st.warning(t(lang, "stale_result", question=last["question"]), icon=":material/history:")

    if result["explanation"]:
        st.info(result["explanation"])

    # Modelin soruda açık olmayan noktalarda verdiği kararlar. Soru netse liste boştur.
    if result.get("assumptions"):
        with st.container(border=True):
            st.markdown(f"**{t(lang, 'assumptions')}**")
            st.markdown("\n".join(f"- {a}" for a in result["assumptions"]))

    if result["sql"]:
        with st.expander(t(lang, "generated_sql"), expanded=True):
            st.code(format_sql(result["sql"]), language="sql")  # yalnızca gösterim biçimlenir

    if result["error"]:
        st.error(t(lang, "query_failed", error=result["error"]))
    elif result["df"] is not None:
        df = result["df"]
        if df.empty:
            st.warning(t(lang, "empty_result"))
        else:
            x, y = result["x"], result["y"]
            if result["chart"] != "none" and x in df.columns and y in df.columns:
                # Altair: çubuklar SQL'deki sırayla, tarih ekseni kronolojik (bkz. charts.py)
                st.altair_chart(make_chart(df, result["chart"], x, y), width="stretch")
            st.dataframe(df, hide_index=True)
            with st.container(horizontal=True):
                st.download_button(t(lang, "download_csv"), df.to_csv(index=False).encode("utf-8-sig"),
                                   t(lang, "csv_name"), "text/csv")
                # Yorum ayrı bir çağrı: sorgu yeniden çalışmaz, yalnızca bu sonuç yorumlanır.
                want_comment = interpret_on and st.button(
                    t(lang, "interpret"), icon=":material/chat:",
                    disabled="comment" in last,  # aynı sonuç için ikinci kez ücret ödeme
                )
            if want_comment and not may_call_model():
                st.warning(t(lang, "limit_reached"), icon=":material/hourglass_disabled:")
            elif want_comment:
                with st.spinner(t(lang, "interpreting")):
                    try:
                        last["comment"] = interpret_result(last["question"], result["sql"], df,
                                                           api_key=user_key)
                    except Exception as exc:  # hata görünür kalsın; düğme tekrar denenebilir
                        st.error(t(lang, "interpret_failed", error=exc))
                if "comment" in last:
                    st.rerun()  # düğme devre dışı görünsün
            if interpret_on and last.get("comment"):
                st.success(last["comment"], icon=":material/chat:")
                st.caption(t(lang, "ai_note"))
