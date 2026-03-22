# FACETTE E-Commerce Platform PRD

## Original Problem Statement
facette.com.tr ile birebir aynı görünüme sahip kapsamlı e-ticaret platformu.

## Tech Stack
- Frontend: React 18, Tailwind CSS, Shadcn/UI
- Backend: FastAPI (Python 3.11), Motor (async MongoDB)
- Database: MongoDB
- Storage: Emergent Object Storage
- Auth: JWT + Google OAuth (Emergent Auth)

## Current Status: v3.0 - facette.com.tr Replica ✅

### What's Been Implemented (2026-03-22)

#### UI/UX - facette.com.tr Replica
- [x] **Üst Banner**: "500 TL ÜZERİ ÜCRETSİZ KARGO" (beyaz bg, siyah text)
- [x] **Logo**: Doğru FACETTE logosu
- [x] **Header Menü**: EN YENİLER, GİYİM ▾, AKSESUAR ▾, SALE (kırmızı)
- [x] **Alt Kategori Dropdown**: Hoverde tüm alt kategoriler
- [x] **Hero Slider**: Tam genişlik, boşluksuz
- [x] **Banner Yapısı**: 
  - Tam genişlik (BLOOM TOGETHER)
  - Yarı yarıya (GÖMLEK, ÇANTA)
  - Aralarında boşluk yok
- [x] **Ürün Kartları**: Bookmark, sepete ekle (ad yanında)
- [x] **Ürün Detay**:
  - İki resim yan yana
  - Sol/sağ navigasyon okları
  - Sticky header (scroll sonrası)
  - Beden Tablosu popup

#### Authentication
- [x] **Google Auth**: Emergent Auth ile entegre
- [x] **JWT Auth**: Normal e-posta/şifre girişi

#### Object Storage
- [x] **Görsel Yükleme**: /api/upload/image endpoint'i
- [x] **Dosya Servisi**: /api/files/{path} endpoint'i

#### Ürün Modeli - Ticimax Excel Alanları
- [x] urun_karti_id, urun_id, stock_code, variation_code
- [x] barcode, gtip_code, unit, keywords
- [x] supplier, purchase_price, market_price
- [x] vat_rate, vat_included, currency
- [x] cargo_weight, product_weight, dimensions
- [x] min/max_order_qty, estimated_delivery
- [x] marketplace_active, custom_fields

#### Admin Panel Özellikleri
- [x] Sipariş yönetimi (fatura kes, kargo barkodu)
- [x] Toplu işlemler (toplu barkod, toplu durum)
- [x] Detay modal (fatura/kargo bilgileri)

## API Endpoints

### Auth
- POST /api/auth/register
- POST /api/auth/login
- GET /api/auth/me
- POST /api/auth/google/session - Google OAuth callback

### Upload
- POST /api/upload/image - Görsel yükleme
- GET /api/files/{path} - Dosya servisi

### Orders (Admin)
- GET /api/orders/{id}/detail
- POST /api/orders/{id}/invoice
- POST /api/orders/{id}/cargo-barcode
- POST /api/orders/bulk/cargo-barcode
- POST /api/orders/bulk/status

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://fashion-ecom-mvp.preview.emergentagent.com

## P1 - Devam Eden Görevler
- [ ] Sayfa tasarım yönetimi (CMS)
- [ ] Excel import - tüm ürünleri güncelleme
- [ ] Admin ürün ekleme - görsel yükleme arayüzü
- [ ] Checkout akışı tamamlama

## P2 - Entegrasyonlar
- [ ] Iyzico ödeme
- [ ] MNG/DHL kargo API
- [ ] Netgsm SMS
- [ ] Trendyol API
- [ ] GIB e-fatura

## Last Updated
2026-03-22 - v3.0 facette replica + Google Auth + Object Storage
