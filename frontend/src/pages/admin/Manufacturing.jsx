import { useState, useEffect, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Factory, Plus, ChevronRight, Save, Trash2, Edit, X, Package, CheckCircle2,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../../components/ui/dialog";

// Renk/Beden seçim penceresi için hazır listeler (tıkla-seç; özel değer de eklenebilir)
const PRESET_COLORS = ["Siyah", "Beyaz", "Ekru", "Bej", "Taş", "Vizon", "Kahve", "Camel",
  "Lacivert", "Mavi", "Buz Mavi", "Kırmızı", "Bordo", "Yeşil", "Haki", "Mint",
  "Gri", "Antrasit", "Pembe", "Pudra", "Lila", "Mor", "Sarı", "Turuncu"];
const PRESET_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XS/S", "M/L", "STD",
  "34", "36", "38", "40", "42", "44", "46", "48"];

function _plus21(dateStr) {
  // Tahmini teslim = sipariş tarihi + 21 gün (kullanıcı isteği)
  try {
    const d = new Date(dateStr);
    d.setDate(d.getDate() + 21);
    return d.toISOString().substring(0, 10);
  } catch { return ""; }
}

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STAGE_COLORS = {
  siparis_dosyasi: "bg-slate-100 text-slate-700",
  kumas_okeyi: "bg-blue-100 text-blue-700",
  anlasma: "bg-slate-100 text-slate-700",
  numune_hazirlaniyor: "bg-amber-100 text-amber-700",
  numune_onaylandi: "bg-green-100 text-green-700",
  kumas_siparisi: "bg-blue-100 text-blue-700",
  kumas_teslim: "bg-indigo-100 text-indigo-700",
  aksesuar: "bg-cyan-100 text-cyan-700",
  kesim: "bg-orange-100 text-orange-700",
  dikim: "bg-rose-100 text-rose-700",
  utu_paketleme: "bg-pink-100 text-pink-700",
  kalite_kontrol: "bg-purple-100 text-purple-700",
  teslim_alindi: "bg-emerald-100 text-emerald-700",
  fatura_kesildi: "bg-gray-800 text-white",
};

