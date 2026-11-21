"""Sonuç grafikleri (Altair). Streamlit'ten bağımsız; böylece testlerde çizilmeden denetlenebilir.

Neden st.bar_chart değil: st.bar_chart x eksenini alfabetik sıralar. "En çok satan 5 ürün"
sorusunda SQL'in ORDER BY ile kurduğu sıra (çoktan aza) grafikte kaybolur.
Burada x ekseni sort=None ile çizilir: çubuklar SQL sonucundaki satır sırasıyla gelir.
"""
import re

import altair as alt
import pandas as pd

# 2026-10 veya 2026-10-02 biçimindeki metinler tarih sayılır. Yalın sayılar (1, 2, 2025)
# sayılmaz: pd.to_datetime onları da tarihe çevirebilir, bu da yanlış bir eksen üretir.
DATE_TEXT = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def is_date_column(values: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(values):
        return True
    texts = values.dropna().astype(str)
    return len(texts) > 0 and texts.map(lambda v: bool(DATE_TEXT.match(v))).all()


def make_chart(df: pd.DataFrame, kind: str, x: str, y: str) -> alt.Chart:
    """kind: 'bar' veya 'line'. x ve y, df'deki sütun adları."""
    tooltip = [alt.Tooltip(x), alt.Tooltip(y)]
    if kind == "line" and is_date_column(df[x]):
        # Tarih ekseni: değerleri gerçek tarihe çevir ve kronolojik sırala. Böylece SQL
        # sonucu ters sıralı (yeniden eskiye) gelse bile çizgi soldan sağa zamanda ilerler.
        data = df.assign(**{x: pd.to_datetime(df[x].astype(str))}).sort_values(x)
        fmt = "%Y-%m" if df[x].astype(str).str.len().max() <= 7 else "%Y-%m-%d"
        x_enc = alt.X(x, type="temporal", title=x, axis=alt.Axis(format=fmt))
        tooltip[0] = alt.Tooltip(x, type="temporal", format=fmt)
        return alt.Chart(data).mark_line(point=True).encode(x=x_enc, y=alt.Y(y, title=y), tooltip=tooltip)

    # Kategorik eksen: sort=None -> SQL'deki satır sırası korunur (alfabetik sıralama yok)
    data = df.assign(**{x: df[x].astype(str)})
    x_enc = alt.X(x, type="ordinal" if kind == "line" else "nominal", sort=None, title=x,
                  axis=alt.Axis(labelAngle=-30, labelLimit=180))
    mark = alt.Chart(data).mark_line(point=True) if kind == "line" else alt.Chart(data).mark_bar()
    return mark.encode(x=x_enc, y=alt.Y(y, title=y), tooltip=tooltip)
