# Değerlendirme raporu — 2026-11-21

Model: `claude-sonnet-5-5` · Her soru 3 kez soruldu (`--runs 3`) · "Bugün": 2026-11-20
Ham sonuçlar: `evals/results/2026-11-21_211055_questions_x3.json`, `evals/results/2026-11-21_211800_holdout_x3.json` (git'e eklenmez)

## Doğruluk

| Set | Doğruluk | Kolay | Orta | Zor | Kararsız | Hep kalan |
|---|---|---|---|---|---|---|
| questions (geliştirme) | 60/60 = %100 | 21/21 | 21/21 | 18/18 | — | — |
| holdout (ayrı test) | 56/60 = %93,3 | 12/12 | 26/30 | 18/18 | 117 | 115 |

Aradaki fark: **6,7 puan**. Holdout'ta 4 başarısız denemenin hiçbiri model hatası değil (aşağıda). Bu sınıflandırmaya göre gerçek model hatası oranı iki sette de 0'dır.

## Holdout'ta başarısız sorular

### 115 — "ortalama sepet kaç ürün oluyor" · 0/3 · **belirsiz soru**

- Model üç denemede de aynı yorumu seçti: yalnızca **tamamlanan** siparişler, sipariş başına toplam adet → **4,045**. Açıklaması: "İptal ve iade siparişleri gerçekleşmiş sepet sayılmadığı için hariç tutuldu."
- Referans **tüm** siparişleri sayıyor → **4,076**.
- Fark %0,76; %0,5 toleransın biraz dışında. Yani tolerans bu farkı gizlemedi, sorunun iki yorumu gerçekten farklı sonuç veriyor.
- Modelin yorumu savunulabilir, hatta projenin "harcama/ciro = tamamlanan siparişler" kuralıyla daha tutarlı. Referansın yorumu daha zayıf olabilir; ama soru metni ikisini de destekliyor.

### 117 — "masa lambasi en cok hangi ay satildi" · 2/3 (kararsız) · **ölçüt katılığı (hatalı referans sınıfı)**

- Başarısız denemede model **tüm ayları** çoktan aza sıralı döndürdü (16 satır, `LIMIT 1` yok) ve açıklamada "ilk satır en çok satılan aydır" dedi. İlk satır doğru: 2026-09, 72 adet.
- Karşılaştırıcı tek satır beklediği için bu deneme yanlış sayıldı. Bir kullanıcı ekranda doğru cevabı görürdü.
- Sorgunun mantığında hata yok (yazım hatalı ürün adını `LIKE '%masa lamba%'` ile doğru buldu). Sorun, referansın "tam olarak bir satır" biçimini zorunlu tutması. Modelin sorulan biçime ("hangi ay" → tek ay) tam uymaması da bir payı; bu yüzden kararsız.

## Holdout'ta öne çıkan başarılar (3/3)

- **Aynı ad tuzağı** (108, 109): model her seferinde müşteri id'sine göre grupladı; ada göre gruplasaydı 62 ve 41 gibi yanlış sayılar çıkardı.
- **Pencere fonksiyonları** (106, 107, 114): kümülatif toplam ve grup içi sıralama doğru.
- **Yazım hataları** (103 "istanbuldaki", 117 "masa lambasi"): doğru değerlere eşlendi.
- **Cevaplanamaz sorular** (118–120): üçünde de SQL üretilmedi; şemada var gibi görünen teslimat şehri sorusu dahil.

## Yorum

- İki set de modelin gerçek bir hatasını yakalamadı. Holdout'taki puan kaybı, belirsiz bir soru ve katı bir karşılaştırma ölçütünden geliyor.
- Holdout, geliştirme setinin göremediği bir şeyi gösterdi: puan kaybının kaynağı burada sorunun ve ölçütün belirsizliği. Böyle durumlarda düşük puan, modelden çok sorunun ve ölçütün tasarımını sorgulamayı gerektirir.
- Kurala uygun olarak hiçbir şey düzeltilmedi: prompt, holdout soruları ve referanslar aynı kaldı.
