"""Çekirdek mantık: şema okuma, LLM ile SQL üretme, güvenlik kontrolü, sorgu çalıştırma.

Arayüzden (app.py) bilerek ayrı tutuldu: böylece test edilebilir ve
ileride Streamlit yerine başka bir arayüz (API, Next.js) takılabilir.
"""
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pandas as pd

MODEL = os.getenv("NL2SQL_MODEL", "claude-sonnet-5-5")
MAX_ROWS = 500
QUERY_TIMEOUT_S = float(os.getenv("NL2SQL_QUERY_TIMEOUT", "5"))  # tek sorgu için üst süre
MAX_DISTINCT_VALUES = 20   # bundan fazla farklı değeri olan sütun kategorik sayılmaz, değerleri gösterilmez
MAX_VALUE_CHARS = 40       # tek bir değerin modele gönderilen en fazla uzunluğu
VALUE_SCAN_TIMEOUT_S = 2.0 # büyük tablolarda değer taramasının üst süresi

SYSTEM_PROMPT = """Sen bir veri analistisin. Kullanıcının sorusunu SQLite sorgusuna çevirirsin.

Veritabanı şeması:
{schema}

Kurallar:
- Yalnızca tek bir SELECT (veya WITH ... SELECT) sorgusu yaz. Veriyi değiştiren komut yazma.
- Yalnızca şemadaki tablo ve sütunları kullan; olmayan sütun uydurma.
- Tarihler 'YYYY-MM-DD' metni olarak saklanır; strftime / date fonksiyonlarını kullan. Bugün: {today}.
- Ciro = quantity * unit_price. Aksi istenmedikçe ciro hesabında yalnızca status = 'tamamlandi' siparişleri say.
- "En az satan", "X adetten az", "hiç sipariş vermeyen" gibi sorularda sıfır değerli satırları kaybetme:
  ana tablodan başla (ör. FROM products, FROM customers), hareket tablolarını LEFT JOIN ile bağla,
  tarih/durum filtresini WHERE'e değil alt sorguya veya ON koşuluna koy, boş toplamı COALESCE(..., 0) ile 0 yap.
- Sütunlara okunaklı Türkçe takma adlar ver (ör. toplam_ciro).
- Soru şemayla cevaplanamıyorsa sql alanını boş bırak ve nedenini explanation'da yaz.

Yalnızca şu JSON'u döndür, başka hiçbir şey yazma:
{{"sql": "...", "explanation": "sorgunun ne yaptığını 1-2 cümleyle anlat",
  "chart": "bar" | "line" | "none", "x": "x ekseni sütunu veya null", "y": "y ekseni sütunu veya null"}}"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)


class UnsafeSQL(ValueError):
    pass


class QueryTimeout(RuntimeError):
    pass


# İzin listesi: {"tablo": ["sütun", ...]}. None = her şeye izin (değerlendirme ve testler için).
Allowed = dict[str, list[str]]


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    """Salt-okunur bağlantı. closing() ile kullan: `with sqlite3.connect()` bağlantıyı kapatmaz."""
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def list_columns(db_path: Path) -> dict[str, list[str]]:
    """Her tablonun sütun adları; arayüzde izin listesini seçtirmek için."""
    with closing(_connect_ro(db_path)) as con:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {t: [r[1] for r in con.execute(f"PRAGMA table_info({_quote(t)})")] for t in tables}


def _normalize(allowed: Allowed) -> dict[str, set[str]]:
    """Karşılaştırma büyük/küçük harf duyarsız olsun; sütunu seçilmemiş tablo hiç yokmuş gibi."""
    return {t.lower(): {c.lower() for c in cols} for t, cols in allowed.items() if cols}


def _value_hint(con: sqlite3.Connection, table: str, column: str) -> str:
    """Kategorik bir sütunun farklı değerlerini modele gösterilecek kısa bir nota çevirir.

    Bu, modele GERÇEK VERİ gönderilen tek yerdir; bu yüzden sınırlı tutulur:
    - yalnızca kullanıcının işaretlediği sütunlar,
    - en fazla MAX_DISTINCT_VALUES farklı değer (fazlası varsa hiçbiri gönderilmez:
      sütun büyük ihtimalle ad, e-posta gibi kişiye özgü bir alandır),
    - her değer MAX_VALUE_CHARS karakterle kesilir.
    """
    deadline = time.monotonic() + VALUE_SCAN_TIMEOUT_S
    con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        values = [r[0] for r in con.execute(
            f"SELECT DISTINCT {_quote(column)} FROM {_quote(table)} "
            f"WHERE {_quote(column)} IS NOT NULL LIMIT {MAX_DISTINCT_VALUES + 1}"
        )]
    except sqlite3.OperationalError:
        return "değerler taranamadı (tablo çok büyük)"
    finally:
        con.set_progress_handler(None, 0)
    if len(values) > MAX_DISTINCT_VALUES:
        return f"{MAX_DISTINCT_VALUES}'den fazla farklı değer var, gösterilmedi"
    shown = sorted(str(v)[:MAX_VALUE_CHARS].replace("'", "''") for v in values)
    return "değerler: " + ", ".join(f"'{v}'" for v in shown)


def get_schema(db_path: Path, allowed: Allowed | None = None,
               value_columns: Allowed | None = None) -> str:
    """LLM'e bağlam olarak verilen şema.

    allowed verilirse yalnızca izinli tablo ve sütunlar yazılır: model izinsiz bir
    sütunun ADINI bile görmez. Asıl koruma yine de run_sql'deki yetkilendiricidir.

    value_columns verilirse bu sütunların farklı değerleri yorum olarak eklenir
    (ör. status -> 'iade', 'iptal', 'tamamlandi'), böylece model WHERE koşulunda
    doğru değeri yazar. Yalnızca izinli sütunlar için geçerlidir.
    """
    if allowed is None and value_columns:
        allowed = list_columns(db_path)
    with closing(_connect_ro(db_path)) as con:
        rows = con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if allowed is None:
            return "\n\n".join(sql for _, sql in rows)

        ok = _normalize(allowed)
        show_values = _normalize(value_columns or {})
        parts = []
        for table, create_sql in rows:
            cols_ok = ok.get(table.lower())
            if not cols_ok:
                continue
            # Sütun satırlarındaki "-- açıklama" yorumlarını koru (ör. status değerleri)
            comments = {
                m.group(1).lower(): m.group(2).strip()
                for m in re.finditer(r'^\s*"?(\w+)"?\s[^\n]*?--([^\n]*)$', create_sql, re.MULTILINE)
            }
            refs = {  # yabancı anahtar, yalnızca hedefi de izinliyse yazılır
                fk[3].lower(): f" REFERENCES {fk[2]}({fk[4]})"
                for fk in con.execute(f"PRAGMA foreign_key_list({_quote(table)})")
                if fk[4] and fk[4].lower() in ok.get(fk[2].lower(), set())
            }
            lines = []
            for _, name, col_type, notnull, _, pk in con.execute(f"PRAGMA table_info({_quote(table)})"):
                if name.lower() not in cols_ok:
                    continue
                line = f"    {name} {col_type}"
                line += " PRIMARY KEY" if pk else (" NOT NULL" if notnull else "")
                line += refs.get(name.lower(), "")
                notes = [comments.get(name.lower())]
                if name.lower() in show_values.get(table.lower(), set()):
                    notes.append(_value_hint(con, table, name))
                lines.append((line, "; ".join(n for n in notes if n)))
            body = [
                f"{line}{',' if i < len(lines) - 1 else ''}" + (f"  -- {comment}" if comment else "")
                for i, (line, comment) in enumerate(lines)
            ]
            parts.append(f"CREATE TABLE {table} (\n" + "\n".join(body) + "\n)")
    return "\n\n".join(parts)


def validate_sql(sql: str) -> str:
    """LLM çıktısına güvenme: yalnızca tek bir salt-okunur sorguya izin ver."""
    cleaned = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL).strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQL("Boş sorgu.")
    if ";" in cleaned:
        raise UnsafeSQL("Birden fazla SQL ifadesine izin verilmiyor.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeSQL("Yalnızca SELECT sorgularına izin veriliyor.")
    # Metin sabitlerinin içindeki kelimeler yanlış alarm vermesin
    without_strings = re.sub(r"'(?:[^']|'')*'", "''", cleaned)
    if FORBIDDEN.search(without_strings):
        raise UnsafeSQL("Sorgu veriyi değiştiren bir komut içeriyor.")
    return cleaned


def _authorizer(allowed: dict[str, set[str]], real_tables: set[str], denied: list[str]):
    """SQLite, sorguyu derlerken her tablo/sütun okumasını bu fonksiyona sorar.

    Regex'ten farklı olarak SQL'i SQLite'ın kendisi çözümler; takma ad, alt sorgu,
    CTE, SELECT * gibi hileler işe yaramaz. İzinsiz her okuma reddedilir.
    """
    always_ok = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}

    def check(action, arg1, arg2, _db, _trigger):
        if action in always_ok:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            table = (arg1 or "").lower()
            # Özyinelemeli CTE kendi adını "tablo" olarak okur (ör. WITH RECURSIVE r ...).
            # Gerçek bir tablo değilse serbest; iç tablolar (sqlite_*, pragma_*) her zaman kapalı.
            # Gerçek bir tabloyla aynı adı taşıyan CTE yine kontrolden geçer (güvenli tarafta kalır).
            if table not in real_tables and not table.startswith(("sqlite_", "pragma_")):
                return sqlite3.SQLITE_OK
            cols = allowed.get(table)
            # arg2 == "": tablo kullanılıyor ama sütun okunmuyor (ör. COUNT(*))
            if cols and (arg2 == "" or (arg2 or "").lower() in cols):
                return sqlite3.SQLITE_OK
            denied.append(f"{arg1}.{arg2}" if arg2 else str(arg1))
        else:  # PRAGMA, ATTACH vb. her şey: zaten salt-okunuruz ama yine de kapalı
            denied.append(f"işlem {action}")
        return sqlite3.SQLITE_DENY

    return check


def run_sql(db_path: Path, sql: str, allowed: Allowed | None = None,
            timeout: float = QUERY_TIMEOUT_S) -> pd.DataFrame:
    """Savunma katmanları: validate_sql (regex) -> yetkilendirici (izin listesi)
    -> salt-okunur bağlantı -> süre sınırı."""
    safe = validate_sql(sql)
    denied: list[str] = []
    deadline = time.monotonic() + timeout
    with closing(_connect_ro(db_path)) as con:
        if allowed is not None:
            real_tables = {r[0].lower() for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
            con.set_authorizer(_authorizer(_normalize(allowed), real_tables, denied))
        # SQLite her ~10 bin sanal makine adımında bu fonksiyonu çağırır;
        # sıfırdan farklı dönerse sorgu yarıda kesilir ("interrupted").
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            return pd.read_sql_query(f"SELECT * FROM ({safe}) LIMIT {MAX_ROWS}", con)
        except Exception as exc:
            if denied:
                raise UnsafeSQL(
                    "Sorgu izin verilmeyen tablo/sütunlara erişmeye çalıştı: "
                    + ", ".join(sorted(set(denied)))
                ) from exc
            if time.monotonic() > deadline:
                raise QueryTimeout(
                    f"Sorgu {timeout:g} saniyede bitmediği için durduruldu. "
                    "Soruyu daraltmayı dene (ör. tarih aralığı ekle)."
                ) from exc
            raise


def parse_llm_json(text: str) -> dict:
    """Model bazen JSON'u ```json bloğuna sarar; ilk { ... } gövdesini al."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Model JSON döndürmedi: {text[:200]}")
    data = json.loads(match.group(0))
    return {
        "sql": (data.get("sql") or "").strip(),
        "explanation": data.get("explanation") or "",
        "chart": data.get("chart") if data.get("chart") in ("bar", "line") else "none",
        "x": data.get("x"),
        "y": data.get("y"),
    }


