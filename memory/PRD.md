# FACETTE E-Commerce Platform PRD

## Original Problem Statement
facette.com.tr ile birebir aynı görünüme sahip kapsamlı e-ticaret platformu.

## Tech Stack
- Frontend: React 18, Tailwind CSS, Shadcn/UI
- Backend: FastAPI (Python 3.11), Motor (async MongoDB)
- Database: MongoDB
- Storage: Emergent Object Storage
- Auth: JWT + Google OAuth (Emergent Auth)
- Payment: Iyzico (Sandbox)

## Current Status: v6.0 - Full Feature Implementation ✅

### Tamamlanan Özellikler (2026-03-22)

#### v6.0 - New Features
- [x] **Varyant Yönetimi** - Admin panelinde beden/renk/barkod/stok varyant yönetimi
- [x] **Benzer Ürünler** - Ürün sayfasında otomatik kategori-bazlı benzer ürün önerileri
- [x] **Kombin Ürünler** - "Bu Ürünle Giyin" bölümü (tamamlayıcı kategoriler)
- [x] **Iyzico Ödeme** - 3D Secure ödeme entegrasyonu (sandbox)
- [x] **Kargo Entegrasyonu** - MNG, DHL, Yurtiçi, Aras, PTT kargo firmaları
- [x] **Sipariş Takip** - Kargo takip URL'leri ve takip numaraları

#### v5.0 - Bug Fixes & UI
- [x] Çift ürün sorunu çözüldü (197 duplicate ürün silindi)
- [x] Ürün sayfası slider okları kaldırıldı, 2 sütunlu grid layout
- [x] Accordion kayma sorunu çözüldü
- [x] Admin ürün işlemleri (Edit, Copy, Active/Passive, More menu)

#### UI/UX - facette.com.tr Replica
- [x] Üst Banner, Logo, Header, Mega Menu
- [x] Hero Slider ve Banner yapısı
- [x] Ürün Kartları ve Detay sayfası
- [x] Checkout akışı

## Admin Panel Özellikleri

### Ürün Yönetimi
- 6 sekmeli form: Temel, Fiyat, Görseller, Stok, Varyantlar, SEO
- Varyant yönetimi: Beden, Renk, Barkod, Stok, Fiyat farkı
- Görsel yükleme (Object Storage)
- Kopyalama, Aktif/Pasif, Silme işlemleri

### Sipariş Yönetimi
- Sipariş listesi ve filtreleme
- Fatura oluşturma (FAT-YYYYMMDD-XXXXXX)
- Kargoya verme modal'ı
- Kargo takip linki
- Toplu işlemler (barkod, durum güncelleme)

## API Endpoints

### Products
- GET /api/products - Ürün listesi
- GET /api/products/{id} - Ürün detayı
- GET /api/products/{id}/similar - Benzer ürünler
- GET /api/products/{id}/combo - Kombin ürünler
- POST /api/products/{id}/variants - Varyant ekle
- PUT /api/products/{id}/variants/{vid} - Varyant güncelle
- DELETE /api/products/{id}/variants/{vid} - Varyant sil

### Payment (Iyzico)
- POST /api/payment/initialize - Ödeme başlat
- POST /api/payment/callback - Ödeme callback

### Cargo
- GET /api/cargo/companies - Kargo firmaları
- POST /api/orders/{id}/ship - Kargoya ver
- GET /api/orders/{id}/track - Sipariş takip

## Test Results
- Backend: 20/20 tests passed (100%)
- Frontend: All features working (100%)

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://mega-menu-catalog.preview.emergentagent.com

## Kargo Firmaları
| Firma | Kod | Takip URL |
|-------|-----|-----------|
| MNG Kargo | MNG | mngkargo.com.tr |
| DHL | DHL | dhl.com |
| Yurtiçi | YURTICI | yurticikargo.com |
| Aras | ARAS | araskargo.com.tr |
| PTT | PTT | ptt.gov.tr |

## MOCKED APIs
- **Iyzico Payment**: Sandbox mode only (no real payments)

## P1 - Sonraki Görevler
- [ ] Iyzico production key entegrasyonu
- [ ] SMS bildirimi (Netgsm)
- [ ] E-mail bildirimi (Resend/SendGrid)
- [ ] Müşteri hesap sayfası (sipariş geçmişi)

## P2 - Backlog
- [ ] Trendyol marketplace entegrasyonu
- [ ] GIB e-fatura entegrasyonu
- [ ] Gelişmiş raporlama
- [ ] SEO iyileştirmeleri

## File Structure
```
/app/
├── backend/
│   ├── server.py        # Main API (~1300 lines)
│   ├── models.py        # Pydantic models
│   ├── tests/
│   │   └── test_new_features.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Header.jsx
│       │   ├── Footer.jsx
│       │   └── ProductCard.jsx
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── ProductDetail.jsx  # 2-col grid, similar/combo
│       │   ├── Checkout.jsx       # Iyzico integration
│       │   └── admin/
│       │       ├── Products.jsx   # Variants tab
│       │       ├── Orders.jsx     # Ship modal
│       │       └── ...
│       └── context/
└── memory/PRD.md
```

## Last Updated
2026-03-22 - v6.0 Full Feature Implementation
