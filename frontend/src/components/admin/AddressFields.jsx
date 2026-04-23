/**
 * =============================================================================
 * AddressFields.jsx — İl/İlçe Dropdown'lu Adres Girişi
 * =============================================================================
 *
 * AMAÇ:
 *   Admin sipariş oluşturma, müşteri adres düzenleme vb. formlarda serbest
 *   metin yerine backend'deki `/api/locations/tr/provinces` ve
 *   `/api/locations/tr/districts?province=X` endpoint'lerinden beslenen
 *   dropdown'lar ile il/ilçe seçimi sağlamak. Hatalı veri girişini önler,
 *   kargo entegrasyonlarındaki adres eşlemesini kolaylaştırır.
 *
 * PROPS:
 *   - value    : { city, district, address, phone, postal_code, full_name }
 *   - onChange : (newValue) => void
 *   - compact  : true ise grid'i daraltır (modallar için)
 *
 * NOT: Şehir seçimi değiştiğinde ilçe otomatik temizlenir ve yeni ilçe
 *      listesi yüklenir.
 * =============================================================================
 */
import { useEffect, useState, useMemo } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AddressFields({ value = {}, onChange, compact = false }) {
  const [provinces, setProvinces] = useState([]);
  const [districts, setDistricts] = useState([]);

  const token = useMemo(() => localStorage.getItem("token"), []);
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  useEffect(() => {
    axios.get(`${API}/locations/tr/provinces`, auth)
      .then((r) => setProvinces(r.data?.provinces || r.data || []))
      .catch(() => setProvinces([]));
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    if (!value.city) { setDistricts([]); return; }
    axios.get(`${API}/locations/tr/districts?province=${encodeURIComponent(value.city)}`, auth)
      .then((r) => setDistricts(r.data?.districts || r.data || []))
      .catch(() => setDistricts([]));
    // eslint-disable-next-line
  }, [value.city]);

  const set = (k, v) => onChange({ ...value, [k]: v });

  return (
    <div className={`grid ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-3"} gap-3`}>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Ad Soyad</label>
        <input value={value.full_name || ""} onChange={(e) => set("full_name", e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          data-testid="addr-fullname" />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Telefon</label>
        <input value={value.phone || ""} onChange={(e) => set("phone", e.target.value)}
          placeholder="0 555 123 45 67"
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          data-testid="addr-phone" />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">İl <span className="text-red-500">*</span></label>
        <select value={value.city || ""} onChange={(e) => onChange({ ...value, city: e.target.value, district: "" })}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
          data-testid="addr-city">
          <option value="">Seçiniz...</option>
          {provinces.map((p) => (<option key={p.name || p} value={p.name || p}>{p.name || p}</option>))}
        </select>
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">İlçe <span className="text-red-500">*</span></label>
        <select value={value.district || ""} onChange={(e) => set("district", e.target.value)}
          disabled={!value.city}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white disabled:bg-gray-50"
          data-testid="addr-district">
          <option value="">{value.city ? "Seçiniz..." : "Önce il seçin"}</option>
          {districts.map((d) => (<option key={d.name || d} value={d.name || d}>{d.name || d}</option>))}
        </select>
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1">Posta Kodu</label>
        <input value={value.postal_code || ""} onChange={(e) => set("postal_code", e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          data-testid="addr-postal" />
      </div>
      <div className={compact ? "col-span-2" : "col-span-2 md:col-span-3"}>
        <label className="block text-xs text-gray-600 mb-1">Açık Adres</label>
        <textarea value={value.address || ""} onChange={(e) => set("address", e.target.value)}
          rows={2}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
          data-testid="addr-street" />
      </div>
    </div>
  );
}
