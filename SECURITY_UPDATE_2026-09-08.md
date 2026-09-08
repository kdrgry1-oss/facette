# Güvenlik düzeltmeleri — 8 Eylül 2026

Durum: Yerel çalışma kopyasında uygulandı ve test edildi; kullanıcı açıkça deploy onayı verdi. Yayın öncesinde `origin/main` üzerindeki `95e83dd` kupon teşhis günlüğü değişikliği fast-forward ile korundu. Yayın sonucu GitHub/Railway/Cloudflare deployment kayıtlarından doğrulanmalıdır; bu dosya tek başına canlı dağıtım kanıtı değildir. Müşteri, sipariş, ödeme, stok veya canlı sağlayıcı ayarı değiştirilmedi; e-posta gönderilmedi.

## Uygulananlar

| Alan | Yeni davranış |
|---|---|
| Panel yetkisi | Rolü olmayan, silinmiş/boş rolü bulunan veya veritabanında admin olmayan hesap yönetim API'sine giremez. E-posta adresinden örtük süper yönetici hakkı verilmez. |
| Açılış işlemi | Önceden var olan hesabın sırf bootstrap e-postasıyla eşleştiği için otomatik yükseltilmesi kaldırıldı. Mevcut açık süper yönetici bayrağı ve atanmış roller korunur. |
| Oturum iptali | Bozuk token_version verisi yetkiyi açık bırakmaz. Çıkış sonrası geciken auth/me cevabı eski kullanıcıyı arayüze geri getiremez. |
| E-posta yetkileri | Sağlayıcı ayarları okuma/yazma/doğrulama `settings.emails`; kampanya, şablon, kitle ve engelleme listesi erişimi `tasarim.email` ister. Sınırlı personel ayar anahtarlarını görmeden kampanya ekranını kullanabilir. |
| Anahtar saklama | Brevo API/webhook ve SES gizli anahtarı şifrelenemezse hiçbir ayar yazılmaz. Şifre çözme hatası sağlayıcıyı kullanılabilir göstermez. Şifreleme için güçlü anahtar bulunamıyorsa sabit/boş değerden anahtar türetilmez. |
| Gönderim güvenliği | Engellenen adresler listesi eksik okunursa gönderim durur. Beklenmeyen gönderim sonucu inceleme gerektirir; kör SES yeniden gönderimi yapılmaz. SES ayarları silinmedi. |
| Adres gizliliği | Hesaplar arasında ortak localStorage adresi okunmaz/yazılmaz; eski kayıt temizlenir. Kullanıcı değişince form temizlenir, eski hesaba ait gecikmiş adres yanıtı yok sayılır. Üyenin kendi kayıtlı adres API'si korunur. |
| Belge erişimi | Fatura/kargo etiketi, ürün barkodu, müşteri 360 raporu ve influencer belgelerinde JWT query parametresi kaldırıldı. Belge Authorization başlığıyla alınır, blob üzerinden açılır. Belge yanıtları no-store/no-referrer kullanır. |
| Fatura HTML | Fatura/sipariş numarası ve sağlayıcı alanları HTML olarak çalıştırılmaz, escape edilir. Fatura iframe'i sandbox içindedir. |
| Güvenlik CI | Eksik/bozuk gitleaks raporu issue kapatamaz. pip-audit bulguları ve tarama hataları başarısız sayılır. Frontend yüksek/kritik açıkları ve tarama hataları başarısız sayılır. JSON kanıtları artifact olarak saklanır. |
| Eğitim & Yardım | Sürümlü rehbere yetki, anahtar, adres ve yeni yazdırma davranışı eklendi; firmaya özel mevcut yardım metinleri korunur. |

## Doğrulama