def response_text(content) -> str:
    """Cevap bir blok listesidir; model önce 'thinking' bloğu döndürebilir.

    Bu yüzden content[0].text güvenli değil: yalnızca 'text' türündeki blokları topla.
    """
    return "".join(block.text for block in content if block.type == "text")


def generate_sql(question: str, schema: str, today: str, error_feedback: str | None = None) -> dict:
    """Soruyu Claude'a gönderir. error_feedback doluysa önceki hatayı düzelttirir."""
    import anthropic  # geç import: testler API anahtarı olmadan çalışabilsin

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY ortam değişkenini okur
    messages = [{"role": "user", "content": question}]
    if error_feedback:
        messages[0]["content"] += (
            f"\n\nÖnceki denemen şu hatayı verdi, düzelt:\n{error_feedback}"
        )
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,  # düşünme (thinking) de bu sınırdan yer; 1024 cevabı kesebilir
        system=SYSTEM_PROMPT.format(schema=schema, today=today),
        messages=messages,
    )
    return parse_llm_json(response_text(response.content))


def answer(question: str, db_path: Path, today: str, max_retries: int = 1,
           allowed: Allowed | None = None, value_columns: Allowed | None = None) -> dict:
    """Uçtan uca: soru -> SQL -> sonuç. SQL hata verirse modele hatayı gösterip bir kez daha dener.

    İzinsiz erişim (UnsafeSQL) ve süre aşımı (QueryTimeout) yeniden denenmez; kullanıcıya gösterilir.
    """
    schema = get_schema(db_path, allowed, value_columns)
    feedback = None
    for attempt in range(max_retries + 1):
        result = generate_sql(question, schema, today, feedback)
        if not result["sql"]:
            return {**result, "df": None, "error": None}
        try:
            df = run_sql(db_path, result["sql"], allowed)
            return {**result, "df": df, "error": None}
        except (UnsafeSQL, QueryTimeout) as exc:  # yeniden deneme bekleme süresini ikiye katlardı
            return {**result, "df": None, "error": str(exc)}
        except Exception as exc:  # SQL sözdizimi / olmayan sütun vb.
            feedback = f"SQL: {result['sql']}\nHata: {exc}"
            if attempt == max_retries:
                return {**result, "df": None, "error": str(exc)}
