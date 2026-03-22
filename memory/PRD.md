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

## Current Status: v10.0 - Backend Modüler Mimari ✅

### Tamamlanan Özellikler (2026-03-22)

#### v10.0 - Backend Modüler Mimari Refactoring
- [x] **Monolitik server.py Parçalandı**
  - 3400+ satırlık server.py → modüler routes/ dizini
  - Her endpoint grubu ayrı dosyada
- [x] **Yeni Dosya Yapısı**
  - routes/auth.py - Login, Register, Google OAuth, /me
  - routes/products.py - Ürün CRUD ve listeleme
  - routes/orders.py - Sipariş CRUD
  - routes/categories.py - Kategori CRUD
  - routes/banners.py - Banner CRUD
  - routes/cms.py - CMS sayfa blokları
  - routes/admin.py - Dashboard istatistikleri
  - routes/customer.py - Müşteri hesap yönetimi
  - routes/integrations.py - 3. parti entegrasyon durumları
  - routes/deps.py - Ortak bağımlılıklar (db, auth helpers)
- [x] **Güvenlik Düzeltmesi**
  - /auth/me endpoint'i artık password hash döndürmüyor
- [x] **Tüm API'ler Çalışıyor**
  - 26/26 backend test geçti
  - Frontend tamamen fonksiyonel

#### v9.8 - Admin Dashboard ve Raporlama
- [x] **Ana İstatistikler**
  - Toplam Sipariş, Gelir, Ürün, Müşteri kartları
  - Geçen aya göre büyüme oranları (%)
  - Renkli ikonlar ve modern tasarım
- [x] **İkincil İstatistikler**
  - Bekleyen Siparişler (sarı)
  - Kargodaki Siparişler (mor)
  - Bugünkü Gelir (yeşil)
- [x] **Sipariş Durumu Dağılımı**
  - Progress bar'lı görsel dağılım
  - Beklemede, Onaylandı, Kargoda, Teslim, İptal
- [x] **En Çok Satan Ürünler**
  - Top 5 ürün listesi
  - Satış adedi ve gelir
  - Sıralama badge'leri (altın, gümüş, bronz)
- [x] **Son Siparişler**
  - Son 5 sipariş tablosu
  - "Tümünü Gör" linki
- [x] **Tarih Filtresi**
  - Son 7, 30, 90 gün ve 1 yıl seçenekleri
- [x] **Backend API**
  - GET /api/admin/dashboard-stats

#### v9.7 - Müşteri Hesap Yönetimi ve Checkout İyileştirmeleri
- [x] **Checkout Varyant Bilgisi**
  - Sipariş özetinde beden ve renk gösterimi
- [x] **Hesabım Sayfası**
  - Profil Bilgileri - Ad, Soyad, E-posta, Telefon, Üyelik Tarihi
  - Profil düzenleme formu
  - Şifre değiştir bölümü
