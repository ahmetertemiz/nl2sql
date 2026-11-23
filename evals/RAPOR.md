# Değerlendirme raporu

Model: `claude-sonnet-5-5` · Her soru 3 kez soruldu (`--runs 3`) · "Bugün": 2026-11-20 · Ham sonuçlar `evals/results/` altında (git'e eklenmez)

---

# İş sözlüğü taşıması (2026-11-23, commit 6d4307f)

"Kendi veritabanını bağla" desteği için örnek veriye özgü ciro kuralı prompt'tan çıkarıldı. Kural artık iş sözlüğü dosyalarında: `glossaries/shop_tr.md` ve `glossaries/shop_en.md`. Sözlük satırları prompt'ta eski ciro satırının yerine giriyor. Ayrıca "SQLite" ifadesi ve tarih kuralı veritabanı türüne göre dolduruluyor.

**Prompt değişmedi.** Değişiklikten önce iki örnek veritabanı için modele giden şema ve sistem prompt'u kaydedildi (`testdata/demo_golden.json`). Yeni kodun ürettiği prompt bu kayıtla karakteri karakterine aynı. `test_db.py::test_demo_schema_and_prompt_unchanged` bunu her test çalıştırmasında denetliyor. Bu yüzden aşağıdaki ölçüm bir "bozulma yok" kontrolü; olası farklar modelin örneklemesinden gelir.

| Ölçüt | questions (Türkçe) | önceki tek koşu | questions_en (İngilizce) | önceki (x3) |
|---|---|---|---|---|
| Doğruluk | **20/20** | 20/20 | **20/20** | 60/60 |
| Beklenmeyen sorularda boş liste | 13/13 | 13/13 | 13/13 | 39/39 |
| Beklenen sorularda dolu liste | 6/7 | 7/7 | 5/7 | 20/21 |

Ham sonuçlar: `2026-11-23_103212_questions_x1.json` ve `2026-11-23_103759_questions_en_x1.json` (`--runs 1`).

- Doğruluk değişmedi. Gereksiz varsayım da çıkmadı.
- Eksik kalan üç varsayım: Türkçe 14, İngilizce 13 ve 18. Üçünde de model "yalnızca tamamlanan siparişler" kuralını uyguladı ve açıklamasında yazdı ("tamamlanmış siparişlerin kalemlerinde...", "for completed orders..."), ama varsayım listesine koymadı. İngilizce 18 önceki x3 ölçümde de bir kez eksik kalmıştı.
- Prompt aynı olduğu için bu fark sözlük taşımasına bağlanamaz: aynı girdiyle tek koşuda görülen örnekleme farkı. Tek koşu kararsız bir varsayımı yakalamaya yetmez; kesin oran için `--runs 3` gerekir.

## PostgreSQL'de koşmak için referans SQL'ler

questions setinin 18 referans sorgusu (`kabul_edilen` alternatifleri dahil) örnek verinin PostgreSQL kopyasında denendi. Tarihler `DATE`, fiyatlar `NUMERIC(10,2)` olarak taşındı.

| Sonuç | Sorgu | Neden |
|---|---|---|
| Olduğu gibi çalışıyor, sonuç SQLite ile aynı | 10 | |
| PostgreSQL karşılığı gerekiyor | 8 | 9, 11, 12, 13, 14: `strftime` / `date()` · 15: `HAVING` içinde takma ad (`adet`) · 16, 17: `SUM(koşul)` (PostgreSQL'de `SUM(CASE ...)` ya da `COUNT(*) FILTER`) |

Bu 8 sorgunun PostgreSQL karşılıkları yazılmadı (karar bekliyor). Bu yüzden modelin PostgreSQL'deki doğruluğu ölçülmedi; README'de "Limits" altında da böyle yazıyor.

---

# İngilizce (2026-11-22, prompt commit cc78bad + d3829f6)

Uygulama iki dilli oldu. Prompt'lar İngilizceye çevrildi; kuralların anlamı aynı kaldı. Eklenen tek kural: açıklama, varsayımlar, yorum ve sütun takma adları sorunun dilinde yazılır. Takvim kuralı artık dilden bağımsız. Ciro kuralındaki durum değeri ('tamamlandi' / 'completed') veritabanından okunuyor. İngilizce demo verisi (`shop_en.db`) aynı tohumla üretildi: sipariş, tarih, adet ve durum dağılımı `shop.db` ile birebir aynı; adlar, şehirler, kategoriler ve para birimi (USD) farklı.

## Türkçe setler: prompt çevirisi doğruluğu bozdu mu?

| Set | Önce (Türkçe prompt) | Sonra (İngilizce prompt, `--runs 1`) |
|---|---|---|
| questions | 60/60 (5. ölçüm, x3) | 20/20 |
| holdout v1 | 53/60 (2. ölçüm, x3) | 19/20 |
| holdout v2 | 60/60 (x3) | 20/20 |

Bozmadı. Holdout v1'de kalan tek soru 115 ("ortalama sepet kaç ürün oluyor"). Model yine yalnızca tamamlanan siparişleri saydı; bu soru önceki ölçümlerde de 0/3'tü ve "belirsiz soru" olarak sınıflandırılmıştı.
Sınırlar:
- Sonra sütunu tek koşu; kararsız bir soru bu koşuda şanslı geçmiş olabilir.
- Holdout v1'in "önce" değeri eski bir prompt'a (07299d0) ait.
- Holdout v1 bu turda üçüncü kez ölçüldü. Ayar için kullanılmış sayıldığından buradaki sonuç yalnızca "bozulma yok" kontrolü.

Türkçe sorularda açıklama, varsayımlar ve takma adlar (ör. `ortalama_sepet_urun_adedi`) Türkçe kaldı. Varsayım oranları (tek koşu):

| Set | Beklenmeyen sorularda boş liste | Beklenen sorularda dolu liste |
|---|---|---|
| questions | 13/13 (5. ölçümde %97,4) | 7/7 (5. ölçümde %100) |
| holdout v2 | 3/6 (önce %50) | 14/14 (önce %100) |

## İngilizce set (questions_en, `--runs 3`)

`evals/questions_en.yaml`: questions.yaml'daki 20 sorunun İngilizce karşılığı, `shop_en.db` üzerinde. Etiketler aynı. Referanslar `--check-gold` ile çalışıyor. Fiyattan bağımsız 13 soru Türkçe karşılığıyla birebir aynı sonucu veriyor. Fiyat ya da ciro içeren 3, 7, 8, 13 ve 14 USD olduğu için farklı sayı veriyor; 3. soru aynı 8 ürünü seçiyor. Ham sonuç: `2026-11-22_180111_questions_en_x3.json`.

| Ölçüt | questions_en (İngilizce) | questions (Türkçe, 5. ölçüm) |
|---|---|---|
| Doğruluk | **60/60 (%100)** | 60/60 |
| — kolay / orta / zor | 21/21 · 21/21 · 18/18 | |
| Kararsız / hep kalan | yok / yok | yok / yok |
| Beklenmeyen sorularda boş liste | **39/39 (%100)** | 38/39 (%97,4) |
| Beklenen sorularda dolu liste | **20/21 (%95,2)** | 21/21 (%100) |
| Denemeler arası tutarsız soru | 1 (18) | 1 (9) |

- Tek eksik: 18'in bir denemesinde ("her kategoride iade edilen siparişlerin yüzdesi") paydaya iptallerin de girdiği yazılmadı. Diğer iki denemede yazıldı.
- Model İngilizce sorularda açıklamayı, varsayımları ve takma adları (`total_revenue`, `customer_name`) İngilizce yazdı. Ciro kuralını `status = 'completed'` ile uyguladı ve bunu her denemede varsayım olarak bildirdi.
- 8. soruda aynı adlı müşteriler var (ör. 5 "Noah Brown"; Türkçe veride de aynı yapı). Model üç denemede de müşteri kimliğine göre grupladı.

**Yorum.** Dil değişimi doğruluğu ve varsayım davranışını etkilemedi. Bu sonuç ayar setinin çevirisiyle alındı: questions_en, questions.yaml'ın birebir karşılığı olduğu için genelleme ölçüsü değil. İngilizce için görülmemiş bir holdout seti henüz yok.

---

# Holdout v2 (2026-11-22, prompt commit cda1df7)

20 yeni soru (201–220). Sohbetteki Claude yazdı, referanslar shop.db üzerinde doğrulandı (commit 355804c). Prompt'u ayarlarken bu sorular görülmedi. Bu ölçümden sonra da sorular, referanslar, etiketler ve prompt değiştirilmedi.
`--check-gold`: 17 referans sorgunun hepsi hatasız çalıştı (215–217 cevaplanamaz). Ham sonuç: `2026-11-22_163505_holdout_v2_x3.json` (`--runs 3`).

| Ölçüt | Holdout v2 | questions (5. ölçüm, aynı prompt) |
|---|---|---|
| Doğruluk | **60/60 (%100)** | 60/60 |
| — kolay / orta / zor | 9/9 · 30/30 · 21/21 | |
| Kararsız / hep kalan | yok / yok | yok / yok |
| Beklenmeyen sorularda boş liste | **9/18 (%50,0)** | 38/39 (%97,4) |
| Beklenen sorularda dolu liste | 42/42 (%100) | 21/21 (%100) |
| Denemeler arası tutarsız soru | yok | 1 |

## Başarısız sorular

Yok. 20 sorunun hepsi 3/3 geçti. Bu nedenle sınıflandırılacak doğruluk hatası (model hatası / belirsiz soru / hatalı referans / ölçüt katılığı) bulunmuyor.
- 60 denemenin 7'si `kabul_edilen` alternatifiyle geçti: 201 (2/3), 205 (3/3), 219 (3/3). Üçünde de model "yalnızca tamamlanan siparişler" yorumunu seçti ve bunu varsayım olarak yazdı. Bu alternatifler soru yazılırken, model cevapları görülmeden tanımlanmıştı. Tanımlanmasalardı bu 7 deneme kalırdı ve hepsi "belirsiz soru" sınıfına girerdi.
- Cevaplanamaz üç soru (215 teslim süresi, 216 kâr marjı, 217 cinsiyet) 9/9 denemede SQL üretmeden reddedildi. Tuzaklara düşülmedi: model liste ve satış fiyatı farkını kâr saymadı, adlardan cinsiyet tahmin etmedi.

## Varsayımlar: neden %50?

Varsayım beklenmeyen 6 sorudan 3'ü (215–217, cevaplanamaz) her denemede boş liste verdi. Diğer üçü (206, 208, 209) her denemede dolu çıktı. 9 gereksiz listenin hepsi bu üç sorudan geliyor. Her maddenin bu veride sonucu değiştirip değiştirmediği elle kontrol edildi:

| Soru | Modelin yazdığı | Bu veride sonucu değiştiriyor mu? | Sınıf |
|---|---|---|---|
| 206 "içinde 3 farklı ürün olan kaç sipariş" | "Sipariş durumuna bakılmadı" (3/3) | **Evet:** tüm durumlar 509, yalnızca tamamlanan 452 | Etiket tutarsızlığı (aşağıda) |
| 206 | "Tam 3, 3 veya fazlası değil" (2/3) | Hayır: hiçbir siparişte 3'ten fazla ürün yok (≥3 de 509) | Gürültü: veride gerçekleşmeyen kenar durum |
| 208 "kayıt olduğu gün ilk siparişini veren" | "İlk sipariş için tüm durumlar dikkate alındı" (3/3) | Hayır: iki yorum da 6 | Gürültü: veride gerçekleşmeyen kenar durum |
| 209 "en yüksek tutarlı sipariş kimindi" | "Yalnızca tamamlanan siparişler" (3/3) | Hayır: en büyük sipariş zaten tamamlanmış (yorum alanında da yazıyor) | Gürültü: veride gerçekleşmeyen kenar durum |

**Hatalı olabilecek etiket (yalnızca raporlanıyor, değiştirilmedi): 206.** Sipariş durumu belirsizliği aynı sette 203, 207, 211, 218 ve 219'da `varsayim_beklenir: true` sayılmış ve bu sorulara `kabul_edilen` alternatifi eklenmiş. 206'da da durum yorumu farklı sayı veriyor (509 / 452). Dosyanın kendi ölçütüne göre 206 `true` olmalı. Etiket `true` olsaydı oran 9/15 (%60) olurdu. Referans SQL ise doğru ve tamamlanan siparişler yorumu için `kabul_edilen` yok, ama model üç denemede de referansın yorumunu seçtiği için doğruluk etkilenmedi.

**Gürültünün kalıbı.** Kalan üç madde de questions setinde 9. sorudaki tek gürültüyle aynı türden: model bir yorum farkını fark ediyor ve farkın bu veride sonucu değiştirip değiştirmediğini bilmeden yazıyor. Prompt bu türü yasaklıyor ("bu veride gerçekleşmeyen kenar durumlar"). Ama model yalnızca şemayı görüyor, verinin içeriğini görmüyor. Bu yüzden "bu veride farklı bir sayı verir miydi?" sorusunu çoğu zaman cevaplayamıyor ve emin olmadığında yazmayı seçiyor. Durum belirsizliği şemadan görülebildiği için (`status` sütunu) holdout v2'nin sorularında bu kalıp sık çıkıyor. questions setinde ise prompt'u ayarlarken görülen sorular bu türden çoğunlukla arındırılmıştı.

**Yorum.** Doğruluk yeni sorulara genellendi (60/60). Gerekli varsayımlar da genellendi (42/42). "Gereksiz varsayım yazma" ayarı ise genellenmedi: questions setindeki %97,4, ayar setine uyumun bir parçası. Holdout v2'deki gerçek oran %50 civarında, 206 etiketi düzeltilirse %60. Kalan gürültünün hiçbiri yanlış bilgi değil: madde doğru, yalnızca gereksiz.

---

# 5. ölçüm — takvim ifadeleri tanımlandıktan sonra (2026-11-22, commit cda1df7)

4. ölçümdeki gürültünün 9/10'u "geçen ay takvim ayı olarak alındı" maddesiydi. "Kurallar" bölümüne takvim ifadelerinin tanımı eklendi: "geçen ay", "bu ay", "geçen yıl" ve "bu yıl". Tanımın yanında bunların Türkçedeki yerleşik anlamlar olduğu ve varsayım olarak yazılmayacağı da söylendi. Böylece bir önceki madde ("kullanıcı talimatları görmez") bu tanıma uygulanmıyor: ölçütün ilk sorusunun cevabı "hayır". Ciro tanımı ise bir iş kararı olarak yazılmaya devam ediyor.
Yalnızca questions seti koşuldu (`--runs 3`); holdout v1 koşulmadı. Ham sonuç: `2026-11-22_151418_questions_x3.json`.

| Ölçüt | 2. (07299d0) | 3. (8932a8e) | 4. (8d10ab0) | 5. (cda1df7) |
|---|---|---|---|---|
| Doğruluk | 60/60 | 60/60 | 60/60 | 60/60 |
| Beklenmeyen sorularda boş liste | %64,1 | %82,1 | %74,4 | **38/39 (%97,4)** |
| Beklenen sorularda dolu liste | %95,2 | %57,1 | %100 | **21/21 (%100)** |
| Tutarsız soru | 2 | 4 | 1 | 1 (9) |

- **"Geçen ay" maddesi tamamen kayboldu.** 9, 11 ve 12'nin 9 denemesinin hiçbirinde artık yok. Doğruluk etkilenmedi: model tanımı SQL'de de doğru uyguluyor.
- **Beklenen varsayımlar korundu.** Ciro (7, 8, 13, 14), sıfır satışlı ürünler (15) ve oranın paydası (17, 18) 21/21 denemede yazıldı.
- **Kalan tek gürültü** 9'da tek denemede çıkan şu madde: "geçen aydan sonra kayıt olan müşteriler de sipariş vermemiş sayıldı". `customers.signup_date` sütunu var, yani soru kavramsal olarak yerinde. Ama veride Ekim'den sonra kaydolan müşteri yok (0 kişi), dolayısıyla madde sonucu değiştirmiyor. Bu, kuralın yasakladığı "bu veride gerçekleşmeyen kenar durum" türü. Model bunu verinin içeriğini görmeden bilemez; yalnızca şemayı görüyor. 1/39 düzeyinde kabul edilebilir.

**Toplam sonuç (2. ölçümden 5. ölçüme):** Doğruluk 60/60'ta kaldı. Gereksiz varsayım 14 denemeden 1'e indi. Gerekli varsayımlar 20/21'den 21/21'e çıktı. Bu ölçümler ayar için kullanılan questions setinde yapıldı. Değişikliklerin genellenip genellenmediğini yalnızca yeni ve görülmemiş sorular (holdout_v2) gösterebilir.

---

# 4. ölçüm — "kullanıcı bu talimatları görmez" maddesinden sonra (2026-11-22, commit 8d10ab0)

3. ölçümde ciro sorularındaki varsayımın kaybolduğu görülmüştü. Olası neden: model prompt'taki ciro tanımını "soruda zaten söylenmiş" sayıyordu. Bunun için varsayım kuralına tek bir genel madde eklendi: kullanıcı talimatları görmez, bu yüzden "Kurallar" bölümünden gelen ve soruda açıkça belirtilmeyen bir tanım, iki sorunun cevabı evetse yine yazılır. Maddede ne ciro kelimesi ne de belirli bir soru geçiyor.
Yalnızca questions seti koşuldu (`--runs 3`); holdout v1 koşulmadı. Ham sonuç: `2026-11-22_142829_questions_x3.json`.

| Ölçüt | 2. ölçüm (07299d0) | 3. ölçüm (8932a8e) | 4. ölçüm (8d10ab0) |
|---|---|---|---|
| Doğruluk | 60/60 | 60/60 | 60/60 |
| Beklenmeyen sorularda boş liste | 25/39 (%64,1) | 32/39 (%82,1) | 29/39 (%74,4) |
| Beklenen sorularda dolu liste | 20/21 (%95,2) | 12/21 (%57,1) | **21/21 (%100)** |
| Denemeler arası tutarsız soru | 2 (8, 16) | 4 (7, 8, 9, 13) | 1 (10) |

- **Tahmin doğrulandı.** Ciro sorularının (7, 8, 13, 14) 12 denemesinin hepsinde "yalnızca tamamlanan siparişler sayıldı" varsayımı var. Beklenen 21 denemenin 21'i dolu ve tutarlı.
- **Kalan gürültünün neredeyse tamamı tek tür.** Beklenmeyen sorulardaki 10 dolu listenin 9'u "geçen ay takvim ayı olarak alındı, son 30 gün değil" maddesi (9, 11, 12; 3/3). Onuncusu 10'da tek denemede çıkan "satışı olmayan kategoriler 0 adetle listelendi" maddesi.
- **"Geçen ay" etiket ile model arasındaki bir anlaşmazlık.** Etiket ölçütü "geçen ay"ı Türkçedeki yerleşik anlamıyla belirsiz saymıyor. Model ise "son 30 gün"ü makul ve farklı sayı veren bir yorum sayıyor ve bunu üç denemede de tutarlı yapıyor. Bu ya prompt'a "geçen ay = önceki takvim ayı" tanımı ekleyerek çözülür (o zaman yeni madde gereği model bunu yine yazabilir), ya da etiket değiştirilerek. Bu bir tasarım kararı, burada yapılmadı.
- 3. ölçümle karşılaştırınca boş liste oranı 82,1'den 74,4'e indi. Fark, 9'daki "geçen ay" maddesinin bir denemeden üç denemeye çıkmasından geliyor (+2). Bir de 10'da yeni çıkan tek madde var (+1).

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
