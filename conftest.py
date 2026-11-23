"""Ortak test fixture'ları: geçici bir PostgreSQL sunucusu.

Sırayla denenir:
1. NL2SQL_TEST_PG_URL ortam değişkeni (zaten çalışan bir sunucu; testler içinde kendi
   veritabanını oluşturur ve siler),
2. Docker çalışıyorsa geçici bir postgres container'ı (iş bitince kaldırılır),
3. .venv içindeki gömülü pgserver paketi (pip install -r requirements-dev.txt).
Hiçbiri olmazsa PostgreSQL testleri nedeni yazılarak ATLANIR (başarısız sayılmaz).
"""
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from pathlib import Path

import pytest

import seed_db

TEST_DB = "nl2sql_test"

# Örnek veritabanının PostgreSQL karşılığı: aynı tablolar, gerçek tarih ve sayı türleri,
# SQLite'taki "-- açıklama" yorumları COMMENT ON COLUMN olarak.
PG_SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    signup_date DATE NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date DATE NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);
COMMENT ON COLUMN products.price IS 'TL';
COMMENT ON COLUMN orders.status IS 'tamamlandi | iptal | iade';
COMMENT ON COLUMN order_items.unit_price IS 'satış anındaki fiyat, TL';
"""


def _wait_ready(url: str, seconds: float = 60) -> bool:
    import psycopg

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            psycopg.connect(url, connect_timeout=3).close()
            return True
        except Exception:
            time.sleep(1)
    return False


def _start_docker():
    """(adres, temizlik) ya da (None, neden)."""
    if not shutil.which("docker"):
        return None, "docker yok"
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return None, "Docker kurulu ama çalışmıyor"
    run = subprocess.run(["docker", "run", "-d", "--rm", "-e", "POSTGRES_PASSWORD=test",
                          "-p", "127.0.0.1::5432", "postgres:16-alpine"],
                         capture_output=True, text=True)
    if run.returncode != 0:
        return None, "postgres container'ı başlatılamadı"
    cid = run.stdout.strip()

    def cleanup():
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)

    port = subprocess.run(["docker", "port", cid, "5432"], capture_output=True, text=True).stdout
    url = f"postgresql://postgres:test@127.0.0.1:{port.strip().rsplit(':', 1)[-1]}/postgres"
    if not _wait_ready(url):
        cleanup()
        return None, "postgres container'ı hazır olmadı"
    return (url, cleanup), None


def _start_pgserver():
    try:
        import pgserver
    except ImportError:
        return None, "pgserver kurulu değil (pip install -r requirements-dev.txt)"
    # Veri klasörü kalıcı (git'e girmez): küme yalnızca ilk çalıştırmada oluşturulur (Windows'ta
    # bu bir dakikayı bulabilir), sonraki çalıştırmalarda sunucu ~1 sn'de açılır. Test veritabanı
    # her çalıştırmada silinip yeniden kurulur.
    data = Path(__file__).parent / ".pytest_cache" / "nl2sql_pg"
    data.parent.mkdir(exist_ok=True)
    try:
        server = pgserver.get_server(data, cleanup_mode="stop")
    except Exception as exc:
        return None, f"pgserver başlatılamadı ({type(exc).__name__})"

    return (server.get_uri(), server.cleanup), None


@pytest.fixture(scope="session")
def pg_server():
    """Sunucu (yönetici) adresi. Başlatılamazsa bu fixture'ı kullanan testler atlanır."""
    if os.getenv("NL2SQL_TEST_PG_URL"):
        yield os.environ["NL2SQL_TEST_PG_URL"]
        return
    reasons = []
    for start in (_start_docker, _start_pgserver):
        started, reason = start()
        if started:
            url, cleanup = started
            try:
                yield url
            finally:
                cleanup()
            return
        reasons.append(reason)
    pytest.skip("PostgreSQL başlatılamadı: " + "; ".join(reasons))


def _with_db(url: str, name: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def pg_url(pg_server):
    """Örnek veriyle (shop.db, Türkçe) doldurulmuş geçici bir PostgreSQL veritabanının adresi."""
    import psycopg

    with psycopg.connect(pg_server, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        admin.execute(f"CREATE DATABASE {TEST_DB}")
    url = _with_db(pg_server, TEST_DB)
    src = seed_db.build(tempfile.mkdtemp() + "/shop.db")
    with psycopg.connect(url) as con, closing(sqlite3.connect(src)) as lite:
        con.execute(PG_SCHEMA)
        with con.cursor() as cur:
            for table in ("customers", "products", "orders", "order_items"):
                rows = lite.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                marks = ", ".join(["%s"] * len(rows[0]))
                cur.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    try:
        yield url
    finally:
        with psycopg.connect(pg_server, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
