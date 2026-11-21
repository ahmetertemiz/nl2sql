# Doğal Dille SQL

Türkçe yazılan soruyu SQL'e çevirir, örnek bir e-ticaret veritabanında çalıştırır ve sonucu tablo + grafik olarak gösterir.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # Windows (PowerShell): $env:ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```

Veritabanı (`shop.db`) ilk çalıştırmada otomatik oluşur. Farklı bir model denemek için `NL2SQL_MODEL` ortam değişkenini ayarla.

## Dosyalar

| Dosya | Görevi |
|---|---|
| `seed_db.py` | 200 müşteri, 14 ürün, 1500 siparişlik örnek veritabanını üretir |
| `nl2sql.py` | Çekirdek mantık: şema okuma, SQL üretme, güvenlik kontrolü, çalıştırma |
| `app.py` | Streamlit arayüzü |
| `charts.py` | Altair grafikleri: çubuklar SQL'deki satır sırasıyla, tarih ekseni kronolojik |
| `test_charts.py` | Grafik sıralama testleri |
| `test_nl2sql.py` | API anahtarı gerektirmeyen testler (`python -m pytest -q`) |
| `test_app.py` | Arayüz testleri: model yalnızca Gönder'e basılınca çağrılıyor mu, grafik ve SQL gösterimi (sahte model, API anahtarı gerektirmez) |
| `evals/questions.yaml` | 20 soruluk değerlendirme seti: soru, referans SQL, zorluk (kolay/orta/zor), kategori |
| `evals/holdout.yaml` | 20 soruluk ayrı test seti: gerçekçi, dağınık sorular; yalnızca ölçmek için (prompt bu sete göre değiştirilmez) |
| `evals/run_evals.py` | Soruları modele sorar, sonucu referansla karşılaştırır, doğruluğu toplam ve zorluğa göre yazar |
| `test_run_evals.py` | Karşılaştırma mantığının ve soru setinin testleri (API anahtarı gerektirmez) |

## Değerlendirme

```bash
python evals/run_evals.py --check-gold   # API'siz: referans SQL'lerin sonuçlarını gösterir
python evals/run_evals.py                # 20 soruyu modele sorar (20-40 API çağrısı)
python evals/run_evals.py --only 13 15   # yalnızca seçilen soruları sorar
python evals/run_evals.py --set holdout --runs 3   # ayrı test seti, her soru 3 kez
```

İki set var:

- `questions` (varsayılan): geliştirme seti. Prompt'u iyileştirirken buna bakılır.
- `holdout`: ayrı test seti. Belirsiz ifadeler, yazım hataları, iki adımlı sorular, pencere fonksiyonları ve aynı adlı müşteri tuzağı içerir. Prompt bu sete bakılarak **değiştirilmez**; yoksa set, modelin görmediği sorulardaki başarıyı ölçmez olur.

`--runs N` her soruyu N kez sorar. Model aynı soruya her seferinde aynı SQL'i yazmayabilir. Rapor soru başına geçme oranını ve "kararsız" soruları (bazen geçen, bazen kalan) ayrıca listeler.

Ölçüt çalıştırma doğruluğudur: modelin SQL'i referansla aynı metin olmak zorunda değil, aynı sonucu döndürmesi yeterli.

- Sütun adları, sütun sırası ve fazladan sütunlar yok sayılır.
- Satır sırası yalnızca `sirali: true` olan sorularda (soru sıralama istiyorsa) önemlidir.
- Ondalıklı sayılarda %0.5 göreli tolerans vardır: `ROUND(..., 1)` ile yuvarlanmış doğru bir cevap yanlış sayılmaz. İki değer de tam sayıysa (sayım gibi) birebir eşit olmalıdır.
- "Bugün" 2026-11-20'ye sabitlenmiştir (`seed_db.py` ile aynı); "geçen ay", "son 3 ay" gibi sorular her gün aynı cevabı verir.

Çıktıda toplam doğruluk, zorluk seviyesine göre doğruluk ve başarısız her soru için üretilen SQL ile referans SQL yan yana gösterilir. Sonuçlar `evals/results/` altına tarihli bir JSON dosyası olarak kaydedilir.