export default function Manufacturing() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [stages, setStages] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState("");
  const [search, setSearch] = useState("");

  const [editing, setEditing] = useState(null);  // null | record
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState(initialForm());
  const [qtyDetail, setQtyDetail] = useState(() => new Set()); // Toplam Adet detay satırı açık kayıtlar
  const toggleQtyDetail = (id) => setQtyDetail(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  function initialForm() {
    const _today = new Date().toISOString().substring(0, 10);
    return {
      product_name: "",
      supplier_id: "",              // İmalatçı (zorunlu, kayıtlı listeden)
      order_no: "",                 // İmalat Sipariş No (boşsa otomatik IMLT-... atanır)
      order_flags: { new: true, rpt: false }, // Yeni Sipariş / RPT
      stock_code: "",               // ürün ilk burada doğar
      agreement_date: _today,       // Sipariş Tarihi
      expected_delivery_date: _plus21(_today), // otomatik +21 gün
      colors: [],                   // sipariş edilen renkler
      sizes: [],                    // bedenler (matris kolonları)
      size_distribution: {},        // {"Renk|Beden": adet}
      unit_price: 0,
      agreed_total: 0,
      payment_done: false,          // tek tik: ödeme yapıldı mı
      has_lining: false,            // astarlı ürün mü (Astar Okeyi kolonunu açar)
      color_approvals: {},          // {"Renk": {fabric: bool, lining: bool}}
      cutting_start_date: "",       // kesim başlangıç tarihi (kesime geçerken sorulur)
      actual_distribution: {},      // gerçekleşen kesim adedi {"Renk|Beden": n}
      waste_meters: 0,
      notes: "",
      current_stage: "siparis_dosyasi",
    };
  }

  // İmalatçı listesi (kayıtlı) + inline ekleme
  const [suppliers, setSuppliers] = useState([]);
  const [supplierSearch, setSupplierSearch] = useState("");
  const fetchSuppliers = async () => {
    try {
      const token = localStorage.getItem("token");
      const r = await axios.get(`${API}/manufacturing-suppliers`, { headers: { Authorization: `Bearer ${token}` } });
      setSuppliers(r.data.items || r.data || []);
    } catch { /* sessiz */ }
  };
  useEffect(() => { fetchSuppliers(); }, []);
  const addSupplierInline = async () => {
    const name = window.prompt("Yeni imalatçı adı:", supplierSearch.trim());
    if (!name || !name.trim()) return;
    const phone = window.prompt("Telefon (opsiyonel):") || "";
    try {
      const token = localStorage.getItem("token");
      const r = await axios.post(`${API}/manufacturing-suppliers`, { name: name.trim(), phone, type: "atolye" },
        { headers: { Authorization: `Bearer ${token}` } });
      const sup = r.data.supplier || r.data;
      toast.success("İmalatçı eklendi");
      await fetchSuppliers();
      if (sup?.id) setForm((f) => ({ ...f, supplier_id: sup.id }));
      setSupplierSearch("");
    } catch (e) { toast.error(e.response?.data?.detail || "İmalatçı eklenemedi"); }
  };

  useEffect(() => { fetchAll(); }, [stageFilter]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const hdr = { headers: { Authorization: `Bearer ${token}` } };
      let url = `${API}/manufacturing`;
      const params = [];
      if (stageFilter) params.push(`stage=${stageFilter}`);
      if (search) params.push(`search=${encodeURIComponent(search)}`);
      if (params.length) url += "?" + params.join("&");
      const [stagesRes, listRes] = await Promise.all([
        axios.get(`${API}/manufacturing/stages`, hdr),
        axios.get(url, hdr),
      ]);
      setStages(stagesRes.data.stages || []);
      setItems(listRes.data.items || []);
      setCounts(listRes.data.counts_by_stage || {});
    } catch (err) {
      toast.error("Veriler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setForm(initialForm());
    setModalOpen(true);
  };

  const openEdit = (item) => {
    setEditing(item);
    // Mevcut size_distribution'dan renk/beden eksenlerini çıkar ("Renk|Beden" veya çıplak beden)
    const _dist = item.size_distribution || {};
    const _colors = [...new Set(Object.keys(_dist).map((k) => (k.includes("|") ? k.split("|")[0] : "")).filter(Boolean))];
    const _sizes = [...new Set(Object.keys(_dist).map((k) => (k.includes("|") ? k.split("|")[1] : k)))];
    setForm({
      product_name: item.product_name || "",
      supplier_id: item.supplier_id || "",
      order_no: item.order_no || item.code || "",
      order_flags: item.order_flags || { new: false, rpt: false },
      stock_code: item.stock_code || "",
      colors: item.colors?.length ? item.colors : _colors,
      sizes: _sizes,
      agreement_date: (item.agreement_date || "").substring(0, 10),
      expected_delivery_date: (item.expected_delivery_date || "").substring(0, 10),
      size_distribution: _dist,
      unit_price: item.unit_price || 0,
      agreed_total: item.agreed_total || 0,
      payment_done: !!item.payment_done,
      has_lining: !!item.has_lining,
      color_approvals: item.color_approvals || {},
      cutting_start_date: item.cutting_start_date || "",
      actual_distribution: item.actual_distribution || {},
      waste_meters: item.waste_meters || 0,
      notes: item.notes || "",
      current_stage: item.current_stage || "siparis_dosyasi",
    });
    setModalOpen(true);
  };

  const saveRecord = async (e) => {
    e?.preventDefault?.();
    if (!form.product_name.trim()) { toast.error("Ürün adı gerekli"); return; }
    if (!form.supplier_id) { toast.error("İmalatçı seçimi zorunlu — listeden seçin veya ekleyin"); return; }
    if (!String(form.order_no || "").trim()) { toast.error("İmalat Sipariş No zorunlu"); return; }
    if (!form.agreement_date) { toast.error("Sipariş Tarihi zorunlu"); return; }
    setSaving(true);
    try {
      const token = localStorage.getItem("token");
      const hdr = { headers: { Authorization: `Bearer ${token}` } };
      const payload = { ...form };
      // Clean empty sizes
      payload.size_distribution = Object.fromEntries(
        Object.entries(payload.size_distribution || {}).filter(([, v]) => Number(v) > 0)
          .map(([k, v]) => [k, Number(v)])
      );
      payload.unit_price = Number(payload.unit_price || 0);
      // Gerçekleşen kesim adetleri: yalnız sayı girilen hücreler kaydedilir
      payload.actual_distribution = Object.fromEntries(
        Object.entries(payload.actual_distribution || {})
          .filter(([, v]) => v !== "" && v !== null && v !== undefined)
          .map(([k, v]) => [k, Number(v)])
      );
      // Toplam anlaşma bedeli OTOMATİK: genel toplam adet × birim fiyat (kullanıcı isteği)
      const _qty = Object.values(payload.size_distribution).reduce((a, b) => a + Number(b || 0), 0);
      payload.agreed_total = Number((payload.unit_price * _qty).toFixed(2));
      payload.waste_meters = 0;
      if (editing) {
        await axios.put(`${API}/manufacturing/${editing.id}`, payload, hdr);
        toast.success("Kayıt güncellendi");
      } else {
        await axios.post(`${API}/manufacturing`, payload, hdr);
        toast.success("İmalat kaydı oluşturuldu");
      }
      setModalOpen(false);
      fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  // Depo teslimatındaki kaydı ÜRÜN KARTINA taşı: Ürünler sayfasındaki "Yeni Ürün" formu
  // üretim bilgileriyle (ad, stok kodu, sezon, alış fiyatı, renk×beden=stok) önden dolu açılır.
  const openProductFromMfg = (item) => {
    const dist = Object.keys(item.actual_distribution || {}).length
      ? item.actual_distribution : (item.size_distribution || {});
    const variants = Object.entries(dist)
      .filter(([, q]) => Number(q) > 0)
      .map(([k, q]) => {
        const [color, size] = k.includes("|") ? k.split("|") : ["", k];
        return { size, color, stock: Number(q) };
      });
    const sc = (item.stock_code || "").toUpperCase();
    const season = sc.startsWith("FCFW") ? "Kış" : sc.startsWith("FCSS") ? "Yaz" : "";
    sessionStorage.setItem("mfg_product_prefill", JSON.stringify({
      mfg_record_id: item.id,
      name: item.product_name || "",
      stock_code: item.stock_code || "",
      season,
      purchase_price: Number(item.unit_price || 0),
      manufacturer: item.partner_name || "FACETTE",
      variants,
    }));
    navigate("/admin/urunler?newFromMfg=1");
  };

  // Her aşama geçişinde kullanıcı o aşamanın TARİHİNİ girer (kullanıcı isteği)
  const _STAGE_DATE_LABELS = {
    kumas_okeyi: "Kumaş okeyi tarihi",
    kesim: "Kesim başlangıç tarihi",
    dikim: "Dikiş başlangıç tarihi",
    kalite_kontrol: "Kalite kontrol tarihi",
    teslim_alindi: "Depo teslim tarihi",
  };
  const advanceStage = async (item, newStage) => {
    let stageDate = "";
    if (_STAGE_DATE_LABELS[newStage]) {
      stageDate = window.prompt(`${_STAGE_DATE_LABELS[newStage]} (YYYY-AA-GG):`, new Date().toISOString().substring(0, 10));
      if (stageDate === null) return;
      stageDate = (stageDate || "").trim();
    }
    const note = window.prompt(`"${stageLabel(newStage)}" aşamasına geçiyorsunuz. Not (opsiyonel):`);
    if (note === null) return;
    try {
      const token = localStorage.getItem("token");
      await axios.post(`${API}/manufacturing/${item.id}/advance`,
        { stage: newStage, note, ...(stageDate ? { stage_date: stageDate } : {}) },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Aşama güncellendi");
      if (newStage === "teslim_alindi") toast.success("Stok otomatik güncellendi");
      fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Aşama değiştirilemedi");
    }
  };

  const deleteRecord = async (item) => {
    if (!await window.appConfirm(`"${item.code}" kaydını silmek istiyor musunuz?`)) return;
    try {
      const token = localStorage.getItem("token");
      await axios.delete(`${API}/manufacturing/${item.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Silindi");
      fetchAll();
    } catch (err) {
      toast.error("Silinemedi");
    }
  };

  const stageLabel = (key) => stages.find(s => s.key === key)?.label || key;
  const nextStage = (current) => {
    const idx = stages.findIndex(s => s.key === current);
    return idx >= 0 && idx < stages.length - 1 ? stages[idx + 1].key : null;
  };

  // ── Renk × Beden kombinasyon matrisi ──────────────────────────────────
  const matrixKey = (color, size) => (color ? `${color}|${size}` : size);
  const cellVal = (color, size) => Number(form.size_distribution?.[matrixKey(color, size)] || 0);
  const setCell = (color, size, val) => setForm(f => ({
    ...f,
    size_distribution: { ...f.size_distribution, [matrixKey(color, size)]: Number(val || 0) },
  }));
  // Renk/Beden seçim penceresi (prompt yerine tablo — kullanıcı isteği)
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickColors, setPickColors] = useState([]);
  const [pickSizes, setPickSizes] = useState([]);
  const [customColor, setCustomColor] = useState("");
  const [customSize, setCustomSize] = useState("");
  const openPicker = () => {
    setPickColors([...form.colors]);
    setPickSizes([...form.sizes]);
    setCustomColor(""); setCustomSize("");
    setPickerOpen(true);
  };
  const togglePick = (list, setList, val) =>
    setList(list.includes(val) ? list.filter(x => x !== val) : [...list, val]);
  const applyPicker = () => {
    setForm(f => {
      // Seçimden çıkarılan renk/bedenlerin matris hücreleri temizlenir
      const dist = Object.fromEntries(Object.entries(f.size_distribution || {}).filter(([k]) => {
        const c = k.includes("|") ? k.split("|")[0] : "";
        const s = k.includes("|") ? k.split("|")[1] : k;
        return (c === "" ? pickColors.length === 0 : pickColors.includes(c)) && pickSizes.includes(s);
      }));
      return { ...f, colors: pickColors, sizes: pickSizes, size_distribution: dist };
    });
    setPickerOpen(false);
  };
  const removeColor = (c) => setForm(f => ({
    ...f, colors: f.colors.filter(x => x !== c),
    size_distribution: Object.fromEntries(Object.entries(f.size_distribution).filter(([k]) => !k.startsWith(c + "|"))),
  }));
  const removeSize = (s) => setForm(f => ({
    ...f, sizes: f.sizes.filter(x => x !== s),
    size_distribution: Object.fromEntries(Object.entries(f.size_distribution).filter(([k]) => (k.includes("|") ? k.split("|")[1] : k) !== s)),
  }));
  // Onay değişiminde zaman damgası da tutulur (ödeme→okey süresi ölçümü için)
  const _stampApproval = (cur, kind) => {
    const on = !cur[kind];
    return { ...cur, [kind]: on, [`${kind}_at`]: on ? new Date().toISOString() : null };
  };

  // Listeden tek tıkla renk onayı değiştir (modal açmadan) — iyimser güncelle + sunucuya yaz
  const toggleRowApproval = async (item, color, kind) => {
    const key = color || "_tek";
    const cur = item.color_approvals?.[key] || {};
    const next = { ...(item.color_approvals || {}), [key]: _stampApproval(cur, kind) };
    setItems(prev => prev.map(x => x.id === item.id ? { ...x, color_approvals: next } : x));
    try {
      const token = localStorage.getItem("token");
      await axios.put(`${API}/manufacturing/${item.id}`, { color_approvals: next },
        { headers: { Authorization: `Bearer ${token}` } });
    } catch { toast.error("Onay kaydedilemedi"); fetchAll(); }
  };

  // Renk bazlı onaylar: kumaş okeyi her renkte; astar okeyi yalnız astarlı üründe
  const approvalOf = (color, kind) => !!(form.color_approvals?.[color || "_tek"]?.[kind]);
  const toggleApproval = (color, kind) => setForm(f => {
    const key = color || "_tek";
    const cur = f.color_approvals?.[key] || {};
    return { ...f, color_approvals: { ...(f.color_approvals || {}), [key]: _stampApproval(cur, kind) } };
  });

  // Gerçekleşen (kesilen) adet — kesim ve sonraki aşamalarda girilir; fire/fazla % gösterilir
  const actualVal = (color, size) => form.actual_distribution?.[matrixKey(color, size)];
  const setActual = (color, size, val) => setForm(f => ({
    ...f,
    actual_distribution: { ...(f.actual_distribution || {}), [matrixKey(color, size)]: val === "" ? "" : Number(val || 0) },
  }));
  const showActuals = !!editing && ["kesim", "dikim", "kalite_kontrol", "teslim_alindi"].includes(form.current_stage);

  const rowTotal = (color) => form.sizes.reduce((s, sz) => s + cellVal(color, sz), 0);
  const grandTotal = (form.colors.length ? form.colors : [""]).reduce((s, c) => s + rowTotal(c), 0);

  return (
    <div className="p-6 max-w-7xl mx-auto" data-testid="manufacturing-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Factory className="text-rose-600" /> İmalat Takip
          </h1>
          <p className="text-sm text-gray-500 mt-1">Üretim sürecinin anlaşmadan teslime kadar tüm aşamalarını takip edin.</p>
        </div>
        <button onClick={openCreate} data-testid="create-mfg-btn"
          className="flex items-center gap-2 px-4 py-2 bg-rose-600 text-white rounded-lg text-sm font-bold hover:bg-rose-700">
          <Plus size={16} /> Yeni İmalat Kaydı
        </button>
      </div>

      {/* Aşamalar — kutucuk yerine TIMELINE (kullanıcı isteği); tıklayınca filtreler */}
      <div className="bg-white rounded-xl shadow-sm p-4 mb-6 overflow-x-auto">
        <div className="flex items-start min-w-[640px]">
          {[{ key: "", label: "Tümü", count: Object.values(counts).reduce((a, b) => a + b, 0) },
            ...stages.map(s => ({ key: s.key, label: s.label, count: counts[s.key] || 0 }))].map((n, i) => {
            const active = stageFilter === n.key;
            return (
              <div key={n.key || "all"} className="flex items-start flex-1 min-w-0">
                {i > 0 && <div className="flex-1 h-0.5 bg-gray-200 mt-[19px] min-w-[16px]" />}
                <button
                  onClick={() => setStageFilter(n.key)}
                  data-testid={n.key ? `stage-filter-${n.key}` : "stage-filter-all"}
                  className="flex flex-col items-center gap-1 shrink-0 px-1 group"
                >
                  <span className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold border-2 transition
                    ${active ? "bg-rose-600 text-white border-rose-600 shadow" : "bg-white border-gray-300 text-gray-700 group-hover:border-rose-400"}`}>
                    {n.count}
                  </span>
                  <span className={`text-[11px] leading-tight text-center max-w-[86px] ${active ? "font-bold text-rose-700" : "text-gray-500"}`}>
                    {n.label}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* List */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Kayıt bulunamadı. Sağ üstten yeni kayıt ekleyebilirsiniz.</div>
        ) : (
          <table className="w-full">
            <thead className="border-b bg-gray-50">
              <tr>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase w-10">#</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">İmalatçı</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">İmalat Sipariş No</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Ürün</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase">Sipariş Edilen Toplam Adet</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Sipariş Tarihi</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Kumaş Okeyi</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase" title="Gerçekleşen (kesilen) toplam adet">Toplam Adet</th>
                <th className="px-3 py-3"></th>
                <th className="text-center px-3 py-3 text-xs font-bold text-gray-500 uppercase">Ürün Aç</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                // Kalan gün: tahmini teslim (sipariş tarihi + 21 gün kuralı) − bugün
                const _exp = item.expected_delivery_date || (item.agreement_date ? _plus21(item.agreement_date) : "");
                const _days = _exp ? Math.ceil((new Date(String(_exp).substring(0, 10)) - new Date(new Date().toISOString().substring(0, 10))) / 864e5) : null;
                const _delivered = item.current_stage === "teslim_alindi";
                const _rowColors = (item.colors?.length ? item.colors
                  : [...new Set(Object.keys(item.size_distribution || {}).map(k => k.includes("|") ? k.split("|")[0] : ""))].filter(Boolean));
                // Okey tamamlanma (hatırlatıcı nokta için) — zaman damgaları çip tooltip'inde
                const _keys = (_rowColors.length ? _rowColors : [""]).map(c => c || "_tek");
                const _ap = item.color_approvals || {};
                const _okeysDone = _keys.every(k => _ap[k]?.fabric) && (!item.has_lining || _keys.every(k => _ap[k]?.lining));
                // Kırmızı yanıp sönen hatırlatıcı: kumaş okeyinde okeyler tamamsa → kesime geç;
                // kesim ve sonraki ara aşamalarda her zaman (ilerletme dış haberle yapılır)
                const _showDot = (_okeysDone && item.current_stage === "kumas_okeyi")
                  || ["kesim", "dikim", "kalite_kontrol"].includes(item.current_stage);
                return (
                <Fragment key={item.id}>
                <tr className="border-b hover:bg-gray-50" data-testid={`mfg-row-${item.code}`}>
                  <td className="px-3 py-3 text-sm font-bold text-gray-400 tabular-nums">{idx + 1}</td>
                  <td className="px-3 py-3 text-sm font-semibold">{item.partner_name || "—"}</td>
                  <td className="px-3 py-3 font-mono text-xs text-rose-600 font-bold">{item.order_no || item.code}</td>
                  <td className="px-3 py-3">
                    <p className="font-medium">{item.product_name}</p>
                    <p className="flex items-center gap-1.5 mt-0.5">
                      {/* Aşama rozeti kaldırıldı — aşama zaten üstteki timeline'da görünüyor */}
                      {item.payment_done
                        ? <span className="text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1 py-0.5">ÖDENDİ</span>
                        : <span className="text-[9px] font-bold text-red-600 bg-red-50 border border-red-200 rounded px-1 py-0.5">ÖDENMEDİ</span>}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-sm font-bold text-right tabular-nums">{item.total_units}</td>
                  <td className="px-3 py-3 text-xs">
                    <p className="text-gray-700">{item.agreement_date ? new Date(item.agreement_date).toLocaleDateString('tr-TR') : '—'}</p>
                    {(() => {
                      // Girilen aşama tarihleri (eski kayıtlarda yalnız kesim tarihi olabilir)
                      const sd = { ...(item.cutting_start_date && !(item.stage_dates || {}).kesim ? { kesim: item.cutting_start_date } : {}), ...(item.stage_dates || {}) };
                      return Object.entries(sd).map(([k, v]) => (
                        <p key={k} className="text-[9px] text-orange-600 whitespace-nowrap">
                          {stageLabel(k)}: {new Date(v).toLocaleDateString('tr-TR')}
                        </p>
                      ));
                    })()}
                    {_delivered ? (
                      <p className="text-[10px] font-bold text-emerald-600">Teslim alındı ✓</p>
                    ) : _days == null ? null : _days < 0 ? (
                      <p className="text-[11px] font-bold text-red-700">{Math.abs(_days)} gün GECİKTİ!</p>
                    ) : (
                      <p className="text-[11px] font-bold text-red-600">{_days} gün kaldı</p>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {/* Ödeme bekliyorsa uyarı; ödendiyse tekrar yazılmaz (ürün sütununda zaten var) */}
                    {!item.payment_done && (
                      <p className="text-[10px] font-bold mb-1 text-amber-600">ÖDEME BEKLİYOR</p>
                    )}
                    {/* Renk bazlı kumaş okeyi — etiket sabit kolonda, çipler kendi kolonunda sarar (simetrik) */}
                    <div className="flex items-start gap-1">
                      <span className="text-[9px] text-emerald-600 font-bold uppercase w-11 shrink-0 mt-1">Kumaş:</span>
                      <div className="flex flex-wrap gap-1 max-w-[190px]">
                      {(_rowColors.length ? _rowColors : [""]).map(c => {
                        const ok = !!(item.color_approvals?.[c || "_tek"]?.fabric);
                        const at = item.color_approvals?.[c || "_tek"]?.fabric_at;
                        return (
                          <button key={c || "_tek"} type="button" onClick={() => toggleRowApproval(item, c, "fabric")}
                            title={`${c || "Tek renk"} — kumaş ${ok ? `onaylı${at ? " (" + new Date(at).toLocaleDateString("tr-TR") + ")" : ""}` : "onaysız (onaylamak için tıkla)"}`}
                            className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold border transition ${ok ? "bg-emerald-600 text-white border-emerald-600" : "bg-white text-gray-500 border-gray-300 hover:border-emerald-400"}`}>
                            {c || "Tek"} {ok ? "✓" : ""}
                          </button>
                        );
                      })}
                      </div>
                    </div>
                    {item.has_lining && (
                      <div className="flex items-start gap-1 mt-1">
                        <span className="text-[9px] text-indigo-500 font-bold uppercase w-11 shrink-0 mt-1">Astar:</span>
                        <div className="flex flex-wrap gap-1 max-w-[190px]">
                        {(_rowColors.length ? _rowColors : [""]).map(c => {
                          const ok = !!(item.color_approvals?.[c || "_tek"]?.lining);
                          const at = item.color_approvals?.[c || "_tek"]?.lining_at;
                          return (
                            <button key={c || "_tek"} type="button" onClick={() => toggleRowApproval(item, c, "lining")}
                              title={`${c || "Tek renk"} — astar ${ok ? `onaylı${at ? " (" + new Date(at).toLocaleDateString("tr-TR") + ")" : ""}` : "onaysız"}`}
                              className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold border transition ${ok ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-gray-500 border-gray-300 hover:border-indigo-400"}`}>
                              {c || "Tek"} {ok ? "✓" : ""}
                            </button>
                          );
                        })}
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right cursor-pointer hover:bg-gray-100 rounded"
                    onClick={() => toggleQtyDetail(item.id)}
                    title="Detay için tıklayın — renk|beden bazında sipariş → kesilen">
                    {(() => {
                      const _actTot = Object.values(item.actual_distribution || {}).reduce((a, b) => a + Number(b || 0), 0);
                      return (
                        <div>
                          <p className="text-[9px] text-gray-400 whitespace-nowrap">Sipariş: <b className="text-gray-600">{item.total_units || 0}</b></p>
                          {_actTot > 0 ? (
                            <p className={`text-sm font-bold tabular-nums whitespace-nowrap ${_actTot < (item.total_units || 0) ? "text-red-600" : _actTot > (item.total_units || 0) ? "text-emerald-600" : "text-gray-800"}`}>
                              Kesilen: {_actTot}
                            </p>
                          ) : (
                            <p className="text-[10px] text-gray-300">Kesilen: —</p>
                          )}
                          <p className="text-[9px] text-blue-500">{qtyDetail.has(item.id) ? "detayı gizle ▴" : "detay ▾"}</p>
                        </div>
                      );
                    })()}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {/* Kırmızı yanıp sönen hatırlatıcı: bir sonraki aşamaya ilerletme gerekiyor */}
                    {_showDot && (
                      <span className="relative inline-flex h-3 w-3 mr-2 align-middle"
                        title={item.current_stage === "kumas_okeyi"
                          ? "Okeyler tamamlandı — Kesim Başlangıcı'na ilerletin!"
                          : "Bu aşama tamamlandıysa bir sonrakine ilerletin"}>
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-red-600"></span>
                      </span>
                    )}
                    {nextStage(item.current_stage) && (
                      <button
                        onClick={() => advanceStage(item, nextStage(item.current_stage))}
                        data-testid={`advance-${item.id}`}
                        className="px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 rounded font-medium"
                      >
                        <ChevronRight size={13} className="inline" /> İlerlet
                      </button>
                    )}
                    <button onClick={() => openEdit(item)} className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded">
                      <Edit size={13} className="inline" />
                    </button>
                    <button onClick={() => deleteRecord(item)} className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded">
                      <Trash2 size={13} className="inline" />
                    </button>
                  </td>
                  <td className="px-3 py-3 text-center">
                    {["teslim_alindi", "fatura_kesildi"].includes(item.current_stage) ? (
                      item.product_created ? (
                        <span className="text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5">ürün açıldı ✓</span>
                      ) : (
                        <button onClick={() => openProductFromMfg(item)}
                          data-testid={`open-product-${item.id}`}
                          title="Üretim bilgileriyle (ad, stok kodu, sezon, alış fiyatı, renk×beden stokları) Yeni Ürün formunu açar"
                          className="px-2.5 py-1.5 text-xs bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg font-bold whitespace-nowrap">
                          🛍 Ürün Aç
                        </button>
                      )
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>
                </tr>
                {qtyDetail.has(item.id) && (
                  <tr className="bg-blue-50/40 border-b">
                    <td colSpan={10} className="px-6 py-3">
                      <div className="text-[11px] font-bold text-gray-600 uppercase mb-1.5">Adet Detayı — Sipariş → Kesilen</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(item.size_distribution || {}).map(([k, q]) => {
                          const act = (item.actual_distribution || {})[k];
                          const diff = act != null && q > 0 ? ((Number(act) - q) / q) * 100 : null;
                          return (
                            <span key={k} className="px-2.5 py-1 bg-white border rounded-lg text-xs whitespace-nowrap">
                              <b>{k}</b>: {q} → {act ?? "—"}
                              {diff != null && Math.round(diff) !== 0 && (
                                <b className={diff < 0 ? "text-red-600 ml-1" : "text-emerald-600 ml-1"}>
                                  {diff > 0 ? "+" : ""}{diff.toFixed(1).replace(".0", "")}%
                                </b>
                              )}
                            </span>
                          );
                        })}
                        {Object.keys(item.size_distribution || {}).length === 0 && <span className="text-xs text-gray-400">Dağılım girilmemiş.</span>}
                      </div>
                    </td>
                  </tr>
                )}
                </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Create / Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="mfg-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Factory size={18} className="text-rose-600" />
              {editing ? `İmalat Kaydı: ${editing.code}` : "Yeni İmalat Kaydı"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); saveRecord(); }} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Ürün Adı / Model <span className="text-red-500">*</span></label>
                <input value={form.product_name} onChange={e => setForm({ ...form, product_name: e.target.value })} required
                  data-testid="mfg-product-name" className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">İmalatçı <span className="text-red-500">*</span></label>
                <select value={form.supplier_id} onChange={e => setForm({ ...form, supplier_id: e.target.value })}
                  required data-testid="mfg-supplier-select" className="w-full border px-3 py-2 rounded text-sm">
                  <option value="">— İmalatçı seçin —</option>
                  {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}{s.phone ? ` (${s.phone})` : ""}</option>)}
                </select>
                <button type="button" onClick={addSupplierInline}
                  className="mt-1 text-xs text-rose-600 hover:bg-rose-50 px-2 py-1 rounded" data-testid="mfg-add-supplier">
                  <Plus size={12} className="inline" /> İmalatçı Ekle
                </button>
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">İmalat Sipariş No <span className="text-red-500">*</span></label>
                <input value={form.order_no} onChange={e => setForm({ ...form, order_no: e.target.value })}
                  required placeholder="Örn: IMLT-2026-0012" className="w-full border px-3 py-2 rounded text-sm" />
                <div className="flex items-center gap-4 mt-2">
                  <label className="inline-flex items-center gap-1.5 text-xs font-semibold">
                    <input type="checkbox" checked={!!form.order_flags?.new}
                      onChange={e => setForm({ ...form, order_flags: { ...form.order_flags, new: e.target.checked } })}
                      className="accent-rose-600" data-testid="mfg-flag-new" /> Yeni Sipariş
                  </label>
                  <label className="inline-flex items-center gap-1.5 text-xs font-semibold">
                    <input type="checkbox" checked={!!form.order_flags?.rpt}
                      onChange={e => setForm({ ...form, order_flags: { ...form.order_flags, rpt: e.target.checked } })}
                      className="accent-rose-600" data-testid="mfg-flag-rpt" /> RPT
                  </label>
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Sipariş Tarihi <span className="text-red-500">*</span></label>
                <input type="date" value={form.agreement_date}
                  onChange={e => setForm({ ...form, agreement_date: e.target.value, expected_delivery_date: _plus21(e.target.value) })}
                  className="w-full border px-3 py-2 rounded text-sm" data-testid="mfg-order-date" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Tahmini Teslim Tarihi <span className="text-gray-400 font-normal">(sipariş +21 gün otomatik)</span></label>
                <input type="date" value={form.expected_delivery_date} onChange={e => setForm({ ...form, expected_delivery_date: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Stok Kodu <span className="text-gray-400 font-normal">(FCFW/FCSS seç — otomatik üretilir)</span></label>
                <div className="flex gap-2">
                  <input value={form.stock_code} readOnly placeholder="Üret butonuyla oluşur"
                    className="flex-1 border px-3 py-2 rounded text-sm font-mono bg-gray-50" data-testid="mfg-stock-code" />
                  {/* Ürün kartındaki kuralla birebir aynı: FCFW/FCSS + 6 haneli numara */}
                  <button type="button" onClick={() => setForm({ ...form, stock_code: `FCFW${Math.floor(100000 + Math.random() * 900000)}` })}
                    className="px-3 py-2 bg-orange-100 text-orange-800 rounded-lg text-[10px] font-black tracking-widest uppercase whitespace-nowrap hover:bg-orange-200" data-testid="mfg-gen-fcfw">
                    Üret (FCFW)
                  </button>
                  <button type="button" onClick={() => setForm({ ...form, stock_code: `FCSS${Math.floor(100000 + Math.random() * 900000)}` })}
                    className="px-3 py-2 bg-blue-100 text-blue-800 rounded-lg text-[10px] font-black tracking-widest uppercase whitespace-nowrap hover:bg-blue-200" data-testid="mfg-gen-fcss">
                    Üret (FCSS)
                  </button>
                </div>
              </div>
            </div>

            {/* Renk × Beden kombinasyon matrisi (kullanıcı isteği): satır=renk, kolon=beden,
                hücre=adet; satır sonunda toplam, tablonun altında sağda GENEL TOPLAM. */}
            <div>
              <label className="block text-xs font-bold text-gray-600 mb-2 flex items-center gap-2 justify-between">
                <span className="flex items-center gap-2"><Package size={12} /> Sipariş Edilen Renkler × Bedenler</span>
                <span className="flex items-center gap-2">
                  {/* Astar ön seçeneği: astarlı üründe her renk için Astar Okeyi kolonu açılır */}
                  <button type="button" onClick={() => setForm(f => ({ ...f, has_lining: !f.has_lining }))}
                    data-testid="mfg-has-lining"
                    className={`text-xs px-3 py-1.5 rounded font-semibold border transition ${form.has_lining ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-gray-500 border-gray-300 hover:border-indigo-400"}`}>
                    {form.has_lining ? "Astarlı Ürün ✓" : "Astarlı Ürün mü?"}
                  </button>
                  <button type="button" onClick={openPicker}
                    className="text-xs bg-rose-600 text-white hover:bg-rose-700 px-3 py-1.5 rounded font-semibold" data-testid="mfg-open-picker">
                    <Plus size={12} className="inline" /> Renk / Beden Seç
                  </button>
                </span>
              </label>
              {showActuals && form.sizes.length > 0 && (
                <p className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-1.5">
                  Kesim aşamasındasınız: her hücrede üstteki kutu <b>sipariş adedi</b>, alttaki kesikli kutu <b>gerçekleşen (kesilen) adet</b>tir.
                  Fark varsa yanında <b className="text-red-600">−% fire</b> / <b className="text-emerald-600">+% fazla</b> gösterilir.
                </p>
              )}
              {form.sizes.length === 0 ? (
                <div className="bg-gray-50 border-2 border-dashed rounded-lg p-4 text-center text-xs text-gray-400">
                  "Renk / Beden Seç" ile hazır tablodan seçim yapın — kombinasyon tablosu burada oluşur.
                </div>
              ) : (
                <div className="overflow-x-auto border border-rose-200 rounded-lg">
                  <table className="w-full text-sm" data-testid="mfg-matrix">
                    <thead className="bg-rose-50 text-xs text-rose-700">
                      <tr>
                        <th className="text-left px-3 py-2">Renk \ Beden</th>
                        {form.sizes.map(s => (
                          <th key={s} className="px-2 py-2 text-center">
                            {s}
                            <button type="button" onClick={() => removeSize(s)} className="ml-1 text-red-400 hover:text-red-600" title="Bedeni kaldır">×</button>
                          </th>
                        ))}
                        <th className="px-3 py-2 text-right">Sipariş Adedi</th>
                        <th className="px-2 py-2 text-center">Kumaş Okeyi</th>
                        {form.has_lining && <th className="px-2 py-2 text-center">Astar Okeyi</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {(form.colors.length ? form.colors : [""]).map(c => (
                        <tr key={c || "_tek"} className="border-t">
                          <td className="px-3 py-1.5 font-semibold whitespace-nowrap">
                            {c || "(Tek renk)"}
                            {c && <button type="button" onClick={() => removeColor(c)} className="ml-1.5 text-red-400 hover:text-red-600" title="Rengi kaldır">×</button>}
                          </td>
                          {form.sizes.map(s => {
                            const _ord = cellVal(c, s);
                            const _act = actualVal(c, s);
                            const _hasAct = showActuals && _act !== undefined && _act !== "" && _ord > 0;
                            const _pct = _hasAct ? ((Number(_act) - _ord) / _ord) * 100 : null;
                            return (
                            <td key={s} className="px-1.5 py-1.5 text-center align-top">
                              <input type="number" min={0} value={_ord || ""}
                                onChange={e => setCell(c, s, e.target.value)}
                                className="w-16 border px-1.5 py-1 rounded text-sm text-center" placeholder="0" />
                              {showActuals && (
                                <div className="mt-0.5">
                                  <input type="number" min={0} value={_act ?? ""}
                                    onChange={e => setActual(c, s, e.target.value)}
                                    title="Gerçekleşen (kesilen) adet"
                                    className="w-16 border border-dashed border-amber-300 bg-amber-50/40 px-1.5 py-0.5 rounded text-xs text-center" placeholder="kesilen" />
                                  {_pct != null && Math.round(_pct) !== 0 && (
                                    <p className={`text-[9px] font-bold mt-0.5 ${_pct < 0 ? "text-red-600" : "text-emerald-600"}`}
                                      title={_pct < 0 ? "Fire: sipariş edilenden az kesildi" : "Fazla: sipariş edilenden çok kesildi"}>
                                      {_pct > 0 ? "+" : ""}{_pct.toFixed(1).replace(".0", "")}%
                                    </p>
                                  )}
                                  {_pct != null && Math.round(_pct) === 0 && (
                                    <p className="text-[9px] text-gray-400 mt-0.5">tam</p>
                                  )}
                                </div>
                              )}
                            </td>
                            );
                          })}
                          <td className="px-3 py-1.5 text-right font-bold tabular-nums">{rowTotal(c)}</td>
                          <td className="px-2 py-1.5 text-center">
                            <button type="button" onClick={() => toggleApproval(c, "fabric")}
                              data-testid={`fabric-ok-${c || "tek"}`}
                              title="Bu rengin kumaşı onaylandı mı?"
                              className={`w-7 h-7 rounded border-2 text-sm font-bold transition ${approvalOf(c, "fabric") ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-gray-300 hover:border-emerald-400 text-transparent"}`}>
                              ✓
                            </button>
                          </td>
                          {form.has_lining && (
                            <td className="px-2 py-1.5 text-center">
                              <button type="button" onClick={() => toggleApproval(c, "lining")}
                                data-testid={`lining-ok-${c || "tek"}`}
                                title="Bu rengin astarı onaylandı mı?"
                                className={`w-7 h-7 rounded border-2 text-sm font-bold transition ${approvalOf(c, "lining") ? "bg-indigo-600 text-white border-indigo-600" : "bg-white border-gray-300 hover:border-indigo-400 text-transparent"}`}>
                                ✓
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="text-sm text-gray-700 mt-1.5 text-right">
                TOPLAM SİPARİŞ ADEDİ: <b className="text-rose-700" data-testid="mfg-grand-total">{grandTotal}</b> adet
              </p>
            </div>

            {/* Renk/Beden seçim penceresi — hazır tablodan tıkla-seç + özel değer */}
            {pickerOpen && (
              <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={() => setPickerOpen(false)}>
                <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-5" onClick={e => e.stopPropagation()} data-testid="mfg-picker">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-bold text-sm uppercase tracking-wider">Renk & Beden Seçimi</h3>
                    <button type="button" onClick={() => setPickerOpen(false)} className="text-gray-400 hover:text-black text-lg leading-none">×</button>
                  </div>
                  <p className="text-xs font-bold text-gray-600 mb-2">Renkler <span className="font-normal text-gray-400">({pickColors.length} seçili)</span></p>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {[...new Set([...PRESET_COLORS, ...pickColors])].map(c => (
                      <button key={c} type="button" onClick={() => togglePick(pickColors, setPickColors, c)}
                        className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${pickColors.includes(c) ? "bg-rose-600 text-white border-rose-600" : "bg-white text-gray-700 border-gray-300 hover:border-rose-400"}`}>
                        {c}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2 mb-5">
                    <input value={customColor} onChange={e => setCustomColor(e.target.value)} placeholder="Özel renk yaz..."
                      className="border rounded px-3 py-1.5 text-xs flex-1"
                      onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); if (customColor.trim()) { togglePick(pickColors, setPickColors, customColor.trim()); setCustomColor(""); } } }} />
                    <button type="button" onClick={() => { if (customColor.trim()) { togglePick(pickColors, setPickColors, customColor.trim()); setCustomColor(""); } }}
                      className="text-xs border rounded px-3 hover:bg-gray-50">Ekle</button>
                  </div>
                  <p className="text-xs font-bold text-gray-600 mb-2">Bedenler <span className="font-normal text-gray-400">({pickSizes.length} seçili)</span></p>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {[...new Set([...PRESET_SIZES, ...pickSizes])].map(s => (
                      <button key={s} type="button" onClick={() => togglePick(pickSizes, setPickSizes, s)}
                        className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${pickSizes.includes(s) ? "bg-rose-600 text-white border-rose-600" : "bg-white text-gray-700 border-gray-300 hover:border-rose-400"}`}>
                        {s}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2 mb-5">
                    <input value={customSize} onChange={e => setCustomSize(e.target.value)} placeholder="Özel beden yaz..."
                      className="border rounded px-3 py-1.5 text-xs flex-1"
                      onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); if (customSize.trim()) { togglePick(pickSizes, setPickSizes, customSize.trim().toUpperCase()); setCustomSize(""); } } }} />
                    <button type="button" onClick={() => { if (customSize.trim()) { togglePick(pickSizes, setPickSizes, customSize.trim().toUpperCase()); setCustomSize(""); } }}
                      className="text-xs border rounded px-3 hover:bg-gray-50">Ekle</button>
                  </div>
                  <div className="flex justify-end gap-2 border-t pt-3">
                    <button type="button" onClick={() => setPickerOpen(false)} className="px-4 py-2 text-sm border rounded-lg">Vazgeç</button>
                    <button type="button" onClick={applyPicker} data-testid="mfg-picker-apply"
                      className="px-4 py-2 text-sm bg-rose-600 text-white rounded-lg hover:bg-rose-700 font-semibold">
                      Uygula ({pickColors.length} renk × {pickSizes.length} beden)
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Finansal — üç kolon TAM HİZALI: eşit etiket satırı + eşit yükseklikte kontrol + sabit ipucu alanı */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-start">
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1 h-4">Birim Fiyat (₺, KDV Hariç)</label>
                <input type="number" step="0.01" value={form.unit_price}
                  onChange={e => setForm({ ...form, unit_price: e.target.value })}
                  className="w-full h-[42px] border px-3 rounded text-sm" />
                <p className="text-[11px] text-emerald-700 mt-1 min-h-[16px] whitespace-nowrap overflow-hidden text-ellipsis" data-testid="mfg-vat-hint">
                  {Number(form.unit_price) > 0 && (<>
                    KDV'li: <b>{(Number(form.unit_price) * 1.10).toFixed(2)} ₺</b>{grandTotal > 0 && <> · {grandTotal} adet KDV'li: <b>{(Number(form.unit_price) * 1.10 * grandTotal).toFixed(2)} ₺</b></>}
                  </>)}
                </p>
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1 h-4">Toplam Anlaşma Bedeli (₺)</label>
                <div className="w-full h-[42px] border px-3 rounded text-sm bg-gray-50 font-semibold tabular-nums whitespace-nowrap flex items-center" data-testid="mfg-agreed-total">
                  {(Number(form.unit_price || 0) * grandTotal).toFixed(2)} ₺
                  <span className="text-[11px] text-gray-400 font-normal ml-2">({grandTotal} adet × {Number(form.unit_price || 0).toFixed(2)} ₺)</span>
                </div>
                <p className="mt-1 min-h-[16px]" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1 h-4">Ödeme Durumu</label>
                <button type="button"
                  onClick={() => setForm(f => ({ ...f, payment_done: !f.payment_done }))}
                  data-testid="mfg-payment-done"
                  className={`w-full h-[42px] px-3 rounded text-sm font-semibold border-2 transition flex items-center justify-center gap-2
                    ${form.payment_done ? "bg-emerald-600 text-white border-emerald-600" : "bg-white text-gray-600 border-gray-300 hover:border-emerald-400"}`}>
                  <CheckCircle2 size={16} /> {form.payment_done ? "Ödeme Yapıldı ✓" : "Ödeme Yapıldı mı?"}
                </button>
                <p className="mt-1 min-h-[16px]" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-600 mb-1">Notlar</label>
              <textarea rows={3} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm" />
            </div>

            {editing && (
              <div>
                <label className="text-xs font-bold text-gray-600 mb-1 block">Aşama Geçmişi</label>
                <div className="border rounded-lg bg-gray-50 p-3 max-h-40 overflow-y-auto">
                  {(editing.stage_history || []).map((h, i) => (
                    <div key={i} className="text-xs py-1 border-b last:border-0 flex justify-between">
                      <span className={`px-2 py-0.5 rounded ${STAGE_COLORS[h.stage] || 'bg-gray-100'}`}>{h.label}</span>
                      <span className="text-gray-500">
                        {h.by} · {new Date(h.at).toLocaleString('tr-TR')}
                        {h.note && <span className="ml-1">— {h.note}</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4 border-t">
              <button type="button" onClick={() => setModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50 text-sm">İptal</button>
              <button type="button" onClick={saveRecord} disabled={saving} data-testid="save-mfg-btn"
                className="px-4 py-2 bg-rose-600 text-white rounded hover:bg-rose-700 disabled:opacity-50 text-sm font-bold">
                <Save size={14} className="inline mr-1" /> {saving ? "Kaydediliyor..." : "Kaydet"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
