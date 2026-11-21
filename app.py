"""Doğal dille SQL — Streamlit arayüzü. Çalıştır: streamlit run app.py"""
import json
import os
from datetime import date
from pathlib import Path

import streamlit as st

import seed_db
from charts import make_chart
from nl2sql import answer, format_sql, get_schema, list_columns

DB_PATH = Path(__file__).parent / "shop.db"
EXAMPLES = [
    "Geçen ay en çok satan 5 ürün hangileri?",
    "Aylara göre toplam ciro nasıl değişti?",
    "Şehirlere göre müşteri sayısı ve ortalama sipariş tutarı nedir?",
    "Hangi kategoride iade oranı en yüksek?",
]

st.set_page_config(page_title="Doğal Dille SQL", page_icon="🔎", layout="wide")

if not DB_PATH.exists():
    seed_db.build(DB_PATH)

COLUMNS = list_columns(DB_PATH)


def set_all(on: bool) -> None:
    for table, cols in COLUMNS.items():
        st.session_state[f"cols_{table}"] = cols if on else []
    if not on:
        st.session_state.value_cols = []


with st.sidebar:
    st.header("Modelin görebileceği veriler")
    st.caption(
        "Yalnızca seçtiğin tablo ve sütunlar modele gösterilir ve sorgulanabilir. "
        "Veri satırları hiçbir zaman modele gönderilmez."
    )
    with st.container(horizontal=True):
        st.button("Tümünü aç", on_click=set_all, args=(True,), width="stretch")
        st.button("Tümünü kapat", on_click=set_all, args=(False,), width="stretch")
    # Varsayılan: hiçbir şey açık değil. Kullanıcı bilerek seçmeli.
    allowed = {table: st.multiselect(table, cols, key=f"cols_{table}") for table, cols in COLUMNS.items()}
    allowed = {table: cols for table, cols in allowed.items() if cols}

    # Değerleri gösterilecek sütunlar yalnızca izinli sütunlar arasından seçilebilir.
    # İzin kaldırılan bir sütun bu listeden de düşer.
    value_options = [f"{table}.{col}" for table, cols in allowed.items() for col in cols]
    if "value_cols" in st.session_state:
        st.session_state.value_cols = [v for v in st.session_state.value_cols if v in value_options]
    picked = st.multiselect(
        "Değerleri modele gösterilecek sütunlar",
        value_options,
        key="value_cols",
        help=(
            "Durum, kategori gibi az sayıda değeri olan sütunlar için. Model bu sütunun "
            "farklı değerlerini (en fazla 20) görür ve WHERE koşulunu doğru yazar. "
            "Ad, e-posta gibi kişiye özgü sütunları seçme."
        ),
    )
    value_columns: dict[str, list[str]] = {}
    for item in picked:
        table, col = item.split(".", 1)
        value_columns.setdefault(table, []).append(col)
    if value_columns:
        st.warning("Seçilen sütunların gerçek değerleri modele gönderilir.", icon=":material/info:")

    with st.expander("Modele gönderilen şema", icon=":material/visibility:"):
        st.code(get_schema(DB_PATH, allowed, value_columns) or "-- Henüz bir sütun seçilmedi",
                language="sql")

st.title("Doğal Dille SQL")
st.caption("Sorunu Türkçe yaz; araç SQL'e çevirsin, çalıştırsın ve sonucu göstersin.")

if not os.getenv("ANTHROPIC_API_KEY"):
    st.error("ANTHROPIC_API_KEY ortam değişkeni tanımlı değil. README'deki kurulum adımına bak.")
    st.stop()

if not allowed:
    st.info("Başlamak için soldaki panelden modelin görebileceği sütunları seç.",
            icon=":material/lock:")
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
        st.text_input("Sorun", key="question", placeholder=EXAMPLES[0])
        submitted = st.form_submit_button("Gönder", icon=":material/send:", type="primary")

# Sonucun hangi ayarlarla üretildiğini hatırla: ayar değişince eski sonuç uyarıyla gösterilir.
settings = json.dumps([allowed, value_columns], sort_keys=True)
question = st.session_state.question.strip()
if (submitted or st.session_state.pop("run_now", False)) and question:
    with st.spinner("Sorgu hazırlanıyor..."):
        try:
            result = answer(question, DB_PATH, today=date.today().isoformat(),
                            allowed=allowed, value_columns=value_columns)
        except Exception as exc:
            st.error(f"Model çağrısı başarısız oldu: {exc}")
            st.stop()
    st.session_state.last = {"question": question, "settings": settings, "result": result}

last = st.session_state.get("last")
if last:
    result = last["result"]
    if last["settings"] != settings or last["question"] != question:
        st.warning(
            f"Bu sonuç önceki soru veya ayarlarla üretildi (soru: \"{last['question']}\"). "
            "Güncel ayarlarla yanıt almak için Gönder'e bas.",
            icon=":material/history:",
        )

    if result["explanation"]:
        st.info(result["explanation"])

    if result["sql"]:
        with st.expander("Üretilen SQL", expanded=True):
            st.code(format_sql(result["sql"]), language="sql")  # yalnızca gösterim biçimlenir

    if result["error"]:
        st.error(f"Sorgu çalıştırılamadı: {result['error']}")
    elif result["df"] is not None:
        df = result["df"]
        if df.empty:
            st.warning("Sorgu çalıştı ama sonuç boş.")
        else:
            x, y = result["x"], result["y"]
            if result["chart"] != "none" and x in df.columns and y in df.columns:
                # Altair: çubuklar SQL'deki sırayla, tarih ekseni kronolojik (bkz. charts.py)
                st.altair_chart(make_chart(df, result["chart"], x, y), width="stretch")
            st.dataframe(df, hide_index=True)
            st.download_button("CSV indir", df.to_csv(index=False).encode("utf-8-sig"),
                               "sonuc.csv", "text/csv")
