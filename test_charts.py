"""Grafik testleri: sıralama SQL sonucundaki gibi mi? (Çizim yapılmaz, Vega-Lite tanımı denetlenir.)"""
import pandas as pd

from charts import is_date_column, make_chart

# "En çok satan ürünler": SQL çoktan aza sıralamış; alfabetik sıra bundan farklı
TOP = pd.DataFrame({"urun": ["Powerbank", "Akıllı Saat", "Yoga Matı"], "adet": [87, 62, 68]})


def spec(chart):
    d = chart.to_dict()
    return d["encoding"], d["datasets"][next(iter(d["datasets"]))]


def test_bar_chart_keeps_sql_row_order():
    enc, rows = spec(make_chart(TOP, "bar", "urun", "adet"))
    assert enc["x"]["sort"] is None                    # Altair kendi sıralamasını yapmaz
    assert [r["urun"] for r in rows] == ["Powerbank", "Akıllı Saat", "Yoga Matı"]


def test_line_chart_with_months_is_chronological_even_if_sql_is_reversed():
    df = pd.DataFrame({"ay": ["2026-03", "2026-01", "2026-02"], "ciro": [3, 1, 2]})
    enc, rows = spec(make_chart(df, "line", "ay", "ciro"))
    assert enc["x"]["type"] == "temporal"
    assert [r["ciro"] for r in rows] == [1, 2, 3]       # Ocak, Şubat, Mart


def test_line_chart_with_non_date_x_keeps_sql_order():
    df = pd.DataFrame({"hafta": ["3. hafta", "1. hafta", "2. hafta"], "n": [3, 1, 2]})
    enc, rows = spec(make_chart(df, "line", "hafta", "n"))
    assert enc["x"]["type"] == "ordinal" and enc["x"]["sort"] is None
    assert [r["hafta"] for r in rows] == ["3. hafta", "1. hafta", "2. hafta"]


def test_numeric_x_is_category_not_epoch_date():
    # Yıl gibi yalın sayılar tarih sanılmamalı (1970'e yakın bir zaman damgasına dönüşürdü)
    assert not is_date_column(pd.Series([2024, 2025]))
    enc, _ = spec(make_chart(pd.DataFrame({"yil": [2025, 2024], "n": [5, 4]}), "bar", "yil", "n"))
    assert enc["x"]["type"] == "nominal" and enc["x"]["sort"] is None


def test_date_detection():
    assert is_date_column(pd.Series(["2026-10-01", "2026-10-02"]))
    assert not is_date_column(pd.Series(["Ankara", "İzmir"]))
    assert not is_date_column(pd.Series([None, None]))
