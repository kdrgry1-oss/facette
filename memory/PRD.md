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
- SMS: Netgsm API

## Current Status: v9.0 - Real Product Data + Variants ✅

### Tamamlanan Özellikler (2026-03-22)

#### v9.0 - Gerçek Ürün Verileri ve Varyantlar
- [x] **XML + Excel'den Gerçek Veriler**
  - 170 ürün, 900 varyant satırı
  - Gerçek stok kodları (FCSS1100001, FCSS0700004...)
  - Gerçek barkodlar (8684483525551, 8684483525452...)
  - Varyasyon kodları (2828-8335, 2829-8340...)
- [x] **Varyant Sistemi**
  - Her ürünün birden fazla varyantı (beden + renk kombinasyonları)
  - Her varyantın kendi stok kodu, barkodu, stok miktarı
  - Bedenler: XS, S, M, L, XL, STD
  - Renkler: Mavi, Buz Mavisi, Ekru, Bej, Siyah, Kahverengi...
- [x] **Varyantları Görüntüle Butonu**
  - Admin ürün listesinde "X Varyant" butonu
  - Modal ile tüm varyant detayları
  - Beden, Renk, Stok Kodu, Barkod, Varyasyon Kodu, Stok, Fiyat, Durum

#### v8.0 - Order Tracking + SMS
- [x] Sipariş Takip Sayfası
- [x] Netgsm SMS Entegrasyonu

#### v7.0 - MNG Kargo
- [x] MNG Kargo API entegrasyonu
- [x] Kargo etiketi (10cm x 15cm)

## Varyant Yapısı (Excel'den)
```
URUNADI: Tina Straight Fit Jean
├── Varyant 1: L + Mavi
│   ├── STOKKODU: FCSS1100001
│   ├── BARKOD: 8684483525551
│   ├── VARYASYONKODU: 2828-8335
│   └── STOKADEDI: 47
├── Varyant 2: M + Mavi
│   ├── STOKKODU: FCSS1100001
│   ├── BARKOD: 8684483525568
│   └── ...
└── ... (15 varyant total)
```

## Admin Panel - Ürünler Sayfası
| Sütun | Açıklama |
|-------|----------|
| Görsel | Ürün resmi |
| Ürün Adı | Ad + Kategori |
| Stok Kodu | Ana stok kodu |
| Barkod | Ana barkod |
| **Varyantlar** | "X Varyant" butonu (tıklanabilir) |
| Fiyat | Satış fiyatı |
| Stok | Toplam stok |
| Durum | Aktif/Pasif |
| İşlemler | Edit, Copy, Toggle, More |

## Import Scripts
- `/app/backend/import_excel_v2.py` - Excel'den varyantlı ürün import
- XML'den görseller çekme (inline script)

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://mega-menu-catalog.preview.emergentagent.com

## Veri Kaynakları
- XML: https://www.facette.com.tr/XMLExport/7BECCB0A782647BFAB843E68AD11E468
- Excel: TicimaxExport (23).xls

## P1 - Sonraki Görevler
- [ ] Ürün detay sayfasında varyant seçimi (beden/renk dropdown)
- [ ] Sepete varyant bazlı ekleme
- [ ] Stok kontrolü varyant bazlı

## P2 - Backlog
- [ ] Trendyol marketplace
- [ ] GIB e-fatura
- [ ] Gelişmiş raporlama

## Last Updated
2026-03-22 - v9.0 Real Product Data + Variants System
