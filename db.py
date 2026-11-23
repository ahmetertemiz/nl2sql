"""Veritabanı katmanı: örnek SQLite dosyası ya da NL2SQL_DATABASE_URL ile verilen dış veritabanı.

Desteklenen: SQLite ve PostgreSQL (SQLAlchemy üzerinden). Şema, sütun listesi ve değer
ipuçları SQLAlchemy inspector ile okunur. SQLite'a özel iki ek korunur: tablo sırası ve
CREATE TABLE satırlarındaki "-- açıklama" yorumları (sqlite_master'dan). Böylece örnek
veritabanı için modele giden şema metni değişmez.

Gizlilik: bağlantı adresi (kullanıcı, parola, sunucu) yalnızca bu nesnenin içinde tutulur.
repr() adresi göstermez; bağlantı hataları ayrıntısız bir DatabaseError'a çevrilir, sorgu
hatalarında adresin parçaları maskelenir.
"""
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pandas as pd

from errors import DatabaseError, QueryTimeout, UnsafeSQL

SUPPORTED = ("sqlite", "postgresql")
SQLGLOT_DIALECTS = {"sqlite": "sqlite", "postgresql": "postgres"}


def _normalize(allowed: dict[str, list[str]]) -> dict[str, set[str]]:
    """Karşılaştırma büyük/küçük harf duyarsız olsun; sütunu seçilmemiş tablo hiç yokmuş gibi."""
    return {t.lower(): {c.lower() for c in cols} for t, cols in allowed.items() if cols}


class QueryError(Exception):
    """Veritabanının kendi sorgu hatası (ör. olmayan sütun), adres parçaları maskelenmiş olarak.

    Yeniden denemede modele de bu metin gider."""


