# Ask Your Data in Plain Language

**[Live demo](https://nl2sql-test.streamlit.app/)**

A text-to-SQL tool. You ask a question in plain language (English or Turkish), Claude turns it into a SQLite query, the query runs read-only on a sample e-commerce database behind a column-level allowlist, and the result is shown as a table and a chart.

*Türkçe özet [aşağıda](#türkçe).*

![Screenshot](docs/screenshot.png)

## Highlights

- **Column-level allowlist.** The model only sees the schema of the columns the user selects. Generated SQL is checked in five layers (see [Security layers](#security-layers)).
- **Assumptions on screen.** If a question is ambiguous, the model states the decision it made ("only completed orders were counted") above the result.
- **Measured prompt changes.** Every prompt change is reported with before/after numbers; the prompt is never tuned against the holdout sets.
- **Bilingual.** English by default, Turkish selectable. Each language has its own sample database with the same numeric structure; the model answers in the language of the question.

## Evaluation results

Model `claude-sonnet-5-5`. Metric: execution accuracy (the generated SQL returns the same result as the reference SQL). Each question was asked 3 times unless noted.

| Set | Accuracy |
|---|---|
| Dev set, Turkish (20 questions × 3) | 60/60 |
| Dev set, English (20 questions × 3, `shop_en.db`) | 60/60 |
| Holdout v1, Turkish (20 × 3) | 53/60 (88.3%) |
| Holdout v2, Turkish (20 × 3, unseen while tuning) | 60/60 |

| Assumption behaviour | Dev (TR) | Dev (EN) | Holdout v2 |
|---|---|---|---|
| Clear questions: no unnecessary assumption | 38/39 | 39/39 | 9/18 |
| Ambiguous questions: decision stated | 21/21 | 20/21 | 42/42 |

- None of the 7 failed holdout v1 attempts is a SQL error: 4 return a correctly sorted full list instead of one row, 3 are a single question with two reasonable interpretations.
- The dev-set figure for unnecessary assumptions (~97%) does not generalize: on unseen holdout v2 questions it is about 50%. The remaining items are true but unnecessary (the model cannot see the data, so it cannot tell whether an interpretation would change the number).
- Translating the prompt to English did not change accuracy on the Turkish sets.
- Full history, including steps that were rolled back: [evals/RAPOR.md](evals/RAPOR.md) (Turkish).

## Security layers

The model never gets write access, and never sees columns the user did not allow.

1. **Schema allowlist.** Only the selected tables and columns are sent to the model as `CREATE TABLE` statements. All columns are selected when the page opens, so a visitor can try an example question right away; any table or column can be turned off. No data rows are sent while generating SQL. Optionally, the distinct values of low-cardinality columns (status, category) can be shown, capped at 20 values of 40 characters each.
2. **`validate_sql`.** Only a single `SELECT` (or `WITH ... SELECT`) is allowed; data-modifying keywords are rejected.
3. **`check_access`.** The SQL is parsed with [sqlglot](https://github.com/tobymao/sqlglot); aliases, subqueries and CTEs are resolved to real tables, and any table or column outside the allowlist is rejected by name. `SELECT *` and `table.*` are refused on tables with hidden columns.
4. **SQLite authorizer.** `set_authorizer` enforces the same allowlist inside the database at compile time, as a backstop for anything the parser misses.
5. **Read-only connection and timeout.** The database is opened in `mode=ro`; each query is stopped after 5 seconds (`NL2SQL_QUERY_TIMEOUT`).

Unauthorized access and timeouts are not retried; other SQL errors are sent back to the model once for a fix.

These five layers describe the sample SQLite databases. For PostgreSQL see [Connect your own database](#connect-your-own-database): layer 4 has no PostgreSQL equivalent and is replaced by weaker checks.

**Optional interpretation.** A second model call can explain the result in plain language. It is off by default because this is the only place where result rows reach the model: the first 50 rows plus a pandas-computed summary (min/max with row labels, mean, sum over all rows). The model must take rankings only from that summary, cell contents are marked as data, and the text is labelled as AI-generated.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```

The sample databases (`shop.db`, `shop_en.db`) are created on first run; `python seed_db.py` rebuilds both. Set `NL2SQL_MODEL` to try another model. "Today" is fixed to the last day of the sample data (2026-11-20), so "last month" always means October 2026.

### Public deployment

Anyone with the link can ask questions with the server's key, so there are three safeguards:

1. **Spending limit (the real safeguard).** Set a monthly limit on the key's workspace in the Anthropic Console.
2. **Daily call limit.** `NL2SQL_DAILY_LIMIT` caps the total model calls per day with the shared key, e.g. `100`. Every question, every automatic retry after a SQL error, and every interpretation uses one call; when no call is left, the retry is skipped and the first error is shown. Unset or `0` means no limit. The counter is in memory and resets on restart.
3. **Visitor's own key.** A visitor can enter their own key in the sidebar; their calls skip the daily limit. The key is kept only in that browser session.

On Streamlit Community Cloud, put `ANTHROPIC_API_KEY` and `NL2SQL_DAILY_LIMIT` in the app's Secrets as top-level keys. Never commit the key.

## Connect your own database

You can point the app at your own database and run it **on your own machine**. The public demo does not change: when no address is given, the sample SQLite databases open as before. Supported: **SQLite** and **PostgreSQL**.

### 1. Create a read-only user (PostgreSQL)

The database user's privileges are the real boundary, so give the app a user that can only read what it needs:

```sql
CREATE ROLE nl2sql_reader LOGIN PASSWORD 'change-me';
GRANT CONNECT ON DATABASE mydb TO nl2sql_reader;
GRANT USAGE ON SCHEMA public TO nl2sql_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl2sql_reader;       -- or only the tables you need
ALTER ROLE nl2sql_reader SET default_transaction_read_only = on;

-- Optional, recommended for personal data: grant columns, not whole tables
REVOKE SELECT ON customers FROM nl2sql_reader;
GRANT SELECT (id, city, signup_date) ON customers TO nl2sql_reader;

-- PostgreSQL 14 and older only: nobody should be able to create objects in public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

When the app starts it checks whether the connected user can write (`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` on a table, `CREATE` in the schema or database, superuser). If it can, a red warning stays at the top of the page.

### 2. Set the environment variables and run

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:NL2SQL_DATABASE_URL = "postgresql://nl2sql_reader:change-me@localhost:5432/mydb"
$env:NL2SQL_GLOSSARY = "C:\path\to\glossary.md"     # optional
streamlit run app.py
```

| Variable | Meaning |
|---|---|
| `NL2SQL_DATABASE_URL` | `postgresql://user:password@host:5432/db` or `sqlite:///path/to/file.db`. Empty: sample databases. |
| `NL2SQL_DB_SCHEMA` | PostgreSQL schema to use (default: the connection's default, usually `public`). Only one schema. |
| `NL2SQL_GLOSSARY` | Path to a business glossary (below). Optional. |
| `NL2SQL_QUERY_TIMEOUT` | Seconds per query (default 5). |
| `ANTHROPIC_API_KEY`, `NL2SQL_MODEL` | As in [Setup](#setup). |

The address is never shown in the page, in error messages or in logs: connection errors are reported without details, and parts of the address are masked in database error messages.

### 3. Business glossary (optional)

Rules that belong to your data, not to SQL, go in a Markdown file. Only lines that start with `- ` (and their continuation lines indented by two spaces) are sent to the model; headings and notes are for people. The sample databases ship with their own glossaries in [`glossaries/`](glossaries/).

```markdown
# Business glossary: sales database

- Revenue = quantity * unit_price. Count only orders with status = 'shipped' unless asked otherwise.
- An active customer is one with an order in the last 90 days.
- Fiscal year starts on 1 April; "this year" means the current fiscal year.
```

### What reaches the model

- The schema of the tables and columns you select in the sidebar: names, types, primary/foreign keys and column comments (`COMMENT ON COLUMN`). All columns are selected when the page opens, so **turn off sensitive columns first**.
- The glossary lines and the question.
- Only if you pick them under "Columns whose values are shown to the model": up to 20 distinct values per column, 40 characters each.
- Only if you press "Interpret": the first 50 result rows and a numeric summary.
- On a retry: the generated SQL and the database's error message.
- Never: the connection address, other rows, columns you did not select.

### PostgreSQL security layers

| Layer | SQLite (sample data) | PostgreSQL |
|---|---|---|
| 1. Schema allowlist | Selected columns only | Same (read with the SQLAlchemy inspector) |
| 2. `validate_sql` | Single `SELECT`, no modifying keywords | Same, plus PostgreSQL keywords (`INTO`, `COPY`, `TRUNCATE`, `GRANT`, `CALL`, `LOCK`, ...) |
| 3. `check_access` (sqlglot) | Allowlist, aliases, CTEs, `*` | Same with the `postgres` dialect, plus, on tables with hidden columns: whole-row references (`SELECT c FROM customers c`, `c::text`, `(c).name`, `json_agg(c)`, `(c.*)::text`) and column alias lists (`customers AS c(id, city)`) are refused. Tables in other schemas (`pg_catalog`, `information_schema`, ...) are refused, and functions are allowlisted (`pg_read_file`, `set_config`, `current_setting`, `version()`, `current_user`, `dblink`, ... are refused) |
| 4. Database-side check | SQLite authorizer checks every column read | No authorizer; two checks instead. **Shadow CTEs:** every allowed table with hidden columns is replaced, for that query, by `WITH customers AS NOT MATERIALIZED (SELECT id, city FROM public.customers)`. Any reference to the table by name, including whole-row references the parser might miss, returns only the allowed columns. `public.customers` is rewritten to use the shadow. **`EXPLAIN`:** every table PostgreSQL will read must be allowed and in the schema. The user's `GRANT`s remain the final boundary |
| 5. Read-only + timeout | `mode=ro` + progress handler | Every query in its own `SET TRANSACTION READ ONLY` transaction, rolled back afterwards, with `statement_timeout`; the connection also sets `default_transaction_read_only` |

**What is still weaker on PostgreSQL than on SQLite.** Hidden columns are now enforced on both sides: sqlglot refuses the query, and the shadow CTE means that the database cannot return a hidden column when a table is reached by its name. The tests run 45 known bypass queries (whole rows, row comparisons, `LATERAL`, `ONLY`, `TABLESAMPLE`, column alias lists, schema-qualified names, ...) against the database layer alone, and the 38 whole-row and escape queries among them against the parser alone; neither layer leaks on its own. What remains:

- **Functions are checked only by sqlglot.** The shadow covers names in the query, not SQL that a function would run from text. Functions that do this (`query_to_xml`, `dblink`, ...) are refused by the allowlist, but no database-side check backs it up. SQLite's authorizer, by contrast, also sees reads made inside functions.
- **The real table's row type is not shadowed.** Through a function such as `json_populate_record(null::customers, ...)`, the names and types of hidden columns (not their values) could be read. The allowlist refuses those functions.
- **The rewrite is this project's own code.** A bug in it would only be caught by the database user's privileges. Column-level `GRANT`s (above) remain the strongest guarantee for personal data.
- **Side effects:** `TABLESAMPLE` and column alias lists do not work on tables with hidden columns.

### Limits

- Supported: SQLite and PostgreSQL. Tested with PostgreSQL 16. MySQL, SQL Server and others are not supported.
- Model accuracy on PostgreSQL is measured only on the `questions` set (`--postgres`, below). The holdout sets have no PostgreSQL references.
- One schema; tables only (views are not listed).
- On tables with hidden columns, `TABLESAMPLE`, column alias lists and whole-row expressions are refused. They work on fully allowed tables.
- "Today" is the real date for your database (the demo uses a fixed date).
- No row-level filtering: if a column is allowed, all of its rows can be queried.

## Running the evaluation

```bash
python evals/run_evals.py --check-gold                   # no API: show reference results
python evals/run_evals.py --set questions --runs 3       # Turkish dev set
python evals/run_evals.py --set questions_en --runs 3    # English dev set (shop_en.db)
python evals/run_evals.py --set holdout_v2 --runs 3      # Turkish holdout
python evals/run_evals.py --only 13 15                   # selected questions only
python evals/run_evals.py --set questions --postgres     # same data copied into a temporary PostgreSQL
```

`--postgres` starts a temporary PostgreSQL server (Docker or `pgserver`, see `pg_local.py`), copies the sample data into it with real `DATE` and `NUMERIC` types, runs the set there and removes it. Questions whose reference uses SQLite-only syntax have a `referans_sql_postgres` field in the YAML.

Tests run without an API key. PostgreSQL tests start a temporary server: a Docker container if Docker is running, otherwise the embedded `pgserver` package (`pip install -r requirements-dev.txt`, inside the virtual environment only). If neither works they are skipped, and the end of the test output says why. `NL2SQL_TEST_PG=off` skips them on purpose; `NL2SQL_TEST_PG_URL` uses an existing server.

Column names, column order and extra columns are ignored; row order matters only when the question asks for sorting. Decimals use a 0.5% relative tolerance; integers must match exactly. Ambiguous questions can list alternative reference SQLs (`kabul_edilen`). Results are saved as JSON under `evals/results/`.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI |
| `i18n.py` | All UI texts and error messages, English and Turkish |
| `nl2sql.py` | Core: prompts, SQL generation, security checks, interpretation |
| `db.py` | Database layer: sample SQLite or your own SQLite/PostgreSQL (SQLAlchemy), read-only execution |
| `errors.py` | Error types shown to the user |
| `glossaries/` | Business glossaries of the sample databases |
| `seed_db.py` | Builds `shop.db` (Turkish) and `shop_en.db` (English) from the same seed |
| `charts.py` | Altair charts: bars in SQL order, chronological date axis |
| `quota.py` | Daily call counter for the shared key |
| `evals/` | Question sets (`questions`, `questions_en`, `holdout`, `holdout_v2`), runner and report |
| `test_*.py`, `conftest.py` | Tests; none of them need an API key (`python -m pytest -q`) |

## License

[MIT](LICENSE) © 2026 Muhammed Ahmet Ertemiz

---

## Türkçe

Doğal dille (Türkçe ya da İngilizce) sorulan soruyu Claude ile SQLite sorgusuna çevirir, örnek bir e-ticaret veritabanında salt-okunur çalıştırır ve sonucu tablo ve grafik olarak gösterir. Arayüz varsayılan olarak İngilizcedir; kenar çubuğunun en üstündeki seçiciden Türkçeye geçilir. Türkçe seçilince Türkçe veritabanı (`shop.db`) açılır.

- Model yalnızca kullanıcının seçtiği sütunların şemasını görür. Üretilen SQL beş katmanda denetlenir: izin listesi, `validate_sql`, sqlglot ile `check_access`, SQLite yetkilendiricisi, salt-okunur bağlantı ve süre sınırı.
- Belirsiz sorularda model verdiği kararı "Varsayımlar" başlığıyla sonucun üstünde yazar.
- Değerlendirme raporu, tüm ölçümler ve geri alınan adımlarla birlikte Türkçe: [evals/RAPOR.md](evals/RAPOR.md). Holdout sorusu yazım kılavuzu: [evals/HOLDOUT_KILAVUZU.md](evals/HOLDOUT_KILAVUZU.md).

- Kendi veritabanını bağlamak için (yalnızca kendi bilgisayarında): `NL2SQL_DATABASE_URL` ile SQLite ya da PostgreSQL adresi ver, salt-okunur bir kullanıcı kullan; iş kuralların için `NL2SQL_GLOSSARY` ile bir sözlük dosyası ver. Ayrıntılar ve PostgreSQL'de zayıflayan güvenlik katmanı: "Connect your own database".

Kurulum yukarıdaki "Setup" bölümündeki komutlarla yapılır.

Lisans: [MIT](LICENSE).
