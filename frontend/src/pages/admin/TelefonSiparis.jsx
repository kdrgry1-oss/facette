// =============================================================================
// TelefonSiparis.jsx — Telefonla / Manuel Sipariş Oluştur
// -----------------------------------------------------------------------------
// Telefon veya mağaza içi satışları panelden sipariş olarak girer.
// Backend: POST /admin/orders/create-manual (order_number MNL-…, source admin_manual,
// stok düşülür). Ürünler GET /products?search= ile aranır.
// =============================================================================
import { useState } from "react";
import axios from "axios";
import { Phone, Search, Plus, Trash2, ShoppingCart } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function money(v) {
  const n = Number(v) || 0;
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " TL";
}

const PAYMENT_METHODS = [
  { v: "cash", l: "Nakit" },
  { v: "havale", l: "Havale / EFT" },
  { v: "credit_card", l: "Kredi Kartı" },
  { v: "kapida", l: "Kapıda Ödeme" },
];

export default function TelefonSiparis() {
  const [cust, setCust] = useState({ full_name: "", phone: "", email: "" });
  const [addr, setAddr] = useState({ city: "", district: "", address: "", postal_code: "" });
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [paymentStatus, setPaymentStatus] = useState("paid");
  const [shippingCost, setShippingCost] = useState(0);
  const [discount, setDiscount] = useState(0);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const setC = (k, v) => setCust((p) => ({ ...p, [k]: v }));
  const setA = (k, v) => setAddr((p) => ({ ...p, [k]: v }));

  const searchProducts = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/products`, {
        params: { search: q, limit: 12 },
        headers: { Authorization: `Bearer ${token}` },
      });
      setResults(res.data?.products || []);
    } catch {
      toast.error("Ürün araması başarısız");
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const addItem = (p) => {
    const price = Number(p.sale_price) > 0 ? Number(p.sale_price) : Number(p.price) || 0;
    setItems((prev) => {
      const exist = prev.find((i) => i.product_id === p.id && !i.variant_label);
      if (exist) {
        return prev.map((i) =>
          i === exist ? { ...i, quantity: i.quantity + 1 } : i
        );
      }
      return [
        ...prev,
        {
          product_id: p.id,
          name: p.name || "",
          barcode: p.barcode || "",
          price,
          quantity: 1,
          variant_label: "",
        },
      ];
    });
  };

  const updItem = (idx, k, v) =>
    setItems((prev) => prev.map((i, n) => (n === idx ? { ...i, [k]: v } : i)));
  const removeItem = (idx) => setItems((prev) => prev.filter((_, n) => n !== idx));

  const subtotal = items.reduce((s, i) => s + (Number(i.price) || 0) * (Number(i.quantity) || 0), 0);
  const total = Math.max(0, subtotal + (Number(shippingCost) || 0) - (Number(discount) || 0));

  const submit = async () => {
    if (items.length === 0) { toast.error("En az 1 ürün ekleyin"); return; }
    if (!cust.full_name.trim() || !cust.phone.trim()) { toast.error("Müşteri adı ve telefon zorunlu"); return; }
    setSubmitting(true);
    try {
      const token = localStorage.getItem("token");
      const payload = {
        items: items.map((i) => ({
          product_id: i.product_id,
          name: i.name,
          barcode: i.barcode,
          price: Number(i.price) || 0,
          quantity: Number(i.quantity) || 1,
          variant_label: i.variant_label || "",
        })),
        shipping_address: {
          full_name: cust.full_name.trim(),
          phone: cust.phone.trim(),
          email: cust.email.trim(),
          city: addr.city.trim(),
          district: addr.district.trim(),
          address: addr.address.trim(),
          postal_code: addr.postal_code.trim(),
        },
        subtotal,
        total,
        shipping_cost: Number(shippingCost) || 0,
        discount: Number(discount) || 0,
        payment_method: paymentMethod,
        payment_status: paymentStatus,
        note: note.trim(),
      };
      const res = await axios.post(`${API}/admin/orders/create-manual`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const on = res.data?.order?.order_number || "";
      toast.success(`Sipariş oluşturuldu${on ? `: ${on}` : ""}`);
      // formu sıfırla
      setItems([]); setResults([]); setQuery("");
      setCust({ full_name: "", phone: "", email: "" });
      setAddr({ city: "", district: "", address: "", postal_code: "" });
      setShippingCost(0); setDiscount(0); setNote("");
      setPaymentMethod("cash"); setPaymentStatus("paid");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sipariş oluşturulamadı");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full px-3 py-2 border rounded-lg text-sm";

  return (
    <div className="p-4 md:p-6 max-w-5xl">
      <div className="flex items-center gap-2 mb-1">
        <Phone className="w-5 h-5 text-indigo-600" />
        <h1 className="text-xl font-semibold">Telefonla Sipariş Oluştur</h1>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Telefon / mağaza satışlarını sipariş olarak girer. Sipariş no <b>MNL-…</b> formatında üretilir,
        stok otomatik düşülür.
      </p>

      <div className="grid md:grid-cols-2 gap-6">
        {/* SOL: Müşteri + Adres */}
        <div className="space-y-3">
          <h3 className="font-medium text-sm text-gray-700">Müşteri</h3>
          <input className={inputCls} placeholder="Ad Soyad *" value={cust.full_name} onChange={(e) => setC("full_name", e.target.value)} />
          <input className={inputCls} placeholder="Telefon *" value={cust.phone} onChange={(e) => setC("phone", e.target.value)} />
          <input className={inputCls} placeholder="E-posta (opsiyonel)" value={cust.email} onChange={(e) => setC("email", e.target.value)} />
          <h3 className="font-medium text-sm text-gray-700 pt-2">Teslimat Adresi</h3>
          <div className="grid grid-cols-2 gap-2">
            <input className={inputCls} placeholder="İl" value={addr.city} onChange={(e) => setA("city", e.target.value)} />
            <input className={inputCls} placeholder="İlçe" value={addr.district} onChange={(e) => setA("district", e.target.value)} />
          </div>
          <textarea className={inputCls} rows={2} placeholder="Açık adres" value={addr.address} onChange={(e) => setA("address", e.target.value)} />
          <input className={inputCls} placeholder="Posta kodu" value={addr.postal_code} onChange={(e) => setA("postal_code", e.target.value)} />
        </div>

        {/* SAĞ: Ödeme + Notlar + Toplam */}
        <div className="space-y-3">
          <h3 className="font-medium text-sm text-gray-700">Ödeme</h3>
          <div className="grid grid-cols-2 gap-2">
            <select className={inputCls} value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}>
              {PAYMENT_METHODS.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
            </select>
            <select className={inputCls} value={paymentStatus} onChange={(e) => setPaymentStatus(e.target.value)}>
              <option value="paid">Ödendi</option>
              <option value="pending">Ödeme Bekliyor</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-gray-500">Kargo ücreti
              <input type="number" className={inputCls} value={shippingCost} onChange={(e) => setShippingCost(e.target.value)} />
            </label>
            <label className="text-xs text-gray-500">İndirim
              <input type="number" className={inputCls} value={discount} onChange={(e) => setDiscount(e.target.value)} />
            </label>
          </div>
          <textarea className={inputCls} rows={2} placeholder="Sipariş notu (opsiyonel)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="border rounded-lg p-3 bg-gray-50 text-sm space-y-1">
            <div className="flex justify-between"><span className="text-gray-500">Ara Toplam</span><span>{money(subtotal)}</span></div>
            <div className="flex justify-between"><span className="text-gray-500">Kargo</span><span>{money(shippingCost)}</span></div>
            <div className="flex justify-between"><span className="text-gray-500">İndirim</span><span>- {money(discount)}</span></div>
            <div className="flex justify-between font-semibold text-base pt-1 border-t"><span>Genel Toplam</span><span>{money(total)}</span></div>
          </div>
        </div>
      </div>

      {/* ÜRÜN ARAMA + KALEMLER */}
      <div className="mt-6">
        <h3 className="font-medium text-sm text-gray-700 mb-2">Ürünler</h3>
        <div className="flex gap-2 mb-3">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm"
              placeholder="Ürün adı / barkod ara…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); searchProducts(); } }}
            />
          </div>
          <button onClick={searchProducts} className="px-3 py-2 text-sm bg-gray-800 text-white rounded-lg hover:bg-gray-900">
            {searching ? "Aranıyor…" : "Ara"}
          </button>
        </div>

        {results.length > 0 && (
          <div className="border rounded-lg divide-y mb-4 max-h-64 overflow-y-auto">
            {results.map((p) => {
              const price = Number(p.sale_price) > 0 ? Number(p.sale_price) : Number(p.price) || 0;
              return (
                <div key={p.id} className="flex items-center justify-between px-3 py-2 text-sm hover:bg-gray-50">
                  <div className="min-w-0">
                    <div className="truncate">{p.name}</div>
                    <div className="text-xs text-gray-400">{p.barcode || ""} · {money(price)} · Stok: {p.stock ?? "—"}</div>
                  </div>
                  <button onClick={() => addItem(p)} className="ml-2 inline-flex items-center gap-1 px-2 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700">
                    <Plus className="w-3.5 h-3.5" /> Ekle
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Ürün</th>
                <th className="text-right px-3 py-2 font-medium w-28">Fiyat</th>
                <th className="text-right px-3 py-2 font-medium w-20">Adet</th>
                <th className="text-right px-3 py-2 font-medium w-28">Tutar</th>
                <th className="px-3 py-2 w-10"></th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-400">Henüz ürün eklenmedi.</td></tr>
              )}
              {items.map((i, idx) => (
                <tr key={idx} className="border-t">
                  <td className="px-3 py-2">
                    <div>{i.name}</div>
                    {i.barcode && <div className="text-xs text-gray-400">{i.barcode}</div>}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <input type="number" value={i.price} onChange={(e) => updItem(idx, "price", e.target.value)} className="w-24 px-2 py-1 border rounded text-right" />
                  </td>
                  <td className="px-2 py-2 text-right">
                    <input type="number" min={1} value={i.quantity} onChange={(e) => updItem(idx, "quantity", Math.max(1, parseInt(e.target.value) || 1))} className="w-16 px-2 py-1 border rounded text-right" />
                  </td>
                  <td className="px-3 py-2 text-right">{money((Number(i.price) || 0) * (Number(i.quantity) || 0))}</td>
                  <td className="px-2 py-2 text-right">
                    <button onClick={() => removeItem(idx)} className="text-red-500 hover:text-red-700"><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-end gap-3">
        <span className="text-sm text-gray-500">Genel Toplam: <b>{money(total)}</b></span>
        <button
          onClick={submit}
          disabled={submitting}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
        >
          <ShoppingCart className="w-4 h-4" />
          {submitting ? "Oluşturuluyor…" : "Siparişi Oluştur"}
        </button>
      </div>
    </div>
  );
}
