# Facette E-Commerce PRD

## Problem Statement
Facette e-ticaret uygulaması - React + FastAPI + MongoDB tabanlı admin paneli ve mağaza yönetimi. Trendyol entegrasyonu, ürün yönetimi, stok takibi, sipariş yönetimi ve toplu işlem özellikleri.

## Core Requirements
1. Ürün yönetimi (CRUD, varyantlar, özellikler, fiyatlandırma)
2. Trendyol entegrasyonu (kategori/özellik eşleştirme, ürün aktarma)
3. Cariler (Tedarikçi/Üretici) yönetimi
4. Global ayarlar (KDV, kâr oranı)
5. Excel toplu import/export
6. İade/İptal yönetimi (iskonto, gider pusulası, toplu yazdırma)
7. Doğan e-Dönüşüm e-Fatura entegrasyonu

## Architecture
- Frontend: React, Tailwind CSS, Shadcn/UI, Lucide icons
- Backend: FastAPI, Motor (Async MongoDB)
- DB: MongoDB (test_database)
- Routes: /api prefix, Turkish URL slugs (/admin/urunler, /admin/iadeler)
- Integrations: Trendyol API, Doğan e-Dönüşüm SOAP (zeep)

## Completed Features
- [2026-04-20] **Görevler & Haftalık Checklist Modülü (Iteration 12)**:
  - `/api/admin/tasks` CRUD + `/complete` (tekrar kur) + `/snooze` + `/seed-defaults` (16 hazır görev) + `/summary` + `/history`
  - Tekrar tipleri: once, daily, weekly, biweekly, monthly, quarterly, yearly, custom
  - Tamamlandığında `last_completed_at` + `completion_count++` + `due_at = next_period`; log `admin_task_logs` koleksiyonuna yazılır
  - 16 varsayılan görev (kullanıcının liste verdiği): müşteri sorularını kontrol, havale onayla, yorum moderasyonu, terkedilmiş sepet mail at, haftalık bülten, kampanya kurgula, satış raporu, stok ikmali, banner güncelle vb.
  - `/admin/gorevler` sayfası: 4 özet kartı (bugün/gecikmiş/bu hafta/son 30 gün), kategori rozetleri (müşteri/sipariş/stok/pazarlama/rapor/içerik/SEO/ayar/entegrasyon), öncelik noktaları (acil/yüksek/normal/düşük), "Git" (ilgili admin sayfasına) + "Tamamla" + "+1g ertele" butonları, tamamlanma ısı haritası (son 30 gün)
  - **Dashboard widget**: "Bugün Yapılacaklar" paneli (6 görev + tek tıkla tamamla + gecikmiş/bekleyen/bu hafta özeti) Sipariş Durumu Dağılımı yanında
  - Menüde "Görevler" ana link Dashboard'dan sonra

- [2026-04-20] **Ticimax P1 — 20 yeni modül (Iteration 11)**:
  - **Katalog**: Marka Yönetimi (brands), Etiket Yönetimi (product_tags, bg_color+text_color), Stok & Fiyat Alarm Hatırlatma (public /alerts POST, admin liste/delete)
  - **Siparişler**: Admin Manuel Sipariş Oluştur (MNL-YYMMDD-XXXXXX, stok düşer), Silinmiş Siparişler arşivi + restore, Havale/EFT Bildirimleri (müşteri /payments/havale-notify; admin onay → siparişe payment_status=paid işler)
  - **Üyeler**: Üye Grupları (B2B/VIP), Destek Talepleri (Tickets — ticket_number, reply thread)
  - **İçerik**: Duyuru Yönetimi, Süreli Popup Yönetimi (delay_seconds, trigger)
  - **Pazarlama**: Kargo Kuralları (min_cart, free_shipping), Ödeme Tipi İndirimleri, Toplu Mail Gönderme (Resend API — segment=all/newsletter/abandoned, batch 100, email_campaigns log)
  - **Raporlar Gelişmiş**: Saatlik Satış (BarChart), İl Bazında Satış, Ürün Karlılık (margin), Stok Hareket
  - **Ayarlar**: Döviz Kurları (exchangerate.host)
  - **Resend entegrasyonu**: RESEND_API_KEY env'de boş (kullanıcı verince aktif)
  - Backend 16 yeni router (catalog_extras.py tek dosya), Frontend 12 yeni admin sayfası
  - Test 23/23 backend + 12/12 frontend (profit KeyError fix + Promise.allSettled)
