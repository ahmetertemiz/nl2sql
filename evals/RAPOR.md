# Değerlendirme raporu

Model: `claude-sonnet-5-5` · Her soru 3 kez soruldu (`--runs 3`) · "Bugün": 2026-11-20 · Ham sonuçlar `evals/results/` altında (git'e eklenmez)

---

# 3. ölçüm — varsayım kuralı sıkılaştırıldıktan sonra (2026-11-22, commit 8932a8e)

Değişen tek şey prompt'taki varsayım kuralı. Yeni kural iki soruluk ölçütle başlıyor ("başka bir yorum beklenebilir miydi, farklı bir sayı verir miydi"). Dört gürültü türünü (soruyu tekrar etmek, sonucu değiştirmeyen teknik ayrıntı, gerçekleşmeyen kenar durum, yapılmayan işlemi bildirmek) açıkça yasaklıyor. Madde sınırı 3'ten 2'ye indi.
Yalnızca questions seti koşuldu (`--runs 3`). Holdout v1 bu tur koşulmadı: o set ayar için kullanılmış sayılıyor.
"Önce" sütunu, 2. ölçümün ham sonucuna (`2026-11-21_213441_questions_x3.json`) yeni `varsayim_beklenir` etiketleri uygulanarak hesaplandı. "Sonra": `2026-11-22_105409_questions_x3.json`.

## Önce / sonra

| Ölçüt | Önce (07299d0) | Sonra (8932a8e) | Değişim |
|---|---|---|---|
| Doğruluk | 60/60 (%100) | 60/60 (%100) | — |
| Beklenmeyen sorularda boş liste | 25/39 (%64,1) | 32/39 (%82,1) | +18,0 puan |
| Beklenen sorularda dolu liste | 20/21 (%95,2) | 12/21 (%57,1) | **−38,1 puan** |
| Denemeler arası tutarsız soru | 2 (8, 16) | 4 (7, 8, 9, 13) | +2 |

Doğruluk düşmediği için değişiklik geri alınmadı (kural: "doğruluk düşerse geri al"). Ama değişiklik net bir iyileşme değil, bir takas:

- **Gürültü azaldı.** 10 ve 16'daki gereksiz varsayımlar tamamen kayboldu. 9 tek denemeye indi.
- **Gerçek belirsizlik de susturuldu.** Ciro sorularında (7, 8, 13, 14) "yalnızca tamamlanan siparişler sayıldı" varsayımı 12 denemenin 9'unda yazılmadı. 14'te hiç yazılmadı. Bu kayıp ciro sorularının tamamından geliyor. 15, 17 ve 18 hâlâ 3/3 doğru varsayım yazıyor.
- **Tutarsızlık arttı.** 7, 8 ve 13'te model aynı soruda bazen yazıyor, bazen yazmıyor.

**Olası neden (sınıflandırma, düzeltme değil):** Ciro tanımı ("yalnızca tamamlanan siparişler") prompt'ta bir kural olarak duruyor. Model bunu sorunun bir parçası gibi görüp "soruda söyleneni tekrar etme" yasağına sokuyor olabilir. Oysa kullanıcı bu kuralı görmüyor. 15, 17 ve 18'deki kararlar prompt'ta yazmıyor ve bunlar etkilenmedi; bu da açıklamayla tutarlı.

**Kalan gürültü:** 11 ve 12'de "geçen ay takvim ayı olarak yorumlandı" maddesi 6/6 denemede hâlâ var. Etiket ölçütüne göre bu gereksiz: Türkçede "geçen ay"ın yerleşik anlamı bir önceki takvim ayı. Yeni kural bu türü kapatmadı, çünkü model "son 30 gün" yorumunu makul ve farklı sayı veren bir alternatif sayıyor. Ölçütün kendisi bu konuda iki türlü okunabiliyor.

---

# 2. ölçüm — "assumptions" alanından sonra (2026-11-21, commit 07299d0 sonrası)

Değişen tek şey prompt: modele soruda açık olmayan kararlarını `assumptions` listesinde yazması söylendi. Holdout v1 dondurulmuş durumda; `kabul_edilen` / `ilk_satir` alanları ona eklenmedi. questions.yaml'daki 17. soruya `ilk_satir` eklendi, ama o soru iki ölçümde de 3/3 geçti, yani sonucu etkilemedi.
Ham sonuçlar: `2026-11-21_213441_questions_x3.json`, `2026-11-21_215502_holdout_x3.json`.

## Doğruluk: önce / sonra

| Set | 1. ölçüm | 2. ölçüm | Fark |
|---|---|---|---|
| questions | 60/60 = %100 | 60/60 = %100 | 0 |
| holdout v1 | 56/60 = %93,3 | 53/60 = %88,3 | −3 deneme (−5 puan) |
| — kolay | 12/12 | 10/12 | −2 (112) |
| — orta | 26/30 | 25/30 | −1 (117) |
| — zor | 18/18 | 18/18 | 0 |

### Holdout'taki başarısızlıklar

| Soru | 1. ölçüm | 2. ölçüm | Sınıf | Açıklama |
|---|---|---|---|---|
| 112 "iptaller en çok hangi şehirden" | 3/3 | 1/3 | ölçüt katılığı | Başarısız iki denemede model 8 şehrin tümünü iptal sayısına göre azalan sırada döndürdü; ilk satır doğru (Bursa, 18). Tek satır beklendiği için yanlış sayıldı. |
| 117 "masa lambasi en cok hangi ay" | 2/3 | 1/3 | ölçüt katılığı | Aynı desen: 16 ayın tamamı sıralı döndü, ilk satır doğru (2026-09, 72). |
| 115 "ortalama sepet kaç ürün" | 0/3 | 0/3 | belirsiz soru | Model yine "yalnızca tamamlanan siparişler" yorumunu seçti. Fark: bu kararı artık varsayım olarak açıkça yazıyor. |

### Prompt değişikliğinin doğruluğa etkisi

- **SQL düzeyinde yeni bir model hatası yok.** Holdout'taki 7 başarısız denemenin tamamı yukarıdaki iki sınıftan geliyor: biçim (tek satır yerine sıralı liste) ve belirsiz soru.
- **Holdout düşüşünün tamamı tek satır / sıralı liste farkından geliyor.** Bu desen 1. ölçümde de vardı (117). Bu kez 112'de de görüldü.
- **Düşüşün nedeni prompt mu, bilmiyoruz.** Fark soru başına 3 denemede 2 deneme. Bu kadar küçük bir örneklemle bu fark rastlantıdan ayırt edilemez. Prompt uzadığı için modelin daha "açıklayıcı" (tüm listeyi gösteren) cevaplara kaydığı bir olasılık, ama kanıtlanmış değil.
- **Prompt değişikliğinin doğruluğu artırdığına dair kanıt yok.** Bu beklenen bir sonuç: değişiklik doğru SQL'i değil, kullanıcının kararları görmesini hedefliyordu.

## Modelin ürettiği varsayımlardan 5 örnek

Hepsi, soruda açık olmayan ve sonucu gerçekten değiştiren kararlar:

1. **101 "en iyi 5 müşterimiz kimler":** "'En iyi' müşteri, toplam ciro en yüksek olan müşteri olarak tanımlandı; sipariş sayısı veya sipariş adedi ölçüt alınmadı."
2. **102 "son 6 ayda":** "Son 6 ay, içinde bulunulan ay dahil 6 takvim ayı olarak alındı (Haziran-Kasım 2026). Kasım ayı henüz bitmediği için ... diğer aylardan düşük görünebilir."
3. **115 "ortalama sepet":** "Yalnızca 'tamamlandi' durumundaki siparişler sayıldı; iptal ve iade siparişleri dışarıda bırakıldı." 1. ölçümde gizli kalan ve sorunun başarısız sayılmasına yol açan karar artık ekranda.
4. **108 "en çok sipariş veren müşteri":** "Sipariş sayısına tüm durumlar dahil edildi; yalnızca tamamlanan siparişler sayılırsa sonuç değişebilir."
5. **questions 18, iade oranı:** "Yüzde paydasına tüm sipariş durumları dahil edildi; iptal edilen siparişler çıkarılırsa oranlar yükselir."

Kontrol: Varsayımların söylediği şey, SQL'in yaptığıyla örtüşüyor. Örneğin "satışı olmayan kategoriler 0 adetle gösterildi" diyen sorgularda gerçekten `LEFT JOIN` ve `COALESCE` var.

## Net sorularda gereksiz varsayım üretiyor mu?

**Tam belirtilmiş sorularda hayır.** Şu soruların 3 denemesinde de liste boş kaldı:
- 1–6 (sayım, filtre, gruplama; 6. soru "durumu ne olursa olsun" diyor),
- 109 ("kaç farklı müşteri iade yaptı"),
- 5 cevaplanamaz sorunun hepsi (19, 20, 118, 119, 120).

**Sınırda net sorularda kısmen evet.** Varsayım listesi boş olmayan denemeler: questions setinde 34/60, holdout'ta 45/60. Holdout'taki yüksek oran beklenen bir şey, çünkü sorular bilerek belirsiz. Ama elle sınıflandırdığımda (her sorunun 1. denemesi) questions setindeki 20 maddenin yaklaşık 8'i gereksizdi. Dört tür:

- **Soruyu tekrar etmek.** 13. soru "son 3 tamamlanmış ay" diyor; model "Kasım tamamlanmış ay sayılmadı" diye yazıyor.
- **Sonucu değiştirmeyen teknik ayrıntı.** 10. soruda "Şehir değeri tam olarak 'İstanbul' (büyük İ ile) yazılmış kabul edildi". 12. soruda 4. sırada olmayan bir eşitlik için kural yazıyor.
- **Varsayımsal kenar durumlar.** 17, 107, 114: "Bir şehirde 1 siparişi iade olan küçük bir şehir en üste çıkabilir", "hiç satışı olmayan bir kategori olursa...". Bu verilerde böyle bir durum yok.
- **Yapılmayan bir şeyi söylemek.** 7 ve 101'de "tarih filtresi uygulanmadı"; soruda tarih geçmiyor.

**Tutarsızlık:** Aynı soru için varsayım listesi denemeden denemeye değişebiliyor. 16. soru bir denemede boş, iki denemede 2 madde aldı.

**Değerlendirme:** Prompt'taki "varsayım uydurma" kuralı tam belirtilmiş sorularda işe yarıyor. Sınırda sorularda ise model "sonucu değiştiren" ölçütünü geniş yorumluyor. Holdout v1 dondurulduğu için bu bulgu prompt'u değiştirmek için kullanılmadı. Düzeltme yapılırsa etkisi questions setiyle ve yeni holdout v2 ile ölçülmeli.

---

# 1. ölçüm — ilk durum

Ham sonuçlar: `2026-11-21_211055_questions_x3.json`, `2026-11-21_211800_holdout_x3.json`.

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