Setteki sorular kategorilere ayrılır: filtreleme, gruplama, çoklu JOIN, tarih aralığı, oran hesabı ve şemayla cevaplanamayan 2 soru (beklenen davranış: SQL üretmemek). 15. soru sıfır satışlı ürünleri yakalıyor mu diye bakar: satış kalemlerinden başlayan bir INNER JOIN, o gün hiç satılmayan ürünleri göremez.

## Nasıl çalışır

1. Kullanıcı kenar çubuğunda modelin görebileceği tablo ve sütunları seçer (varsayılan: hiçbiri).
2. Yalnızca seçilen sütunların şeması (`CREATE TABLE` ifadeleri) modele bağlam olarak verilir. SQL üretilirken veri satırları modele gönderilmez; "Modele gönderilen şema" bölümü tam olarak neyin gittiğini gösterir.
   - İstisna: kullanıcı durum, kategori gibi sütunları "Değerleri modele gösterilecek sütunlar" listesinden işaretlerse, bu sütunların farklı değerleri şemaya yorum olarak eklenir (ör. `-- değerler: 'iade', 'iptal', 'tamamlandi'`), böylece model `WHERE` koşulunda doğru değeri yazar. 20'den fazla farklı değeri olan sütunların (ad, e-posta gibi) değerleri gönderilmez; her değer 40 karakterle kesilir.
3. Model soruyu JSON olarak döndürür: SQL, açıklama, varsayımlar ve grafik önerisi. Varsayımlar, soruda açık olmayan ama sonucu değiştiren kararlardır (ör. "Yalnızca tamamlanan siparişler sayıldı"); arayüzde sonucun üstünde "Varsayımlar" başlığıyla gösterilir. Soru netse liste boştur. Arayüz SQL'i okunaklı olsun diye `sqlparse` ile biçimlendirip gösterir; çalıştırılan sorgu modelin ürettiği metnin kendisidir.
4. SQL dört katmanda denetlenir:
   - `validate_sql` yalnızca tek bir `SELECT`'e izin verir.
   - `check_access` SQL'i [sqlglot](https://github.com/tobymao/sqlglot) ile ayrıştırır, takma adları ve alt sorguları gerçek tablolara bağlar, izin listesi dışındaki her tablo/sütunu adıyla bildirerek reddeder. Gizli sütunu olan bir tabloda `SELECT *` ve `tablo.*` yasaktır.
   - Ayrıştırıcının kaçırabileceği her şeye karşı SQLite yetkilendiricisi (`set_authorizer`) aynı kuralı veritabanı içinde, sorgu çalışmadan uygular.
   - Bağlantı salt-okunur açılır. Her sorgu en fazla 5 saniye çalışabilir (`NL2SQL_QUERY_TIMEOUT` ile değiştirilebilir); süreyi aşan sorgu durdurulur.
5. Sorgu hata verirse hata mesajı modele geri gönderilir ve bir kez daha denenir. İzinsiz erişim denemesi ve süre aşımı yeniden denenmez, kullanıcıya gösterilir.
6. İsteğe bağlı yorum: kenar çubuğundaki "Sonucu düz dille yorumla" anahtarı varsayılan olarak kapalıdır. Açılırsa sonucun altında "Yorumla" düğmesi çıkar. Basınca ikinci bir model çağrısı soruyu, SQL'i ve sonucun ilk 50 satırını alır ve 2-4 cümlelik bir yorum döndürür.
   - Bu, sorgu **sonucunun** (gerçek veri satırlarının) modele gittiği tek yerdir; bu yüzden kullanıcı açıkça istemedikçe çalışmaz.
   - Sonuç zaten izin listesine göre süzülmüştür: gizli sütunlar yorum için de gönderilmez.
   - Hücre içerikleri `<sonuc>` etiketi içinde veri olarak işaretlenir; model içlerindeki talimat benzeri metinleri uygulamaz.
   - Sorgu yeniden çalışmaz ve aynı sonuç için yorum bir kez alınır.

## Sonraki adımlar

- [x] Değerlendirme seti: 20 soru + beklenen sonuç; doğruluk oranını ölç
- [x] Sonucu düz dille yorumlayan ikinci bir model çağrısı (isteğe bağlı, varsayılan kapalı)
- [ ] Sohbet geçmişi ("peki ya sadece İstanbul?" gibi takip soruları)
- [ ] Kendi CSV / veritabanını yükleme
- [ ] Streamlit Community Cloud'a yayınlama
