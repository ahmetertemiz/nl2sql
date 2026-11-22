"""Değerlendirme: evals/questions.yaml'daki soruları modele sorar, doğruluk oranını ölçer.

Çalıştır (proje klasöründen):
    python evals/run_evals.py               # modeli çağırır (ANTHROPIC_API_KEY gerekir)
    python evals/run_evals.py --check-gold  # API'siz: yalnızca referans SQL'leri çalıştırıp gösterir
    python evals/run_evals.py --only 13 15  # yalnızca seçilen soruları modele sor
    python evals/run_evals.py --set holdout --runs 3   # ayrı seti, her soruyu 3 kez sor

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
SETS = {"questions": QUESTIONS, "holdout": ROOT / "evals" / "holdout.yaml",
        "holdout_v2": ROOT / "evals" / "holdout_v2.yaml"}
RESULTS_DIR = ROOT / "evals" / "results"
LEVELS = ("kolay", "orta", "zor")
# Örnek verinin bittiği gün (seed_db.TODAY). Sabit tutuyoruz ki "geçen ay", "son 3 ay"
# gibi göreli sorular her gün aynı cevabı versin.
TODAY = seed_db.TODAY.isoformat()


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []  # boş şablon -> []


# Sayılar için göreli tolerans: 14.917 ile ROUND(..., 1) = 14.9 arasındaki fark %0.11, eşit sayılır.
REL_TOL = 0.005


def _norm(value):
    """Hücreyi karşılaştırılabilir hale getir: sayılar float, metinler kırpılmış str."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) or hasattr(value, "item"):  # numpy sayıları dahil
        return float(value)
    return str(value).strip()


def cells_equal(a, b) -> bool:
    """İki hücre aynı mı?

    - İkisi de tam sayıysa (sayım gibi) birebir eşit olmalı: 1093 ile 1090 farklıdır,
      oysa %0.5 tolerans bunu kabul ederdi.
    - Biri ondalıklıysa göreli tolerans: |a - b| <= REL_TOL * max(|a|, |b|).
      Böylece yuvarlanmış (ROUND) ama doğru bir cevap yanlış sayılmaz.
    """
    if isinstance(a, float) and isinstance(b, float):
        if a.is_integer() and b.is_integer():
            return a == b
        return abs(a - b) <= REL_TOL * max(abs(a), abs(b))
    return a == b


def _sort_key(v):
    return (0, v, "") if isinstance(v, float) else (1, 0.0, repr(v))


def _cols_equal(gc: list, pc: list, ordered: bool) -> bool:
    if not ordered:  # sıra önemsizse ikisini de sıralayıp eleman eleman karşılaştır
        gc, pc = sorted(gc, key=_sort_key), sorted(pc, key=_sort_key)
    return all(cells_equal(a, b) for a, b in zip(gc, pc))


def _rows_equal(gold_rows: list, pred_rows: list, ordered: bool) -> bool:
    def same(r1, r2):
        return all(cells_equal(a, b) for a, b in zip(r1, r2))

    if ordered:
        return all(same(g, p) for g, p in zip(gold_rows, pred_rows))
    unused = list(pred_rows)  # her beklenen satıra, henüz kullanılmamış eşleşen bir satır bul
    for g in gold_rows:
        match = next((i for i, p in enumerate(unused) if same(g, p)), None)
        if match is None:
            return False
        unused.pop(match)
    return True


def results_match(gold: pd.DataFrame, pred: pd.DataFrame, ordered: bool = False) -> bool:
    """Tahmin edilen sonuç, beklenen sonuçla aynı veriyi içeriyor mu?

    - Sütun ADLARI önemsiz (model 'toplam_ciro' der, referans 'ciro' diyebilir).
    - Sütun SIRASI önemsiz.
    - Modelin fazladan sütun döndürmesi serbest (ör. adın yanında id); ama
      beklenen her sütun tahminde bulunmalı.
    - Satır sırası yalnızca ordered=True ise önemli.
    - Ondalıklı sayılarda %0.5 göreli tolerans (bkz. cells_equal).
    """
    if len(gold) != len(pred) or len(gold.columns) > len(pred.columns):
        return False

    gold_cols = [[_norm(v) for v in gold[c]] for c in gold.columns]
    pred_cols = [[_norm(v) for v in pred.iloc[:, i]] for i in range(len(pred.columns))]

    # Her beklenen sütun için, değerleri tutan aday tahmin sütunları
    candidates = [[i for i, pc in enumerate(pred_cols) if _cols_equal(gc, pc, ordered)]
                  for gc in gold_cols]
    if any(not c for c in candidates):
        return False

    # Sütunlar tek tek tutsa da satırlar tutmayabilir (değerler satırlar arası
    # karışmış olabilir); bu yüzden satırları bütün olarak da karşılaştır.
    gold_rows = list(zip(*gold_cols))
    for choice in product(*candidates):
        if len(set(choice)) < len(choice):
            continue  # aynı tahmin sütunu iki beklenen sütuna eşlenemez
        if _rows_equal(gold_rows, list(zip(*(pred_cols[i] for i in choice))), ordered):
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
    out["varsayimlar"] = result.get("assumptions", [])

    if item["referans_sql"] is None:  # şemayla cevaplanamayan soru: model SQL yazmamalı
        out["gecti"] = not result["sql"]
        out["neden"] = "" if out["gecti"] else "Cevaplanamaz soruya SQL üretti"
        return out

    if not result["sql"]:
        out["neden"] = "SQL üretmedi"
    elif result["error"]:
        out["neden"] = f"SQL hatası: {result['error']}"
    else:
        match = match_any(item, result["df"], db_path)
        out["gecti"] = match is not None
        out["eslesme"] = match
        if match is None:
            out["neden"] = f"Sonuç beklenenden farklı ({len(result['df'])} satır döndü)"
    return out