- [2026-04-20] **Iteration 10 Ticimax P0** (6 modül): Kuponlar, Ürün Yorumları, Terkedilmiş Sepet, 4 Rapor (satış/ürün/stok/üye), SEO Meta + 301 Yönlendirmeler
- [2026-04-20] **Iteration 9 Büyük restructure**: Menü 9 gruba bölündü, Üyeler modülü, Attribution/Funnel takibi, HB/Temu Eşleştir sayfaları, HB Basic Auth düzeltildi

- [2026-04-20] **Büyük admin restructure (Iteration 9)**:
  - **Menü 9 ana gruba bölündü**: Dashboard | Katalog | Siparişler | Üretim | Üyeler | İçerik | Pazarlama | Entegrasyonlar | Ayarlar (İmalat Üretim altına, Banner/Sayfalar İçerik altına taşındı)
  - **Üyeler modülü (YENİ)**: `/api/admin/members` CRUD + stats (VIP/Sadık/Yeni/Aday segmentleri, edinim kanalları), `/admin/uyeler` sayfası (drawer detay, segment filtresi, UTM kaynakları görünümü)
  - **Attribution / Funnel takibi (YENİ)**: `/api/attribution/track-visit` (public, UTM + referrer + gclid/fbclid), `/api/attribution/stats` (admin). Otomatik kanal algılama: instagram_ads, google_ads, instagram_organic, google_organic, email, influencer, direct, referral, trendyol, hepsiburada, vs. `/admin/kaynak` sayfası: Kanal Bazında Gelir/Ziyaret grafikleri, en iyi kampanyalar tablosu, dönüşüm oranı
  - **Sipariş Kaynağı**: Order detay modalında attribution kartı (kanal, UTM source/medium/campaign, referrer, landing page, device)
  - **Storefront UTM tracker**: `lib/attribution.js` App.js'te otomatik çağrılır, facette_sid localStorage'a yazılır, Checkout'ta siparişe iliştirilir
  - **Hepsiburada Eşleştir (YENİ sayfa)**: Basic Auth (Merchant ID + Username + Password) ayar formu + kategori ID/ad eşleştirme tablosu. Integrations.jsx HB modalı da Basic Auth'a düzeltildi
  - **Temu Eşleştir (YENİ sayfa)**: Shop ID + App Key + App Secret + kategori eşleştirme
  - **Test-connection artık GERÇEK**: Hepsiburada'ya httpx ile Basic Auth listing endpoint ping'i atılır, 200/401/403/timeout mesajları açıkça döner
  - **Ölçü Tabloları listesi**: `/admin/olcu-tablolari` ürün bazlı gezinti
  - **Dashboard**: "Toplam Müşteri" → "Toplam Üye"
  - Backend testing iteration 9: 19/19 backend + frontend 5 yeni sayfa doğrulandı
