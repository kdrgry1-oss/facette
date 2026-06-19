# Paket 3 (KÜMÜLATİF) — Meta Feed + Kupon + SEO + Taksit + Güven/Teslimat

> Önceki tüm paketleri içerir. Tek başına deploy edilebilir.

## backend/routes/products.py
- Google feed: item_group_id + color + size (flag arkasında; ?group=off / settings.feed_variant_grouping=false geri al). g:id sabit.

## frontend/src/pages/Checkout.jsx
- "En avantajlı indirim otomatik uygulandı" onayı + katlanır promosyon alanı (Mango usulü).
- (YENİ) Güven şeridi: Güvenli ödeme · 3D Secure · 14 gün kolay iade · Gizli ücret yok.
- (YENİ) Özet panelinde Tahmini teslimat tarihi (2-4 iş günü, hafta sonu atlanır).

## frontend/src/pages/ProductDetail.jsx
- JSON-LD duplicate fix (edge bastıysa client basmaz).
- Taksit bilgisi (fiyat altında).
- (YENİ) Sepete Ekle altında görünür "🚚 Tahmini teslimat: X - Y" satırı.

## frontend/src/pages/Cart.jsx
- Sepet özetinde taksit bilgisi.

## Doğrulama
- products.py: ast.parse + feed simülasyonu OK (g:id sabit, gruplama doğru, well-formed).
- Checkout/ProductDetail/Cart: esbuild (jsx=automatic) exit 0.

## KAPSAM DIŞI (bilerek): Express ödeme (Apple/Google Pay)
- Gerçek ödeme sağlayıcı (iyzico/PSP) entegrasyonu + sertifika gerektirir; tek oturumda güvenli paketlenemez.
  Ayrı bir entegrasyon görevi olarak ele alınmalı.

## Zaten mevcut (dokümanın istediği, halihazırda var)
- index.html OG/Twitter/canonical + Organization/WebSite JSON-LD; functions/_middleware.js edge SEO;
  PDP beden/beden-tablosu/sticky/Eklendi✓/Gelince Haber Ver; sepet ücretsiz kargo eşiği; checkout SSL badge + toast validasyon.
