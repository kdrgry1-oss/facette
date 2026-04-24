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


## Completed in Iteration 14 (2026-04-23) — FAZ 1 + FAZ 2 + FAZ 3

### FAZ 1 — TR Lokasyon (İl/İlçe)
- `ProvinceDistrictSelect.jsx` — iki dropdown, `/api/locations/tr/provinces` (81 il) + `/api/locations/tr/districts?province=` (973 ilçe)
- `Checkout.jsx` ve `Account.jsx` adres formları serbest metin inputlarından dropdown'a geçirildi
- Modül içi cache ile sayfa geçişlerinde tekrar fetch etmiyor

### FAZ 2 — Bildirim Altyapısı (SMS + WhatsApp + E-posta)
- **Backend servis**: `/app/backend/notification_service.py`
  - 8 SMS sağlayıcı slot (Netgsm, İletiMerkezi, Twilio, VatanSMS + 4 mock slot)
  - WhatsApp Meta Cloud API (text + template mesaj desteği)
  - Resend e-posta
  - `{variable}` tabanlı template render + TR telefon normalizasyonu
  - `notification_logs` koleksiyonu (her gönderim log'lanır)
- **Admin CRUD**: `/api/notifications/*` endpoint'leri
  - `GET /providers/catalog` — sağlayıcı listesi + event listesi
  - `GET/POST /providers` — credential yönetimi (**secret maskeleme** + UI'den maskeli değer dönünce eski değer korunur)
  - `GET/POST /templates` + `POST /templates/seed` (default 30 şablon)
  - `POST /test` — canlı test gönderimi
  - `GET /logs` — son gönderim geçmişi
- **Admin UI**:
  - `/admin/ayarlar/bildirim` → sağlayıcı seçimi + credential + test paneli
  - `/admin/ayarlar/bildirim/sablonlar` → 10 event × 3 kanal şablon editörü
- **Order hook**: `PUT /api/orders/{id}/status` durum değişikliğinde `asyncio.create_task` ile fire-and-forget bildirim tetikler (UI bloklamıyor)

### FAZ 3 (kısmi) — SMS OTP Şifre Sıfırlama
- `POST /api/auth/forgot-password/request-otp` — 6 haneli OTP, SHA256 hash, 5 dk ömür, **60 sn rate limit** (aynı telefon), eski kodlar yeni OTP üretilince iptal
- `POST /api/auth/forgot-password/verify-otp` — 5 yanlış deneme → 429, başarılı doğrulamada 10 dk ömürlü `reset_token`
- `POST /api/auth/forgot-password/reset` — reset_token ile şifre değiştirme
- Enumeration önlemi: bilinmeyen numara için de aynı başarılı cevap

### Testing
- `/app/backend/tests/test_iteration14_notifications_locations_otp.py` — 18/18 PASS
- `/app/test_reports/iteration_14.json` — başarı oranı %100 (backend)


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

## Iteration 15 (2026-04-23) — FAZ 4 + FAZ 5 + FAZ 6

### FAZ 4 — Checkout İyileştirmeleri
- **Hediye notu** (300 karaktere kadar) — `orders.gift_note` alanına kaydedilir
- **Hediye paketi** (+130 TL) — checkbox, toplam tutara eklenir, `orders.gift_wrap`/`gift_wrap_price` ile kayda girer
- **Trendyol Go stili kupon kutusu**: Yeni endpoint `POST /api/coupons/available` (sepet+kullanıcı için uygun kuponları hesaplanmış discount ile listeler), checkout sepet özetinde kart olarak görünür, tıklayınca otomatik uygulanır
- Uygulanmış kupon "Kaldır" butonu + kupon kodu order'a kaydolur

### FAZ 5 — Sipariş Durum Zinciri Standardizasyonu
- Yeni durum: **`undelivered`** (Teslim Edilemedi — Şubede Bekliyor)
- Durum seçenekleri: `pending → confirmed → processing (Paketleniyor) → shipped (Kargoda) → delivered | undelivered | cancelled`
- Yeni endpoint'ler:
  - `POST /api/orders/{id}/ship?cargo_company=&tracking_number=` — 9 geçerli kargo firması whitelist; bildirim fire-and-forget
  - `POST /api/orders/{id}/undeliver?reason=&branch_info=` — teslim edilemedi bildirimi
- Status hook `order_undelivered` event'ini notification_service'e taşır

### FAZ 6 — Müşteri Risk & Blok Yönetimi
- **Sipariş oluştururken IP + User-Agent kaydı** (`customer_ip`, `user_agent` — X-Forwarded-For destekli)
- **Risk skoru endpoint'leri**: `GET /api/customer-risk/users/{uid}`, `/by-email`, `/bulk?user_ids=&emails=`
  - Formül: `return_rate = returns / (total_orders - cancelled)`, risk_level: low (<20%) / medium (20-49%) / high (≥50%)
- **Blok CRUD**: `POST /block`, `GET /blocked`, `DELETE /blocked/{id}` (user_id VEYA ip VEYA email)
- **Otomatik blok enforcement**: POST /api/orders üzerinde blocked_customers lookup → 403 "sipariş veremez"
- **Admin UI — `/admin/bloklu-musteriler`** (yeni sayfa): form + liste + kaldır
- **Sipariş listesinde risk rozeti**: yüksek iadeli müşterilerin adı kırmızı + "⚠ %X" rozeti (medium için sarı)

### Testing (Iteration 15)
- `/app/backend/tests/test_iteration15_faz456.py` — 14/14 PASS
- Minor fix: `_compute_risk` fast-path now includes `return_rate_pct: 0.0` for UI consistency


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

## Iteration 16 (2026-04-23) — FAZ 7 İmalat Planı 18 Sütunlu Tablo

### Ürün kartı
- Yeni alanlar: `collection` (ör. "2026 İlkbahar/Yaz"), `color` (ana renk), `purchase_price` (mevcut — imalat ile entegre)
- Admin "Ürün Ekle/Düzenle" formunda yeni 2 input (datalist ile koleksiyon önerisi)

### İmalat Planı (`/api/production-plan`)
- 18 sütunluk spreadsheet-style CRUD endpoint'leri:
  - `GET /api/production-plan?search=&manufacturer_id=&collection=`
  - `POST /api/production-plan` — seq_no = `max(seq_no)+1` (silme sonrası uniqueness), ürün seçilirse collection/price/color/product_description otomatik dolum
  - `PUT /api/production-plan/{id}` — payment_date → planned_delivery (+21 gün) otomatik hesap; delay_days + qty_diff_pct türetilir
  - `DELETE /api/production-plan/{id}`
  - `GET /api/production-plan/collections` — distinct koleksiyonlar (product + plan)
- Türetilmiş alanlar:
  - `planned_delivery` = payment_date + 21 gün
  - `delay_days` = actual_delivery − planned_delivery (pozitif=gecikme kırmızı, negatif/0=zamanında yeşil)
  - `qty_diff_pct` = ((delivered − order) / order) × 100 (pozitif yeşil, negatif kırmızı; delivered=0 ise null)

### Admin UI — `/admin/uretim-plani` (yeni sayfa)
- 18 sütunluk tablo, satır bazlı 800 ms debounced auto-save
- Üretici dropdown (vendors/manufacturer), koleksiyon datalist, ürün select (autofill)
- Inline QC + Final QC: Geçti (yeşil) / Kaldı (kırmızı) butonlu + **resim upload** (base64 önizleme)
- Gecikme ve +/-% göstergesi hücre altında
- Menü: Üretim → İmalat Planı (Tablo)

### Testing
- `test_iteration16_production_plan.py` — 16/16 PASS (%100)
- Minor: seq_no race condition fix eklendi (max-based), PUT Pydantic validation optional iyileştirme


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

## Iteration 17 (2026-04-23) — FAZ 8 + FAZ 9 + Üretici Performans

### FAZ 8 — Gelişmiş Raporlar
Backend (`/api/admin/reports/*`):
- `GET /returns/by-size` — beden bazlı iade sayısı (en çok iade edilen beden)
- `GET /returns/by-product` — ürün bazlı iade + satışa oranla `return_rate_pct` (sarı >%20, kırmızı >%50)
- `GET /returns/reasons` — iade sebebi dağılımı
- `GET /fast-selling?window_days=14&min_sold=10` — "ilk 14 günde ≥10 satış" dedektörü; `recommend_ads: true` → kartta yeşil "Reklam Öneriliyor" rozeti
- `GET /manufacturer-performance` — üretici bazında avg_delay, avg_qty_diff, skor (100 - gecikme*3 - |%|*0.5)

Admin UI: `/admin/raporlar/iade-ve-trend` — 5 kart (beden, sebep, ürün, hızlı satış kartları, üretici performans tablosu renk kodlu)

### FAZ 9 — Pazarlama Pixel Yönetimi
Backend (`/api/marketing-pixels`):
- `GET /providers` — 8 sağlayıcı (GA4, Meta Pixel, Google Ads, TikTok, Yandex, Hotjar, Clarity, Custom)
- `GET/POST/DELETE` — CRUD (tag_id → otomatik snippet template; custom için manuel HTML)
- `GET /active-public` — **AUTH YOK** — frontend site'a inject için head + body snippet birleşimi (60s cache)

Frontend:
- `MarketingPixelsInjector.jsx` (App.js'e yüklendi) — ilk render'da /active-public'ten pixel'leri çekip `<head>`'e enjekte (script tag'leri yeniden oluşturarak execute olur)
- Admin sayfası `/admin/ayarlar/pixel` — form + liste, sadece GA4 tag ID yapıştır→aktif

### Testing
- `test_iteration17_reports_pixels.py` — **22/22 PASS** (%100)
- Cache-Control eklendi (middleware override'dan etkilenebilir; iyi-bir-çaba)

## Iteration 18 (2026-04-23) — Pixel E-commerce Events + Apple/FB Sosyal Login Scaffold

### Pixel E-commerce Events (FAZ 9 potansiyel iyileştirme)
- `/app/frontend/src/utils/pixelEvents.js` helper — Meta Pixel + GA4 için 6 olay: ViewContent, AddToCart, InitiateCheckout, Purchase, Search, CompleteRegistration
- `ProductDetail.jsx` → ViewContent (ürün sayfasında) + AddToCart
- `Checkout.jsx` → InitiateCheckout (mount) + Purchase (direkt ödeme VE iyzico callback)
- Pixel pasifse sessizce no-op olur — hataya neden olmaz

### Apple + Facebook Sosyal Login (FAZ 3 upcoming)
Backend (`/api/auth/social/*`):
- `GET /providers` (public) — UI'nın hangi butonu göstereceğini belirler
- `GET/POST /settings` (admin) — credential yönetimi, **tam maskeleme** (only `"****"` + `has_*` bayrağı döner, ilk/son karakter sızıntısı yok)
- `POST /apple` — Apple public key fetch + RS256 verify (aud/iss check) → user upsert → JWT
- `POST /facebook` — OAuth code → access_token → profile → user upsert → JWT
- `_upsert_social_user`: 3 aşama (provider_id match → email match → yeni oluştur) + `auth_providers.{provider}` kaydı

Frontend:
- `Login.jsx` — `/providers` endpoint'ine bağlı Apple + Facebook butonları (credential girilince görünür)
- `/admin/ayarlar/sosyal-giris` — SocialAuthSettings sayfası (Apple Services ID/Team/Key/Private Key + FB App ID/Secret/Redirect URI)

### Testing
- `test_iteration18_social_auth.py` — **9/9 PASS** (%100)
- Minor fix: secret masking güvenliği artırıldı (tam maskeleme)




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

## Changelog — 23 Nis 2026 (Oturum 5)
- **RFM Müşteri Segmentasyonu** (`/admin/musteri-segmentleri`): `analytics_extra.py`. Recency/Frequency/Monetary quintile puanları (1-5) + klasik pazarlama segmentleri (VIP, Sadık, Yeni, Risk Altında, Kaybedilen, Hibernasyon). Renkli segment kartları filter olarak tıklanabilir, CSV export. Test: 18 müşteri (10 Hibernasyon, 6 Kaybedilen, 2 Yeni).
- **Pazaryeri Karlılık Raporu** (`/admin/pazaryeri-karlilik`): Brüt ciro - komisyon - kargo - iade = net kâr. Komisyon oranı `marketplace_accounts.transfer_rules.commission_{type,value}`'dan otomatik okunur. Kanal bazlı ağırlıklı kıyaslama, net marj renkli badge (yeşil ≥%20, sarı ≥%10, kırmızı <%10). Test: web 5 sipariş/6742₺ net.
- **Google Merchant XML Feed** (`/api/feeds/google-merchant.xml` — **public**, Google Merchant Center tarafından otomatik çekilir): 248 ürün aktarıldı, g:gtin/g:mpn/g:brand/g:availability/g:price alanlarıyla.
- **Menü güncellemeleri**: Üyeler altına "Müşteri Segmentleri (RFM)", Raporlar altına "Pazaryeri Karlılık".

## Changelog — 23 Nis 2026 (Oturum 4)
**Piyasa araştırması (ideaSoft/T-Soft/Akinon) sonucu eksik modüller:**
- **Toplu Fiyat/Stok Excel** (`/admin/toplu-fiyat-stok`): 3 adım (şablon indir → preview dry-run → apply). `bulk_ops.py` + openpyxl. Ürün stock_code VEYA barcode ile eşleştirme, varyant seviyesi stok güncellemesi.
- **Stok Uyarıları + Reorder Önerileri** (`/admin/stok-uyarilari`): Kritik Stok sekmesi (threshold ayarlanabilir) + Yeniden Sipariş Önerileri (son 60 gündeki sipariş kalemlerinden stok=0 ama satılanlar, agg pipeline).
- **Multi-Marketplace Kategori Eşleştirme** (`/admin/kategori-eslestir`): BrandMapping ile aynı üst yapı. `category_mapping.py` + `category_mappings` koleksiyonu. 13 pazaryeri sekmesi.
- **Scheduled Auto-Sync** (scheduler.py): `_marketplace_sync_tick()` her dk çalışır; her enabled marketplace_account için `products_interval_min` ve `orders_interval_min`'e göre queued log atar (`_last_products_sync` / `_last_orders_sync` zaman damgalarıyla). İlerde gerçek integrations.py servisleri bu cron'a bağlanacak.
- **AddressFields** component (`components/admin/AddressFields.jsx`): İl/İlçe dropdown (backend `/api/locations/tr/{provinces,districts}`) — Siparişler/Checkout adres formlarında kullanılmak üzere yeniden kullanılabilir bileşen.

**Test edildi**:
- stock-alerts threshold=3 → 230 kritik varyant ✅
- reorder-suggestions → 0 (son 60 günde hiç sipariş yok) ✅
- Template download (.xlsx) → 4971 bytes ✅
- category-mapping/trendyol → 33 kategori / 0 eşleşme ✅
- locations/tr/provinces → 81 il ✅
- UI: Stok Uyarıları tablosu (Haki Trençkot, Gri Blazer, vb. 230 varyant) + Toplu Fiyat/Stok 3 adım kart + Kategori Eşleştirme 13 sekme ✅

## Changelog — 23 Nis 2026 (Oturum 3)
- **Integration Logging Middleware**: `server.py`'ye otomatik logging middleware eklendi. `/api/integrations/{marketplace}/...` altındaki tüm POST/PUT/DELETE çağrıları `integration_logs` koleksiyonuna otomatik kaydediliyor (marketplace + action + status + HTTP kod + süre). Manuel wrapping gereksiz.
- **Aktarılamayanlar sayfası** (`/admin/aktarilamayanlar`): integration_logs'tan `status=failed` kayıtları; tek satır veya seçili satırlarda "Tekrar Aktar" butonu uygun endpoint'e (product_push → /integrations/{mp}/products/{id}/sync, stock_update → /sync-inventory, order_pull → /orders/import) yönlendirir.
- **Marka Eşleştirme** (`/admin/marka-eslestir`): Multi-marketplace tek ekran. 13 pazaryeri sekmesi, özet kartlar (toplam/eşleşti/eşleşmedi), arama + filtre (tümü/eşleşti/eşleşmedi), satır başına manuel "Düzenle/Sil", toplu "Otomatik Eşleştir" (isim bazlı upsert) + "Hepsini Sıfırla". Backend `brand_mapping.py` + `brand_mappings` koleksiyonu. Brand koleksiyonu boşsa `products.distinct("brand")` fallback ile sistem markalarını türetir.

## Changelog — 23 Nis 2026 (Oturum 2)
- **Marketplace Hub (yeni)**: `routes/marketplace_hub.py` — 13 pazaryeri (Trendyol, Hepsiburada, Temu, N11, Amazon TR/DE, AliExpress, Etsy, Hepsi Global, Fruugo, eMAG, Trendyol İhracat, Çiçek Sepeti) için tek merkezli yönetim. Her biri için:
  - Credential şeması (Supplier ID, API Key/Secret, Username/Password, vb.)
  - 19 Ortak Transfer Kuralı (Lisans Kodu, Eksi Stok, Fiyat Türü, Komisyon, Barkod/Stok Kodu aktarım, Yeni Ürün Otomatik, Sipariş Durum güncelleme, İade, Ödeme Vade/Teslim tarihi, Marka, Kargo Süresi)
  - Auto-sync (products/orders ayrı on-off + dk periyot + lookback saat)
  - `marketplace_accounts` koleksiyonu ile tek kayıt.
  - Frontend: `MarketplaceHub.jsx` Ticimax Marketplace v2 ile birebir görünüm (sol pazaryeri listesi + sağ 3 kart: API + Kurallar + Auto-Sync).
- **Integration Logs (yeni)**: `integration_logs` koleksiyonu + endpoint'ler (`/api/marketplace-hub/logs`, `logs/summary`, `logs/test`). Her API çağrısı status/direction/ref_id/message/duration ile kaydedilir.
  - `log_integration_event()` helper — integrations.py'den çağrılabilir.
  - Frontend: `IntegrationLogs.jsx` — filtreleme (pazaryeri, aktarım türü, durum, tarih, ref_id), "Son 5 İşlem" özet kartları, CSV export, pagination.
- **E-Fatura aktif provider routing**: `POST /api/orders/{id}/create-invoice` endpoint'i eklendi. `providers_config.einvoice.active_provider`'ı okur, provider prefix + sıra no ile `FAC00000001` formatında invoice_number üretir, siparişe yazar, integration_logs'a kayıt düşer. `GET /api/orders/{id}/invoice/print` yazdırılabilir HTML fatura. Bulk invoice akışları artık uçtan uca çalışıyor.
- **Menü**: Entegrasyonlar altına **Pazaryerleri Hub** ve **Entegrasyon Logları** eklendi.
- **Test**: Backend 13 pazaryeri şeması OK, account save/load OK, log summary OK, create-invoice FAC00000001 + provider=dogan-edonusum + integration_logs kayıt OK. Frontend screenshot'larında Pazaryerleri Yönetimi (sol liste + Trendyol seçili + 3 kart) ve Entegrasyon Logları (özet + filtre + tablo) beklenen şekilde render.
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

## [2026-04-23] Pazaryeri Konsolidasyon + Otomasyon + İade Motoru

Kullanıcının "karıştı" geribildirimi üzerine yapılan büyük temizlik ve otomasyon işi:

### Sidebar konsolidasyonu (AdminLayout.jsx)
- "Entegrasyonlar" menüsü 10 kalemden 6 kaleme indi. Ayrı Trendyol/Hepsiburada/Temu Eşleştir ve Trendyol Logları kalemleri kaldırıldı — artık detaylı sayfalar "Detaylı Aktarım & Eşleştirme" (`/admin/entegrasyonlar`) ve "Entegrasyon Logları" (`/admin/entegrasyon-loglari?marketplace=...`) içinden erişilir.
- `MarketplaceHub.jsx` header kartına 4 quick-link eklendi: Aktarım İşlemleri, Marka Eşleştirme, Kategori Eşleştirme, Bu Pazaryerinin Logları.
- `Integrations.jsx` Trendyol/HB/Temu kartlarına "Gelişmiş Eşleştirme" ve "Trendyol Logları" butonları (href destekli) eklendi.
- `IntegrationLogs.jsx` URL `?marketplace=trendyol` query parametresini okuyor, filtre otomatik set ediliyor.

### APScheduler gerçek bağlantı (scheduler.py)
- `_run_trendyol_auto_products_sync` → Trendyol config varsa aktif ürünleri `_sync_inventory_to_trendyol` ile gerçek push.
- `_run_trendyol_auto_orders_pull` → Trendyol'dan son 15 günlük siparişleri çekip `map_trendyol_order` ile DB'ye yazar.
- `_marketplace_sync_tick` artık Trendyol için gerçek fonksiyonu `asyncio.create_task` ile arka plan kuyruğuna alıyor (her 1 dk).
- `_send_abandoned_cart_reminders` → 24 saatte bir, RESEND_API_KEY varsa 2–48 saatlik sepetlere "Sepetinizi unutmayın" maili gönderir (tekrar göndermez).

### Stok pasifleme (bulk_ops.py + StockAlerts.jsx)
- `POST /api/bulk-ops/stock-alerts/deactivate-on-marketplaces` — stoku threshold altı olan aktif ürünleri tüm etkin pazaryerlerinde pasife alır (Trendyol'a qty=0 güncelleme; diğer MP'lere log kuyruğa alır).
- Frontend'de StockAlerts sayfasına "Pazaryerinde Pasife Al" butonu + onay modalı. Test: 14 ürün için başarıyla tetiklendi.

### Iyzico kısmi iade + kargo kesintisi (integrations.py)
- `POST /api/integrations/iyzico/refund` — body: `{order_id, amount, shipping_deduction, reason}`. Kargo bedeli iade tutarından düşülüp Iyzico `/payment/refund` çağrısı yapılır. `_iyzico_auth_header` PKI Base64 auth builder eklendi.
- Siparişe `refunds[]` array'i push edilir; integration_logs'a `iyzico.refund` event yazılır.
- Validasyonlar: zorunlu alanlar, geçersiz sipariş, payment_id yoksa, net iade ≤ 0 hataları doğrulandı.

### Trendyol Mikro İhracat faturalandırma (integrations.py + orders.py)
- `map_trendyol_order` artık `is_micro_export`, `shipment_country`, `delivery_type` alanlarını ekliyor (country≠TR veya deliveryType=international/micro olan siparişler).
- `POST /api/orders/{id}/create-invoice` — sipariş `is_micro_export` ise e-arşiv yerine `ETGB00000001` formatında ETGB beyannamesi üretilir, provider `etgb-micro-export` olarak işaretlenir.

### Test durumu
- Backend e2e curl: ✅ login, stock-alerts deactivate (14 ürün), marketplace-hub/logs filtreli çekim, iyzico/refund (zorunlu alan + 404 sipariş).
- Frontend konsolide sidebar canlı önizlemede (preview uyku modu dışında) beklendiği gibi render ediliyor; eski eşleştirme sayfaları route olarak korundu, Integrations ve MarketplaceHub üzerinden erişilebilir.

## Pending / Backlog

### P0 (Kullanıcı Credential Bekliyor)
- **Pazaryeri Canlı API testleri**: Trendyol/HB/Temu gerçek credential'larla uçtan uca ürün push + sipariş pull doğrulaması.
- **E-Fatura/Kargo Canlı Entegrasyonları**: Doğan e-Dönüşüm SOAP + Yurtiçi Kargo REST için gerçek payload gönderimi ve dönen PDF/URL'in siparişe yazılması.

### P1
- **Hepsiburada / Temu / Pazarama auto-sync**: Scheduler hook'u var (log ile kuyruğa alınıyor) — canlı API entegrasyonu için `_run_hepsiburada_*`, `_run_temu_*` fonksiyonları eklenecek.
- **integrations.py refactoring**: 3700+ satır, pazaryeri bazlı modüllere (integrations_trendyol.py, integrations_hepsiburada.py, integrations_temu.py) bölünmeli.

### P2
- Iyzico refund için UI entegrasyonu (iade detay sayfasına "Kısmi İade + Kargo Kesintisi" modalı).
- Mikro ihracat ETGB için gerçek gümrük beyannamesi PDF üretimi (şu an sadece belge numarası).
- A/B test altyapısı, push notification altyapısı (gelecek).

## [2026-04-23] Entegrasyon Denetimi + 10 Fix (iteration_12 & 13)

Kullanıcı "tüm entegrasyonların test API'larıyla kontrol edilmesi — canlıya alırken sadece credential girmesi yeterli olsun" istedi. `testing_agent_v3_fork` ile 2 iterasyon denetimi yapıldı:
- iteration_12: 46/46 pytest → 1 CRITICAL + 4 HIGH + 3 MEDIUM + 1 LOW bug bulundu
- iteration_13 (retest): **77/77 pytest geçti, 0 critical, 3 minor iyileştirme (tümü fix edildi)**

### Yapılan Fix'ler
- **[CRITICAL] Sessiz pasifleme hatası**: `integrations.py:798` `update_inventory` → `update_price_and_inventory`. `bulk_ops.py` dönüş `success` artık `total_fail==0` bazlı.
- **[HIGH] Settings required-field validasyonu** (5 endpoint): Iyzico/Trendyol/HB/Temu/Doğan — `is_active`/`enabled` true iken zorunlu alanlar eksikse 400 döner.
- **[HIGH] Doğan password leak**: `GET /dogan/settings` artık `password: '********'` maskeli. Payload'da `********` gelirse mevcut değer korunur.
- **[HIGH] Webhooks HMAC signature**: `X-Trendyol-Signature` HMAC-SHA256 (hex + base64) `TRENDYOL_WEBHOOK_SECRET` env ile doğrulanıyor.
- **[MEDIUM] Trendyol özel test-connection**: YENİ endpoint `POST /api/integrations/trendyol/test-connection` — `TrendyolClient.get_brands` probe ile 401/403/HTTP hata net.
- **[MEDIUM] Temu gerçek probe**: `bg.auth.access_token.info.get` MD5 signed çağrı; sandbox `openapi-b-global-stg.temu.com`, live `openapi-b-us.temu.com`.
- **[LOW] HB 400 errorCode parse**: Hepsiburada 400 body'sinden errorCode/errorMessage parse ediliyor.
- **[MINOR] Doğan sync SOAP → threadpool**: event loop bloklanmasın.

### Canlıya Hazır Checklist (iteration_13)
- ✅ **HAZIR**: Iyzico settings + refund, Trendyol settings + test-connection, HB/Temu settings + gerçek probe, Doğan settings + mask, bulk-ops pasifleme, webhooks HMAC, 13 MP Hub + 11 E-fatura + 13 Kargo şeması, create-invoice + ETGB.
- ⏳ **CREDENTIAL BEKLİYOR**: Iyzico live key, Trendyol supplier_id/key/secret, HB merchant_id/user/pass, Temu shop_id/app_key/secret, Doğan prod, `TRENDYOL_WEBHOOK_SECRET` env, 10 einvoice provider SDK (sadece Doğan SDK hazır).

### Canlıya Geçiş Adımları
1. Admin panelden her entegrasyon Ayarlar → credential gir, `is_active=true`.
2. "Test Et" butonu → 401/403/timeout/errorCode mesajı net görünür.
3. Prod'da `TRENDYOL_WEBHOOK_SECRET` env set et.
4. Trendyol `mode: live` seçildiğinde otomatik `https://api.trendyol.com` host.

## [2026-04-23] Eşleştirme UX İyileştirmeleri (Search + Bulk Delete)

Kullanıcı "eşleştirmelerde bana ID soruyorsun, search ile seçeyim; kategori eşleştirmede tek tek/toplu silmek istiyorum; ürün özellikleri görünmüyor" diye şikayet etti:

### Backend
- `GET /api/brand-mapping/{mp}/options?q=` — pazaryerinin marka cache'inden arama (Trendyol için `trendyol_brands`, diğerleri için "cache yok, manuel gir" hint'i).
- `GET /api/category-mapping/{mp}/options?q=` — Trendyol kategori ağacını flatten edip arama (full_path içerir: "Giyim > Abiye & Mezuniyet Elbisesi").
- `POST /api/{brand|category}-mapping/{mp}/bulk-delete` — body `{brand_ids: []}` / `{category_ids: []}`.
- Route sıralama fix: options/bulk-delete/reset-all, generic `{brand_id}`/`{category_id}` route'undan ÖNCE tanımlandı (FastAPI catch-all önceliği).
- `GET /api/attributes` artık `_id` projection ile sızmıyor.

### Frontend
- `SearchableMapSelect.jsx` yeni ortak bileşen (`/app/frontend/src/components/admin/`) — debounced fetch + dropdown + full_path gösterimi + "seçili ID" etiketi.
- `BrandMapping.jsx`: ID/Name inputları SearchableMapSelect'e değiştirildi. Checkbox sütunu + Toggle-all + bulk-delete bar.
- `CategoryMapping.jsx`: aynı — checkbox + SearchableMapSelect + tek-tek + toplu sil butonu.
- Ürün global attributes response `_id` temizliği → attribute picker/seçici UI yan etkisi kaldırıldı.

### Test
Backend curl: brand/cat bulk-delete ikisi de `{success:true,deleted:0}` (boş ID), cat options `?q=elbise` → 2+ gerçek sonuç, brand options hepsiburada → hint. Tüm lint temiz.

## [2026-04-23] Gelişmiş Eşleştirme — Tüm Pazaryerleri için Konsolide

Kullanıcı isteği: "Gelişmiş kategori eşleştirme sayfasına (TrendyolEslestir) tıklanınca açılan özellikler, normal kategori eşleştirme sayfasının içinde olsun ve tüm pazaryerleri için çalışsın."

### Backend (generic, MP-agnostic)
- `GET /api/category-mapping/{mp}/{local_cat_id}/attributes` — MP'nin bu kategori için zorunlu+opsiyonel özellikleri. Trendyol için `TrendyolClient.get_category_attributes` canlı çağrısı + DB cache (`trendyol_category_attributes`). Diğer MP'ler için `{mp}_category_attributes` cache varsa dönüyor, yoksa boş + hint.
- `POST /api/category-mapping/{mp}/{local_cat_id}/attribute-map` — attribute_mappings + default_mappings + value_mappings kaydeder (mapping doküman alanları).
- `GET /api/category-mapping/{mp}/{local_cat_id}/values` — bu kategorideki sistem ürünlerinin distinct attribute değerleri (MP'ye gönderirken "Kırmızı ↔ Red" gibi value mapping için).

### Frontend
- Yeni `components/admin/MarketplaceAdvancedMatch.jsx` — iki ortak modal:
  - `AdvancedAttributeMatchModal` — Zorunlu/opsiyonel attribute tablosu, otomatik eşleştir, datalist ile global attr öneri, listeden seçme + serbest yazı (allowCustom), default mappings. MP_COLORS map'i ile her pazaryeri kendi rengiyle gösterilir.
  - `AdvancedValueMatchModal` — attribute tab'ları + değer-bazlı mapping tablosu.
- `CategoryMapping.jsx` her matched kategori satırına 2 yeni buton: "⚙ Özellik" ve "⇅ Değer" — tıklayınca ilgili modal açılır, kaydedince tablo yenilenir.
- Route `/admin/trendyol-eslestir` artık `<Navigate to="/admin/kategori-eslestir">` ile redirect. Eski `TrendyolEslestir.jsx` silinmedi ama menü+route bağlantıları kaldırıldı.
- `Integrations.jsx` içindeki Trendyol/HB/Temu "Gelişmiş Eşleştirme" butonları artık `/admin/kategori-eslestir`'e gider (önceden MP-spesifik ayrı sayfalardı).

### Test
Backend curl: `/category-mapping/trendyol/nonexistent/attributes` → hint "Önce eşleştirin" ✅, `/hepsiburada/*/attributes` → hint+boş ✅, `/values` → `{local_values:{},value_mappings:{}}` ✅, `/attribute-map` POST → `{success:true}` ✅. Lint 4/4 temiz.

## [2026-04-23] Tümünü Otomatik Eşleştir (Potansiyel İyileştirme)

Önceki finish'te önerilen potansiyel iyileştirme uygulandı:

### Backend
`POST /api/category-mapping/{mp}/bulk-auto-match-attributes` — matched tüm kategoriler için toplu otomatik attribute eşleştirme:
- Global attributes bir kez çekilir.
- Trendyol için canlı `TrendyolClient.get_category_attributes` + cache write; diğer MP'ler için `{mp}_category_attributes` cache'inden.
- İsim eşleştirmesi: exact/contains + alias (color↔renk, size↔beden).
- **Manuel eşleştirmeler korunur**, sadece boşlar doldurulur.
- Rapor: `{processed, total_new_mappings, details:[{category_name, new, total_mp_attrs, fetched}]}`.

### Frontend
- CategoryMapping üst barına gradient turuncu-amber "⚡ Tümünü Otomatik Eşleştir" butonu.
- Sonuç modal'ı: 3 özet kart + kategori bazlı detay tablosu (CANLI/CACHE/YOK rozet).

### Test
- Credential yokken Trendyol → 1 matched kategori için `{processed:1, new:0, note:"MP attribute listesi boş"}` ✅
- matched yok iken → `{message:"Eşleştirilecek matched kategori bulunamadı"}` ✅
- Lint: CategoryMapping + category_mapping.py temiz.

## [2026-04-23] Ürün Özellikleri Regression + Değer Otomatik Eşleştir

Kullanıcı şikayetleri: (1) "Ürün özellikleri sekmesinde değerler görünmüyor" (2) "Eşleştirme ayarlarında bu değerleri bulmuyor".

### 1. ProductAttributes.jsx — API env regression
`const API = process.env.REACT_APP_API_URL || 'http://localhost:8001/api'` → Var olmayan env ile production'da `localhost:8001` fallback'ine düşüyor, K8s ingress dışarı yönlendiremiyor → tüm istekler sessiz fail, özellikler boş görünüyor.
**Fix**: `${process.env.REACT_APP_BACKEND_URL}/api`. DB'de zaten 53 attribute + değerleriyle dolu (sync-from-products ile eklendi).

### 2. AdvancedValueMatchModal — Global attribute değerleri eklendi
`GET /api/category-mapping/{mp}/{cat_id}/values` artık `db.products` distinct değerlerine ek olarak `db.attributes` koleksiyonundaki tüm global değerleri birleştirerek döner. Ayrıca ürünün `type` alanı okunuyor (önceden sadece `name`). Kategoride ürün olmasa bile sistemde tanımlı "Renk: Kırmızı/Mavi…" vs görünür.
**Test**: 51 attribute grubu (Renk: 100 değer, Boy: 101, Kol Tipi: 30…) ✅.

### 3. "⚡ Otomatik Değer Eşleştir" Butonu
`AdvancedValueMatchModal` başlığında yeni yeşil "Otomatik Eşleştir" butonu. İsim benzerliği + alias tablosuyla (Kırmızı↔Red, S↔Small, XL↔X-Large…) otomatik eşleştirir. Manuel eşleştirmeler korunur.

### Test
- `sync-from-products`: 9 yeni + 3 güncelleme → 53 attribute dolu ✅
- `/values` 51 grup, 10-100+ değer ✅
- Lint: MarketplaceAdvancedMatch.jsx, ProductAttributes.jsx, category_mapping.py — 3/3 temiz.

## [2026-04-23] Modal Özellik Autocomplete — Datalist Yerine Görünür Dropdown

Kullanıcı: "kategori eşleştirme ayarlarında ürünlerin özellik alanlarını sistemden çekmiyor." Arka planda `GET /api/attributes` 53 attribute çekiyordu ama UI `<datalist>` kullanıyordu; çoğu browser'da input boşken açılmaz.

### Fix
- Yeni `LocalAttrAutoComplete` bileşeni: Focus'ta tüm 53 sistem özelliği açılır dropdown'da (değer sayacıyla) görünür, yazdıkça filtreler.
- Banner: "Sistemde tanımlı **N** özellik var — kutuya tıkladığınızda liste açılır."
- Boş fallback: globalAttrs=0 ise sarı "Ürünlerden Yükle" → `POST /attributes/sync-from-products`.

## [2026-04-23] Empty State + Zorunlu Ayrımı (Screenshot Sorunu)

Kullanıcı ekran görüntüsü: Trenço kategori modal'ı "özellik bulunamadı" gösteriyordu (Trendyol cache yok).

### Fix
- mpAttrs boşsa, globalAttrs'ı pseudo-satırlar olarak listeler (kullanıcı manuel seçim yapar).
- Amber banner "credential/cache eksik — N sistem özelliğinden manuel seç".
- Zorunlu satırlar: `bg-red-50/40` kırmızı zemin + kırmızı ZORUNLU badge + "ZORUNLU ALANLAR (N)" / "OPSİYONEL ALANLAR (N)" grup başlıkları.
- React.Fragment key ile header+row çifti, `isReq` hatasız durum sütunu.

## [2026-04-23] P1/P2/P3 — Canlı Çek + Manuel Cache Upload + Eski Sayfa Temizlik

Kullanıcı isteği: önceki "Next Action Items" (P1 Trendyol canlı çek butonu, P1 HB/Temu cache besleme, P2 eski TrendyolEslestir silme).

### 1. "Canlı Çek" Butonu (Modal içinde)
- Backend: `POST /api/category-mapping/{mp}/{local_cat_id}/refresh-attributes` — tek kategoride MP attribute listesini anlık yeniler.
  - **Trendyol**: `TrendyolClient.get_category_attributes(mp_cat_id)` canlı çağrı + cache upsert + `{success:true, count:N}` dönüş.
  - **Diğer MP'ler**: "canlı API yok, manuel upload yap" mesajı.
- Frontend: AdvancedAttributeMatchModal header'ına mavi **"{marketplace} Canlı Çek"** butonu. İşlem sonrası modal tablosu otomatik yeniden yüklenir.

### 2. HB/Temu için Manuel Attribute Cache Upload
`POST /api/category-mapping/{mp}/attr-cache` yeni endpoint:
- Body: `{marketplace_category_id, attributes: [{id, name, required, attributeValues:[...]}]}`
- Kullanıcı kendi HB/Temu panelinden export ettiği JSON'u buraya POST eder → `{mp}_category_attributes` cache'e yazılır → Modal'da o kategori için attribute listesi görünür hale gelir.
- Route sıralaması düzeltildi: `attr-cache` `{category_id}` generic'ten ÖNCE tanımlı.
- Test: HB için 1 attribute (Renk: Kırmızı/Mavi) upload → `{success:true, count:1}` ✅

### 3. Eski Eşleştirme Sayfaları Silindi
- `TrendyolEslestir.jsx` (1286 satır), `HepsiburadaEslestir.jsx`, `TemuEslestir.jsx` fiziksel olarak silindi.
- App.js'te 3 route → `<Navigate to="/admin/kategori-eslestir" replace />`
- Import satırları temizlendi. Lint: temiz.

### Test
Backend: `/refresh-attributes` → "önce eşleştirin" net hata ✅; `/attr-cache` → manuel 1 attr yüklendi ✅
Frontend lint: App.js, MarketplaceAdvancedMatch.jsx, category_mapping.py — 3/3 temiz.

Kullanıcı şikayeti: "Kategori eşleştirme ayarlarında ürünlerin özellik alanlarını sistemden çekmiyor." Arka planda `GET /api/attributes` doğru şekilde 53 attribute çekiyordu ama UI `<datalist>` kullanıyordu — bu element çoğu browser'da input boşken açılmaz, kullanıcı sistem özelliklerini göremezdi.

### Fix
- **Yeni `LocalAttrAutoComplete` bileşeni**: `MarketplaceAdvancedMatch.jsx` içinde standalone autocomplete. Focus'ta sistem özelliklerinin tamamını (53 tane, "Beden — 100 değer" gibi) gösterir, yazdıkça filtreler.
- **Banner bilgisi**: "Sistemde tanımlı **N** özellik var — kutuya tıkladığınızda öneri listesi açılır."
- **Fallback**: Global attrs boşsa (yeni kurulum) banner'da "Ürünlerden Yükle" butonu → `POST /api/attributes/sync-from-products` çağırır, liste yeniler.

### Test
- `/api/attributes` 53 attribute döner, değer sayılarıyla birlikte autocomplete'de görünür ✅
- Lint temiz ✅

## [2026-04-23] Bulk Delete + Global AppConfirm Pop-up

Kullanıcı şikayetleri: (1) Ürün sayfasında birden fazla ürün seçince sil butonu aktif olmuyor. (2) Tüm sitede onaylar browser native popup (sekme üstü) çıkıyor, app içinde pop-up istendi.

### 1. Global `appConfirm` Altyapısı
- Yeni `components/admin/AppConfirm.jsx`: Shadcn AlertDialog tabanlı Promise API.
- `appConfirm("metin")` veya `appConfirm({title, description, confirmText, cancelText, variant:"danger"|"warning"|"default"})` Promise<boolean> döner.
- Tek global resolver; `<AppConfirmRoot />` AdminLayout'ta mount, `window.appConfirm` global.

### 2. Migration: `window.confirm` → `await window.appConfirm`
- 20 admin sayfası (Orders, Products, Returns, Vendors, Coupons, Members, BulkPriceStock, StockAlerts, ProductReviews, Manufacturing, Settings, UsersRoles, PageDesign, SeoAdmin, CatalogExtras, AdminTasks, BrandMapping, CategoryMapping, Questions, Account) sed ile migrated.
- Sonuç: browser native popup kayboldu; Shadcn app-içi pop-up (temayla uyumlu, variant'lı danger/warning/default).
- Lint: tüm admin + Account.jsx — temiz ✅.

### 3. Products Bulk Delete
- Seçili ürünler bar'ına kırmızı **"Seçili Ürünleri Sil"** butonu (Trash2 ikonu).
- `handleBulkDeleteProducts` → appConfirm `danger` ile "{N} ürün silinsin mi?" → DELETE loop → başarı/fail sayacı toast + liste refresh.


