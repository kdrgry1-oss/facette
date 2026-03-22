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
- SMS: Netgsm API (Optional)

## Current Status: v8.0 - Full E-commerce Suite ✅

### Tamamlanan Özellikler (2026-03-22)

#### v8.0 - Product Data Fix + Order Tracking + SMS
- [x] **Ürün Stok Kodları** - Otomatik oluşturuldu (örn: FC-BKMI-7171)
- [x] **Ürün Barkodları** - 13 haneli EAN-13 (örn: 8690017164670)
- [x] **Duplicate Görseller Temizlendi** - 243 tekrar görsel silindi
- [x] **Sipariş Takip Sayfası** - `/siparis-takip` müşteri için
  - Sipariş numarası veya kargo takip numarası ile arama
  - Timeline görünümü (Alındı → Onaylandı → Hazırlanıyor → Kargoda → Teslim)
  - Kargo takip linki
- [x] **Netgsm SMS Entegrasyonu**
  - Sipariş onay SMS'i
  - Kargo bildirim SMS'i
  - Admin panelinde SMS butonları
- [x] **Footer'a Sipariş Takip Linki** eklendi

#### v7.1 - MNG Kargo
- [x] MNG Kargo SOAP API entegrasyonu
- [x] 10 haneli tracking number
- [x] Kargo etiketi (10cm x 15cm)
- [x] Toplu etiket yazdırma

#### v6.0 - Full Features
- [x] Varyant Yönetimi
- [x] Benzer Ürünler & Kombin
- [x] Iyzico Ödeme
- [x] Multi-carrier cargo

## API Endpoints

### Public
- `GET /api/track/{code}` - Sipariş takip (auth gerektirmez)

### SMS (Admin)
- `POST /api/orders/{id}/send-confirmation-sms` - Sipariş onay SMS
- `POST /api/orders/{id}/send-shipping-sms` - Kargo bildirim SMS
- `POST /api/sms/send-test` - Test SMS

### Cargo
- `POST /api/orders/{id}/create-mng-shipment` - MNG ile gönder
- `GET /api/orders/{id}/cargo-label` - Kargo etiketi
- `POST /api/orders/bulk-labels` - Toplu etiket

## Netgsm SMS Ayarları
```env
# .env dosyasına ekleyin
NETGSM_USERNAME=your_username
NETGSM_PASSWORD=your_password
NETGSM_HEADER=FACETTE
```

**SMS Şablonları:**
1. Sipariş Onay: "Merhaba {isim}, siparişiniz alındı. Sipariş No: {no} Tutar: {tutar}TL FACETTE"
2. Kargo Bildirim: "Merhaba, siparişiniz {kargo} ile gönderildi. Takip: {takip_no} FACETTE"

## Ürün Kodlama Sistemi
- **Stok Kodu**: FC-{ISIM_KISALTMA}-{4_RAKAM} (örn: FC-BKMI-7171)
- **Barkod**: 13 haneli EAN-13, Türk prefix 869 (örn: 8690017164670)

## Sayfa URL'leri
- `/siparis-takip` - Müşteri sipariş takip sayfası
- `/siparis-takip/:trackingCode` - Direkt sipariş takip

## Test Results
- ✅ Sipariş takip API çalışıyor
- ✅ Sipariş takip sayfası çalışıyor
- ✅ Ürün stok kodları oluşturuldu
- ✅ Ürün barkodları oluşturuldu
- ✅ Duplicate görseller temizlendi

## Test Credentials
- Admin: admin@facette.com / admin123
- URL: https://mega-menu-catalog.preview.emergentagent.com

## P1 - Sonraki Görevler
- [ ] Netgsm credentials ile canlı SMS test
- [ ] E-mail bildirimi (Resend/SendGrid)
- [ ] Iyzico production key

## P2 - Backlog
- [ ] Trendyol marketplace
- [ ] GIB e-fatura
- [ ] Gelişmiş raporlama
- [ ] Müşteri hesap sayfası geliştirmeleri

## File Structure
```
/app/
├── backend/
│   ├── server.py        # ~2260 lines
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/
        │   ├── TrackOrder.jsx    # NEW
        │   └── admin/Orders.jsx  # SMS buttons
        └── components/
            └── Footer.jsx        # Sipariş takip linki
```

## Last Updated
2026-03-22 - v8.0 Product Data + Order Tracking + SMS
