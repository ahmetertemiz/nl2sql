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
| `test_nl2sql.py` | API anahtarı gerektirmeyen testler (`python -m pytest -q`) |
| `eval_set.json` | 21 soruluk değerlendirme seti: soru + referans SQL |
| `evaluate.py` | Soruları modele sorar, sonucu referansla karşılaştırır, doğruluk oranını yazar |
| `test_evaluate.py` | Karşılaştırma mantığının testleri (API anahtarı gerektirmez) |
| `test_app.py` | Arayüz testleri: model yalnızca Gönder'e basılınca çağrılıyor mu (sahte model, API anahtarı gerektirmez) |

## Değerlendirme

```bash
python evaluate.py --check-gold   # API'siz: referans SQL'lerin sonuçlarını gösterir
python evaluate.py                # tüm soruları modele sorar (21-42 API çağrısı), doğruluğu yazar
python evaluate.py --only 21      # yalnızca seçilen soruları sorar
```

21. soru, sıfır satışlı ürünleri yakalıyor mu diye bakar: o gün hiç satılmayan ürünler de "3 adetten az" sayılmalıdır. Satış kalemlerinden başlayan (INNER JOIN) bir sorgu bu ürünleri göremez ve soruyu kaçırır.

Ölçüt çalıştırma doğruluğudur: modelin SQL'i referansla aynı metin olmak zorunda değil, aynı sonucu döndürmesi yeterli. Sütun adları ve fazladan sütunlar yok sayılır; satır sırası yalnızca `"ordered": true` olan sorularda önemlidir. Ayrıntılar `eval_results.json` dosyasına yazılır.

## Nasıl çalışır

1. Kullanıcı kenar çubuğunda modelin görebileceği tablo ve sütunları seçer (varsayılan: hiçbiri).
2. Yalnızca seçilen sütunların şeması (`CREATE TABLE` ifadeleri) modele bağlam olarak verilir. Veri satırları modele hiç gönderilmez; "Modele gönderilen şema" bölümü tam olarak neyin gittiğini gösterir.
   - İstisna: kullanıcı durum, kategori gibi sütunları "Değerleri modele gösterilecek sütunlar" listesinden işaretlerse, bu sütunların farklı değerleri şemaya yorum olarak eklenir (ör. `-- değerler: 'iade', 'iptal', 'tamamlandi'`), böylece model `WHERE` koşulunda doğru değeri yazar. 20'den fazla farklı değeri olan sütunların (ad, e-posta gibi) değerleri gönderilmez; her değer 40 karakterle kesilir.
3. Model soruyu JSON olarak döndürür: SQL, açıklama ve grafik önerisi.
4. SQL dört katmanda denetlenir:
   - `validate_sql` yalnızca tek bir `SELECT`'e izin verir.
   - `check_access` SQL'i [sqlglot](https://github.com/tobymao/sqlglot) ile ayrıştırır, takma adları ve alt sorguları gerçek tablolara bağlar, izin listesi dışındaki her tablo/sütunu adıyla bildirerek reddeder. Gizli sütunu olan bir tabloda `SELECT *` ve `tablo.*` yasaktır.
   - Ayrıştırıcının kaçırabileceği her şeye karşı SQLite yetkilendiricisi (`set_authorizer`) aynı kuralı veritabanı içinde, sorgu çalışmadan uygular.
   - Bağlantı salt-okunur açılır. Her sorgu en fazla 5 saniye çalışabilir (`NL2SQL_QUERY_TIMEOUT` ile değiştirilebilir); süreyi aşan sorgu durdurulur.
5. Sorgu hata verirse hata mesajı modele geri gönderilir ve bir kez daha denenir. İzinsiz erişim denemesi ve süre aşımı yeniden denenmez, kullanıcıya gösterilir.

## Sonraki adımlar

- [x] Değerlendirme seti: 20 soru + beklenen sonuç; doğruluk oranını ölç
- [ ] Sonucu düz dille yorumlayan ikinci bir model çağrısı
- [ ] Sohbet geçmişi ("peki ya sadece İstanbul?" gibi takip soruları)
- [ ] Kendi CSV / veritabanını yükleme
- [ ] Streamlit Community Cloud'a yayınlama
