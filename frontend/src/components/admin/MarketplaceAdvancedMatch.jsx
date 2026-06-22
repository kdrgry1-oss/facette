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
  Search, RefreshCw, Check, X, Store, AlertCircle, ArrowRight, Link as LinkIcon, FileJson, ChevronsUpDown,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../ui/dialog";
import { Popover, PopoverTrigger, PopoverContent } from "../ui/popover";
import {
  Command, CommandInput, CommandList, CommandEmpty, CommandItem, CommandGroup,
} from "../ui/command";
import AttrCacheUploadDialog from "./AttrCacheUploadDialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

// Beden gibi size attribute'lar için sıralama yardımcısı:
// XXS, XS, S, M, L, XL, XXL, XXXL ... STD/Standart önce, sayısal bedenler ortada, karışık olanlar sonda.
const SIZE_ORDER = [
  "xxxxxs","xxxxs","xxxs","xxs","2xs","xs","s","m","l","xl","xxl","2xl","xxxl","3xl","xxxxl","4xl","xxxxxl","5xl",
  "std","standart","tek beden","tek ebat","free size","onesize","one size",
];
function _isSizeAttrName(n) {
  const x = (n || "").toLowerCase();
  return x.includes("beden") || x.includes("size") || x.includes("numara");
}
function _sizeRank(name) {
  const n = (name || "").toString().toLowerCase().trim().replace(/[\s\-_./]/g, "");
  const idx = SIZE_ORDER.indexOf(n);
  if (idx >= 0) return [0, idx];                    // standart bedenler en başta
  // Sayısal (örn 36, 38, 40) → orta
  const m = n.match(/^(\d+)$/);
  if (m) return [1, parseInt(m[1], 10)];
  // Range (36-38, 38/42) → biraz daha aşağı
  const r = n.match(/^(\d+)[/-](\d+)$/);
  if (r) return [2, parseInt(r[1], 10)];
  // Yaş/ay grubu (2-3 yaş, 0-2 ay) → en sonlardan biri
  if (/(yaş|yas|ay)/.test(n)) return [4, n];
  // Diğer (XL/L, M/S, Onesize varyantları vs) → 3
  return [3, n];
}
// Türkçe duyarsız + boşluk/noktalama temizleyen agresif normalize (backend _norm_val ile uyumlu)
function _normVal(s) {
  let x = (s || "").toString().toLocaleLowerCase("tr");
  const map = { "ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c" };
  x = x.replace(/[ışğüöçİ]/g, (ch) => map[ch] || ch);
  return x.replace(/[^a-z0-9]/g, "");
}

function sortLikeSize(arr, getName) {
  return [...(arr || [])].sort((a, b) => {
    const ra = _sizeRank(getName(a));
    const rb = _sizeRank(getName(b));
    if (ra[0] !== rb[0]) return ra[0] - rb[0];
    if (typeof ra[1] === "number" && typeof rb[1] === "number") return ra[1] - rb[1];
    return String(ra[1]).localeCompare(String(rb[1]), "tr");
  });
}

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
        className="border rounded px-2 py-1 text-sm w-full focus:outline-none focus:ring-2 focus:ring-stone-300"
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
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-stone-100 border-b last:border-b-0 border-gray-100 flex items-center justify-between gap-2"
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

