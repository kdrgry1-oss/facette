/**
 * MarketplaceAdvancedMatch.jsx — Tüm pazaryerleri için çalışan
 * "Gelişmiş Eşleştirme" modal grubudur (kategori/attribute/değer).
 *
 * TrendyolEslestir.jsx içindeki ~1200 satır MP-spesifik kodun generic hali.
 * Tek fark: endpoint'ler `/api/category-mapping/{mp}/...` altında toplanmıştır
 * (bkz. backend/routes/category_mapping.py > get_advanced_attributes/values).
 *
 * Kullanım:
 *   <AdvancedAttributeMatchModal
 *      open={...} onClose={...}
 *      marketplace="trendyol"
 *      category={row}  // category_id, category_name, marketplace_category_id
 *   />
 */
import React, { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Search, RefreshCw, Check, X, Store, AlertCircle, ArrowRight, Link as LinkIcon, FileJson,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../ui/dialog";
import AttrCacheUploadDialog from "./AttrCacheUploadDialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

// ─── Local Attribute AutoComplete (gözle görünür suggestions) ───────────────
function LocalAttrAutoComplete({ value, onChange, options, placeholder, testId }) {
  const [q, setQ] = useState(value || "");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => { setQ(value || ""); }, [value]);

  useEffect(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const qLower = q.toLowerCase().trim();
  const filtered = qLower
    ? (options || []).filter((o) => (o.name || "").toLowerCase().includes(qLower))
    : (options || []);

  return (
    <div className="relative" ref={ref}>
      <input
        type="text"
        value={q}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); onChange(e.target.value); setOpen(true); }}
        placeholder={placeholder}
        className="border rounded px-2 py-1 text-sm w-full focus:outline-none focus:ring-2 focus:ring-orange-300"
        data-testid={testId}
      />
      {open && (filtered.length > 0 || (options || []).length > 0) && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-400">
              "{q}" ile eşleşen özellik yok — serbest yazı olarak kalacak
            </div>
          ) : (
            filtered.map((opt) => {
              const n = opt.name || "";
              const vCount = (opt.values || []).length;
              return (
                <button
                  key={opt.id || n}
                  type="button"
                  onClick={() => { onChange(n); setQ(n); setOpen(false); }}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-orange-50 border-b last:border-b-0 border-gray-100 flex items-center justify-between gap-2"
                >
                  <span className="font-medium">{n}</span>
                  {vCount > 0 && (
                    <span className="text-[10px] text-gray-400">{vCount} değer</span>
                  )}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

const MP_COLORS = {
  trendyol: "orange",
  hepsiburada: "red",
  temu: "orange",
  n11: "purple",
  "amazon-tr": "yellow",
  "amazon-de": "yellow",
  aliexpress: "red",
  etsy: "red",
  "hepsi-global": "red",
  fruugo: "blue",
  emag: "blue",
  "trendyol-ihracat": "orange",
  ciceksepeti: "pink",
};

// ═══════════════════════════════════════════════════════════════════════════
// Advanced Attribute Match Modal (MP'nin zorunlu/opsiyonel özellikleri ↔ sistem)
// ═══════════════════════════════════════════════════════════════════════════
export function AdvancedAttributeMatchModal({ open, onClose, marketplace, category }) {
  const [mpAttrs, setMpAttrs] = useState([]);
  const [globalAttrs, setGlobalAttrs] = useState([]);
  const [mappings, setMappings] = useState({});
  const [defaults, setDefaults] = useState({});
  const [searchTerms, setSearchTerms] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hint, setHint] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const color = MP_COLORS[marketplace] || "orange";

  useEffect(() => {
    if (!open || !category) return;
    setLoading(true);
    Promise.all([
      axios
        .get(`${API}/category-mapping/${marketplace}/${category.category_id}/attributes`, { headers: auth() })
        .catch(() => ({ data: { attributes: [], attribute_mappings: [], default_mappings: {} } })),
      axios
        .get(`${API}/attributes`, { headers: auth() })
        .catch(() => ({ data: { attributes: [] } })),
    ]).then(([mpRes, gRes]) => {
      setMpAttrs(mpRes.data?.attributes || []);
      setGlobalAttrs(gRes.data?.attributes || []);
      const savedMap = {};
      (mpRes.data?.attribute_mappings || []).forEach((m) => {
        if (m.mp_attr_id || m.trendyol_attr_id) {
          savedMap[String(m.mp_attr_id ?? m.trendyol_attr_id)] = m.local_attr;
        }
      });
      setMappings(savedMap);
      setDefaults(mpRes.data?.default_mappings || {});
      setHint(mpRes.data?.hint || "");
    }).finally(() => setLoading(false));
  }, [open, marketplace, category]);

  const handleAutoMatch = () => {
    const next = { ...mappings };
    let count = 0;
    mpAttrs.forEach((a) => {
      const id = String(a.id ?? a.attribute?.id ?? "");
      const name = (a.name || a.attribute?.name || "").toLowerCase().trim();
      if (next[id]) return;
      const g = globalAttrs.find((ga) => {
        const gn = (ga.name || "").toLowerCase().trim();
        return (
          gn === name ||
          gn.includes(name) ||
          name.includes(gn) ||
          (name === "web color" && gn === "renk") ||
          (name === "color" && gn === "renk") ||
          (name === "size" && gn === "beden")
        );
      });
      if (g) { next[id] = g.name; count++; }
    });
    setMappings(next);
    toast.success(`${count} özellik otomatik eşleştirildi`);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = Object.entries(mappings)
        .filter(([, v]) => v !== "" && v != null)
        .map(([id, v]) => ({ local_attr: v, mp_attr_id: isNaN(Number(id)) ? id : Number(id) }));
      await axios.post(
        `${API}/category-mapping/${marketplace}/${category.category_id}/attribute-map`,
        { attribute_mappings: payload, default_mappings: defaults },
        { headers: auth() }
      );
      toast.success("Eşleştirmeler kaydedildi");
      onClose(true);
    } catch {
      toast.error("Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const refreshFromMarketplace = async () => {
    if (!category) return;
    try {
      const r = await axios.post(
        `${API}/category-mapping/${marketplace}/${category.category_id}/refresh-attributes`,
        {}, { headers: auth() }
      );
      if (r.data?.fetched) {
        toast.success(r.data?.message || "Yenilendi");
        // Modal'ı yeniden yükle
        setLoading(true);
        const mpRes = await axios.get(
          `${API}/category-mapping/${marketplace}/${category.category_id}/attributes`, { headers: auth() }
        ).catch(() => ({ data: { attributes: [] } }));
        setMpAttrs(mpRes.data?.attributes || []);
        setHint(mpRes.data?.hint || "");
        setLoading(false);
      } else {
        toast.info(r.data?.message || "Bu pazaryeri için canlı API yok");
      }
    } catch (e) {
      toast.error("Yenileme hatası: " + (e.response?.data?.detail || e.message));
    }
  };

  const required = mpAttrs.filter((a) => a.required);
  const optional = mpAttrs.filter((a) => !a.required);
  // mpAttrs boşsa, kullanıcı yine de sistem özelliklerinden seçebilsin diye
  // globalAttrs'ı manuel eşleştirme rowları olarak sun (pseudo MP attributes).
  const manualRows = mpAttrs.length === 0
    ? globalAttrs.map((g) => ({
        id: `local:${g.name}`,
        name: g.name,
        required: false,
        manual: true,
        attributeValues: (g.values || []).map((v) => ({ id: v, name: v })),
      }))
    : [];
  const rows = mpAttrs.length > 0 ? [...required, ...optional] : manualRows;

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Store size={18} className={`text-${color}-500`} />
              Özellik Eşleştirme — {category?.category_name}
              {category?.marketplace_category_name && (
                <>
                  <ArrowRight size={14} className="text-gray-400" />
                  <span className="text-gray-500">{category.marketplace_category_name}</span>
                </>
              )}
              <span className={`text-[10px] font-bold bg-${color}-100 text-${color}-700 px-2 py-0.5 rounded-full uppercase`}>
                {marketplace}
              </span>
            </DialogTitle>
            <div className="flex items-center gap-2">
              <button
                onClick={refreshFromMarketplace}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-500 text-white rounded text-xs font-semibold hover:bg-blue-600"
                data-testid="adv-refresh-mp-btn"
                title="Pazaryerinden anlık attribute listesini çek (Trendyol için canlı API)"
              >
                <RefreshCw size={14} /> {marketplace} Canlı Çek
              </button>
              <button
                onClick={handleAutoMatch}
                className="flex items-center gap-2 px-3 py-1.5 bg-green-500 text-white rounded text-xs font-semibold hover:bg-green-600"
                data-testid="adv-auto-match-btn"
              >
                <LinkIcon size={14} /> Otomatik Eşleştir
              </button>
            </div>
          </div>
        </DialogHeader>

        {hint && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs text-blue-800">
            <AlertCircle size={12} className="inline mr-1" /> {hint}
          </div>
        )}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-800 space-y-1">
          <div className="flex items-center justify-between gap-3">
            <div className="flex-1">
              <p className="font-semibold flex items-center gap-1"><AlertCircle size={14} /> Dikkat</p>
              <p>• Zorunlu alanları mutlaka eşleştirmeniz gerekir.</p>
              <p>• Eşleştirilen yerel değerler ürünlerinizde karşılığı olmalıdır.</p>
              <p>• Sistemde tanımlı <b>{globalAttrs.length}</b> özellik var — "Yerel Özellik" kutusuna tıkladığınızda öneri listesi açılır.</p>
            </div>
            {globalAttrs.length === 0 && (
              <button
                onClick={async () => {
                  try {
                    const r = await axios.post(`${API}/attributes/sync-from-products`, {}, { headers: auth() });
                    toast.success(r.data?.message || "Sync tamam");
                    const g = await axios.get(`${API}/attributes`, { headers: auth() });
                    setGlobalAttrs(g.data?.attributes || []);
                  } catch { toast.error("Sync başarısız"); }
                }}
                className="bg-yellow-500 text-white text-xs px-3 py-1.5 rounded-lg font-semibold hover:bg-yellow-600 whitespace-nowrap"
                data-testid="adv-sync-attrs-btn"
              >
                Ürünlerden Yükle
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <RefreshCw size={22} className="animate-spin text-gray-400" />
          </div>
        ) : rows.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-12 text-gray-400 text-sm gap-2">
            <AlertCircle size={32} />
            <p>Hem pazaryeri özellik listesi hem de sistem özellikleri boş.</p>
            <p className="text-xs">"Ürünlerden Yükle" butonuyla sistemdeki özellikleri senkronize edebilirsiniz.</p>
          </div>
        ) : (
          <>
            {mpAttrs.length === 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-900 flex items-start gap-2">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <div className="flex-1">
                  <b>{marketplace} canlı özellik listesi yüklenemedi</b> (credential yok ya da cache boş).
                  Bu arada <b>{globalAttrs.length} sistem özelliğinden</b> manuel seçim yapabilirsiniz.
                  Credential eklendikten sonra "Tümünü Otomatik Eşleştir" ile zenginleştirilecektir.
                </div>
                {marketplace !== "trendyol" && (
                  <button
                    onClick={() => setUploadOpen(true)}
                    className="bg-blue-600 text-white text-xs px-3 py-1.5 rounded hover:bg-blue-700 whitespace-nowrap flex items-center gap-1"
                    data-testid="adv-upload-cache-btn"
                  >
                    <FileJson size={12} /> JSON Yükle
                  </button>
                )}
              </div>
            )}
            <div className="flex-1 overflow-auto border rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0 border-b">
                  <tr>
                    <th className="text-left px-4 py-2.5 w-16 text-xs text-gray-500">Zorunlu</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500">
                      {mpAttrs.length === 0 ? "Sistem Özelliği" : `${marketplace} Özelliği`}
                    </th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500">Yerel Özellik (Eşleştir)</th>
                    <th className="text-left px-4 py-2.5 w-20 text-xs text-gray-500">Durum</th>
                  </tr>
                </thead>
                <tbody>
                {rows.map((attr, idx) => {
                  const name = attr.name || attr.attribute?.name || "Bilinmeyen";
                  const id = String(attr.id ?? attr.attribute?.id ?? name);
                  const hasVals = attr.attributeValues?.length > 0;
                  const mapped = mappings[id];
                  const isReq = !!attr.required;
                  // Zorunlu/opsiyonel geçişinde küçük başlık satırı
                  const showReqHeader = idx === 0 && isReq;
                  const showOptHeader = !isReq && idx > 0 && rows[idx - 1]?.required;
                  return (
                    <React.Fragment key={id}>
                      {showReqHeader && (
                        <tr className="bg-red-50">
                          <td colSpan={4} className="px-4 py-1.5 text-[11px] font-bold text-red-700 uppercase tracking-wide">
                            Zorunlu Alanlar ({required.length})
                          </td>
                        </tr>
                      )}
                      {showOptHeader && (
                        <tr className="bg-gray-50">
                          <td colSpan={4} className="px-4 py-1.5 text-[11px] font-bold text-gray-500 uppercase tracking-wide">
                            Opsiyonel Alanlar ({mpAttrs.length > 0 ? optional.length : rows.length})
                          </td>
                        </tr>
                      )}
                      <tr className={`border-b hover:bg-gray-50 ${isReq ? "bg-red-50/40" : ""}`}>
                        <td className="px-4 py-2.5">
                          {isReq ? (
                            <span className="text-[10px] font-bold bg-red-500 text-white px-2 py-0.5 rounded uppercase">Zorunlu</span>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <p className={`font-medium ${isReq ? "text-red-900" : "text-gray-800"}`}>{name}</p>
                          {attr.attributeType && (
                            <p className="text-xs text-gray-400">Tür: {attr.attributeType}</p>
                          )}
                        </td>
                        <td className="px-4 py-2.5 space-y-2">
                          <LocalAttrAutoComplete
                            value={mapped || ""}
                            onChange={(v) => setMappings((p) => ({ ...p, [id]: v }))}
                            options={globalAttrs}
                            placeholder={globalAttrs.length
                              ? `Sistem özelliği seç veya yazın (${globalAttrs.length} adet)`
                              : "Sistem özelliği henüz yok"}
                            testId={`adv-mapinput-${id}`}
                          />
                          {(attr.allowCustom || attr.attribute?.allowCustom) && (
                            <div className="p-1 bg-blue-50/50 rounded border border-blue-100">
                              <div className="text-[10px] font-bold text-blue-800 mb-1 px-1">Özel Değer:</div>
                              <input
                                type="text"
                                placeholder="Varsayılan metin..."
                                value={defaults[id] || ""}
                                onChange={(e) => setDefaults((p) => ({ ...p, [id]: e.target.value }))}
                                className="border border-blue-200 rounded px-2 py-1 text-xs w-full bg-white"
                              />
                            </div>
                          )}
                          {hasVals && (
                            <div className="p-1 bg-orange-50/50 rounded border border-orange-100">
                              <div className="text-[10px] font-bold text-orange-800 mb-1 px-1">Listeden Seçin:</div>
                              <div className="relative">
                                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-orange-400" />
                                <input
                                  type="text"
                                  placeholder="Değer ara..."
                                  value={searchTerms[id] || ""}
                                  onChange={(e) => setSearchTerms((p) => ({ ...p, [id]: e.target.value }))}
                                  className="w-full pl-6 pr-2 py-1 text-xs border-b border-transparent bg-transparent focus:bg-white focus:border-orange-300 outline-none rounded-t"
                                />
                              </div>
                              <select
                                value={defaults[id] || ""}
                                onChange={(e) => setDefaults((p) => ({ ...p, [id]: e.target.value }))}
                                className="border rounded px-2 py-1 text-xs w-full bg-white"
                              >
                                <option value="">Varsayılan Seçilmedi</option>
                                {attr.attributeValues
                                  .filter((v) => v.name.toLowerCase().includes((searchTerms[id] || "").toLowerCase()))
                                  .map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                              </select>
                            </div>
                        )}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {mapped || defaults[id] ? (
                            <Check size={16} className="text-green-500 mx-auto" />
                          ) : isReq ? (
                            <X size={16} className="text-red-400 mx-auto" />
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                      </tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          </>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t">
          <button onClick={() => onClose(false)}
            className="px-4 py-2 border rounded text-sm hover:bg-gray-50">İptal</button>
          <button onClick={handleSave} disabled={saving}
            className={`flex items-center gap-2 px-4 py-2 bg-${color}-500 text-white rounded text-sm hover:bg-${color}-600 disabled:opacity-50`}
            data-testid="adv-attr-save">
            {saving && <RefreshCw size={14} className="animate-spin" />}
            Eşleştirmeleri Kaydet
          </button>
        </div>
      </DialogContent>
      <AttrCacheUploadDialog
        open={uploadOpen}
        onClose={async (ok) => {
          setUploadOpen(false);
          if (ok && category) {
            // Modal'ı yeniden yükle
            setLoading(true);
            try {
              const r = await axios.get(
                `${API}/category-mapping/${marketplace}/${category.category_id}/attributes`,
                { headers: auth() }
              );
              setMpAttrs(r.data?.attributes || []);
              setHint(r.data?.hint || "");
            } finally { setLoading(false); }
          }
        }}
        marketplace={marketplace}
        mpCategoryId={category?.marketplace_category_id}
      />
    </Dialog>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Advanced Value Match Modal (ürünlerdeki değerler ↔ MP değerleri)
// ═══════════════════════════════════════════════════════════════════════════
export function AdvancedValueMatchModal({ open, onClose, marketplace, category }) {
  const [mpAttrs, setMpAttrs] = useState([]);
  const [localValues, setLocalValues] = useState({});
  const [valueMappings, setValueMappings] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedAttrId, setSelectedAttrId] = useState("");
  const [hint, setHint] = useState("");
  const color = MP_COLORS[marketplace] || "orange";

  const load = useCallback(async () => {
    if (!category) return;
    setLoading(true);
    try {
      const [a, v] = await Promise.all([
        axios.get(`${API}/category-mapping/${marketplace}/${category.category_id}/attributes`, { headers: auth() }),
        axios.get(`${API}/category-mapping/${marketplace}/${category.category_id}/values`, { headers: auth() }),
      ]);
      const attrs = (a.data?.attributes || []).filter((x) => x.attributeValues?.length > 0);
      setMpAttrs(attrs);
      setLocalValues(v.data?.local_values || {});
      setValueMappings(v.data?.value_mappings || {});
      setHint(a.data?.hint || "");
      if (attrs.length && !selectedAttrId) setSelectedAttrId(String(attrs[0].id || attrs[0].attribute?.id));
    } catch {
      toast.error("Değerler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [marketplace, category, selectedAttrId]);

  useEffect(() => { if (open && category) load(); }, [open, category, load]);

  const save = async () => {
    setSaving(true);
    try {
      await axios.post(
        `${API}/category-mapping/${marketplace}/${category.category_id}/attribute-map`,
        { value_mappings: valueMappings },
        { headers: auth() }
      );
      toast.success("Değer eşleştirmeleri kaydedildi");
      onClose(true);
    } catch {
      toast.error("Kaydedilemedi");
    } finally { setSaving(false); }
  };

  // Otomatik değer eşleştirme — isim benzerliği (Kırmızı ↔ Red, S ↔ Small vb.)
  const handleAutoMatchValues = () => {
    const next = { ...valueMappings };
    let matched = 0;
    // Alias tablosu — en yaygın Türkçe↔İngilizce & beden kısaltmaları
    const aliases = {
      "kırmızı": ["red"], "mavi": ["blue"], "yeşil": ["green"], "sarı": ["yellow"],
      "siyah": ["black"], "beyaz": ["white"], "gri": ["gray", "grey"], "pembe": ["pink"],
      "mor": ["purple"], "turuncu": ["orange"], "kahverengi": ["brown"], "bej": ["beige"],
      "lacivert": ["navy", "dark blue"], "altın": ["gold"], "gümüş": ["silver"],
      "s": ["small", "küçük"], "m": ["medium", "orta"], "l": ["large", "büyük"],
      "xl": ["x-large", "extra large"], "xxl": ["xx-large", "2xl"], "xs": ["x-small", "extra small"],
    };

    mpAttrs.forEach((mpAttr) => {
      const id = String(mpAttr.id ?? mpAttr.attribute?.id);
      const mpName = (mpAttr.name || mpAttr.attribute?.name || "").toLowerCase();
      const mpValues = mpAttr.attributeValues || [];
      const localVals = localValues[mpAttr.name || mpAttr.attribute?.name] || [];

      localVals.forEach((lv) => {
        const key = `${id}|${lv}`;
        if (next[key]) return; // mevcut korunur
        const lvLower = lv.toLowerCase().trim();
        const candidates = aliases[lvLower] || [];
        const found = mpValues.find((mv) => {
          const mvN = (mv.name || "").toLowerCase().trim();
          return (
            mvN === lvLower ||
            mvN.includes(lvLower) ||
            lvLower.includes(mvN) ||
            candidates.some((a) => mvN === a || mvN.includes(a))
          );
        });
        if (found) {
          next[key] = String(found.id);
          matched++;
        }
      });
    });

    setValueMappings(next);
    if (matched) toast.success(`${matched} değer otomatik eşleştirildi`);
    else toast.info("Eşleştirilecek yeni değer bulunamadı");
  };

  const currentAttr = mpAttrs.find((a) => String(a.id ?? a.attribute?.id) === String(selectedAttrId));
  const attrName = currentAttr?.name || currentAttr?.attribute?.name;

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-base flex items-center gap-2">
              <Store size={18} className={`text-${color}-500`} />
              Değer Eşleştirme — {category?.category_name}
              <span className={`text-[10px] font-bold bg-${color}-100 text-${color}-700 px-2 py-0.5 rounded-full uppercase`}>
                {marketplace}
              </span>
            </DialogTitle>
            {mpAttrs.length > 0 && (
              <button
                onClick={handleAutoMatchValues}
                className="flex items-center gap-2 px-3 py-1.5 bg-green-500 text-white rounded text-xs font-semibold hover:bg-green-600"
                data-testid="adv-auto-match-values-btn"
              >
                <LinkIcon size={14} /> Otomatik Eşleştir
              </button>
            )}
          </div>
        </DialogHeader>

        {hint && <div className="text-xs text-blue-800 bg-blue-50 border border-blue-200 rounded px-3 py-2">
          <AlertCircle size={12} className="inline mr-1" /> {hint}
        </div>}

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <RefreshCw size={22} className="animate-spin text-gray-400" />
          </div>
        ) : mpAttrs.length === 0 ? (
          <div className="py-10 text-center text-sm text-gray-400">
            Bu kategori için değer eşleştirmeye uygun özellik (listeden seçilen) yok.
          </div>
        ) : (
          <>
            <div className="flex gap-2 flex-wrap pb-2 border-b">
              {mpAttrs.map((a) => {
                const id = String(a.id ?? a.attribute?.id);
                const name = a.name || a.attribute?.name;
                return (
                  <button
                    key={id}
                    onClick={() => setSelectedAttrId(id)}
                    className={`px-3 py-1.5 text-xs rounded-full transition ${
                      id === String(selectedAttrId)
                        ? `bg-${color}-500 text-white`
                        : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                    }`}
                    data-testid={`adv-attr-tab-${id}`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>

            <div className="flex-1 overflow-auto border rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0 border-b">
                  <tr>
                    <th className="text-left px-4 py-2 text-xs text-gray-500">Sistem Değeri</th>
                    <th className="text-left px-4 py-2 text-xs text-gray-500">{marketplace} Değeri</th>
                  </tr>
                </thead>
                <tbody>
                  {(localValues[attrName] || []).length === 0 ? (
                    <tr><td colSpan={2} className="py-8 text-center text-xs text-gray-400">
                      Bu kategorideki ürünlerde "{attrName}" özelliği için değer yok.
                    </td></tr>
                  ) : (
                    (localValues[attrName] || []).map((lv) => (
                      <tr key={lv} className="border-b hover:bg-gray-50">
                        <td className="px-4 py-2 font-medium">{lv}</td>
                        <td className="px-4 py-2">
                          <select
                            value={valueMappings[`${selectedAttrId}|${lv}`] || ""}
                            onChange={(e) =>
                              setValueMappings((p) => ({ ...p, [`${selectedAttrId}|${lv}`]: e.target.value }))
                            }
                            className="border rounded px-2 py-1 text-sm w-full bg-white"
                            data-testid={`adv-valmap-${lv}`}
                          >
                            <option value="">— seçilmemiş —</option>
                            {(currentAttr?.attributeValues || []).map((v) => (
                              <option key={v.id} value={v.id}>{v.name}</option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t">
          <button onClick={() => onClose(false)} className="px-4 py-2 border rounded text-sm hover:bg-gray-50">İptal</button>
          <button onClick={save} disabled={saving}
            className={`flex items-center gap-2 px-4 py-2 bg-${color}-500 text-white rounded text-sm hover:bg-${color}-600 disabled:opacity-50`}
            data-testid="adv-val-save">
            {saving && <RefreshCw size={14} className="animate-spin" />}
            Değerleri Kaydet
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
