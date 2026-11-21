"""Değerlendirme: eval_set.json'daki soruları modele sorar, doğruluk oranını ölçer.

Çalıştır:
    python evaluate.py               # modeli çağırır (ANTHROPIC_API_KEY gerekir)
    python evaluate.py --check-gold  # API'siz: yalnızca referans SQL'leri çalıştırıp gösterir
    python evaluate.py --only 21     # yalnızca seçilen soruları modele sor

Ölçüt "çalıştırma doğruluğu"dur (execution accuracy): modelin SQL metni referans
SQL ile aynı olmak zorunda değil; önemli olan ikisinin de aynı SONUCU döndürmesi.
Çünkü aynı soruyu cevaplayan çok sayıda farklı ama doğru SQL yazılabilir.
"""
import argparse
import json
import os
import sys
from itertools import product
from pathlib import Path

import pandas as pd

import seed_db
from nl2sql import MODEL, answer, run_sql

HERE = Path(__file__).parent
DB_PATH = HERE / "shop.db"
EVAL_SET = HERE / "eval_set.json"
RESULTS = HERE / "eval_results.json"
# seed_db.build içindeki sabit "bugün". Sabit tutuyoruz ki "geçen ay", "bu yıl"
# gibi göreli sorular her çalıştırmada aynı cevabı versin.
TODAY = "2026-11-20"


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
    out = {"id": item["id"], "question": item["question"], "sql": "", "passed": False, "reason": ""}
    try:
        result = answer_fn(item["question"], db_path, today=TODAY)
    except Exception as exc:  # ağ hatası, geçersiz JSON vb.
        out["reason"] = f"Model çağrısı başarısız: {exc}"
        return out
    out["sql"] = result["sql"]

    if item["gold_sql"] is None:  # şemayla cevaplanamayan soru: model SQL yazmamalı
        out["passed"] = not result["sql"]
        out["reason"] = "" if out["passed"] else "Cevaplanamaz soruya SQL üretti"
        return out

    if not result["sql"]:
        out["reason"] = "SQL üretmedi"
    elif result["error"]:
        out["reason"] = f"SQL hatası: {result['error']}"
    elif results_match(run_sql(db_path, item["gold_sql"]), result["df"], item["ordered"]):
        out["passed"] = True
    else:
        out["reason"] = "Sonuç beklenenden farklı"
    return out


def check_gold(items: list[dict]) -> None:
    """Referans SQL'ler gerçekten çalışıyor mu ve ne döndürüyor? (API gerektirmez.)"""
    for item in items:
        print(f"\n[{item['id']}] {item['question']}")
        if item["gold_sql"] is None:
            print("    (cevaplanamaz soru: modelin SQL üretmemesi beklenir)")
            continue
        print(run_sql(DB_PATH, item["gold_sql"]).to_string(index=False))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolunda Türkçe karakterler
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-gold", action="store_true",
                        help="Modeli çağırmadan referans SQL'lerin sonuçlarını göster")
    parser.add_argument("--only", type=int, nargs="+", metavar="ID",
                        help="Yalnızca bu id'li soruları çalıştır (ör. --only 21); API maliyetini azaltır")
    args = parser.parse_args()

    if not DB_PATH.exists():  # tohum sabit (seed=42): veri her kurulumda aynı
        seed_db.build(DB_PATH)
    items = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    if args.only:
        items = [item for item in items if item["id"] in args.only]

    if args.check_gold:
        check_gold(items)
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY tanımlı değil. Önce anahtarı ayarla (README'ye bak).")
        return 1

    print(f"Model: {MODEL} | Soru sayısı: {len(items)}\n")
    results = []
    for item in items:
        r = evaluate_one(item, DB_PATH)
        results.append(r)
        mark = "✓" if r["passed"] else "✗"
        print(f"{mark} [{r['id']:>2}] {r['question']}")
        if not r["passed"]:
            print(f"        {r['reason']}")
            if r["sql"]:
                print(f"        SQL: {r['sql']}")

    passed = sum(r["passed"] for r in results)
    print(f"\nDoğruluk: {passed}/{len(results)} = %{100 * passed / len(results):.0f}")
    RESULTS.write_text(
        json.dumps({"model": MODEL, "passed": passed, "total": len(results), "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Ayrıntılar: {RESULTS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