- 116 odaklı backend testi başarılı. Yeni testler üretim başlangıç/DB yan etkilerini çalıştırmadan gerçek fonksiyon gövdelerini, HTTP bağımlılıklarını ve şifreleme hata yollarını sınar.
- 16 arayüz test paketi / 52 test başarılı; çıkış sonrası yanıt yarışı, hesaplar arası adres izolasyonu, başlıkla belge erişimi ve popup hataları dahil.
- Backend compileall ve git diff --check başarılı.
- Optimize frontend build başarılı. Browserslist veri yaşı uyarısı var; derleme hatası değil.
- Tarayıcı: gerçek derlenmiş arayüz, yalnız localhost'taki sentetik HTTP verileriyle sınandı. Pazarlama personelinde ayarlar gizli, yöneticide görünür; misafir eski adresi görmez ve kayıt silinir. Bu testler canlı veri mutabakatı veya gerçek e-posta teslimatı kanıtı değildir.
- Fatura önizlemesinde blob bağlantısı üretildi ve test sunucusuna Authorization başlığıyla ulaşıldı; ancak tarayıcı aracının blob navigasyon güvenlik kısıtı nedeniyle içerik/yazdırma testi tamamlanamadı. Bu adım başarılı olarak sayılmıyor. Gerçek tarayıcıda fatura, etiket, ürün barkodu ve diğer belge çıktıları ayrıca doğrulanmalı.
- Canlı `/admin` kontrolü `/admin/login` sayfasına yönlendi. Mevcut sahip hesabının yetkisi henüz doğrulanamadı.

## Canlıya alma önkoşulları

1. Yetkili kullanıcı giriş yapmalı. Sahip hesabının gerçek `is_super_admin: true` veya `*` izinli atanmış rolü bulunduğu doğrulanmalı. Rolsüz personele uygun roller mevcut yetkili yönetici tarafından atanmalı; herkese otomatik geniş hak verilmeyecek.
2. Mevcut şifreleme anahtarı korunmalı. Anahtar değiştirmek daha önce şifrelenmiş sırları açılmaz hale getirebilir; anahtar rotasyonu ayrı, kontrollü bir işlemdir.
3. Backend ve frontend birlikte yayımlanmalı. Eski query-token kullanan tarayıcı sürümleri yenilenmeli; eski yazdırma bağlantıları bilerek yetkisiz kalır.
4. CI, yetkili/yetkisiz canlı erişim, fatura/etiket görüntüleme ve panel giriş/çıkış senaryoları yeniden doğrulanmalı. Gerçek sipariş/ödeme veya toplu e-posta testi bu paket kapsamında yapılmayacak.

## Açık kalan işler / bu paketin kapsamı dışında

- Git geçmişinde raporlanan 12 olası sır için geçerlilik tespiti, sağlayıcı tarafında iptal/yenileme ve kontrollü geçmiş temizliği. Kod düzeltmesi bu sırları geçersiz kılmaz.
- Yeni bağımlılık taramasının gerçek bulguları ve uyumluluk testleriyle sürüm güncellemeleri. Testlerin geçmesi bağımlılıkların açıksız olduğunu kanıtlamaz.
- Raporların eski yaklaşık kâr hesabı ve ürün adıyla belirsiz eşleştirmeleri, gerçek platform verileriyle yeniden mutabakat.
- Ücretsiz kargo eşiğine kampanya tarih/uygunluk koşulları uygulanması. Sipariş/ödeme iş kuralı olduğu için ayrı açık kural onayı gerekir; bu pakette değiştirilmedi.
- Kampanya gönderimini kalıcı iş kuyruğuna taşıma ve kampanya bazında bağımsız alıcı listesi. Mevcut asyncio görevi yeniden başlatmada dayanıklı hale getirilmiş değildir; belirsiz sonuç görünürlüğü bunun yerine geçmez.
- Yalnız require_admin kullanan diğer modüllerde işlem bazlı en-az-yetki incelemesi. Bu paket bütün route'ların yetkilerini yeniden tasarlamaz.
- Çok kiracılı SaaS izolasyonu, firma/tenant sınırları, kapsamlı bağımsız sızma testi ve olağanüstü durum/yedekten dönüş denemeleri.

Bu nedenle “tüm sistem güvenli” veya “bütün raporlar doğrulandı” sonucu çıkarılamaz.
