# Paket 5 (KÜMÜLATİF) — Meta Feed + Kupon + SEO + Taksit + Güven/Teslimat + Taksonomi

> Önceki tüm paketleri içerir. Tek başına deploy edilebilir.

## YENİ (bu pakette): P2-13 yorum/puan — storefront PDP entegrasyonu
- Backend reviews API (extras.py: POST /reviews, GET /reviews/product/:id, admin moderasyon) ZATEN vardı;
  admin sayfası (ProductReviews.jsx → /admin/yorumlar) ZATEN bağlıydı. EKSİK olan storefront UI eklendi.
- frontend/src/pages/ProductDetail.jsx: "Değerlendirmeler" bölümü — ortalama yıldız + onaylı yorum listesi
  (kullanıcı adı, yıldız, başlık, yorum, tarih, FACETTE admin yanıtı) + giriş yapan kullanıcıya yorum formu
  (1-5 yıldız + başlık + yorum). POST sonrası "moderasyon sonrası yayınlanır" bilgisi. Giriş yoksa /giris linki.
- Backend modeline birebir uyumlu (rating 1-5, title≤120, comment≤2000, status pending→approved).

## YENİ (bu pakette): P3-19 çift success route → tek canonical + 301
- frontend/public/_redirects (YENİ): /siparis-tamamlandi/* → /order-success/:splat 301 (Cloudflare gerçek 301, SEO tek canonical).
- frontend/src/App.js: Navigate+useParams import; /siparis-tamamlandi/:orderNumber artık OrderSuccess yerine
  <LegacyOrderRedirect> (SPA-içi client redirect, _redirects'in SPA fallback'i). /order-success canonical kalır.

## YENİ (bu pakette): backend/scripts/clean_categories.py — kategori temizlik scripti
- DRY-RUN varsayılan (hiçbir şey değişmez): test/placeholder kategori + bağlı ürün sayısı,
  duplike gruplar (aksesuar + aksesuar-aksesuar) + önerilen ANA + 301 önerisi, bozuk slug'lar raporlanır.
- `--apply` SADECE güvenli işler: ürünsüz test kategorisini siler + bozuk slug'ı düzeltir (eski slug slug_aliases'a).
- Duplike BİRLEŞTİRME (ürün taşıma) OTOMATİK YAPILMAZ — geri alınamaz; rapora göre onayla.
- Çalıştırma (backend container): `python -m scripts.clean_categories`  (uygula: `--apply`)

## backend/routes/products.py — Meta feed item_group_id + color + size (flag; ?group=off ile geri al). g:id sabit.
## backend/routes/categories.py — get_categories visible_only param (storefront pasif+test gizle; admin korunur).
## frontend SlugRouter/MiuMiuTheme/Category — /categories?visible_only=true.
## frontend Checkout — kupon otomatik indirim onayı + katlanır alan + güven şeridi + tahmini teslimat.
## frontend ProductDetail — JSON-LD duplicate fix + taksit + görünür tahmini teslimat.
## frontend Cart — taksit bilgisi.

## Doğrulama
- products.py / categories.py / clean_categories.py: ast.parse OK; feed sim + slug/test/duplike mantığı doğrulandı
  (İç Giyim→ic-giyim, Şort→sort; HB_CAT_TEST yakalanıyor; Giyim/kontes korunuyor).
- 6 frontend dosyası: esbuild (jsx=automatic) exit 0.