- [x] **Siparişlerim**
  - Sipariş listesi (tarih, durum badge'i)
  - Sipariş detayları (ürünler, beden, adet, fiyat)
  - Teslimat adresi ve kargo bilgisi
  - Sipariş durumu: Beklemede, Onaylandı, Kargoda, Teslim Edildi, İptal
- [x] **Adreslerim**
  - Adres listesi
  - Yeni adres ekleme formu
  - Adres düzenleme/silme
  - Varsayılan adres seçimi
- [x] **Favorilerim** (placeholder)
- [x] **Backend API'leri**
  - GET /api/my-orders - Kullanıcının siparişleri
  - PUT /api/users/me - Profil güncelleme
  - CRUD /api/addresses - Adres yönetimi

#### v9.6 - GIB E-Fatura / E-Arşiv Entegrasyonu
- [x] **UBL-TR 1.2.1 XML Fatura Oluşturma**
  - Türkiye e-fatura standardına uygun XML üretimi
  - Satıcı ve alıcı bilgileri
  - Fatura kalemleri ve KDV hesaplaması
- [x] **Fatura API Endpoint'leri**
  - POST /api/orders/{id}/create-invoice - Fatura taslağı oluşturma
  - GET /api/orders/{id}/invoice - Fatura bilgileri
  - GET /api/orders/{id}/invoice/print - Yazdırılabilir HTML fatura
- [x] **QR Kod ve Yazdırılabilir Fatura**
  - Fatura doğrulama QR kodu
  - Profesyonel HTML fatura tasarımı
- [x] **Admin Panel Entegrasyonu**
  - Siparişler sayfasında "Fatura Kes" butonu
  - Entegrasyonlar sayfasında GIB kartı

**Not:** Tam GIB portal entegrasyonu için Mali Mühür gereklidir.

#### v9.5 - Ana Sayfada CMS Bloklarını Render Etme
- [x] **Dinamik Blok Render Sistemi**
  - Admin panelde oluşturulan bloklar ana sayfada otomatik görünüyor
  - sort_order'a göre sıralı gösterim
  - Sadece is_active=true bloklar görünüyor
- [x] **Desteklenen Blok Tipleri**
  - Hero Slider - Dönen banner görselleri
  - Full Banner - Tam genişlik tek görsel
  - Half Banners - İki görsel yan yana
  - Product Slider - Ürün grid'i
  - InstaShop - Instagram tarzı görseller
  - Text Block - Başlık ve açıklama
  - Video Banner - Video arka planlı banner
  - Rotating Text - Dönen metin banner'ı
- [x] **Fallback Mekanizması**
  - CMS bloğu yoksa varsayılan içerik gösteriliyor
  - Her blok tipi için default değerler

#### v9.4 - Iyzico & Trendyol Entegrasyonları (Production-Ready)
- [x] **Iyzico Ödeme Entegrasyonu**
  - Sandbox/Live mod desteği (IYZICO_MODE env)
  - CheckoutForm Initialize ve Callback API'leri
  - 3DS güvenli ödeme desteği
  - Ödeme durumu kontrolü (/api/payment/status)
- [x] **Trendyol Marketplace Entegrasyonu**
  - Ürün senkronizasyonu (/api/trendyol/products/sync)
  - Batch request status kontrolü
  - Stok ve fiyat güncelleme (/api/trendyol/inventory/update)
  - Sipariş çekme (/api/trendyol/orders)
  - Sipariş durumu güncelleme
  - Sipariş içe aktarma (/api/trendyol/orders/import)
  - Kategori ve marka listesi API'leri
- [x] **Admin Entegrasyonlar Sayfası**
  - Tüm entegrasyonların durum gösterimi
  - Gerekli env değişkenleri listesi
  - "Ürünleri Gönder" ve "Siparişleri Al" butonları
  - Yapılandırma talimatları

#### v9.3 - CMS (Sayfa Tasarımı) Sürükle-Bırak
- [x] **Sürükle & Bırak Sıralama**
  - @dnd-kit/core ve @dnd-kit/sortable entegrasyonu
  - Sol tarafta 6 noktalı GripVertical sürükleme ikonu
  - Blokları sürükleyerek yeniden sıralama
  - "Sıralamayı Kaydet" butonu
- [x] **8 Farklı Blok Tipi**
  - 🎠 Hero Slider - Ana sayfa slider
  - 📢 Dönen Yazı - Üst banner'da dönen metin
  - 🖼️ Tam Genişlik Banner - Tek görsel tam genişlik
  - ◧ Yarı Yarıya Banner - İki görsel yan yana
  - 🛍️ Ürün Slider - Yatay ürün listesi
  - 📸 InstaShop - Instagram tarzı görseller
  - 📝 Yazı Bloğu - Başlık ve açıklama
  - 🎬 Video Banner - Video arka planlı banner
- [x] **Blok Yönetimi**
  - Ekleme, düzenleme, silme
  - Aktif/Pasif toggle
  - Görsel yükleme ve bağlantı ayarlama
  - Önizleme görseli
- [x] **Kullanıcı Dostu UI**
  - Her blok için tip etiketi ve emoji ikonu
  - Görsel sayısı ve bağlantı bilgisi
  - Blok Tipleri legend'ı

#### v9.2 - Frontend Ürün Detay Sayfasında Beden Seçimi
- [x] **Beden Seçimi UI**
  - Stokta olmayan bedenler devre dışı (gri, çizgili)
  - Seçilen beden siyah arkaplan ile vurgulanıyor
  - "Stokta: X adet" yeşil yazıyla gösteriliyor
- [x] **Seçili Varyant Detayları**
  - Seçilen beden için ayrı bilgi kutusu
  - Stok kodu ve barkod gösterimi
  - Fiyat farkı varsa gösteriliyor
- [x] **Sepete Ekleme**
  - Beden seçilmeden "Sepete Ekle" butonu devre dışı
  - Stok kontrolü - yetersiz stok uyarısı
  - Toast mesajı beden bilgisi ile birlikte
  - Sepette beden bilgisi görünüyor

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
- URL: https://couture-platform-dev.preview.emergentagent.com

## P0 - Sonraki Görevler
- [x] **Server.py Refactoring** - ✅ TAMAMLANDI - Modüler routes/ yapısına bölündü

## P1 - Yaklaşan Görevler
- [ ] Trendyol kategori ve marka eşleştirmesi UI
- [ ] Favoriler sistemi (tam fonksiyonel)

## P2 - Backlog
- [ ] Netgsm SMS (canlı credentials)
- [ ] Favoriler sistemi (tam fonksiyonel)

## Teknik Borç
- [x] ~~server.py 2000+ satır~~ - ✅ Modüler routes/ yapısına bölündü
- [ ] Eski import scriptleri temizlenmeli (import_excel.py, import_excel_v2.py)

## Kod Mimarisi
```
/app/backend/
├── server.py          # Ana FastAPI app (router import'ları)
├── server.py.old      # Eski monolitik dosya (yedek)
├── models.py          # Pydantic modelleri
├── requirements.txt
└── routes/
    ├── __init__.py    # Router export'ları
    ├── deps.py        # Ortak bağımlılıklar (db, auth)
    ├── auth.py        # /auth/* endpoints
    ├── products.py    # /products/* endpoints
    ├── orders.py      # /orders/* endpoints
    ├── categories.py  # /categories/* endpoints
    ├── banners.py     # /banners/* endpoints
    ├── cms.py         # /page-blocks/* endpoints
    ├── admin.py       # /admin/* endpoints
    ├── customer.py    # Customer account endpoints
    └── integrations.py # Integration status endpoints
```

## Last Updated
2026-03-22 - v10.0 Backend Modüler Mimari Refactoring
