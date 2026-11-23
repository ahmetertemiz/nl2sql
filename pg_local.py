"""Bu makinede geçici bir PostgreSQL sunucusu: testler (conftest.py) ve değerlendirme (run_evals.py --postgres).

Sırayla denenir:
1. Docker çalışıyorsa geçici bir postgres container'ı (iş bitince kaldırılır),
2. .venv içindeki gömülü pgserver paketi (pip install -r requirements-dev.txt).
Sistem geneline hiçbir şey kurmaz.
"""
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).parent


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


def start_docker():
    """((adres, temizlik), None) ya da (None, neden)."""
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


def start_pgserver():
    """((adres, temizlik), None) ya da (None, neden).

    Veri klasörü kalıcı (git'e girmez): küme yalnızca ilk çalıştırmada oluşturulur (Windows'ta
    bu bir dakikayı bulabilir), sonraki çalıştırmalarda sunucu ~1 sn'de açılır.
    """
    try:
        import pgserver
    except ImportError:
        return None, "pgserver kurulu değil (pip install -r requirements-dev.txt)"
    data = ROOT / ".pytest_cache" / "nl2sql_pg"
    data.parent.mkdir(exist_ok=True)
    try:
        server = pgserver.get_server(data, cleanup_mode="stop")
    except Exception as exc:
        return None, f"pgserver başlatılamadı ({type(exc).__name__})"
    return (server.get_uri(), server.cleanup), None


def start():
    """Önce Docker, sonra pgserver. ((adres, temizlik, ad), None) ya da (None, nedenler)."""
    reasons = []
    for name, starter in (("Docker", start_docker), ("pgserver", start_pgserver)):
        started, reason = starter()
        if started:
            return (*started, name), None
        reasons.append(reason)
    return None, "; ".join(reasons)


def with_database(url: str, name: str) -> str:
    """Aynı sunucuda başka bir veritabanının adresi."""
    from sqlalchemy.engine import make_url

    return make_url(url).set(database=name).render_as_string(hide_password=False)


def fresh_database(admin_url: str, name: str, lang: str = "tr") -> str:
    """name veritabanını sıfırdan kurar, örnek veriyle doldurur ve adresini döndürür."""
    import psycopg

    import seed_db

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {name}")
    url = with_database(admin_url, name)
    seed_db.copy_to_postgres(url, lang)
    return url


def drop_database(admin_url: str, name: str) -> None:
    import psycopg

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
