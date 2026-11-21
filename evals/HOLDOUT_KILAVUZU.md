# Holdout soruları yazım kılavuzu

Holdout seti, modelin **görmediği** sorulardaki başarıyı ölçer. Prompt'u bu sete bakarak değiştirirsen set ölçüm değerini kaybeder. Bu yüzden v1 donduruldu (`evals/holdout.yaml`); yeni sorular `evals/holdout_v2.yaml` dosyasına yazılır.

## Alanlar

| Alan | Zorunlu | Açıklama |
|---|---|---|
| `id` | evet | Benzersiz sayı. v2 için 201'den başla. |
| `soru` | evet | Modele aynen sorulan metin. |
| `referans_sql` | evet | Doğru cevabı veren SQL. Cevaplanamaz soruda `null`. |
| `zorluk` | evet | `kolay`, `orta` veya `zor`. |
| `kategori` | evet | Serbest etiket (ör. `belirsiz`, `pencere`, `iki-adim`, `ayni-ad`, `cevaplanamaz`). |
| `sirali` | evet | Soru açıkça sıralama istiyorsa `true`; yoksa satır sırası önemsenmez. |
| `yorum` | hayır | Belirsiz soruda referansın seçtiği yorum. Başarısızlığı sınıflandırırken kullanılır. |
| `kabul_edilen` | hayır | Başka makul yorumların referans SQL listesi. Herhangi biriyle eşleşen geçer. |
| `ilk_satir` | hayır | `true`: tek satır beklenen soruda, model sıralı bir liste döndürürse ilk satırı doğruysa geçer. |

## İyi soru yazmak

1. **Gerçek kullanıcı gibi yaz.** Günlük dil, kısaltma, yazım hatası, Türkçe karaktersiz yazım serbest.
2. **Prompt'u ve `questions.yaml`'ı örnek alma.** Sorular farklı kalıplarda olsun.
3. **Ayırt edici veri seç.** Doğru cevabın sık yapılan hatalardan farklı bir sonuç vermesine dikkat et. Cevabı 0 olan sayım soruları zayıftır: yanlış bir sorgu da kolayca 0 döndürebilir.
4. **Eşitliklere dikkat et.** "En çok satan 3 ürün" gibi sorularda 3. ve 4. sıra eşitse tek bir doğru cevap yoktur. Yazdıktan sonra `--check-gold` ile sonucu ve sınırdaki değerleri kontrol et.
5. **Göreli tarihler sabit bir güne göre hesaplanır:** "bugün" 2026-11-20.

## Belirsiz soruda alternatif yorum

Belirsizlik sorunun doğal bir parçasıysa (gerçek kullanıcılar böyle sorar) soruyu netleştirme. Onun yerine:

1. En makul yorumu `referans_sql` olarak yaz.
2. Bu yorumu `yorum` alanında tek cümleyle açıkla.
3. Aynı derecede makul başka yorumlar varsa her birinin SQL'ini `kabul_edilen` listesine ekle.

Örnek:

```yaml
- id: 201
  soru: ortalama sepet kaç ürün
  referans_sql: >-
    SELECT AVG(a) FROM (SELECT SUM(quantity) AS a FROM order_items GROUP BY order_id)
  yorum: Sipariş başına toplam adet, tüm siparişler.
  kabul_edilen:
    - >-
      SELECT AVG(a) FROM (SELECT SUM(oi.quantity) AS a FROM orders o
      JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'tamamlandi' GROUP BY o.id)
  zorluk: orta
  kategori: belirsiz
  sirali: false
```

**Dikkat:**
- `kabul_edilen`'e yalnızca gerçekten makul yorumları ekle. Hatalı bir sorgunun sonucunu "alternatif" diye eklemek, modelin hatasını gizler.
- Modelin cevabını gördükten sonra o cevabı `kabul_edilen`'e eklemek aynı soruna yol açar. Alternatifleri soruyu yazarken, sonuçlara bakmadan belirle.
- `ilk_satir` yalnızca tek satırlık referanslarda işe yarar ("hangi ay", "hangi şehir"). Model tüm satırları döndürürse listenin doğru sıralanmış olması gerekir.

## Kontrol listesi

- [ ] `python evals/run_evals.py --set holdout_v2 --check-gold` her referansı hatasız çalıştırıyor.
- [ ] `LIMIT` içeren sorularda sınırda eşitlik yok.
- [ ] En az bir cevaplanamaz soru var (`referans_sql: null`).
- [ ] `python -m pytest -q` geçiyor (referanslar kendi kendini geçmeli).
