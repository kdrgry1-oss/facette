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
- Cargo: MNG Kargo (SOAP API - Real Integration)

## Current Status: v7.1 - MNG Kargo Real API + Labels ✅

### Tamamlanan Özellikler (2026-03-22)

#### v7.1 - MNG Kargo Gerçek API Entegrasyonu
- [x] **MNG Kargo SOAP API** - Gerçek sipariş oluşturma
  - SiparisGirisiDetayliV3 endpoint
  - FaturaSiparisListesi ile takip numarası alma
  - 10 haneli gerçek tracking number (örn: 6092614519)
  - IP whitelist gereksinimi (production için)
- [x] **Kargo Etiketi** - 10cm x 15cm yazdırılabilir
  - **MNG KARGO** başlığı (siyah banner)
  - Üst barkod (6 haneli kısa kod)
  - Gönderici Bilgileri
  - Alıcı Bilgileri  
  - Kargo Bilgileri
  - Alt barkod (10 haneli tam takip numarası)
- [x] **Toplu Etiket Yazdırma** - Birden fazla sipariş

#### MNG API Credentials (Production)
```
Username: 490059279
Password: Face.0024E
Customer Code: FACETTE DIŞ TİC.A.Ş.
Tax Number: 6080712084
WSDL: https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL
```

**NOT:** Production ortamında sunucu IP'niz MNG'ye kayıtlı olmalı (IP Whitelist).

## API Endpoints - Kargo

### MNG Kargo
- `POST /api/orders/{id}/create-mng-shipment` - MNG API ile kargo oluştur (Admin)
- `GET /api/orders/{id}/cargo-label` - Kargo etiketi (HTML, 10cm x 15cm)
- `POST /api/orders/bulk-labels` - Toplu etiket (body: order_ids array)

### Genel Kargo
- `GET /api/cargo/companies` - Kargo firmaları listesi
- `POST /api/orders/{id}/ship` - Manuel kargo girişi
- `GET /api/orders/{id}/track` - Sipariş takip

## Gönderici Bilgileri (Sabit)
```
Firma: FACETTE DIŞ TİCARET A.Ş.
Telefon: 90 543 330 03 10
Adres: KÜÇÜKÇEKMECE IKITELLI OSB MAH.
       IMSAN D BLOK
       NO: 3 KÜÇÜKÇEKMECE/ ISTANBUL
       Küçükçekmece / İstanbul
```

## Kargo Etiketi Özellikleri
- Boyut: 10cm x 15cm (termal yazıcı uyumlu)
- Barkod: Code128 formatı
- Print CSS: `@page { size: 10cm 15cm; margin: 0; }`
- Header: Kargo firması adı (siyah banner)
- Page break: Her etiket ayrı sayfada

## Test Results
- MNG API: ✅ Sipariş oluşturma çalışıyor
- Tracking Number: ✅ 10 haneli (örn: 6092614519)
- Kargo Etiketi: ✅ MNG KARGO başlığı, barkodlar, tüm bilgiler

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://mega-menu-catalog.preview.emergentagent.com

## P1 - Sonraki Görevler
- [ ] MNG IP Whitelist kaydı (production için)
- [ ] Netgsm SMS bildirimi
- [ ] E-mail bildirimi
- [ ] Müşteri sipariş takip sayfası

## P2 - Backlog
- [ ] Trendyol marketplace
- [ ] GIB e-fatura
- [ ] Iyzico production
- [ ] Gelişmiş raporlama

## File Structure
```
/app/
├── backend/
│   ├── server.py        # ~2000 lines (MNG SOAP API, cargo labels)
│   ├── models.py
│   ├── tests/
│   └── requirements.txt (zeep, python-barcode)
└── frontend/
    └── src/
        └── pages/
            └── admin/
                └── Orders.jsx  # MNG shipment, print labels
```

## Last Updated
2026-03-22 - v7.1 MNG Kargo Real API + 10-digit Tracking Numbers + Labels
