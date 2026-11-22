"""Arayüz metinleri: tek bir çeviri sözlüğü. Varsayılan dil İngilizce.

Kullanım: t(lang, "key", **params). Eksik anahtar İngilizceye düşer; o da yoksa KeyError
(testler eksik çeviriyi yakalasın diye iki dilin anahtar kümesi ayrıca karşılaştırılır).
"""

LANGS = {"en": "English", "tr": "Türkçe"}
DEFAULT_LANG = "en"

TEXTS: dict[str, dict[str, object]] = {
    "en": {
        "page_title": "Ask Your Data in Plain Language",
        "language": "Language",
        "sidebar_header": "Data the model can see",
        "sidebar_caption": ("Only the tables and columns you select are shown to the model and can be "
                            "queried. While result interpretation is off, no data rows are sent to the model."),
        "select_all": "Select all",
        "clear_all": "Clear all",
        "value_cols_label": "Columns whose values are shown to the model",
        "value_cols_help": ("For columns with few distinct values, such as status or category. The model "
                            "sees up to 20 distinct values and writes the WHERE condition correctly. "
                            "Do not select personal columns such as names or e-mail addresses."),
        "value_cols_warning": "The actual values of the selected columns are sent to the model.",
        "interpret_toggle": "Interpret the result in plain language",
        "interpret_help": ("When on, an 'Interpret' button appears below the result. Pressing it sends the "
                           "first {rows} rows of the result and a numeric summary of the whole result "
                           "(min/max value and row, mean, sum) to the model and asks for a plain-language "
                           "interpretation. Each interpretation is a separate, paid model call."),
        "interpret_warning": ("Pressing 'Interpret' sends the first {rows} rows of the result and a numeric "
                              "summary of the whole result to the model."),
        "schema_expander": "Schema sent to the model",
        "schema_empty": "-- No columns selected yet",
        "own_key_expander": "Your own API key",
        "own_key_label": "Anthropic API key",
        "own_key_help": ("Optional. If you enter one, calls are made with your key and the daily demo "
                         "limit does not apply. The key is not stored; it is gone when you close the page."),
        "title": "Ask Your Data in Plain Language",
        "subtitle": "Ask a question in plain language; the tool turns it into SQL, runs it and shows the result.",
        "data_date": ("The sample data ends on {today}; expressions such as \"today\" or \"last month\" "
                      "are calculated relative to that date."),
        "no_key": ("No API key. Enter your own key in the left panel or set the ANTHROPIC_API_KEY "
                   "environment variable (see the setup step in the README)."),
        "limit_reached": ("Today's free demo quota is used up. Enter your own Anthropic API key in the "
                          "left panel to continue, or try again tomorrow."),
        "start_hint": "To start, select the columns the model can see in the left panel.",
        "question_label": "Your question",
        "submit": "Send",
        "generating": "Preparing the query...",
        "model_failed": "Model call failed: {error}",
        "stale_result": ("This result was produced with an earlier question or settings (question: "
                         "\"{question}\"). Press Send to get an answer with the current settings."),
        "assumptions": "Assumptions",
        "generated_sql": "Generated SQL",
        "query_failed": "The query could not be run: {error}",
        "empty_result": "The query ran but the result is empty.",
        "download_csv": "Download CSV",
        "csv_name": "result.csv",
        "interpret": "Interpret",
        "interpreting": "Interpreting the result...",
        "interpret_failed": "Could not get an interpretation: {error}",
        "ai_note": "AI-generated; compare the numbers with the table.",
        "examples": [
            "Which 5 products sold the most last month?",
            "How did total revenue change by month?",
            "What are the customer count and average order value by city?",
            "Which category has the highest return rate?",
        ],
        # nl2sql.py'nin kullanıcıya dönen hata mesajları
        "err_empty": "Empty query.",
        "err_multi": "Multiple SQL statements are not allowed.",
        "err_select_only": "Only SELECT queries are allowed.",
        "err_modifies": "The query contains a command that modifies data.",
        "err_parse": "Could not parse the SQL: {detail}",
        "err_denied": "The query tried to access tables/columns that are not allowed: {items}",
        "err_star": "{table}.* (* cannot be used on a table with hidden columns)",
        "err_op": "operation {op}",
        "err_timeout": ("The query was stopped because it did not finish within {seconds} seconds. "
                        "Try narrowing the question (e.g. add a date range)."),
    },
    "tr": {
        "page_title": "Doğal Dille SQL",
        "language": "Dil",
        "sidebar_header": "Modelin görebileceği veriler",
        "sidebar_caption": ("Yalnızca seçtiğin tablo ve sütunlar modele gösterilir ve sorgulanabilir. "
                            "Sonuç yorumlama kapalıyken veri satırları modele gönderilmez."),
        "select_all": "Tümünü aç",
        "clear_all": "Tümünü kapat",
        "value_cols_label": "Değerleri modele gösterilecek sütunlar",
        "value_cols_help": ("Durum, kategori gibi az sayıda değeri olan sütunlar için. Model bu sütunun "
                            "farklı değerlerini (en fazla 20) görür ve WHERE koşulunu doğru yazar. "
                            "Ad, e-posta gibi kişiye özgü sütunları seçme."),
        "value_cols_warning": "Seçilen sütunların gerçek değerleri modele gönderilir.",
        "interpret_toggle": "Sonucu düz dille yorumla",
        "interpret_help": ("Açıkken sonucun altında 'Yorumla' düğmesi çıkar. Basınca sonucun ilk "
                           "{rows} satırı ve tüm sonucun sayısal özeti (en düşük/en yüksek "
                           "değer ve satırı, ortalama, toplam) modele gönderilir ve düz dille bir yorum "
                           "istenir. Her yorum ayrı, ücretli bir model çağrısıdır."),
        "interpret_warning": ("'Yorumla'ya basınca sonucun ilk {rows} satırı ve tüm sonucun "
                              "sayısal özeti modele gönderilir."),
        "schema_expander": "Modele gönderilen şema",
        "schema_empty": "-- Henüz bir sütun seçilmedi",
        "own_key_expander": "Kendi API anahtarın",
        "own_key_label": "Anthropic API anahtarı",
        "own_key_help": ("İsteğe bağlı. Girersen çağrılar senin anahtarınla yapılır ve günlük demo "
                         "sınırı uygulanmaz. Anahtar kaydedilmez; sayfayı kapatınca silinir."),
        "title": "Doğal Dille SQL",
        "subtitle": "Sorunu Türkçe yaz; araç SQL'e çevirsin, çalıştırsın ve sonucu göstersin.",
        "data_date": ("Örnek veri {today} tarihinde bitiyor; \"bugün\", \"geçen ay\" gibi ifadeler "
                      "bu tarihe göre hesaplanır."),
        "no_key": ("API anahtarı yok. Soldaki panelden kendi anahtarını gir ya da ANTHROPIC_API_KEY "
                   "ortam değişkenini tanımla (README'deki kurulum adımına bak)."),
        "limit_reached": ("Bugünkü ücretsiz demo hakkı doldu. Soldaki panelden kendi Anthropic API "
                          "anahtarını girerek devam edebilir ya da yarın tekrar deneyebilirsin."),
        "start_hint": "Başlamak için soldaki panelden modelin görebileceği sütunları seç.",
        "question_label": "Sorun",
        "submit": "Gönder",
        "generating": "Sorgu hazırlanıyor...",
        "model_failed": "Model çağrısı başarısız oldu: {error}",
        "stale_result": ("Bu sonuç önceki soru veya ayarlarla üretildi (soru: \"{question}\"). "
                         "Güncel ayarlarla yanıt almak için Gönder'e bas."),
        "assumptions": "Varsayımlar",
        "generated_sql": "Üretilen SQL",
        "query_failed": "Sorgu çalıştırılamadı: {error}",
        "empty_result": "Sorgu çalıştı ama sonuç boş.",
        "download_csv": "CSV indir",
        "csv_name": "sonuc.csv",
        "interpret": "Yorumla",
        "interpreting": "Sonuç yorumlanıyor...",
        "interpret_failed": "Yorum alınamadı: {error}",
        "ai_note": "Yapay zeka tarafından üretildi; sayıları tabloyla karşılaştır.",
        "examples": [
            "Geçen ay en çok satan 5 ürün hangileri?",
            "Aylara göre toplam ciro nasıl değişti?",
            "Şehirlere göre müşteri sayısı ve ortalama sipariş tutarı nedir?",
            "Hangi kategoride iade oranı en yüksek?",
        ],
        "err_empty": "Boş sorgu.",
        "err_multi": "Birden fazla SQL ifadesine izin verilmiyor.",
        "err_select_only": "Yalnızca SELECT sorgularına izin veriliyor.",
        "err_modifies": "Sorgu veriyi değiştiren bir komut içeriyor.",
        "err_parse": "SQL ayrıştırılamadı: {detail}",
        "err_denied": "Sorgu izin verilmeyen tablo/sütunlara erişmeye çalıştı: {items}",
        "err_star": "{table}.* (gizli sütun içeren tabloda * kullanılamaz)",
        "err_op": "işlem {op}",
        "err_timeout": ("Sorgu {seconds} saniyede bitmediği için durduruldu. "
                        "Soruyu daraltmayı dene (ör. tarih aralığı ekle)."),
    },
}


def t(lang: str, key: str, **params):
    """Seçilen dildeki metin; bilinmeyen dil İngilizceye düşer."""
    texts = TEXTS.get(lang, TEXTS[DEFAULT_LANG])
    value = texts[key] if key in texts else TEXTS[DEFAULT_LANG][key]
    return value.format(**params) if isinstance(value, str) and params else value


def error_text(lang: str, key: str, params: dict) -> str:
    """nl2sql hata mesajı. err_denied'de liste öğeleri de (yıldız, işlem) seçilen dilde kurulur."""
    if key == "err_denied":
        items = list(params.get("names", []))
        items += [t(lang, "err_star", table=s) for s in params.get("stars", [])]
        items += [t(lang, "err_op", op=o) for o in params.get("ops", [])]
        return t(lang, key, items=", ".join(sorted(items)))
    return t(lang, key, **params)
