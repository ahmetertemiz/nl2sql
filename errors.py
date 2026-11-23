"""Kullanıcıya gösterilen hata türleri. nl2sql.py ve db.py ikisi de kullanır (döngüsel import olmasın diye ayrı)."""
import i18n


class LocalizedError(Exception):
    """Kullanıcıya gösterilen hata: metin değil anahtar taşır, dil gösterim anında seçilir.

    str(exc) İngilizce metni verir (günlükler ve modele geri bildirim için);
    exc.localized("tr") seçilen dildeki metni.
    """

    def __init__(self, key: str, **params):
        self.key, self.params = key, params
        super().__init__(self.localized("en"))

    def localized(self, lang: str) -> str:
        return i18n.error_text(lang, self.key, self.params)


class UnsafeSQL(LocalizedError, ValueError):
    pass


class QueryTimeout(LocalizedError, RuntimeError):
    pass


class SQLParseError(LocalizedError, ValueError):
    pass


class DatabaseError(LocalizedError, RuntimeError):
    """Bağlantı / yapılandırma hatası. Mesajı bilerek ayrıntısızdır: bağlantı adresi
    (kullanıcı adı, parola, sunucu) hiçbir zaman arayüzde, hatada ya da günlükte görünmemeli."""


def error_message(exc: Exception, lang: str) -> str:
    """Hata mesajı seçilen dilde; çevirisi olmayan (ör. veritabanının kendi) hatalar olduğu gibi."""
    return exc.localized(lang) if isinstance(exc, LocalizedError) else str(exc)
