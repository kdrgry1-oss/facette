# Facette — Önizleme Veritabanı Yedeği (Preview DB Dump)

Bu klasör, **önizleme (preview) ortamındaki güncel MongoDB** verisinin tam yedeğini içerir:
güncellenmiş ürün kataloğu (359 ürün), R2/Cloudflare CDN'e taşınmış görsel URL'leri
(`cdn.facette.com.tr`), düzeltilmiş slug'lar, banner/page_blocks kayıtları, siparişler,
kullanıcılar ve diğer tüm koleksiyonlar.

> ⚠️ **GİZLİ:** Bu dosya kullanıcı kişisel verisi (10.000+ kullanıcı, siparişler) içerir.
> Herkese açık bir yere (public R2/URL, herkese açık repo) **koymayın**. Güvenli tutun.

## Dosya
- `facette_preview_<tarih>.archive.gz` → `mongodump` gzip arşivi (tüm DB).

## Kendi sunucunuza geri yükleme (own-server migration)
Hedef MongoDB'nizde (boş veya üzerine yazılacak):

```bash
# Yeni bir veritabanına geri yükle (önerilen: hedef adı netleştir)
mongorestore --uri="<HEDEF_MONGO_URL>" \
  --gzip --archive=facette_preview_<tarih>.archive.gz \
  --nsFrom='test_database.*' --nsTo='<HEDEF_DB_ADI>.*'

# Üzerine yazmak istiyorsanız (mevcut koleksiyonları düşürerek):
mongorestore --uri="<HEDEF_MONGO_URL>" --drop \
  --gzip --archive=facette_preview_<tarih>.archive.gz \
  --nsFrom='test_database.*' --nsTo='<HEDEF_DB_ADI>.*'
```

Notlar:
- Kaynak DB adı `test_database`'tir; `--nsFrom/--nsTo` ile kendi DB adınıza eşleyin.
- Backend `.env` içinde `MONGO_URL`, `DB_NAME` ve `R2_*` değişkenlerini kendi ortamınıza göre
  ayarlamayı unutmayın. Görseller `cdn.facette.com.tr` (Cloudflare R2 + Transformations)
  üzerinden gelir; bu domain Cloudflare hesabınıza bağlı olduğu için yeni sunucuda da çalışır.

## Emergent production'a geri yükleme
Önizleme ile production AYRI veritabanı kullanır ve production DB'ye dışarıdan erişim yoktur.
Bu yedeği Emergent production'a uygulatmak için **support@emergent.sh** adresine job ID ile
yazıp "preview DB'yi production'a restore edin" talebinde bulunun (bu dosyayı paylaşabilirsiniz).
