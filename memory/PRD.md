# FACETTE E-Commerce Platform PRD

## Original Problem Statement
facette.com.tr ile birebir aynı görünüme sahip kapsamlı e-ticaret platformu.

## Tech Stack
- Frontend: React 18, Tailwind CSS, Shadcn/UI
- Backend: FastAPI (Python 3.11), Motor (async MongoDB)
- Database: MongoDB

## Current Status: v2.0 - facette.com.tr Replica ✅

### What's Been Implemented (2026-03-22)

#### UI/UX - facette.com.tr Replica
- [x] **Üst Banner**: "500 TL ÜZERİ ÜCRETSİZ KARGO"
- [x] **Header**: Logo ortada, menü solda (EN YENİLER, GİYİM, AKSESUAR, SALE kırmızı)
- [x] **Alt Kategori Dropdown**: GİYİM ve AKSESUAR hoverde alt kategoriler
- [x] **Hero Slider**: facette.com.tr görsellerinden
- [x] **Banner Yapısı**: Tam genişlik (BLOOM TOGETHER) + yarı yarıya (GÖMLEK, ÇANTA)
- [x] **Ürün Kartları**: Bookmark ikonu, sepete ekle ikonu (ad yanında), resim noktaları
- [x] **Arama**: "EN ÇOK ARANANLAR", canlı arama sonuçları
- [x] **Ürün Detay**: 
  - "Beden Tablosu" linki SEPETE EKLE üzerinde
  - Son görsel popup olarak açılıyor
  - Sayfa üstten açılıyor (scroll fix)
  - Tekrar eden resimler kaldırıldı
- [x] **Checkout**: Menüler gizli, sadece logo

#### Admin Panel - Gelişmiş Sipariş Yönetimi
- [x] **Fatura Kesme**: Her siparişte "Fatura Kes" butonu
- [x] **Kargo Barkodu**: "Barkod Oluştur" butonu (MNG, DHL, Yurtiçi, Aras)
- [x] **Toplu İşlemler**: Checkbox ile seçim, toplu barkod, toplu durum güncelleme
- [x] **Sipariş Detay Modal**: Fatura ve kargo bilgileri gösterimi

## API Endpoints

### Orders - Advanced
- GET /api/orders/{order_id}/detail - Admin detaylı sipariş
- POST /api/orders/{order_id}/invoice - Fatura oluştur
- POST /api/orders/{order_id}/cargo-barcode - Kargo barkodu
- POST /api/orders/bulk/cargo-barcode - Toplu kargo barkodu
- POST /api/orders/bulk/status - Toplu durum güncelleme

### Search
- GET /api/search/popular - En çok arananlar
- POST /api/search/log - Arama loglama

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://fashion-ecom-mvp.preview.emergentagent.com

## P1 - Devam Eden Görevler
- [ ] Sayfa tasarım yönetimi (admin'den banner/içerik düzenleme)
- [ ] Ürün varyant yönetimi (renk, beden stok takibi)
- [ ] Checkout tamamlama
- [ ] Kullanıcı hesabım sayfası

## P2 - Entegrasyonlar
- [ ] Iyzico ödeme
- [ ] MNG/DHL kargo API
- [ ] Netgsm SMS
- [ ] Trendyol API
- [ ] GIB e-fatura

## File Structure
```
/app/
├── backend/
│   ├── server.py          # All API endpoints
│   ├── models.py          # Pydantic models
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Header.jsx      # facette style, dropdown menu
│       │   ├── ProductCard.jsx # bookmark, cart icon next to name
│       │   ├── CartDrawer.jsx
│       │   └── Footer.jsx
│       ├── pages/
│       │   ├── Home.jsx        # Full/half banners, products
│       │   ├── Category.jsx    # Filter sidebar, grid options
│       │   ├── ProductDetail.jsx # Size chart popup, scroll fix
│       │   ├── Checkout.jsx    # Hidden menu
│       │   └── admin/
│       │       ├── Orders.jsx  # Invoice, cargo, bulk ops
│       │       └── ...
│       └── context/
└── memory/PRD.md
```

## Last Updated
2026-03-22 - facette.com.tr replica + admin enhancements
