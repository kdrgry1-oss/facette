/**
 * CargoSettings.jsx — Kargo Firması Ayarları sayfası.
 *
 * Yönetici hangi kargo firmasıyla çalışacaksa onu seçip credential'larını
 * girer. `/admin/ayarlar/kargo` rotasında render edilir. Jenerik
 * ProviderSettings componentini "cargo" modunda çağırır.
 *
 * Desteklenen kargo firmaları (backend provider_settings.py içinde tanımlı):
 *   MNG Kargo, Yurtiçi Kargo, Aras Kargo, PTT Kargo, Sürat Kargo,
 *   HepsiJet, Trendyol Express, Sendeo, Kolay Gelsin, DHL, UPS, FedEx, TNT.
 *
 * Bağlantılı:
 *   - components/admin/ProviderSettings.jsx (ana UI)
 *   - backend/routes/provider_settings.py (GET/POST /api/provider-settings/cargo/*)
 *   - Orders.jsx kargo ekranı ileride bu aktif provider'ı kullanarak
 *     gerçek API'ye istek atacak (şu an mock).
 */
import ProviderSettings from "../../components/admin/ProviderSettings";

export default function CargoSettings() {
  return (
    <ProviderSettings
      kind="cargo"
      title="Kargo Firması Ayarları"
      subtitle="Çalışacağınız kargo firmalarını yapılandırın. Birden fazla firma için bilgi girilebilir, sistem aktif seçilen firmayı kullanır (sipariş kargo oluşturma, etiket basma vb.)."
    />
  );
}
