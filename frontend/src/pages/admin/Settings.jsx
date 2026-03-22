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
    }
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
      await axios.put(`${API}/settings`, settings);
      toast.success("Ayarlar kaydedildi");
    } catch (err) {
      toast.error("Kayıt başarısız");
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
      </div>
    </div>
  );
}
