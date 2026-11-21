"""Değerlendirme: evals/questions.yaml'daki soruları modele sorar, doğruluk oranını ölçer.

Çalıştır (proje klasöründen):
    python evals/run_evals.py               # modeli çağırır (ANTHROPIC_API_KEY gerekir)
    python evals/run_evals.py --check-gold  # API'siz: yalnızca referans SQL'leri çalıştırıp gösterir
    python evals/run_evals.py --only 13 15  # yalnızca seçilen soruları modele sor

Ölçüt "çalıştırma doğruluğu"dur (execution accuracy): modelin SQL metni referans
SQL ile aynı olmak zorunda değil; önemli olan ikisinin de aynı SONUCU döndürmesi.
Çünkü aynı soruyu cevaplayan çok sayıda farklı ama doğru SQL yazılabilir.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from itertools import product
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # "python evals/run_evals.py" ile çalışınca nl2sql bulunabilsin

import seed_db  # noqa: E402
from nl2sql import MODEL, answer, format_sql, run_sql  # noqa: E402

DB_PATH = ROOT / "shop.db"
QUESTIONS = ROOT / "evals" / "questions.yaml"
RESULTS_DIR = ROOT / "evals" / "results"
LEVELS = ("kolay", "orta", "zor")
# seed_db.build içindeki sabit "bugün". Sabit tutuyoruz ki "geçen ay", "son 3 ay"
# gibi göreli sorular her gün aynı cevabı versin.
TODAY = "2026-11-20"


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _norm(value):
    """Hücreyi karşılaştırılabilir hale getir: 5 ile 5.0, 1234.5 ile 1234.50001 eşit sayılsın."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) or hasattr(value, "item"):  # numpy sayıları dahil
        return round(float(value), 2)
    return str(value).strip()


def results_match(gold: pd.DataFrame, pred: pd.DataFrame, ordered: bool = False) -> bool:
    """Tahmin edilen sonuç, beklenen sonuçla aynı veriyi içeriyor mu?

    - Sütun ADLARI önemsiz (model 'toplam_ciro' der, referans 'ciro' diyebilir).
    - Sütun SIRASI önemsiz.
    - Modelin fazladan sütun döndürmesi serbest (ör. adın yanında id); ama
      beklenen her sütun tahminde bulunmalı.
    - Satır sırası yalnızca ordered=True ise önemli.
    - Sayılar 2 basamağa yuvarlanarak karşılaştırılır.
    """
    if len(gold) != len(pred) or len(gold.columns) > len(pred.columns):
        return False

    gold_cols = [[_norm(v) for v in gold[c]] for c in gold.columns]
    pred_cols = [[_norm(v) for v in pred.iloc[:, i]] for i in range(len(pred.columns))]

    def key(col):  # sıra önemsizse sütunu sıralayıp karşılaştır
        return col if ordered else sorted(col, key=repr)

    # Her beklenen sütun için, değerleri birebir tutan aday tahmin sütunları
    candidates = [
        [i for i, pc in enumerate(pred_cols) if key(pc) == key(gc)] for gc in gold_cols
    ]
    if any(not c for c in candidates):
        return False

    # Sütunlar tek tek tutsa da satırlar tutmayabilir (değerler satırlar arası
    # karışmış olabilir); bu yüzden satırları bütün olarak da karşılaştır.
    gold_rows = list(zip(*gold_cols))
    for choice in product(*candidates):
        if len(set(choice)) < len(choice):
            continue  # aynı tahmin sütunu iki beklenen sütuna eşlenemez
        pred_rows = list(zip(*(pred_cols[i] for i in choice)))
        if ordered:
            if pred_rows == gold_rows:
                return True
        elif sorted(pred_rows, key=repr) == sorted(gold_rows, key=repr):
            return True
    return False