def match_any(item: dict, pred: pd.DataFrame, db_path: Path) -> str | None:
    """Tahmin, sorunun kabul edilen cevaplarından biriyle eşleşiyor mu? Eşleşmenin türünü döndürür.

    İsteğe bağlı iki YAML alanı (yalnızca gerçekten belirsiz sorularda kullanılır):
    - kabul_edilen: ek referans SQL listesi. Sorunun birden fazla makul yorumu varsa
      her yorumun cevabı ayrı bir referanstır; herhangi biriyle eşleşen geçer.
    - ilk_satir: true. Tek satır beklenen bir soruda ("en çok satan ay hangisi") model
      tüm satırları sıralı döndürürse, ilk satırı doğruysa geçer.
    """
    refs = [("referans", item["referans_sql"])]
    refs += [(f"kabul_edilen[{i}]", sql) for i, sql in enumerate(item.get("kabul_edilen") or [])]
    for label, sql in refs:
        gold = run_sql(db_path, sql)
        if results_match(gold, pred, item["sirali"]):
            return label
        if item.get("ilk_satir") and len(gold) == 1 and len(pred) > 1 \
                and results_match(gold, pred.head(1)):
            return f"{label} (ilk satır)"
    return None


def evaluate_repeated(item: dict, db_path: Path, runs: int, answer_fn=answer) -> dict:
    """Aynı soruyu runs kez sor. Model her seferinde aynı SQL'i yazmayabilir;
    tek koşu şanslı ya da şanssız olabilir."""
    attempts = [evaluate_one(item, db_path, answer_fn) for _ in range(runs)]
    passed = sum(a["gecti"] for a in attempts)
    filled = [bool(a.get("varsayimlar")) for a in attempts]  # her denemede liste dolu mu?
    return {"id": item["id"], "soru": item["soru"], "zorluk": item["zorluk"],
            "kategori": item["kategori"], "referans_sql": item["referans_sql"],
            "yorum": item.get("yorum", ""), "gecen": passed, "kosu": runs,
            "kararsiz": 0 < passed < runs, "denemeler": attempts,
            "varsayim_beklenir": item.get("varsayim_beklenir"),  # etiket yoksa None
            "varsayim_dolu": filled,
            "varsayim_tutarsiz": 0 < sum(filled) < len(filled)}  # bazen dolu, bazen boş


def summarize(records: list[dict]) -> dict:
    """Toplam ve zorluk seviyesine göre doğruluk (tüm koşular üzerinden) + kararsız sorular."""
    def rate(rows):
        passed, total = sum(r["gecen"] for r in rows), sum(r["kosu"] for r in rows)
        return {"gecen": passed, "toplam": total,
                "yuzde": round(100 * passed / total, 1) if total else None}

    return {"toplam": rate(records),
            "zorluk": {lvl: rate([r for r in records if r["zorluk"] == lvl]) for lvl in LEVELS},
            "kararsiz": [r["id"] for r in records if r["kararsiz"]],
            "hep_kalan": [r["id"] for r in records if r["gecen"] == 0],
            "varsayim": assumption_stats(records)}


