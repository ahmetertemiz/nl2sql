"""Çeviri sözlüğü ve nl2sql hata mesajlarının dili."""
import pytest

import i18n
from nl2sql import QueryTimeout, UnsafeSQL, error_message, run_sql, validate_sql


def test_both_languages_have_the_same_keys():
    assert set(i18n.TEXTS["en"]) == set(i18n.TEXTS["tr"])


def test_placeholders_match_between_languages():
    import string
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for key, en in i18n.TEXTS["en"].items():
        if isinstance(en, str):
            assert fields(en) == fields(i18n.TEXTS["tr"][key]), key


def test_default_is_english_and_unknown_language_falls_back():
    assert i18n.DEFAULT_LANG == "en"
    assert i18n.t("de", "submit") == "Send"
    assert i18n.t("tr", "submit") == "Gönder"


def test_examples_are_lists_of_four():
    assert len(i18n.t("en", "examples")) == len(i18n.t("tr", "examples")) == 4


def test_validate_error_in_selected_language():
    with pytest.raises(UnsafeSQL) as info:
        validate_sql("DELETE FROM customers")
    assert str(info.value) == "Only SELECT queries are allowed."
    assert error_message(info.value, "tr") == "Yalnızca SELECT sorgularına izin veriliyor."


def test_denied_message_in_both_languages(tmp_path):
    import seed_db
    db = seed_db.build(tmp_path / "s.db")
    with pytest.raises(UnsafeSQL) as info:
        run_sql(db, "SELECT * FROM customers", {"customers": ["id"]})
    assert "customers.* (* cannot be used on a table with hidden columns)" in str(info.value)
    tr = info.value.localized("tr")
    assert tr.startswith("Sorgu izin verilmeyen tablo/sütunlara erişmeye çalıştı: ")
    assert "customers.* (gizli sütun içeren tabloda * kullanılamaz)" in tr


def test_timeout_message_in_turkish():
    exc = QueryTimeout("err_timeout", seconds="5")
    assert error_message(exc, "tr").startswith("Sorgu 5 saniyede bitmediği için durduruldu.")


def test_untranslated_errors_pass_through():
    assert error_message(RuntimeError("no such column: x"), "tr") == "no such column: x"
