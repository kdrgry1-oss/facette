# FACETTE E-Commerce Platform PRD

## Original Problem Statement
facette.com.tr ile birebir aynı görünüme sahip kapsamlı e-ticaret platformu.

## Tech Stack
- Frontend: React 18, Tailwind CSS, Shadcn/UI
- Backend: FastAPI (Python 3.11), Motor (async MongoDB)
- Database: MongoDB
- Storage: Emergent Object Storage
- Auth: JWT + Google OAuth (Emergent Auth)

## Current Status: v4.0 - Full CMS + Excel Import ✅

### Tamamlanan Özellikler (2026-03-22)

#### UI/UX - facette.com.tr Replica
- [x] Üst Banner: "500 TL ÜZERİ ÜCRETSİZ KARGO" (beyaz bg, siyah text)
- [x] Logo: Doğru FACETTE logosu
- [x] Header: EN YENİLER, GİYİM ▾, AKSESUAR ▾, SALE (kırmızı)
- [x] Alt Kategori Dropdown
- [x] Hero Slider: Tam genişlik, boşluksuz
- [x] Banner Yapısı: Tam genişlik + yarı yarıya, boşluk yok
- [x] Ürün Kartları: Bookmark, sepete ekle (ad yanında)
- [x] Ürün Detay: İki resim yan yana, sol/sağ oklar, sticky header
- [x] Checkout: Menüler gizli

#### Excel Import - 900 Ürün
- [x] Ticimax Excel import script
- [x] Stok kodu, barkod, KDV, tedarikçi, ağırlık, boyutlar
- [x] 50+ alan destekli ürün modeli
- [x] 409 ürün başarıyla import edildi

#### Admin Panel - Gelişmiş
- [x] **Ürünler**: Stok kodu, barkod görüntüleme
- [x] **Ürün Düzenleme**: 5 sekmeli form (Temel, Fiyat, Görseller, Stok, SEO)
- [x] **Görsel Yükleme**: Object Storage entegrasyonu
- [x] **Siparişler**: Fatura kes, kargo barkodu, toplu işlemler
- [x] **Sayfa Tasarımı (CMS)**: Banner/blok yönetimi

#### Entegrasyonlar
- [x] Google OAuth (Emergent Auth)
- [x] Object Storage (görsel yükleme)
- [x] API endpoint'leri (page-blocks, upload/image, files)

## Admin Panel Menüsü
1. Dashboard
2. Ürünler (stok kodu, barkod, görsel yükleme)
3. Siparişler (fatura, kargo, toplu işlem)
4. Kategoriler
5. Sayfa Tasarımı (CMS)
6. Bannerlar
7. Kampanyalar
8. Sayfalar
9. Ayarlar

## API Endpoints

### Page Blocks (CMS)
- GET /api/page-blocks - Tüm blokları getir
- POST /api/page-blocks - Yeni blok ekle
- PUT /api/page-blocks/{id} - Blok güncelle
- DELETE /api/page-blocks/{id} - Blok sil

### Upload
- POST /api/upload/image - Görsel yükle
- GET /api/files/{path} - Dosya servis

### Auth
- POST /api/auth/google/session - Google OAuth

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://fashion-ecom-mvp.preview.emergentagent.com

## P1 - Sonraki Görevler
- [ ] Varyant yönetimi (renk, beden bazlı stok)
- [ ] Checkout akışı tamamlama
- [ ] Sipariş takibi müşteri paneli

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
│   ├── server.py
│   ├── models.py
│   ├── import_excel.py    # Excel import script
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Header.jsx
│       │   ├── ProductCard.jsx
│       │   └── ...
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── ProductDetail.jsx
│       │   └── admin/
│       │       ├── Products.jsx      # 5-tab form
│       │       ├── Orders.jsx        # Invoice, cargo
│       │       ├── PageDesign.jsx    # CMS
│       │       └── ...
│       └── context/
└── memory/PRD.md
```

## Last Updated
2026-03-22 - v4.0 CMS + Excel Import + Görsel Yükleme