- [2026-03-25] MongoDB data restore (290 products, 34 categories)
- [2026-03-25] Stock code visibility, Global Markup & VAT, Vendors module
- [2026-03-25] Trendyol category/attribute sync, auto-match, 4-digit IDs
- [2026-03-25] Variant dropdown UX improvements
- [2026-03-26] Excel Technical Details Import (126 products matched)
- [2026-03-26] Attributes tab reorganization (filled > required > hidden)
- [2026-03-26] Fixed Trendyol attribute matching (strict name match)
- [2026-03-26] Auto-fill Yaş Grubu=Yetişkin, Menşei=TR for all products
- [2026-03-26] Cleaned 71 non-textile attributes, hidden Beden/Renk/Web Color
- [2026-03-26] Multi-color variant system (each color = separate product + auto Web Color)
- [2026-03-26] İade iskonto düzeltmesi (sipariş API'den net tutar çekme)
- [2026-03-26] Gider Pusulası (VUK 234 uyumlu, şirket bilgileri ile)
- [2026-03-26] İade sayfası yeniden yapılandırma (checkbox, pasifizasyon, toplu yazdırma, 5dk auto-refresh)
- [2026-03-26] Ayarlara Şirket Bilgileri bölümü eklendi
- [2026-03-26] Doğan e-Dönüşüm entegrasyonu (bağlantı test, CheckUser) temel yapı
- [2026-04-19] Hepsiburada & Temu marketplace scaffolding:
  - Backend: `/api/integrations/{hepsiburada|temu}/settings|status|test-connection`, unified `/api/integrations/marketplace/questions` + stub sync/answer endpoints
  - Frontend Entegrasyonlar: Hepsiburada + Temu kartları, settings dialogları
  - Frontend Products Özellikler: Trendyol altında Hepsiburada & Temu için bağımsız özellik bölümleri (Trendyol'da seçilen değer boş ise HB/Temu'ya otomatik kopyalama)
  - Frontend Questions: marketplace filtresi, sol kenarlıkta renkli çerçeve, sağ üst köşede pazaryeri rozeti, pazaryeri bazlı senkron butonları
  - Products modeli `hepsiburada_attributes` + `temu_attributes` alanlarını destekler
- [2026-04-20] Kapsamlı Admin Panel Genişletme (Fork devamı):
  - **RBAC (Rol & Yetki)**: `/api/admin/roles` + `UsersRoles.jsx`, 64 permission ağacı
  - **APScheduler**: `scheduler.py` 30dk'da bir çalışır, 48 saati geçmiş ödenmemiş Havale siparişlerini iptal eder ve stokları iade eder
  - **İmalat Takip**: 12 aşamalı pipeline (`manufacturing.py`), `Manufacturing.jsx`, tedarikçi yönetimi, F7-F11 (maliyet/fire/satınalma emri), size_distribution opsiyonel (bedenler artık default gelmiyor)
  - **Ölçü Tablosu**: `size_tables.py` + Pillow ile 1200x1800 PNG render, `SizeTablePanel.jsx`, storefront HTML tablo
  - **AI Chatbot**: `ai_chatbot.py` — Emergent LLM (GPT-5.2) ile 7 kanal (WhatsApp, Instagram, Messenger, Web, Trendyol, Hepsiburada, Temu) cevap taslağı ve RAG knowledge base
  - **Kampanya Şablonları**: 10 hazır şablon kart (Campaigns.jsx)
  - **Konum API**: `/api/locations/countries` (pycountry 249 ülke, TR ilk), `/api/locations/tr/provinces` (81 il), `/api/locations/tr/districts?province=`, `/api/locations/tr/search?q=`
  - **7 Kargo Entegrasyon Kartı**: MNG, Aras, Yurtiçi, PTT, HepsiJet, Trendyol Express, Sürat — `/api/integrations/{provider}/settings` (generic, scaffolding; gerçek API keys bekleniyor)
  - **Iyzico Ayar UI**: `/api/integrations/iyzico/settings` (kısmi iade mantığı P1 backlog)
  - **HB/Temu Kategori ID**: Products modeli ve formuna `hepsiburada_category_id`, `temu_category_id` alanları
  - **Sipariş Renklendirme**: Havale bekleyen kırmızı/onaylanan normal, fatura kesilmiş pasif
  - **İade Geliştirmeleri**: Ret Sebebi modalı, Kargo & Ödeme Tipi sütunları
  - Backend testing iteration 8: 24/24 backend test geçti (locations, cargo settings, manufacturing CRUD+advance, products HB/Temu, AI settings, RBAC, size tables)

## Credentials
- Admin: admin@facette.com / admin123
- Doğan e-Dönüşüm: dogantest / dgn2024@!

## Backlog
- P0: Hepsiburada gerçek API entegrasyonu (Listing Products, Orders, QNA) — credentials alındığında
- P0: Temu gerçek API entegrasyonu (Products, Orders, QNA) — credentials alındığında
- P0: Trendyol ürün aktarım detaylı sonuç ekranı (stok kodu, barkod, başarı/hata + hata nedeni)
- P0: Doğan e-Dönüşüm üzerinden e-Fatura kesme (tam entegrasyon)
- P0: Fatura numarası çıkarma (PDF parsing veya API)
- P1: **Iyzico Kısmi İade + Kargo Ücreti Düşme + Kampanya Oransal Hesap** (UI+backend mantığı)
- P1: **Checkout/Sipariş adres formlarında İl/İlçe dropdown bağlama** (`/api/locations/tr/*` endpoint'leri frontend'e bağla)
- P1: 7 Kargo firması gerçek API entegrasyonu (kullanıcı API keys verince)
- P1: Mevcut tüm claim'lerin iskontolarını düzeltme
- P1: Tüm search/dropdown UX tutarlılığı
- P2: Trendyol Mikro İhracat ayrı faturalandırma altyapısı
- P2: Trendyol ürün export testi
- P2: Products.jsx (2500+ satır) ve Orders.jsx (1500+ satır) modal/sekme componentlerine bölme
- P2: integrations.py (3500+ satır) provider'a göre bölme

## Changelog — 23 Nis 2026
- **UI**: Admin Pagination tekdüze hale getirildi. `/app/frontend/src/components/admin/Pagination.jsx` (compact + full variants, jump-to-page input, ilk/son/prev/next, "..." ellipsis). Sayfa başına kayıt seçici (20/50/100/200) hem üst hem alt varyantında.
- **UI**: Ürünler ve Siparişler tablolarına `.admin-table-compact` CSS varyantı → bir ekrana daha çok kayıt sığıyor. Thumbnail w-12→w-10.
- **UI**: ÜST (compact) + ALT (full) pagination — her ikisi aynı state'i paylaşır.
- **Products Bulk Select**: Ürünler tablosuna sol checkbox sütunu + "Tümünü seç" + seçilen ürünler için üst turuncu bulk bar eklendi.
- **Barcode Cards**: Yeni backend router `barcode_cards.py`. Giyim firması ürün kartı (ürün adı, stok kodu, GTIN Code128/EAN-13 barkod, beden, renk, fiyat) — tek ürün `GET /api/products/{id}/barcode-card` + toplu `POST /api/products/barcode-cards/bulk`. A4 2 sütunlu yazdırılabilir HTML.
- **Orders Bulk Invoices**: `Orders.jsx` bulk bar'a **Toplu Fatura Kes** + **Toplu Fatura Yazdır** butonları eklendi. Toplu yazdırma tüm seçili faturaları tek sayfada iframe grid ile basar (A4 başına bir fatura).
- **Provider Settings (yeni)**: Ticimax'teki E-Arşiv/E-Fatura ayarları benzeri jenerik altyapı.
  - Backend: `routes/provider_settings.py` — 11 e-fatura entegratörü (Doğan, Nilvera, Uyumsoft, Logo, Mikro, Foriba/EDM, QNB Finansbank, Turkcell, İzibiz, İdea, Kolaysoft) + 13 kargo firması (MNG, Yurtiçi, Aras, PTT, Sürat, HepsiJet, Trendyol Express, Sendeo, Kolay Gelsin, DHL, UPS, FedEx, TNT). Her biri için alan şeması (field type/required/placeholder) tanımlı.
  - Endpoints: `/api/provider-settings/{einvoice|cargo}/{schemas|config|test}`.
  - MongoDB: tek `providers_config` koleksiyonu, `kind` bazlı tek döküman (active_provider + providers map).
  - Frontend: jenerik `components/admin/ProviderSettings.jsx` (sol liste + sağ dinamik form + arama + şifre toggle + test butonu) → `EInvoiceSettings.jsx` ve `CargoSettings.jsx` sayfaları bu componenti kullanır.
  - Routes: `/admin/ayarlar/e-fatura` ve `/admin/ayarlar/kargo`.
  - Sidebar "Ayarlar" altında yeni menü kalemleri.
- **Refactor (P2 1. adım)**: Products.jsx 2543→2376 satır. Çıkarılan yeni dosyalar:
  - `components/admin/product-form/SearchableAttribute.jsx` (166 satır)
  - `components/admin/product-form/SeoTab.jsx` (65 satır)
  - `components/admin/product-form/StockTab.jsx` (101 satır)
- **Test**: Backend curl testleri başarılı — 11 e-fatura + 13 kargo provider schemas/config/test endpoint'leri çalışıyor. UI smoke testi: sol liste + sağ dinamik form + bulk checkbox'lar + pagination size selector hepsi render ediliyor. Ürün attributes PUT→GET roundtrip doğru (Yaka: V Yaka, Kumaş: Pamuk test edildi).


