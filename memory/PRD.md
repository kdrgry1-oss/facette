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

## Current Status: v9.1 - Admin Varyant Görüntüleme ✅

### Tamamlanan Özellikler (2026-03-22)

#### v9.1 - Admin Panelde Mevcut Varyantları Gösterme
- [x] **Ürün Düzenleme Modalında Varyantlar Sekmesi**
  - "Mevcut Varyantlar" tablosu eklendi
  - Her varyant için: Beden, Stok Kodu, Barkod, Stok, Fiyat Farkı gösteriliyor
  - Stok değeri düşükse (< 5) kırmızı vurgu
  - Toplam stok hesabı footer'da
  - Varyant silme butonu
  - Yeni varyant ekleme formu (Beden, Stok Kodu, Barkod, Stok, Fiyat Farkı)

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
  - Admin ürün listesinde "X Beden" butonu
  - Modal ile tüm varyant detayları

#### v8.0 - Order Tracking + SMS
- [x] Sipariş Takip Sayfası
- [x] Netgsm SMS Entegrasyonu

#### v7.0 - MNG Kargo
- [x] MNG Kargo API entegrasyonu
- [x] Kargo etiketi (10cm x 15cm)

## Admin Panel - Ürünler Sayfası
| Sütun | Açıklama |
|-------|----------|
| Görsel | Ürün resmi |
| Ürün Adı | Ad + Kategori |
| Stok Kodu | Ana stok kodu |
| Barkod | Ana barkod |
| **Bedenler** | "X Beden" butonu (tıklanabilir) |
| Fiyat | Satış fiyatı |
| Stok | Toplam stok |
| Durum | Aktif/Pasif |
| İşlemler | Edit, Copy, Toggle, More |

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://fashion-shop-156.preview.emergentagent.com

## P0 - Sonraki Görevler
- [ ] **Frontend Beden Seçimi** - Ürün detay sayfasında beden seçimi (dropdown)
- [ ] **CMS (Sayfa Tasarımı)** - Sürükle-bırak ile blok sıralama
- [ ] **Iyzico Ödeme** - Mock'tan canlıya geçiş

## P1 - Yaklaşan Görevler
- [ ] Sepete varyant bazlı ekleme
- [ ] Stok kontrolü varyant bazlı

## P2 - Backlog
- [ ] Trendyol marketplace
- [ ] GIB e-fatura
- [ ] Netgsm SMS (canlı)
- [ ] Gelişmiş raporlama
- [ ] Müşteri hesap yönetimi

## Teknik Borç
- [ ] server.py 2000+ satır - modüler yapıya bölünmeli (routes klasörü)
- [ ] Eski import scriptleri temizlenmeli

## Last Updated
2026-03-22 - v9.1 Admin Varyant Görüntüleme