def evaluate_one(item: dict, db_path: Path, answer_fn=answer) -> dict:
    """Tek soruyu değerlendir. answer_fn parametresi testlerde sahte model takabilmek için."""
    out = {"id": item["id"], "soru": item["soru"], "zorluk": item["zorluk"],
           "kategori": item["kategori"], "uretilen_sql": "", "referans_sql": item["referans_sql"],
           "gecti": False, "neden": ""}
    try:
        result = answer_fn(item["soru"], db_path, today=TODAY)
    except Exception as exc:  # ağ hatası, geçersiz JSON vb.
        out["neden"] = f"Model çağrısı başarısız: {exc}"
        return out
    out["uretilen_sql"] = result["sql"]
    out["aciklama"] = result.get("explanation", "")

    if item["referans_sql"] is None:  # şemayla cevaplanamayan soru: model SQL yazmamalı
        out["gecti"] = not result["sql"]
        out["neden"] = "" if out["gecti"] else "Cevaplanamaz soruya SQL üretti"
        return out

    if not result["sql"]:
        out["neden"] = "SQL üretmedi"
    elif result["error"]:
        out["neden"] = f"SQL hatası: {result['error']}"
    elif results_match(run_sql(db_path, item["referans_sql"]), result["df"], item["sirali"]):
        out["gecti"] = True
    else:
        pred = result["df"]
        out["neden"] = f"Sonuç beklenenden farklı ({len(pred)} satır döndü)"
    return out


def summarize(results: list[dict]) -> dict:
    """Toplam ve zorluk seviyesine göre doğruluk."""
    def rate(rows):
        return {"gecen": sum(r["gecti"] for r in rows), "toplam": len(rows),
                "yuzde": round(100 * sum(r["gecti"] for r in rows) / len(rows), 1) if rows else None}

    return {"toplam": rate(results),
            "zorluk": {lvl: rate([r for r in results if r["zorluk"] == lvl]) for lvl in LEVELS}}


def side_by_side(left: str, right: str, width: int = 58) -> str:
    """İki SQL'i biçimlendirip iki sütun halinde yan yana yazar."""
    a = format_sql(left).splitlines() if left else ["(SQL üretilmedi)"]
    b = format_sql(right).splitlines() if right else ["(SQL olmamalı)"]
    lines = [f"    {'ÜRETİLEN':<{width}} │ REFERANS", f"    {'─' * width}─┼─{'─' * width}"]
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else ""
        y = b[i] if i < len(b) else ""
        if len(x) > width:
            x = x[:width - 1] + "…"
        lines.append(f"    {x:<{width}} │ {y}")
    return "\n".join(lines)


def check_gold(items: list[dict]) -> None:
    """Referans SQL'ler gerçekten çalışıyor mu ve ne döndürüyor? (API gerektirmez.)"""
    for item in items:
        print(f"\n[{item['id']}] ({item['zorluk']}, {item['kategori']}) {item['soru']}")
        if item["referans_sql"] is None:
            print("    (cevaplanamaz soru: modelin SQL üretmemesi beklenir)")
            continue
        print(run_sql(DB_PATH, item["referans_sql"]).to_string(index=False))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolunda Türkçe karakterler
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-gold", action="store_true",
                        help="Modeli çağırmadan referans SQL'lerin sonuçlarını göster")
    parser.add_argument("--only", type=int, nargs="+", metavar="ID",
                        help="Yalnızca bu id'li soruları çalıştır; API maliyetini azaltır")
    args = parser.parse_args()

    if not DB_PATH.exists():  # tohum sabit (seed=42): veri her kurulumda aynı
        seed_db.build(DB_PATH)
    items = load_questions()
    if args.only:
        items = [item for item in items if item["id"] in args.only]

    if args.check_gold:
        check_gold(items)
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY tanımlı değil. Önce anahtarı ayarla (README'ye bak).")
        return 1

    print(f"Model: {MODEL} | Soru sayısı: {len(items)} | Bugün: {TODAY}\n")
    results = []
    for item in items:
        r = evaluate_one(item, DB_PATH)
        results.append(r)
        print(f"{'✓' if r['gecti'] else '✗'} [{r['id']:>2}] ({r['zorluk']}) {r['soru']}")

    summary = summarize(results)
    t = summary["toplam"]
    print(f"\nDoğruluk: {t['gecen']}/{t['toplam']} = %{t['yuzde']}")
    for lvl, s in summary["zorluk"].items():
        if s["toplam"]:
            print(f"  {lvl:<6} {s['gecen']}/{s['toplam']} = %{s['yuzde']}")

    failed = [r for r in results if not r["gecti"]]
    if failed:
        print(f"\nBaşarısız sorular ({len(failed)}):")
        for r in failed:
            print(f"\n[{r['id']}] ({r['zorluk']}, {r['kategori']}) {r['soru']}")
            print(f"    Neden: {r['neden']}")
            print(side_by_side(r["uretilen_sql"], r["referans_sql"]))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}.json"
    out.write_text(json.dumps({"model": MODEL, "bugun": TODAY, "ozet": summary, "sonuclar": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAyrıntılar: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
