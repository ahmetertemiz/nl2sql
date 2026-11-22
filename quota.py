"""Ortak (sunucudaki) API anahtarı için günlük çağrı sınırı.

Herkese açık bir demoda linki bulan herkes sahibinin anahtarıyla soru sorabilir.
Bu sayaç günlük toplam model çağrısını sınırlar. Sayaç bellekte tutulur ve bütün
ziyaretçiler için ortaktır; uygulama yeniden başlayınca sıfırlanır. Bu yüzden tek
başına yeterli sayılmamalı: asıl güvence Anthropic Console'daki harcama sınırıdır.
"""
import threading
from datetime import date

_lock = threading.Lock()
_state = {"day": None, "count": 0}


def take(limit: int, today: date | None = None) -> bool:
    """Bir model çağrısı hakkı ayırır. Hak kalmadıysa False döner.

    limit <= 0: sınır yok (yerel kullanım), her zaman True.
    """
    if limit <= 0:
        return True
    today = today or date.today()
    with _lock:
        if _state["day"] != today:  # yeni gün: sayaç sıfırlanır
            _state["day"], _state["count"] = today, 0
        if _state["count"] >= limit:
            return False
        _state["count"] += 1
        return True


def reset() -> None:
    """Testler için."""
    with _lock:
        _state["day"], _state["count"] = None, 0
