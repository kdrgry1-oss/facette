/**
 * Influencer CRM & ROI — işlevsel admin sayfası (Modül 5 basit hali).
 * Görsel tasarım sonradan uygulanacak; bu sürüm tam fonksiyonel.
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Plus, TrendingUp, Package, Send, CheckCircle, Trash2, X,
  Instagram, DollarSign, Truck, Share2, RefreshCw,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
const money = (n) => `${(Number(n) || 0).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} TL`;

export default function Influencers() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/influencers`, auth());
      setList(r.data?.influencers || []);
    } catch {
      toast.error("Influencerlar yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="influencers-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Instagram className="text-pink-600" size={24} /> Influencer / İş Birlikleri
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Influencer kayıtları, seeding kampanyaları, kargo otomasyonu ve ROI takibi.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="new-influencer-btn"
          className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
        >
          <Plus size={16} /> Yeni Influencer
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : list.length === 0 ? (
        <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">
          Henüz influencer eklenmedi. "Yeni Influencer" ile başlayın.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.map((inf) => (
            <button
              key={inf.id}
              onClick={() => setSelected(inf.id)}
              data-testid={`influencer-card-${inf.id}`}
              className="text-left bg-white border rounded-xl p-4 hover:border-black transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold">{inf.name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${inf.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                  {inf.platform}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">{inf.handle || "—"}</p>
              <div className="flex flex-wrap gap-2 mt-3 text-[11px]">
                {inf.coupon_code && <span className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded">Kupon: {inf.coupon_code}</span>}
                {inf.aff_id && <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded">aff: {inf.aff_id}</span>}
                <span className="bg-gray-50 text-gray-600 px-2 py-0.5 rounded">{(inf.follower_count || 0).toLocaleString("tr-TR")} takipçi</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); load(); }} />}
      {selected && <DetailModal influencerId={selected} onClose={() => { setSelected(null); load(); }} />}
    </div>
  );
}

function CreateModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", platform: "instagram", handle: "", phone: "", email: "",
    follower_count: 0, coupon_code: "", aff_id: "", commission_rate: 0,
    address_full_name: "", address_phone: "", il: "", ilce: "", adres: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name.trim()) return toast.error("İsim gerekli");
    setSaving(true);
    try {
      await axios.post(`${API}/influencers`, {
        name: form.name, platform: form.platform, handle: form.handle,
        phone: form.phone, email: form.email,
        follower_count: Number(form.follower_count) || 0,
        coupon_code: form.coupon_code, aff_id: form.aff_id,
        commission_rate: Number(form.commission_rate) || 0,
        shipping_address: {
          full_name: form.address_full_name || form.name, phone: form.address_phone || form.phone,
          il: form.il, ilce: form.ilce, adres: form.adres,
        },
      }, auth());
      toast.success("Influencer eklendi");
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Eklenemedi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Yeni Influencer" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="İsim *"><input data-testid="inf-name" className="inp" value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Platform">
          <select className="inp" value={form.platform} onChange={(e) => set("platform", e.target.value)}>
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
            <option value="youtube">YouTube</option>
            <option value="x">X</option>
          </select>
        </Field>
        <Field label="Kullanıcı Adı (@)"><input className="inp" value={form.handle} onChange={(e) => set("handle", e.target.value)} /></Field>
        <Field label="Takipçi"><input type="number" className="inp" value={form.follower_count} onChange={(e) => set("follower_count", e.target.value)} /></Field>
        <Field label="Telefon"><input className="inp" value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="E-posta"><input className="inp" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Kupon Kodu"><input data-testid="inf-coupon" className="inp uppercase" value={form.coupon_code} onChange={(e) => set("coupon_code", e.target.value)} placeholder="MELIS10" /></Field>
        <Field label="aff_id (takip linki)"><input className="inp" value={form.aff_id} onChange={(e) => set("aff_id", e.target.value)} placeholder="melis" /></Field>
        <Field label="Komisyon %"><input type="number" className="inp" value={form.commission_rate} onChange={(e) => set("commission_rate", e.target.value)} /></Field>
      </div>
      <p className="text-xs font-semibold text-gray-500 mt-4 mb-2">Kargo Adresi (seeding için)</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="İl"><input className="inp" value={form.il} onChange={(e) => set("il", e.target.value)} /></Field>
        <Field label="İlçe"><input className="inp" value={form.ilce} onChange={(e) => set("ilce", e.target.value)} /></Field>
        <Field label="Adres" full><input className="inp" value={form.adres} onChange={(e) => set("adres", e.target.value)} /></Field>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">İptal</button>
        <button onClick={save} disabled={saving} data-testid="inf-save" className="px-4 py-2 text-sm bg-black text-white rounded-lg disabled:opacity-50">
          {saving ? "Kaydediliyor..." : "Kaydet"}
        </button>
      </div>
    </Modal>
  );
}

function DetailModal({ influencerId, onClose }) {
  const [inf, setInf] = useState(null);
  const [roi, setRoi] = useState(null);
  const [showCampaign, setShowCampaign] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([
        axios.get(`${API}/influencers/${influencerId}`, auth()),
        axios.get(`${API}/influencers/${influencerId}/roi`, auth()),
      ]);
      setInf(d.data);
      setRoi(r.data);
    } catch {
      toast.error("Detay yüklenemedi");
    }
  }, [influencerId]);

  useEffect(() => { load(); }, [load]);

  const createCargo = async (cid) => {
    try {
      const r = await axios.post(`${API}/influencer-campaigns/${cid}/cargo`, {}, auth());
      toast.success(`Kargo barkodu: ${r.data.cargo_barcode}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kargo oluşturulamadı");
    }
  };

  const confirmShare = async (cid) => {
    const url = prompt("İçerik linki (opsiyonel):") || "";
    try {
      await axios.post(`${API}/influencer-campaigns/${cid}/confirm-share`, { content_url: url }, auth());
      toast.success("Paylaşım onaylandı");
      load();
    } catch {
      toast.error("Onaylanamadı");
    }
  };

  const delCampaign = async (cid) => {
    if (!window.confirm("Kampanya silinsin mi?")) return;
    await axios.delete(`${API}/influencer-campaigns/${cid}`, auth());
    load();
  };

  if (!inf) return <Modal title="Yükleniyor..." onClose={onClose}><div className="py-8 text-center text-gray-400">...</div></Modal>;

  return (
    <Modal title={`${inf.name} · ${inf.platform}`} wide onClose={onClose}>
      {/* ROI */}
      {roi && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5" data-testid="inf-roi">
          <Stat icon={<DollarSign size={16} />} label="Toplam Maliyet" value={money(roi.cost.total_cost)} color="red" />
          <Stat icon={<TrendingUp size={16} />} label="Ciro" value={money(roi.revenue.revenue)} color="green" />
          <Stat icon={<DollarSign size={16} />} label="Net Kâr" value={money(roi.net_profit)} color={roi.net_profit >= 0 ? "green" : "red"} />
          <Stat icon={<TrendingUp size={16} />} label="ROAS" value={roi.roas != null ? `${roi.roas}x` : "—"} color="blue" />
        </div>
      )}
      {roi && (
        <p className="text-xs text-gray-500 mb-4">
          {roi.revenue.successful_orders} başarılı sipariş · {roi.cost.campaign_count} kampanya · {roi.cost.shared_count} paylaşım · Komisyon: {money(roi.revenue.commission_due)}
        </p>
      )}

      {/* Campaigns */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-sm">Kampanyalar</h3>
        <button onClick={() => setShowCampaign(true)} data-testid="new-campaign-btn" className="inline-flex items-center gap-1 text-sm border px-3 py-1.5 rounded-lg hover:bg-gray-50">
          <Plus size={14} /> Kampanya
        </button>
      </div>
      <div className="space-y-2">
        {(inf.campaigns || []).length === 0 && <p className="text-xs text-gray-400 py-3">Kampanya yok.</p>}
        {(inf.campaigns || []).map((c) => (
          <div key={c.id} className="border rounded-lg p-3" data-testid={`campaign-${c.id}`}>
            <div className="flex items-center justify-between">
              <span className="font-medium text-sm">{c.title}</span>
              <div className="flex items-center gap-2">
                <Badge>{c.status}</Badge>
                <Badge tone="cargo">{c.cargo_status}</Badge>
                {c.shared && <span className="text-green-600 text-xs flex items-center gap-1"><CheckCircle size={12} /> Paylaşıldı</span>}
              </div>
            </div>
            <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-gray-500">
              <span>Ücret: {money(c.fee_paid)}</span>
              <span>Ürün: {money(c.product_cost)}</span>
              <span>Kargo: {money(c.cargo_cost)}</span>
              {c.cargo_barcode && <span className="text-blue-600">Barkod: {c.cargo_barcode}</span>}
            </div>
            <div className="flex gap-2 mt-3">
              <button onClick={() => createCargo(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded hover:bg-gray-50">
                <Truck size={12} /> Kargo Oluştur
              </button>
              <button onClick={() => confirmShare(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded hover:bg-gray-50">
                <Share2 size={12} /> Paylaşıldı
              </button>
              <button onClick={() => delCampaign(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded text-red-600 hover:bg-red-50 ml-auto">
                <Trash2 size={12} /> Sil
              </button>
            </div>
          </div>
        ))}
      </div>

      {showCampaign && (
        <CampaignModal influencerId={influencerId} onClose={() => setShowCampaign(false)} onCreated={() => { setShowCampaign(false); load(); }} />
      )}
    </Modal>
  );
}

function CampaignModal({ influencerId, onClose, onCreated }) {
  const [form, setForm] = useState({ title: "", fee_paid: 0, product_cost: 0, cargo_cost: 0, directives: "" });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    if (!form.title.trim()) return toast.error("Başlık gerekli");
    setSaving(true);
    try {
      await axios.post(`${API}/influencers/${influencerId}/campaigns`, {
        title: form.title, fee_paid: Number(form.fee_paid) || 0,
        product_cost: Number(form.product_cost) || 0, cargo_cost: Number(form.cargo_cost) || 0,
        directives: form.directives,
      }, auth());
      toast.success("Kampanya oluşturuldu");
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Oluşturulamadı");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title="Yeni Kampanya" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Başlık *" full><input data-testid="camp-title" className="inp" value={form.title} onChange={(e) => set("title", e.target.value)} /></Field>
        <Field label="Ödenen Ücret"><input type="number" className="inp" value={form.fee_paid} onChange={(e) => set("fee_paid", e.target.value)} /></Field>
        <Field label="Ürün Maliyeti"><input type="number" className="inp" value={form.product_cost} onChange={(e) => set("product_cost", e.target.value)} /></Field>
        <Field label="Kargo Maliyeti"><input type="number" className="inp" value={form.cargo_cost} onChange={(e) => set("cargo_cost", e.target.value)} /></Field>
      </div>
      <Field label="İçerik Talimatları (boşsa 9:16 dikey format standardı otomatik eklenir)" full>
        <textarea className="inp h-24" value={form.directives} onChange={(e) => set("directives", e.target.value)} placeholder="Boş bırakırsanız zorunlu içerik standartları (9:16 dikey format, @facette mention) otomatik eklenir." />
      </Field>
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">İptal</button>
        <button onClick={save} disabled={saving} data-testid="camp-save" className="px-4 py-2 text-sm bg-black text-white rounded-lg disabled:opacity-50">
          {saving ? "..." : "Oluştur"}
        </button>
      </div>
    </Modal>
  );
}

/* ---- küçük yardımcı bileşenler ---- */
function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-center overflow-y-auto py-10 px-4" onClick={onClose}>
      <div className={`bg-white rounded-xl w-full ${wide ? "max-w-3xl" : "max-w-xl"} p-6`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-lg">{title}</h2>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Field({ label, children, full }) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  );
}
function Stat({ icon, label, value, color }) {
  const c = { red: "bg-red-50 text-red-700", green: "bg-green-50 text-green-700", blue: "bg-blue-50 text-blue-700" }[color] || "bg-gray-50 text-gray-700";
  return (
    <div className={`rounded-lg p-3 ${c}`}>
      <div className="flex items-center gap-1 text-[11px] opacity-80">{icon} {label}</div>
      <div className="text-lg font-bold mt-0.5">{value}</div>
    </div>
  );
}
function Badge({ children, tone }) {
  const c = tone === "cargo" ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-600";
  return <span className={`text-[10px] px-2 py-0.5 rounded-full ${c}`}>{children}</span>;
}
