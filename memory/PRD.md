# FACETTE E-Commerce Platform PRD

## Original Problem Statement
facette.com.tr ile birebir aynı görünüme sahip kapsamlı e-ticaret platformu.

## Tech Stack
- Frontend: React 18, Tailwind CSS, Shadcn/UI
- Backend: FastAPI (Python 3.11), Motor (async MongoDB)
- Database: MongoDB
- Storage: Emergent Object Storage
- Auth: JWT + Google OAuth (Emergent Auth)

## Current Status: v5.0 - Bug Fixes + UI Improvements ✅

### Tamamlanan Özellikler (2026-03-22)

#### Bug Fixes (v5.0)
- [x] Çift ürün sorunu çözüldü (197 duplicate ürün silindi)
- [x] Ürün sayfası slider okları kaldırıldı, 2 sütunlu grid layout eklendi
- [x] Accordion (Ürün Özellikleri) kayma sorunu çözüldü - custom toggle kullanıldı
- [x] Admin ürün listesinde işlem ikonları eklendi (Edit, Copy, Active/Passive, More menu)

#### UI/UX - facette.com.tr Replica
- [x] Üst Banner: "500 TL ÜZERİ ÜCRETSİZ KARGO" (beyaz bg, siyah text)
- [x] Logo: Doğru FACETTE logosu
- [x] Header: EN YENİLER, GİYİM ▾, AKSESUAR ▾, SALE (kırmızı)
- [x] Mega Menu: ÜST GİYİM, ALT GİYİM, DIŞ GİYİM sütunları
- [x] Hero Slider: Tam genişlik, boşluksuz
- [x] Banner Yapısı: Tam genişlik + yarı yarıya, boşluk yok
- [x] Ürün Kartları: Bookmark, sepete ekle (ad yanında)
- [x] Ürün Detay: Tüm görseller 2 sütunlu grid'de, sticky header
- [x] Checkout: Menüler gizli

#### Ürün Yönetimi
- [x] 269 benzersiz ürün (duplicates silindi)
- [x] Stok kodu, barkod, KDV, tedarikçi, ağırlık, boyutlar
- [x] 50+ alan destekli ürün modeli

#### Admin Panel - Gelişmiş
- [x] **Ürünler**: Stok kodu, barkod görüntüleme
- [x] **Ürün İşlemleri**: Edit, Copy (kopyala), Aktif/Pasif, More menu (görüntüle, link kopyala, sil)
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
2. Ürünler (stok kodu, barkod, görsel yükleme, kopyalama, aktif/pasif)
3. Siparişler (fatura, kargo, toplu işlem)
4. Kategoriler
5. Sayfa Tasarımı (CMS)
6. Bannerlar
7. Kampanyalar
8. Sayfalar
9. Ayarlar

## API Endpoints

### Products
- GET /api/products - Ürün listesi
- GET /api/products/{id} - Ürün detayı
- POST /api/products - Yeni ürün (Admin)
- PUT /api/products/{id} - Ürün güncelle (Admin)
- DELETE /api/products/{id} - Ürün sil (Admin)

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
- URL: https://mega-menu-catalog.preview.emergentagent.com

## P1 - Sonraki Görevler
- [ ] Varyant yönetimi (renk, beden bazlı stok)
- [ ] Checkout akışı tamamlama
- [ ] Sipariş takibi müşteri paneli
- [ ] Benzer ürün önerileri geliştirme
- [ ] Kombin ürün seçeneği

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
│   ├── import_excel.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── Header.jsx        # Mega menu
│       │   ├── ProductCard.jsx
│       │   └── ...
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── ProductDetail.jsx # 2-column grid images
│       │   └── admin/
│       │       ├── Products.jsx  # Edit, copy, toggle icons
│       │       ├── Orders.jsx
│       │       ├── PageDesign.jsx
│       │       └── ...
│       └── context/
└── memory/PRD.md
```

## Last Updated
2026-03-22 - v5.0 Bug Fixes + Admin Product Actions
