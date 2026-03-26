import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminSettings() {
  const [settings, setSettings] = useState({
    site_name: "FACETTE",
    logo_url: "",
    free_shipping_limit: 500,
    rotating_texts: [],
    contact_email: "",
    contact_phone: "",
    address: "",
    payment_methods: {
      credit_card: true,
      bank_transfer: true,
      cash_on_delivery: true,
    },
    barcode_range_start: "",
    barcode_range_end: "",
    default_vat_rate: 10,
    trendyol_markup: 0,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await axios.get(`${API}/settings`);
      setSettings(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/settings`, settings, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Ayarlar kaydedildi");
    } catch (err) {
      toast.error("Kayıt başarısız: " + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Yükleniyor...</div>;
  }

  return (
    <div data-testid="admin-settings">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Site Ayarları</h1>
        <button 
          onClick={handleSave}
          disabled={saving}
          className="bg-black text-white px-6 py-2 rounded hover:bg-gray-800 disabled:opacity-50"
        >
          {saving ? "Kaydediliyor..." : "Kaydet"}
        </button>
      </div>

      <div className="space-y-6">
        {/* General */}
        <div className="bg-white p-6 rounded-lg shadow-sm">
          <h2 className="text-lg font-medium mb-4">Genel Ayarlar</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Site Adı</label>
              <input
                type="text"
                value={settings.site_name}
                onChange={(e) => setSettings({ ...settings, site_name: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Logo URL</label>
              <input
                type="url"
                value={settings.logo_url}
                onChange={(e) => setSettings({ ...settings, logo_url: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Ücretsiz Kargo Limiti (TL)</label>
              <input
                type="number"
                value={settings.free_shipping_limit}
                onChange={(e) => setSettings({ ...settings, free_shipping_limit: parseFloat(e.target.value) })}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Varsayılan KDV Oranı (%)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={settings.default_vat_rate || 10}
                  onChange={(e) => setSettings({ ...settings, default_vat_rate: parseInt(e.target.value) || 0 })}
                  className="flex-1 border px-3 py-2 rounded text-sm"
                />
                <button
                  type="button"
                  onClick={async () => {
                    if (window.confirm(`Tüm ürünlerin KDV oranını %${settings.default_vat_rate} olarak güncellemek istediğinize emin misiniz?`)) {
                      try {
                        const token = localStorage.getItem('token');
                        const res = await axios.post(`${API}/products/bulk-update-vat`, { vat_rate: settings.default_vat_rate }, {
                          headers: { Authorization: `Bearer ${token}` }
                        });
                        toast.success(res.data.message);
                      } catch (err) {
                        toast.error("İşlem başarısız");
                      }
                    }
                  }}
                  className="bg-orange-500 text-white px-3 py-2 rounded text-xs font-bold hover:bg-orange-600 transition-colors"
                >
                  Tüm Ürünlere Uygula
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Trendyol Integration Settings */}
        <div className="bg-orange-50 p-6 rounded-lg shadow-sm border border-orange-100">
          <h2 className="text-lg font-medium mb-4 text-orange-900 flex items-center gap-2">
            <span className="w-2 h-6 bg-orange-500 rounded-full inline-block"></span>
            Trendyol Entegrasyon Ayarları
          </h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1 text-orange-900">Global Trendyol Kâr Oranı (%)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={settings.trendyol_markup || 0}
                  onChange={(e) => setSettings({ ...settings, trendyol_markup: parseFloat(e.target.value) || 0 })}
                  className="w-full border-orange-200 border px-3 py-2 rounded text-sm focus:outline-none focus:border-orange-500 font-bold text-orange-700"
                  placeholder="Örn: 20"
                />
              </div>
              <p className="text-xs text-orange-600 mt-2">
                Trendyol fiyatlamasında "Global oranı kullan" seçilen ürünlerde otomatik eklenecek varsayılan markup (kâr / komisyon) yüzdesi.
              </p>
            </div>
          </div>
        </div>

        {/* Rotating Texts */}
        <div className="bg-white p-6 rounded-lg shadow-sm">
          <h2 className="text-lg font-medium mb-4">Dönen Yazılar (Header)</h2>
          <div>
            <label className="block text-sm font-medium mb-1">Yazılar (satır satır)</label>
            <textarea
              value={settings.rotating_texts?.join("\n") || ""}
              onChange={(e) => setSettings({ ...settings, rotating_texts: e.target.value.split("\n").filter(Boolean) })}
              rows={4}
              placeholder="Yeni Sezon Ürünleri&#10;Ücretsiz Kargo&#10;Güvenli Alışveriş"
              className="w-full border px-3 py-2 rounded text-sm"
            />
          </div>
        </div>

        {/* Contact */}
        <div className="bg-white p-6 rounded-lg shadow-sm">
          <h2 className="text-lg font-medium mb-4">İletişim Bilgileri</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">E-posta</label>
              <input
                type="email"
                value={settings.contact_email}
                onChange={(e) => setSettings({ ...settings, contact_email: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Telefon</label>
              <input
                type="tel"
                value={settings.contact_phone}
                onChange={(e) => setSettings({ ...settings, contact_phone: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-1">Adres</label>
              <textarea
                value={settings.address}
                onChange={(e) => setSettings({ ...settings, address: e.target.value })}
                rows={2}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
          </div>
        </div>

        {/* Payment Methods */}
        <div className="bg-white p-6 rounded-lg shadow-sm">
          <h2 className="text-lg font-medium mb-4">Ödeme Yöntemleri</h2>
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.payment_methods?.credit_card || false}
                onChange={(e) => setSettings({ 
                  ...settings, 
                  payment_methods: { ...settings.payment_methods, credit_card: e.target.checked }
                })}
              />
              <span className="text-sm">Kredi Kartı / Banka Kartı</span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.payment_methods?.bank_transfer || false}
                onChange={(e) => setSettings({ 
                  ...settings, 
                  payment_methods: { ...settings.payment_methods, bank_transfer: e.target.checked }
                })}
              />
              <span className="text-sm">Havale / EFT</span>
            </label>
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={settings.payment_methods?.cash_on_delivery || false}
                onChange={(e) => setSettings({ 
                  ...settings, 
                  payment_methods: { ...settings.payment_methods, cash_on_delivery: e.target.checked }
                })}
              />
              <span className="text-sm">Kapıda Ödeme</span>
            </label>
          </div>
        </div>

        {/* Company Info */}
        <div className="bg-white p-6 rounded-lg shadow-sm border-l-4 border-blue-500">
          <h2 className="text-lg font-medium mb-4 flex items-center gap-2">
            <span className="w-2 h-6 bg-blue-500 rounded-full inline-block"></span>
            Şirket Bilgileri
          </h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Firma Ünvanı</label>
              <input type="text" value={settings.company_info?.company_name || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), company_name: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm" placeholder="FACETTE DIŞ. TİC.A.Ş" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Vergi Kimlik No (VKN)</label>
              <input type="text" value={settings.company_info?.tax_number || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), tax_number: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm font-mono" placeholder="7810816779" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Vergi Dairesi</label>
              <input type="text" value={settings.company_info?.tax_office || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), tax_office: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm" placeholder="HALKALI VERGİ DAİRESİ BAŞKANLIĞI" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Web Sitesi</label>
              <input type="text" value={settings.company_info?.website || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), website: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm" placeholder="facette.com.tr" />
            </div>
            <div className="md:col-span-2">
              <label className="block text-sm font-medium mb-1">Adres</label>
              <input type="text" value={settings.company_info?.address || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), address: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm" placeholder="İkitelli O.S.B. İmsan San. Sit. D BLOK NO:3" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">İl / İlçe</label>
              <input type="text" value={settings.company_info?.city || ""}
                onChange={(e) => setSettings({...settings, company_info: {...(settings.company_info || {}), city: e.target.value}})}
                className="w-full border px-3 py-2 rounded text-sm" placeholder="KÜÇÜKÇEKMECE/ İstanbul" />
            </div>
          </div>
        </div>

        {/* Barcode Settings */}
        <div className="bg-white p-6 rounded-lg shadow-sm">
          <h2 className="text-lg font-medium mb-1">Barkod Aralığı (GTIN-13)</h2>
          <p className="text-xs text-gray-500 mb-4">
            Varyant kaydederken "Oluştur" butonuna basıldığında, sistem bu aralık içinden çakışmayan 13 haneli benzersiz bir barkod üretir.
          </p>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Aralık Başlangıcı</label>
              <input
                type="text"
                value={settings.barcode_range_start || ""}
                onChange={(e) => setSettings({ ...settings, barcode_range_start: e.target.value })}
                placeholder="Örn: 8680000000001"
                className="w-full border px-3 py-2 rounded text-sm font-mono"
                maxLength={13}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Aralık Sonu</label>
              <input
                type="text"
                value={settings.barcode_range_end || ""}
                onChange={(e) => setSettings({ ...settings, barcode_range_end: e.target.value })}
                placeholder="Örn: 8689999999999"
                className="w-full border px-3 py-2 rounded text-sm font-mono"
                maxLength={13}
              />
            </div>
          </div>
          <div className="mt-3 p-3 bg-blue-50 rounded text-xs text-blue-700">
            <strong>Not:</strong> Bu aralığa 13 haneli sayısal değerler giriniz. Sistem, sistemdeki diğer ürünlerin barkodlarıyla çakışmayacak şekilde otomatik olarak bir değer seçtiren bir barkod atar.
          </div>
        </div>
      </div>
    </div>
  );
}
