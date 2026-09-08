# İndirim sonrası kargo ve üyelik — 8 Eylül 2026

Kullanıcının son onayı: tüm indirimler sonrası ürün tutarı **4.000,00 TL ve üzeri ücretsiz**, **3.999,99 TL ve altı ücretli**. Önceki “üzerinde” ifadesi bu onayla değiştirilmiştir. Tutar kodda sabit değildir; mevcut kampanya/ayar eşiği kullanılır.

## Değişiklik

- Sunucu kargoyu kampanya/kupon, havale ve gerçekten kullanılan puan tutarı düşüldükten sonra kesinleştirir. Eski ücretsiz-kargo bayrağı minimumu bypass edemez.
- Karar hediye çeki rezervasyonundan ve müşteri-onay tutarı kontrolünden önce verilir. Hediye çeki/mağaza kredisi ödeme aracıdır; hediye paketi, kargo ve hizmet bedelleri ürün tabanını artırmaz.
- Son taban `shipping_eligibility_basis` olarak siparişe kaydedilir. Eşik altına inen ücretsiz-kargo kampanyasının yanlış uygulandı kaydı temizlenir.
- Ödeme arayüzü kampanya, ödeme, üye-grubu ve puan indirimlerinden sonraki tutarı kullanır. Sepet/çekmece, ödeme seçenekleri henüz bilinmediğinden tahmin olduğunu açıklar.
- Ücretsiz kargoda üstü çizili ücret artık sabit 59,99 değil ayardan gelen ücrettir.
- E-posta/şifre üyeliğinde ad ve soyad boş/yalnız boşluk olamaz; tarayıcı ve sunucuda kontrol edilir. Üye Ol formunda “veya” kaldırıldı, giriş formu korunur.
- Eğitim & Yardım sürümlü açıklaması güncellendi; mevcut firma yardım metinleri korunur.

## Sınırlar ve doğrulama

- Sınır matematiği iki tarafta testli: 3999,99 / 4000,00 / 4000,01. Render edilen Checkout'ta havale sonrası 3999,99 ve 4000,00 senaryoları ve eski kargo bayrağı testi vardır.
- Üyelik testleri, boş ad/soyadda DB erişimi başlamadan red cevabını doğrular.
- Sipariş statüsü, ödeme sağlayıcı callback'i, stok düşümü, puan harcama ve hediye çeki rezervasyon işlevleri değiştirilmedi. Gerçek sipariş/ödeme/üyelik oluşturularak test yapılmadı.
- Önceden mevcut genel ödeme-tipi/üye-grubu indirimlerinin server toplamı ile tam mutabakatı bu değişiklikte yeniden tasarlanmadı; onay-tutarı kontrolü korunur. Bu not tüm ödeme varyasyonları için doğruluk sertifikası değildir.
- Geçmiş siparişlere veya kampanya ayarlarına toplu yazma yok. Önceki indirim etiketlerinin dağılım sorunu ve bağımlılık/sır taraması bulguları ayrı açık işlerdir.

Yayın ve canlı tarayıcı sonucu dağıtım kayıtlarından ayrıca doğrulanır.