class Database:
    """Tek bir veritabanı bağlantısı. Oluştur: Database.from_path / from_url / from_env."""

    def __init__(self, engine, kind: str, secrets: tuple[str, ...] = (), schema: str | None = None,
                 sqlite_path: str | None = None):
        self._engine = engine
        self.kind = kind                              # "sqlite" | "postgresql"
        self.dialect = SQLGLOT_DIALECTS[kind]         # sqlglot dialect adı
        self._secrets = tuple(s for s in secrets if s and len(s) >= 3)
        self._sqlite_path = sqlite_path
        self._schema = schema

    def __repr__(self) -> str:  # adres asla görünmesin
        return f"<Database {self.kind}>"

    # --- Oluşturma ---------------------------------------------------------------------

    @classmethod
    def from_path(cls, path: Path | str) -> "Database":
        """Örnek veritabanı gibi yerel bir SQLite dosyası, salt-okunur."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        path = str(path)
        engine = create_engine(
            "sqlite://", poolclass=NullPool,
            # check_same_thread=False: Streamlit bağlantıyı farklı iş parçacığında açıp kullanabilir
            creator=lambda: sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False))
        return cls(engine, "sqlite", sqlite_path=path)

    @classmethod
    def from_url(cls, url: str, schema: str | None = None) -> "Database":
        """sqlite:///yol.db ya da postgresql://kullanici:parola@sunucu/veritabani."""
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url

        try:
            parsed = make_url(url.strip())
        except Exception:  # SQLAlchemy'nin mesajı adresi içerir: gösterme
            raise DatabaseError("err_db_url") from None
        backend = parsed.get_backend_name()
        if backend == "postgres":  # Heroku tarzı adres
            parsed, backend = parsed.set(drivername="postgresql"), "postgresql"
        if backend not in SUPPORTED:
            raise DatabaseError("err_db_unsupported", kind=backend)
        if backend == "sqlite":
            if not parsed.database or not Path(parsed.database).exists():
                raise DatabaseError("err_db_connect")
            return cls.from_path(parsed.database)

        if parsed.drivername == "postgresql":  # sürücü belirtilmemişse psycopg (3)
            parsed = parsed.set(drivername="postgresql+psycopg")
        secrets = (url.strip(), parsed.password, parsed.username, parsed.host,
                   *(str(v) for v in parsed.query.values()))
        try:
            engine = create_engine(parsed, hide_parameters=True, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 10})
        except Exception:
            raise DatabaseError("err_db_connect") from None
        db = cls(engine, "postgresql", secrets=tuple(str(s) for s in secrets if s), schema=schema)
        db.columns()  # bağlantıyı şimdi dene: hata hemen ve ayrıntısız görünsün
        return db

    @classmethod
    def from_env(cls) -> "Database | None":
        """NL2SQL_DATABASE_URL boşsa None (örnek veritabanları kullanılır)."""
        url = os.getenv("NL2SQL_DATABASE_URL", "").strip()
        if not url:
            return None
        return cls.from_url(url, schema=os.getenv("NL2SQL_DB_SCHEMA") or None)

    # --- Yardımcılar -------------------------------------------------------------------

    def scrub(self, text: str) -> str:
        """Metindeki adres parçalarını (parola, kullanıcı, sunucu) maskeler."""
        for s in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(s, "***")
        return text

    def _wrap(self, exc: Exception) -> Exception:
        """Sorgu sırasında çıkan SQLAlchemy hatasını gösterilebilir hale getir."""
        orig = getattr(exc, "orig", None) or exc  # SQLAlchemy'nin eklediği [SQL: ...] kısmı gelmesin
        return QueryError(self.scrub(str(orig).strip()))

    def _connection(self):
        """Bağlantı kurulamazsa ayrıntısız DatabaseError (sürücünün mesajı sunucu adı içerebilir)."""
        try:
            return self._engine.connect()
        except Exception:
            raise DatabaseError("err_db_connect") from None

    def _inspect(self, con):
        """Bağlantı üzerinden inspector; PostgreSQL'de şemayı da çözer."""
        from sqlalchemy import inspect

        insp = inspect(con)
        if self.kind == "postgresql" and self._schema is None:
            self._schema = insp.default_schema_name
        return insp

    @property
    def schema(self) -> str | None:
        """PostgreSQL'de kullanılan şema (varsayılan: bağlantının varsayılanı, genelde public)."""
        if self.kind == "postgresql" and self._schema is None:
            with self._connection() as con:
                self._inspect(con)
        return self._schema

    @staticmethod
    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _table_ref(self, table: str) -> str:
        return f"{self._q(self.schema)}.{self._q(table)}" if self.kind == "postgresql" else self._q(table)

    def raw_sqlite(self) -> sqlite3.Connection:
        """Yetkilendirici ve süre sınırı için ham SQLite bağlantısı. closing() ile kullan."""
        return sqlite3.connect(f"file:{self._sqlite_path}?mode=ro", uri=True, check_same_thread=False)

    def _sqlite_master(self) -> list[tuple[str, str]]:
        """(ad, CREATE TABLE metni), dosyadaki sırayla. Yalnızca SQLite."""
        with closing(self.raw_sqlite()) as con:
            return con.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()

    # --- Şema --------------------------------------------------------------------------

    def columns(self) -> dict[str, list[str]]:
        """Her tablonun sütun adları (tablolar alfabetik); arayüzde izin listesini seçtirmek için."""
        with self._connection() as con:
            try:
                insp = self._inspect(con)
                return {t: [c["name"] for c in insp.get_columns(t, schema=self._schema)]
                        for t in sorted(insp.get_table_names(schema=self._schema))}
            except Exception as exc:
                raise self._wrap(exc) from None

    def schema_text(self, allowed: dict[str, list[str]] | None = None,
                    value_columns: dict[str, list[str]] | None = None,
                    value_hint=None) -> str:
        """LLM'e bağlam olarak verilen şema (CREATE TABLE biçiminde).

        allowed verilirse yalnızca izinli tablo ve sütunlar yazılır. value_columns'taki
        sütunlar için value_hint(db, tablo, sütun) notu eklenir.
        """
        if allowed is None and value_columns:
            allowed = self.columns()
        with self._connection() as con:
            try:
                return self._schema_text(self._inspect(con), allowed, value_columns, value_hint)
            except (DatabaseError, QueryTimeout):
                raise
            except Exception as exc:
                raise self._wrap(exc) from None

    def _schema_text(self, insp, allowed, value_columns, value_hint) -> str:
        if self.kind == "sqlite":
            master = self._sqlite_master()
            if allowed is None:  # değerlendirme ve testler: dosyadaki CREATE metni olduğu gibi
                return "\n\n".join(sql for _, sql in master)
            tables = [name for name, _ in master]
            create_sql = dict(master)
        else:
            tables = sorted(insp.get_table_names(schema=self._schema))
            create_sql = {}
            if allowed is None:
                allowed = {t: [c["name"] for c in insp.get_columns(t, schema=self._schema)] for t in tables}

        ok = _normalize(allowed)
        show_values = _normalize(value_columns or {})
        parts = []
        for table in tables:
            cols_ok = ok.get(table.lower())
            if not cols_ok:
                continue
            cols = insp.get_columns(table, schema=self._schema)
            if self.kind == "sqlite":
                # Sütun satırlarındaki "-- açıklama" yorumlarını koru (ör. status değerleri)
                comments = {
                    m.group(1).lower(): m.group(2).strip()
                    for m in re.finditer(r'^\s*"?(\w+)"?\s[^\n]*?--([^\n]*)$', create_sql[table],
                                         re.MULTILINE)
                }
            else:  # PostgreSQL: COMMENT ON COLUMN
                comments = {c["name"].lower(): (c.get("comment") or "").strip() for c in cols}
            pk = {c.lower() for c in
                  (insp.get_pk_constraint(table, schema=self._schema) or {}).get("constrained_columns") or []}
            refs = {}  # yabancı anahtar, yalnızca hedefi de izinliyse yazılır
            for fk in insp.get_foreign_keys(table, schema=self._schema):
                target = fk["referred_table"]
                for col, ref_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                    if ref_col and ref_col.lower() in ok.get(target.lower(), set()):
                        refs[col.lower()] = f" REFERENCES {target}({ref_col})"
            lines = []
            for c in cols:
                name = c["name"]
                if name.lower() not in cols_ok:
                    continue
                line = f"    {name} {_type_name(c['type'])}"
                line += " PRIMARY KEY" if name.lower() in pk else ("" if c["nullable"] else " NOT NULL")
                line += refs.get(name.lower(), "")
                notes = [comments.get(name.lower())]
                if value_hint and name.lower() in show_values.get(table.lower(), set()):
                    notes.append(value_hint(self, table, name))
                lines.append((line, "; ".join(n for n in notes if n)))
            body = [
                f"{line}{',' if i < len(lines) - 1 else ''}" + (f"  -- {comment}" if comment else "")
                for i, (line, comment) in enumerate(lines)
            ]
            parts.append(f"CREATE TABLE {table} (\n" + "\n".join(body) + "\n)")
        return "\n\n".join(parts)

    def distinct_values(self, table: str, column: str, limit: int, timeout: float) -> list:
        """Bir sütunun NULL olmayan farklı değerleri (en fazla limit tane), süre sınırıyla.

        Süre aşılırsa QueryTimeout. Tablo/sütun adları çağıranın listesinden gelir."""
        sql = (f"SELECT DISTINCT {self._q(column)} FROM {self._table_ref(table)} "
               f"WHERE {self._q(column)} IS NOT NULL LIMIT {int(limit)}")
        if self.kind == "sqlite":
            with closing(self.raw_sqlite()) as con:
                deadline = time.monotonic() + timeout
                con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
                try:
                    return [r[0] for r in con.execute(sql)]
                except sqlite3.OperationalError as exc:
                    if time.monotonic() > deadline:
                        raise QueryTimeout("err_timeout", seconds=f"{timeout:g}") from None
                    raise QueryError(str(exc)) from None
        return list(self._pg_query(sql, timeout).iloc[:, 0])

    # --- Sorgu çalıştırma --------------------------------------------------------------

    def execute(self, sql: str, allowed: dict[str, list[str]] | None, timeout: float,
                max_rows: int) -> pd.DataFrame:
        """Doğrulanmış (validate_sql + check_access) bir SELECT'i çalıştırır, en fazla max_rows satır."""
        if self.kind == "sqlite":
            return self._sqlite_execute(f"SELECT * FROM ({sql}) LIMIT {int(max_rows)}", allowed, timeout)
        return self._pg_query(f"SELECT * FROM ({sql}) AS q LIMIT {int(max_rows)}", timeout)

    def _sqlite_execute(self, sql: str, allowed, timeout: float) -> pd.DataFrame:
        from nl2sql import _authorizer  # yetkilendirici SQLite'a özgü; nl2sql'de belgelenmiş durur

        denied: list[str] = []
        ops: list[int] = []
        with closing(self.raw_sqlite()) as con:
            if allowed is not None:
                real_tables = {r[0].lower() for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
                con.set_authorizer(_authorizer(_normalize(allowed), real_tables, denied, ops))
            deadline = time.monotonic() + timeout
            # SQLite her ~10 bin sanal makine adımında bu fonksiyonu çağırır;
            # sıfırdan farklı dönerse sorgu yarıda kesilir ("interrupted").
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            try:
                return pd.read_sql_query(sql, con)
            except Exception as exc:
                if denied or ops:
                    raise UnsafeSQL("err_denied", names=sorted(set(denied)),
                                    ops=sorted(set(ops))) from exc
                if time.monotonic() > deadline:
                    raise QueryTimeout("err_timeout", seconds=f"{timeout:g}") from exc
                raise

    def _pg_query(self, sql: str, timeout: float) -> pd.DataFrame:
        # Ham psycopg imleci: SQLAlchemy text() ":ad" kalıplarını parametre sanar, sürücüye
        # parametresiz verilen sorguda ise "%" (LIKE 'a%') olduğu gibi kalır.
        with self._connection() as con:
            raw = con.connection.driver_connection
            try:
                raw.rollback()  # temiz bir transaction ile başla
                with raw.cursor() as cur:
                    cur.execute(sql)
                    cols = [d.name for d in cur.description]
                    rows = cur.fetchall()
                return pd.DataFrame(rows, columns=cols)
            except Exception as exc:
                raise self._wrap(exc) from None
            finally:
                raw.rollback()


def _type_name(sa_type) -> str:
    try:
        return str(sa_type)
    except Exception:  # bazı özel türler derleyici olmadan yazılamaz
        return type(sa_type).__name__.upper()
