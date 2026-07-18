/**
 * BusinessRules.jsx — İşletme Kuralları (SaaS ayar merkezi)
 * ---------------------------------------------------------------------------
 * Kodda gömülü tüm işletme kuralları (iptal süreleri, ücretler, eşikler, çalışma
 * saatleri…) buradan yönetilir. Her ayar tipine göre kontrol + hazır ALTERNATİF
 * seçenekleri (chip) gösterir. Backend: GET/PUT /api/admin/business-rules.
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Save, SlidersHorizontal, RotateCcw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const WD = { 1: "Pzt", 2: "Sal", 3: "Çar", 4: "Per", 5: "Cum", 6: "Cmt", 7: "Paz" };

export default function BusinessRules() {
  const [groups, setGroups] = useState([]);
  const [vals, setVals] = useState({});
  const [dirty, setDirty] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const auth = { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } };

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/business-rules`, auth);
      const gs = r.data?.groups || [];
      setGroups(gs);
      const v = {};
      gs.forEach((g) => g.rules.forEach((rl) => { v[rl.key] = rl.value; }));
      setVals(v);
      setDirty({});
    } catch {
      toast.error("Kurallar yüklenemedi");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const set = (key, value) => {
    setVals((p) => ({ ...p, [key]: value }));
    setDirty((p) => ({ ...p, [key]: true }));
  };

  const save = async () => {
    const patch = {};
    Object.keys(dirty).forEach((k) => { patch[k] = vals[k]; });
    if (!Object.keys(patch).length) { toast.info("Değişiklik yok"); return; }
    setSaving(true);
    try {
      await axios.put(`${API}/admin/business-rules`, { values: patch }, auth);
      toast.success(`${Object.keys(patch).length} ayar kaydedildi`);
      setDirty({});
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally { setSaving(false); }
  };

  const control = (rl) => {
    const v = vals[rl.key];
    const opts = rl.options || [];
    if (rl.type === "toggle") {
      return (
        <button
          onClick={() => set(rl.key, !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${v ? "bg-black" : "bg-gray-300"}`}
          role="switch" aria-checked={!!v}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${v ? "translate-x-6" : "translate-x-1"}`} />
        </button>
      );
    }
    if (rl.type === "select") {
      return (
        <select value={String(v)} onChange={(e) => set(rl.key, e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white">
          {opts.map((o) => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
        </select>
      );
    }
    if (rl.type === "time") {
      return (
        <div className="flex items-center gap-2 flex-wrap">
          <input type="time" value={v || ""} onChange={(e) => set(rl.key, e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white" />
          <div className="flex gap-1">
            {opts.map((o) => (
              <button key={o} onClick={() => set(rl.key, o)}
                className={`text-xs px-2 py-1 rounded-full border ${String(v) === String(o) ? "bg-black text-white border-black" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}>{o}</button>
            ))}
          </div>
        </div>
      );
    }
    if (rl.type === "multiselect") {
      const arr = Array.isArray(v) ? v : [];
      return (
        <div className="flex gap-1 flex-wrap">
          {opts.map((o) => {
            const on = arr.includes(o);
            return (
              <button key={o} onClick={() => set(rl.key, on ? arr.filter((x) => x !== o) : [...arr, o].sort())}
                className={`text-xs px-2.5 py-1 rounded-full border ${on ? "bg-black text-white border-black" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}>
                {WD[o] || o}
              </button>
            );
          })}
        </div>
      );
    }
    // number / text
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type={rl.type === "number" ? "number" : "text"}
          value={v ?? ""}
          onChange={(e) => set(rl.key, rl.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm bg-white w-28"
        />
        {rl.unit && <span className="text-sm text-gray-400">{rl.unit}</span>}
        <div className="flex gap-1 flex-wrap">
          {opts.map((o) => (
            <button key={String(o)} onClick={() => set(rl.key, o)}
              className={`text-xs px-2 py-1 rounded-full border ${String(v) === String(o) ? "bg-black text-white border-black" : "border-gray-200 text-gray-500 hover:bg-gray-50"}`}>
              {String(o)}{rl.unit ? ` ${rl.unit}` : ""}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const dirtyCount = Object.keys(dirty).length;

  return (
    <div data-testid="business-rules-page">
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <SlidersHorizontal size={20} /> İşletme Kuralları
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Kodda sabit olan tüm kurallar burada. Değeri değiştir veya hazır alternatiflerden seç; kaydet, anında geçerli olur.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="flex items-center gap-1 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
            <RotateCcw size={14} /> Yenile
          </button>
          <button onClick={save} disabled={saving || !dirtyCount}
            className="flex items-center gap-1 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-40">
            <Save size={14} /> {saving ? "Kaydediliyor…" : `Kaydet${dirtyCount ? ` (${dirtyCount})` : ""}`}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Yükleniyor…</div>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => (
            <div key={g.group} className="bg-white border rounded-xl shadow-sm overflow-hidden">
              <div className="px-5 py-3 border-b bg-gray-50/60 font-semibold text-sm">{g.group}</div>
              <div className="divide-y">
                {g.rules.map((rl) => (
                  <div key={rl.key} className="px-5 py-4 flex flex-col md:flex-row md:items-center gap-3 md:gap-6">
                    <div className="md:w-1/2">
                      <div className="text-sm font-medium flex items-center gap-2">
                        {rl.label}
                        {dirty[rl.key] && <span className="text-[10px] text-amber-600 font-semibold">• değişti</span>}
                      </div>
                      {rl.help && <div className="text-xs text-gray-500 mt-0.5">{rl.help}</div>}
                    </div>
                    <div className="md:w-1/2">{control(rl)}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
