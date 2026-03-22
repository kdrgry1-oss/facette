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
- Cargo: MNG Kargo (SOAP API)

## Current Status: v7.0 - MNG Kargo Integration + Cargo Labels ✅

### Tamamlanan Özellikler (2026-03-22)

#### v7.0 - MNG Kargo & Etiket Sistemi
- [x] **MNG Kargo API** - Gerçek SOAP web service entegrasyonu
  - Customer Code: FACETTE DIŞ TİC.A.Ş.
  - Username: 490059279
  - Kargo Vergi No: 6080712084
- [x] **Kargo Etiketi** - 10cm x 15cm yazdırılabilir etiket
  - Üst barkod (kısa takip numarası)
  - Gönderici Bilgileri (Firma, Telefon, Adres)
  - Alıcı Bilgileri (İsim, Telefon, Adres)
  - Kargo Bilgileri (Firma, Ödeme Türü, Kargo Tipi, Paket Sayısı, Desi)
  - Alt barkod (tam takip numarası)
- [x] **Toplu Etiket Yazdırma** - Birden fazla siparişi tek seferde yazdır
- [x] **Admin Sipariş Butonları**
  - "MNG ile Gönder" - Otomatik MNG API ile kargo oluştur
  - "Etiket Yazdır" - Tek sipariş etiketi
  - "Toplu Etiket Yazdır" - Seçili siparişlerin etiketleri

#### v6.0 - Full Features
- [x] Varyant Yönetimi (beden/renk/stok)
- [x] Benzer Ürünler & Kombin Ürünler
- [x] Iyzico Ödeme (Sandbox)
- [x] Kargo Entegrasyonu (MNG, DHL, Yurtiçi, Aras, PTT)

#### v5.0 - Bug Fixes
- [x] Çift ürün temizliği
- [x] Ürün sayfası 2 sütunlu grid
- [x] Admin ürün işlemleri

## API Endpoints - Kargo

### Kargo İşlemleri
- `GET /api/cargo/companies` - Kargo firmaları listesi
- `POST /api/orders/{id}/ship` - Siparişi kargoya ver (manuel)
- `POST /api/orders/{id}/create-mng-shipment` - MNG API ile kargo oluştur
- `GET /api/orders/{id}/track` - Sipariş takip bilgisi

### Kargo Etiketi
- `GET /api/orders/{id}/cargo-label` - Tek sipariş etiketi (HTML)
- `POST /api/orders/bulk-labels` - Toplu etiket (HTML, body: order_ids array)

## Kargo Etiketi Özellikleri
- Boyut: 10cm x 15cm (termal yazıcı uyumlu)
- Barkod: Code128 formatı
- Print CSS: `@page { size: 10cm 15cm; margin: 0; }`
- Page break: Her etiket ayrı sayfada

## MNG Kargo Bilgileri
| Alan | Değer |
|------|-------|
| Customer Code | FACETTE DIŞ TİC.A.Ş. |
| Username | 490059279 |
| Password | Face.0024E |
| Tax Number | 6080712084 |
| Company Name | MNG KARGO YURTİÇİ VE YURT |
| WSDL URL | https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL |

## Gönderici Bilgileri (Sabit)
- Firma: FACETTE DIŞ TİCARET A.Ş.
- Telefon: 90 543 330 03 10
- Adres: KÜÇÜKÇEKMECE IKITELLI OSB MAH. IMSAN D BLOK NO: 3 KÜÇÜKÇEKMECE/ ISTANBUL

## Test Results
- Backend: 19/19 tests passed (100%)
- Frontend: All features working (100%)

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://mega-menu-catalog.preview.emergentagent.com

## P1 - Sonraki Görevler
- [ ] Netgsm SMS bildirimi
- [ ] E-mail bildirimi (kargo durumu)
- [ ] Müşteri sipariş takip sayfası
- [ ] Iyzico production key

## P2 - Backlog
- [ ] Trendyol marketplace
- [ ] GIB e-fatura
- [ ] Gelişmiş raporlama

## File Structure
```
/app/
├── backend/
│   ├── server.py        # ~1700 lines (MNG API, cargo labels)
│   ├── models.py
│   ├── tests/
│   │   ├── test_new_features.py
│   │   └── test_mng_cargo_labels.py
│   └── requirements.txt (zeep, python-barcode added)
└── frontend/
    └── src/
        └── pages/
            └── admin/
                └── Orders.jsx  # MNG shipment, print labels
```

## Last Updated
2026-03-22 - v7.0 MNG Kargo Integration + Cargo Labels