// ─── Aranabilir Trendyol Değer Seçici (Popover + Command) ───────────────────
function SearchableValueSelect({ value, options, onChange, placeholder, testId, color = "orange" }) {
  const [open, setOpen] = React.useState(false);
  const selected = (options || []).find((o) => String(o.id) === String(value));
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          className={`flex items-center justify-between gap-2 border rounded px-2 py-1 text-sm w-full text-left ${
            selected ? `bg-stone-100 border-stone-400 font-semibold text-stone-900` : "bg-white"
          }`}
          data-testid={testId}
        >
          <span className={`truncate ${selected ? "" : "text-gray-400"}`}>
            {selected ? selected.name : (placeholder || "— seçilmemiş —")}
          </span>
          <ChevronsUpDown size={14} className="shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="p-0 w-[var(--radix-popover-trigger-width)]" align="start">
        <Command filter={(val, search) => (_normVal(val).includes(_normVal(search)) ? 1 : 0)}>
          <CommandInput placeholder="Değer ara..." data-testid={`${testId}-search`} />
          <CommandList>
            <CommandEmpty>Eşleşen değer yok</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="__none__"
                onSelect={() => { onChange(""); setOpen(false); }}
              >
                <span className="text-gray-400">— seçilmemiş —</span>
              </CommandItem>
              {(options || []).map((opt) => (
                <CommandItem
                  key={opt.id}
                  value={`${opt.name} ${opt.id}`}
                  onSelect={() => { onChange(String(opt.id)); setOpen(false); }}
                  data-testid={`${testId}-opt-${opt.id}`}
                >
                  <Check size={14} className={String(opt.id) === String(value) ? "opacity-100 text-stone-700" : "opacity-0"} />
                  <span className="truncate">{opt.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
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
  const autosaveTimer = useRef(null);
  const didLoad = useRef(false);
  const [autoSavedAt, setAutoSavedAt] = useState(null);

  const color = MP_COLORS[marketplace] || "orange";

  useEffect(() => {
    if (!open || !category) return;
    didLoad.current = false;
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
    }).finally(() => {
      setLoading(false);
      // Yukleme bitti; bundan sonraki degisiklikler otomatik kaydedilebilir.
      didLoad.current = true;
    });
  }, [open, marketplace, category]);

  const handleAutoMatch = () => {
    const next = { ...mappings };
    let count = 0;
    let alreadyMapped = 0;
    let noGlobalMatch = 0;
    mpAttrs.forEach((a) => {
      const id = String(a.id ?? a.attribute?.id ?? "");
      const name = (a.name || a.attribute?.name || "").toLowerCase().trim();
      if (next[id]) { alreadyMapped++; return; }
      // Trendyol "Materyal Bileşeni" → bizdeki veri "Ürün İçerik Bilgisi"nde
      if (name.includes("materyal bileşeni")) {
        const ic = globalAttrs.find((ga) => (ga.name || "").toLowerCase().includes("içerik"));
        if (ic) { next[id] = ic.name; count++; return; }
      }
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
      else { noGlobalMatch++; }
    });
    setMappings(next);
    if (count > 0) {
      toast.success(`${count} yeni özellik eşleştirildi (${alreadyMapped} zaten eşliydi)`);
    } else if (alreadyMapped > 0) {
      toast.info(`Tüm eşlenebilir özellikler zaten eşli (${alreadyMapped}). ${noGlobalMatch} alan için global karşılık yok — "Şirket Bilgisi Doldur" ile üretici/ithalatçı bilgilerini ekleyebilirsiniz.`);
    } else {
      toast.info(`${noGlobalMatch} pazaryeri özelliği için sistem karşılığı bulunamadı — manuel girin veya "Şirket Bilgisi Doldur" deneyin.`);
    }
  };

  const handleFillCompanyDefaults = async () => {
    if (!category) return;
    try {
      const r = await axios.post(
        `${API}/category-mapping/${marketplace}/${category.category_id}/fill-company-defaults`,
        {}, { headers: auth() }
      );
      const data = r.data || {};
      if (data.default_mappings) setDefaults(data.default_mappings);
      if (data.filled_count > 0) {
        toast.success(data.message);
      } else {
        toast.info(data.message);
      }
    } catch (e) {
      toast.error("Şirket bilgisi doldurulamadı: " + (e.response?.data?.detail || e.message));
    }
  };

  const persistMappings = useCallback(async ({ silent } = {}) => {
    if (!category) return false;
    const payload = Object.entries(mappings)
      .filter(([, v]) => v !== "" && v != null)
      .map(([id, v]) => ({ local_attr: v, mp_attr_id: isNaN(Number(id)) ? id : Number(id) }));
    await axios.post(
      `${API}/category-mapping/${marketplace}/${category.category_id}/attribute-map`,
      { attribute_mappings: payload, default_mappings: defaults },
      { headers: auth() }
    );
    if (silent) setAutoSavedAt(Date.now());
    return true;
  }, [mappings, defaults, marketplace, category]);

  // Otomatik kaydetme: yukleme sonrasi mappings/defaults degisince debounce ile sessizce kaydet.
  // Boylece sekmeler/section'lar arasinda gezerken onceki secimler kaybolmaz.
  useEffect(() => {
    if (!open || !category || !didLoad.current) return;
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current);
    autosaveTimer.current = setTimeout(() => {
      persistMappings({ silent: true }).catch(() => {});
    }, 800);
    return () => { if (autosaveTimer.current) clearTimeout(autosaveTimer.current); };
  }, [mappings, defaults, open, category, persistMappings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await persistMappings({ silent: false });
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
              <span className={`text-[10px] font-bold bg-stone-200 text-stone-700 px-2 py-0.5 rounded-full uppercase`}>
                {marketplace}
              </span>
            </DialogTitle>
            <div className="flex items-center gap-2">
              <button
                onClick={refreshFromMarketplace}
                className="flex items-center gap-2 px-3 py-1.5 border border-stone-300 text-stone-700 bg-white rounded text-xs font-semibold hover:bg-stone-100"
                data-testid="adv-refresh-mp-btn"
                title="Pazaryerinden anlık attribute listesini çek (Trendyol için canlı API)"
              >
                <RefreshCw size={14} /> {marketplace} Canlı Çek
              </button>
              <button
                onClick={handleFillCompanyDefaults}
                className="flex items-center gap-2 px-3 py-1.5 border border-stone-300 text-stone-700 bg-white rounded text-xs font-semibold hover:bg-stone-100"
                data-testid="adv-fill-company-btn"
                title="Ayarlar > Şirket Bilgisi'nden Üretici / İthalatçı Adı / Adres / Mail alanlarını otomatik doldur"
              >
                <Store size={14} /> Şirket Bilgisi Doldur
              </button>
              <button
                onClick={handleAutoMatch}
                className="flex items-center gap-2 px-3 py-1.5 bg-stone-900 text-white rounded text-xs font-semibold hover:bg-stone-800"
                data-testid="adv-auto-match-btn"
              >
                <LinkIcon size={14} /> Otomatik Eşleştir
              </button>
            </div>
          </div>
        </DialogHeader>

        {hint && (
          <div className="bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-xs text-stone-600">
            <AlertCircle size={12} className="inline mr-1" /> {hint}
          </div>
        )}
        <div className="bg-stone-50 border border-stone-200 rounded-lg px-4 py-3 text-sm text-stone-700 space-y-1">
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
                className="bg-stone-900 text-white text-xs px-3 py-1.5 rounded-lg font-semibold hover:bg-stone-800 whitespace-nowrap"
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
                    className="bg-stone-900 text-white text-xs px-3 py-1.5 rounded hover:bg-stone-800 whitespace-nowrap flex items-center gap-1"
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
                        <tr className="bg-stone-50">
                          <td colSpan={4} className="px-4 py-1.5 text-[11px] font-bold text-[#B0413A] uppercase tracking-wide">
                            Zorunlu Alanlar ({required.length})
                          </td>
                        </tr>
                      )}
                      {showOptHeader && (
                        <tr className="bg-stone-50">
                          <td colSpan={4} className="px-4 py-1.5 text-[11px] font-bold text-stone-500 uppercase tracking-wide">
                            Opsiyonel Alanlar ({mpAttrs.length > 0 ? optional.length : rows.length})
                          </td>
                        </tr>
                      )}
                      <tr className={`border-b hover:bg-stone-50 ${isReq ? "bg-stone-100/60" : ""}`}>
                        <td className="px-4 py-2.5">
                          {isReq ? (
                            <span className="text-[10px] font-bold bg-[#B0413A] text-white px-2 py-0.5 rounded uppercase">Zorunlu</span>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          <p className={`font-medium ${isReq ? "text-stone-900" : "text-stone-800"}`}>{name}</p>
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
                            <div className="p-1.5 bg-stone-50 rounded border border-stone-200">
                              <div className="text-[10px] font-bold text-stone-600 mb-1 px-1">Özel Değer:</div>
                              <input
                                type="text"
                                placeholder="Varsayılan metin..."
                                value={defaults[id] || ""}
                                onChange={(e) => setDefaults((p) => ({ ...p, [id]: e.target.value }))}
                                className="border border-stone-300 rounded px-2 py-1 text-xs w-full bg-white"
                              />
                            </div>
                          )}
                          {hasVals && (
                            <div className="p-1.5 bg-stone-50 rounded border border-stone-200">
                              <div className="text-[10px] font-bold text-stone-600 mb-1 px-1">Listeden Seçin:</div>
                              <div className="relative">
                                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                  type="text"
                                  placeholder="Değer ara..."
                                  value={searchTerms[id] || ""}
                                  onChange={(e) => setSearchTerms((p) => ({ ...p, [id]: e.target.value }))}
                                  className="w-full pl-6 pr-2 py-1 text-xs border-b border-transparent bg-transparent focus:bg-white focus:border-stone-400 outline-none rounded-t"
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
                            <Check size={16} className="text-[#3F7A52] mx-auto" />
                          ) : isReq ? (
                            <X size={16} className="text-[#B0413A] mx-auto" />
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

        <div className="flex justify-end items-center gap-2 pt-3 border-t">
          {autoSavedAt && (
            <span className="text-xs text-[#3F7A52] mr-auto">✓ Değişiklikler otomatik kaydedildi</span>
          )}
          <button onClick={() => onClose(false)}
            className="px-4 py-2 border rounded text-sm hover:bg-gray-50">İptal</button>
          <button onClick={handleSave} disabled={saving}
            className={`flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded text-sm hover:bg-stone-800 disabled:opacity-50`}
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
  const [valSearch, setValSearch] = useState("");
  const [attrSearch, setAttrSearch] = useState("");
  // Attribute değiştiğinde aramayı sıfırla
  useEffect(() => { setValSearch(""); }, [selectedAttrId]);
  const color = MP_COLORS[marketplace] || "orange";

  const load = useCallback(async () => {
    if (!category) return;
    setLoading(true);
    try {
      const [a, v] = await Promise.all([
        axios.get(`${API}/category-mapping/${marketplace}/${category.category_id}/attributes`, { headers: auth() }),
        axios.get(`${API}/category-mapping/${marketplace}/${category.category_id}/values`, { headers: auth() }),
      ]);
      const lv = v.data?.local_values || {};
      // Listeli (attributeValues) özelliklerin yanı sıra, serbest-metin (allowCustom)
      // ama sistemde değeri OLAN özellikleri de göster (ör. Materyal Bileşeni → Ürün İçerik Bilgisi).
      const attrs = (a.data?.attributes || []).filter((x) => {
        const nm = x.name || x.attribute?.name;
        const hasVals = (x.attributeValues?.length || 0) > 0;
        const isCustom = x.allowCustom || x.attribute?.allowCustom;
        return hasVals || (isCustom && (lv[nm]?.length || 0) > 0);
      });
      setMpAttrs(attrs);
      setLocalValues(lv);
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

  // Otomatik değer eşleştirme — TÜM attribute'lardaki TÜM değerleri tarar.
  // ÖNCELİK: birebir (normalize) eşleşme > eşanlamlı > tek-aday substring.
  // Ayrıca: yanlış kaydedilmiş (substring kaynaklı, örn. "Cepli"→"Kargo Cepli")
  // eşleşmeleri, birebir karşılığı varsa OTOMATİK DÜZELTİR.
  const handleAutoMatchValues = () => {
    const next = { ...valueMappings };
    let matched = 0;
    let already = 0;
    let corrected = 0;
    const perAttr = {};
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
      const mpValues = mpAttr.attributeValues || [];
      const localVals = localValues[mpAttr.name || mpAttr.attribute?.name] || [];
      let localMatched = 0;

      // Trendyol değerlerinin normalize haritası (birebir eşleşme için)
      const exactMap = {};
      mpValues.forEach((mv) => {
        const n = _normVal(mv.name);
        if (n && !(n in exactMap)) exactMap[n] = mv;
      });

      localVals.forEach((lv) => {
        const key = `${id}|${lv}`;
        const lvN = _normVal(lv);
        const lvLower = String(lv).toLocaleLowerCase("tr").trim();
        // 1) Birebir (normalize) eşleşme
        let best = exactMap[lvN] || null;
        // 2) Eşanlamlı
        if (!best) {
          const cands = aliases[lvLower] || [];
          for (const a of cands) {
            const m = exactMap[_normVal(a)];
            if (m) { best = m; break; }
          }
        }
        // 3) Tek-aday substring (yalnızca tek bir Trendyol değeri içeriyorsa ve isim ≥3 karakter)
        if (!best && lvN.length >= 3) {
          const subs = mpValues.filter((mv) => {
            const mvN = _normVal(mv.name);
            return mvN.includes(lvN);
          });
          if (subs.length === 1) best = subs[0];
        }

        if (!best) return;

        if (next[key]) {
          // Zaten eşli — ama birebir karşılık varsa ve mevcut eşleşme ondan FARKLIYSA düzelt.
          if (exactMap[lvN] && String(next[key]) !== String(exactMap[lvN].id)) {
            next[key] = String(exactMap[lvN].id);
            corrected++;
            localMatched++;
          } else {
            already++;
          }
          return;
        }
        next[key] = String(best.id);
        matched++;
        localMatched++;
      });
      if (localMatched) perAttr[mpAttr.name || mpAttr.attribute?.name] = localMatched;
    });

    setValueMappings(next);
    if (matched || corrected) {
      const top = Object.entries(perAttr).sort((a, b) => b[1] - a[1]).slice(0, 5)
        .map(([k, n]) => `${k} (${n})`).join(", ");
      const parts = [];
      if (matched) parts.push(`${matched} değer eşleşti`);
      if (corrected) parts.push(`${corrected} yanlış eşleşme düzeltildi`);
      if (already) parts.push(`${already} zaten doğru`);
      toast.success(`${parts.join(" · ")}${top ? ` · En çok: ${top}` : ""}`);
    } else if (already) {
      toast.info(`Tüm değerler zaten doğru eşli (${already})`);
    } else {
      toast.info("Eşleştirilecek değer bulunamadı");
    }
  };

  const currentAttr = mpAttrs.find((a) => String(a.id ?? a.attribute?.id) === String(selectedAttrId));
  const attrName = currentAttr?.name || currentAttr?.attribute?.name;

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-base flex items-center gap-2">
              <Store size={18} className={`text-${color}-500`} />
              Değer Eşleştirme — {category?.category_name}
              <span className={`text-[10px] font-bold bg-stone-200 text-stone-700 px-2 py-0.5 rounded-full uppercase`}>
                {marketplace}
              </span>
            </DialogTitle>
            {mpAttrs.length > 0 && (
              <button
                onClick={handleAutoMatchValues}
                className="flex items-center gap-2 px-3 py-1.5 bg-stone-900 text-white rounded text-xs font-semibold hover:bg-stone-800"
                data-testid="adv-auto-match-values-btn"
                title="Tüm özellik sekmelerindeki TÜM değerleri otomatik eşleştirir"
              >
                <LinkIcon size={14} /> Tümünü Otomatik Eşleştir
              </button>
            )}
          </div>
        </DialogHeader>

        {hint && <div className="text-xs text-stone-600 bg-stone-50 border border-stone-200 rounded px-3 py-2">
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
          <div className="flex-1 flex gap-3 overflow-hidden min-h-[400px]">
            {/* Sol sidebar — özellik listesi */}
            <aside className="w-56 shrink-0 border rounded-lg overflow-hidden flex flex-col">
              <div className="bg-gray-50 px-3 py-2 border-b text-[11px] font-bold text-gray-600 uppercase tracking-wide">
                Özellikler ({mpAttrs.length})
              </div>
              {/* Özellik arama kutusu */}
              <div className="px-2 py-2 border-b bg-white flex items-center gap-1.5">
                <Search size={13} className="text-gray-400 shrink-0" />
                <input
                  type="text"
                  value={attrSearch}
                  onChange={(e) => setAttrSearch(e.target.value)}
                  placeholder="Özellik ara..."
                  className="flex-1 text-xs bg-transparent focus:outline-none placeholder:text-gray-400"
                  data-testid="attr-search-input"
                />
                {attrSearch && (
                  <button onClick={() => setAttrSearch("")} className="text-gray-400 hover:text-black" data-testid="attr-search-clear">
                    <X size={13} />
                  </button>
                )}
              </div>
              <div className="overflow-auto flex-1 divide-y">
                {(() => {
                  const aq = (attrSearch || "").toLocaleLowerCase("tr").trim();
                  const visible = aq
                    ? mpAttrs.filter((a) => (a.name || a.attribute?.name || "").toLocaleLowerCase("tr").includes(aq))
                    : mpAttrs;
                  if (visible.length === 0) {
                    return <div className="px-3 py-4 text-xs text-gray-400 text-center">"{attrSearch}" ile eşleşen özellik yok</div>;
                  }
                  return visible.map((a) => {
                  const id = String(a.id ?? a.attribute?.id);
                  const name = a.name || a.attribute?.name;
                  const localCount = (localValues[name] || []).length;
                  const mappedCount = Object.keys(valueMappings).filter(
                    (k) => k.startsWith(`${id}|`) && valueMappings[k]
                  ).length;
                  const isActive = id === String(selectedAttrId);
                  return (
                    <button
                      key={id}
                      onClick={() => setSelectedAttrId(id)}
                      className={`w-full text-left px-3 py-2 text-xs transition flex items-center justify-between gap-2 ${
                        isActive
                          ? `bg-stone-100 border-l-2 border-stone-500 font-semibold text-stone-900`
                          : "hover:bg-gray-50 border-l-2 border-transparent text-gray-700"
                      }`}
                      data-testid={`adv-attr-tab-${id}`}
                    >
                      <span className="truncate">{name}</span>
                      <span className="flex items-center gap-1 shrink-0">
                        {mappedCount > 0 && (
                          <span className="text-[9px] bg-[#E7EFE9] text-[#3F7A52] px-1 py-0.5 rounded font-bold">
                            {mappedCount}
                          </span>
                        )}
                        <span className="text-[9px] text-gray-400">{localCount}</span>
                      </span>
                    </button>
                  );
                  });
                })()}
              </div>
            </aside>

            {/* Sağ taraf — değer tablosu */}
            <div className="flex-1 border rounded-lg overflow-auto">
              {/* Arama kutusu */}
              <div className="bg-white border-b px-3 py-2 sticky top-0 z-10 flex items-center gap-2">
                <Search size={14} className="text-gray-400" />
                <input
                  type="text"
                  value={valSearch}
                  onChange={(e) => setValSearch(e.target.value)}
                  placeholder={`"${attrName || "değer"}" içinde ara (örn: s, xl, 38)...`}
                  className="flex-1 text-sm bg-transparent focus:outline-none placeholder:text-gray-400"
                  data-testid="val-search-input"
                />
                {valSearch && (
                  <button onClick={() => setValSearch("")} className="text-gray-400 hover:text-black" data-testid="val-search-clear">
                    <X size={14} />
                  </button>
                )}
                <span className="text-[10px] text-gray-400 hidden sm:inline">
                  {(() => {
                    const all = localValues[attrName] || [];
                    const q = (valSearch || "").toLocaleLowerCase("tr").trim();
                    const filtered = q ? all.filter((v) => String(v).toLocaleLowerCase("tr").includes(q)) : all;
                    const mappedN = filtered.filter((v) => valueMappings[`${selectedAttrId}|${v}`]).length;
                    return `${filtered.length} satır · ${mappedN} eşleşti`;
                  })()}
                </span>
              </div>
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-2 text-xs text-gray-500">
                      Sistem Değeri <span className="text-gray-400 font-normal">— {attrName}</span>
                    </th>
                    <th className="text-left px-4 py-2 text-xs text-gray-500 w-1/2">{marketplace} Değeri</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    const all = localValues[attrName] || [];
                    const q = (valSearch || "").toLocaleLowerCase("tr").trim();
                    const filtered = q ? all.filter((v) => String(v).toLocaleLowerCase("tr").includes(q)) : all;
                    if (filtered.length === 0) {
                      return (
                        <tr><td colSpan={2} className="py-8 text-center text-xs text-gray-400">
                          {q ? `"${valSearch}" ile eşleşen değer yok` : `Bu kategorideki ürünlerde "${attrName}" özelliği için değer yok.`}
                        </td></tr>
                      );
                    }
                    const sortedLocal = _isSizeAttrName(attrName) ? sortLikeSize(filtered, (x) => x) : filtered;
                    return sortedLocal.map((lv) => {
                      const mappedId = valueMappings[`${selectedAttrId}|${lv}`] || "";
                      const isMapped = !!mappedId;
                      const mpVals = currentAttr?.attributeValues || [];
                      const sortedMp = _isSizeAttrName(attrName) ? sortLikeSize(mpVals, (v) => v.name) : mpVals;
                      return (
                        <tr key={lv} className={`border-b hover:bg-stone-50 ${isMapped ? "bg-[#F3F7F4]" : ""}`}>
                          <td className="px-4 py-2 font-medium">
                            <div className="flex items-center gap-2">
                              <span>{lv}</span>
                              {isMapped && (
                                <span className="text-[9px] bg-[#E7EFE9] text-[#3F7A52] px-1.5 py-0.5 rounded-full font-bold">✓ EŞLEŞTİ</span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-2">
                            {sortedMp.length === 0 ? (
                              <span className="inline-flex items-center gap-1.5 text-xs text-[#3F7A52] bg-[#F3F7F4] border border-[#D9E6DE] rounded px-2 py-1" data-testid={`adv-valmap-auto-${lv}`}>
                                ✓ Otomatik gönderilir (serbest metin)
                              </span>
                            ) : (
                              <SearchableValueSelect
                                value={mappedId}
                                options={sortedMp}
                                onChange={(val) =>
                                  setValueMappings((p) => ({ ...p, [`${selectedAttrId}|${lv}`]: val }))
                                }
                                placeholder="— seçilmemiş —"
                                color={color}
                                testId={`adv-valmap-${lv}`}
                              />
                            )}
                          </td>
                        </tr>
                      );
                    });
                  })()}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t">
          <button onClick={() => onClose(false)} className="px-4 py-2 border rounded text-sm hover:bg-gray-50">İptal</button>
          <button onClick={save} disabled={saving}
            className={`flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded text-sm hover:bg-stone-800 disabled:opacity-50`}
            data-testid="adv-val-save">
            {saving && <RefreshCw size={14} className="animate-spin" />}
            Değerleri Kaydet
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
