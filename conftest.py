"""Ortak test fixture'ları: geçici bir PostgreSQL sunucusu.

Sırayla denenir:
1. NL2SQL_TEST_PG_URL ortam değişkeni (zaten çalışan bir sunucu; testler içinde kendi
   veritabanını oluşturur ve siler),
2. Docker çalışıyorsa geçici bir postgres container'ı (iş bitince kaldırılır),
3. .venv içindeki gömülü pgserver paketi (pip install -r requirements-dev.txt).
Sunucu başlatma pg_local.py'de (run_evals.py --postgres de kullanır).
Hiçbiri olmazsa PostgreSQL testleri nedeni yazılarak ATLANIR (başarısız sayılmaz); test
çıktısının sonunda hangi yolun kullanıldığı ya da neden atlandığı ayrıca yazılır.
NL2SQL_TEST_PG=off ile PostgreSQL testleri bilerek atlanır.
"""
import os

import pytest

import pg_local

TEST_DB = "nl2sql_test"
_PG_STATUS: list[str] = []  # test sonu özetinde gösterilir


@pytest.fixture(scope="session")
def pg_server():
    """Sunucu (yönetici) adresi. Başlatılamazsa bu fixture'ı kullanan testler atlanır."""
    if os.getenv("NL2SQL_TEST_PG", "").lower() == "off":
        _PG_STATUS.append("ATLANDI: NL2SQL_TEST_PG=off")
        pytest.skip("PostgreSQL testleri kapalı (NL2SQL_TEST_PG=off)")
    if os.getenv("NL2SQL_TEST_PG_URL"):
        _PG_STATUS.append("NL2SQL_TEST_PG_URL ile verilen sunucuda koştu")
        yield os.environ["NL2SQL_TEST_PG_URL"]
        return
    started, reasons = pg_local.start()
    if not started:
        _PG_STATUS.append("ATLANDI: " + reasons)
        pytest.skip("PostgreSQL başlatılamadı: " + reasons)
    url, cleanup, name = started
    _PG_STATUS.append(f"{name} ile koştu")
    try:
        yield url
    finally:
        cleanup()


def pytest_terminal_summary(terminalreporter):
    """PostgreSQL testlerinin durumu her zaman görünsün: koştu mu, atlandı mı, neden?"""
    if _PG_STATUS:
        terminalreporter.write_sep("-", "PostgreSQL testleri: " + _PG_STATUS[0],
                                   yellow=_PG_STATUS[0].startswith("ATLANDI"), bold=True)


@pytest.fixture(scope="session")
def pg_url(pg_server):
    """Örnek veriyle (shop.db, Türkçe) doldurulmuş geçici bir PostgreSQL veritabanının adresi."""
    url = pg_local.fresh_database(pg_server, TEST_DB, "tr")
    try:
        yield url
    finally:
        pg_local.drop_database(pg_server, TEST_DB)