def assumption_stats(records: list[dict]) -> dict | None:
    """Varsayım listesinin ne kadar isabetli doldurulduğu (deneme düzeyinde).

    - bos_beklenmeyende: varsayım BEKLENMEYEN (tam belirtilmiş) sorularda boş liste oranı.
      Yüksek olmalı; düşükse model gereksiz varsayım yazıyor.
    - dolu_beklenende: varsayım BEKLENEN (belirsiz) sorularda dolu liste oranı.
      Yüksek olmalı; düşükse model gerçek belirsizlikleri sessizce geçiyor.
    - tutarsiz: aynı soruda listenin bazı denemelerde dolu, bazılarında boş olduğu sorular.
    Sorularda varsayim_beklenir etiketi yoksa (ör. holdout v1) None.
    """
    labeled = [r for r in records if r.get("varsayim_beklenir") is not None]
    if not labeled:
        return None

    def rate(flags):
        return {"sayi": sum(flags), "toplam": len(flags),
                "yuzde": round(100 * sum(flags) / len(flags), 1) if flags else None}

    unexpected = [not f for r in labeled if not r["varsayim_beklenir"] for f in r["varsayim_dolu"]]
    expected = [f for r in labeled if r["varsayim_beklenir"] for f in r["varsayim_dolu"]]
    return {"bos_beklenmeyende": rate(unexpected), "dolu_beklenende": rate(expected),
            "tutarsiz": [r["id"] for r in labeled if r["varsayim_tutarsiz"]]}


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
    parser.add_argument("--set", choices=sorted(SETS), default="questions",
                        help="questions: geliştirme seti; holdout: yalnızca ölçmek için ayrı set")
    parser.add_argument("--runs", type=int, default=1, metavar="N",
                        help="Her soruyu N kez sor; kararsız soruları bulmak için")
    args = parser.parse_args()

    if not DB_PATH.exists():  # tohum sabit (seed=42): veri her kurulumda aynı
        seed_db.build(DB_PATH)
    items = load_questions(SETS[args.set])
    if args.only:
        items = [item for item in items if item["id"] in args.only]
    if not items:
        print(f"'{args.set}' setinde soru yok ({SETS[args.set].relative_to(ROOT)}).")
        return 1

    if args.check_gold:
        check_gold(items)
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY tanımlı değil. Önce anahtarı ayarla (README'ye bak).")
        return 1

    print(f"Model: {MODEL} | Set: {args.set} | Soru: {len(items)} | Koşu: {args.runs} | Bugün: {TODAY}\n")
    records = []
    for item in items:
        r = evaluate_repeated(item, DB_PATH, args.runs)
        records.append(r)
        mark = "✓" if r["gecen"] == r["kosu"] else ("~" if r["kararsiz"] else "✗")
        print(f"{mark} [{r['id']:>3}] {r['gecen']}/{r['kosu']} ({r['zorluk']}) {r['soru']}")

    summary = summarize(records)
    t = summary["toplam"]
    print(f"\nDoğruluk: {t['gecen']}/{t['toplam']} = %{t['yuzde']}  (✓ hep geçti, ~ kararsız, ✗ hep kaldı)")
    for lvl, s in summary["zorluk"].items():
        if s["toplam"]:
            print(f"  {lvl:<6} {s['gecen']}/{s['toplam']} = %{s['yuzde']}")
    print(f"Kararsız sorular: {summary['kararsiz'] or 'yok'}")
    if summary["varsayim"]:
        v = summary["varsayim"]
        b, d = v["bos_beklenmeyende"], v["dolu_beklenende"]
        print("\nVarsayımlar (deneme düzeyinde):")
        print(f"  Varsayım beklenmeyen sorularda boş liste: {b['sayi']}/{b['toplam']} = %{b['yuzde']}")
        print(f"  Varsayım beklenen sorularda dolu liste:   {d['sayi']}/{d['toplam']} = %{d['yuzde']}")
        print(f"  Denemeler arası tutarsız sorular ({len(v['tutarsiz'])}): {v['tutarsiz'] or 'yok'}")

    failed = [r for r in records if r["gecen"] < r["kosu"]]
    if failed:
        print(f"\nEn az bir kez başarısız olan sorular ({len(failed)}):")
        for r in failed:
            print(f"\n[{r['id']}] {r['gecen']}/{r['kosu']} ({r['zorluk']}, {r['kategori']}) {r['soru']}")
            if r["yorum"]:
                print(f"    Referansın yorumu: {r['yorum']}")
            first_fail = next(a for a in r["denemeler"] if not a["gecti"])
            print(f"    Neden: {first_fail['neden']}")
            print(side_by_side(first_fail["uretilen_sql"], r["referans_sql"]))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}_{args.set}_x{args.runs}.json"
    out.write_text(json.dumps({"model": MODEL, "set": args.set, "kosu": args.runs, "bugun": TODAY,
                               "ozet": summary, "sorular": records},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAyrıntılar: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
