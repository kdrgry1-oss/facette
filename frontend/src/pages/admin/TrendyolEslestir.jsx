import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Search, RefreshCw, Check, X, 
  Store, AlertCircle, ArrowRight, Trash2, PlusCircle, Link, Key
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({
  Authorization: `Bearer ${localStorage.getItem("token")}`,
});

// ─── Attribute Matching Modal ───────────────────────────────────────────────
function AttributeMatchModal({ open, onClose, category }) {
  const [attributes, setAttributes] = useState([]);
  const [trendyolAttrs, setTrendyolAttrs] = useState([]);
  const [globalAttributes, setGlobalAttributes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mappings, setMappings] = useState({});
  const [defaultMappings, setDefaultMappings] = useState({});
  const [searchTerms, setSearchTerms] = useState({});

  useEffect(() => {
    if (!open || !category) return;
    setLoading(true);

    Promise.all([
      axios
        .get(`${API}/integrations/trendyol/categories/${category.trendyol_category_id}/attributes`, {
          headers: authHeaders(),
        })
        .catch(() => ({ data: { attributes: [] } })),
      axios
        .get(`${API}/attributes`, { headers: authHeaders() })
        .catch(() => ({ data: { attributes: [] } })),
    ]).then(([tyRes, globalRes]) => {
      const tyAtts = tyRes.data?.categoryAttributes || tyRes.data?.attributes || [];
      setTrendyolAttrs(tyAtts);

      const gAtts = globalRes.data?.attributes || [];
      setGlobalAttributes(gAtts);

      const saved = {};
      (category.attribute_mappings || []).forEach((m) => {
        if (m.trendyol_attr_id) saved[m.trendyol_attr_id] = m.local_attr;
      });
      setMappings(saved);
      
      setDefaultMappings(category.default_mappings || {});
    }).finally(() => setLoading(false));
  }, [open, category]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = Object.entries(mappings)
        .filter(([, localVal]) => localVal !== "" && localVal !== undefined && localVal !== null)
        .map(([tyId, localVal]) => ({
          local_attr: localVal,
          trendyol_attr_id: parseInt(tyId, 10),
        }))
        .filter((m) => !isNaN(m.trendyol_attr_id));
        
      await axios.post(
        `${API}/integrations/trendyol/category-mappings/${category?.id}/attributes`,
        { attribute_mappings: payload, default_mappings: defaultMappings },
        { headers: authHeaders() }
      );
      toast.success("Özellik ve varsayılan değerler kaydedildi");
      onClose(true);
    } catch {
      toast.error("Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  // Otomatik eşleştir - isimleri eşleşenleri otomatik eşleştir
  const handleAutoMatch = () => {
    const newMappings = { ...mappings };
    let matchCount = 0;
    
    trendyolAttrs.forEach((attr) => {
      const attrName = (attr.name || attr.attribute?.name || "").toLowerCase().trim();
      const attrId = attr.id || attr.attribute?.id;
      
      // Zaten eşleştirilmişse atla
      if (newMappings[attrId]) return;
      
      // Global attributes'da aynı isimde olanı bul
      const matched = globalAttributes.find((gAttr) => {
        const gName = (gAttr.name || "").toLowerCase().trim();
        // Tam eşleşme veya benzer isimler (örn: "Renk" = "renk", "Beden" = "beden")
        return gName === attrName || 
               gName.includes(attrName) || 
               attrName.includes(gName) ||
               // Yaygın eşleşmeler
               (attrName === "web color" && gName === "renk") ||
               (attrName === "color" && gName === "renk") ||
               (attrName === "size" && gName === "beden");
      });
      
      if (matched) {
        newMappings[attrId] = matched.name;
        matchCount++;
      }
    });
    
    setMappings(newMappings);
    toast.success(`${matchCount} özellik otomatik eşleştirildi`);
  };

  const requiredAttrs = trendyolAttrs.filter((a) => a.required);
  const optionalAttrs = trendyolAttrs.filter((a) => !a.required);
  const allRows = [...requiredAttrs, ...optionalAttrs];

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Store size={18} className="text-orange-500" />
              Özellik Eşleştirme — {category?.local_name}
              {category?.trendyol_category_name && (
                <>
                  <ArrowRight size={14} className="text-gray-400" />
                  <span className="text-gray-500">{category.trendyol_category_name}</span>
                </>
              )}
            </DialogTitle>
            <button
              onClick={handleAutoMatch}
              className="flex items-center gap-2 px-3 py-1.5 bg-green-500 text-white rounded text-xs font-semibold hover:bg-green-600 transition-colors"
            >
              <Link size={14} />
              Otomatik Eşleştir
            </button>
          </div>
        </DialogHeader>

        {/* Warning banner */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 text-sm text-yellow-800 space-y-1">
          <p className="font-semibold flex items-center gap-1"><AlertCircle size={14} /> Dikkat Edilmesi Gerekenler</p>
          <p>• Zorunlu alanları mutlaka eşleştirmeniz gerekmektedir.</p>
          <p>• Ticimax seçeneği olarak eşleştirilen değerler ürünlerinizde karşılığı olması gerekmektedir.</p>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <RefreshCw size={22} className="animate-spin text-gray-400" />
          </div>
        ) : allRows.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-12 text-gray-400 text-sm gap-2">
            <AlertCircle size={32} />
            <p>Bu kategori için özellik bilgisi bulunamadı.</p>
            <p className="text-xs">Önce Trendyol kategori eşleştirmesi yapın.</p>
          </div>
        ) : (
          <div className="flex-1 overflow-auto border rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0 border-b">
                <tr>
                  <th className="text-left px-4 py-2.5 w-16 text-xs text-gray-500">Zorunlu</th>
                  <th className="text-left px-4 py-2.5 text-xs text-gray-500">Trendyol Özelliği</th>
                  <th className="text-left px-4 py-2.5 text-xs text-gray-500">Yerel Özellik (Eşleştir)</th>
                  <th className="text-left px-4 py-2.5 w-20 text-xs text-gray-500">Durum</th>
                </tr>
              </thead>
              <tbody>
                {allRows.map((attr) => {
                  const attrName = attr.name || attr.attribute?.name || "Bilinmeyen Özellik";
                  const attrId = attr.id || attr.attribute?.id || attrName;
                  const mapped = mappings[attrId];
                  const hasVals = attr.attributeValues && attr.attributeValues.length > 0;
                  
                  return (
                    <tr key={attrId} className="border-b hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        {attr.required ? (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">Evet</span>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <p className="font-medium text-gray-800">{attrName}</p>
                        {attr.attributeType && (
                          <p className="text-xs text-gray-400">Tür: {attr.attributeType}</p>
                        )}
                      </td>
                      <td className="px-4 py-2.5 space-y-2">
                        <input
                          type="text"
                          list={`global-attributes-list-${attrId}`}
                          placeholder="Yerel özellik eşleştir..."
                          value={mapped || ""}
                          onChange={(e) =>
                            setMappings((prev) => ({
                              ...prev,
                              [attrId]: e.target.value,
                            }))
                          }
                          className="border rounded px-2 py-1 text-sm w-full focus:outline-none focus:ring-2 focus:ring-orange-300"
                        />
                        <datalist id={`global-attributes-list-${attrId}`}>
                          {globalAttributes.map((gAttr) => (
                            <option key={gAttr.id} value={gAttr.name} />
                          ))}
                          <option value="Renk" />
                          <option value="Beden" />
                        </datalist>
                        {(attr.allowCustom || attr.attribute?.allowCustom) ? (
                          <div className="space-y-1 p-1 bg-blue-50/50 rounded border border-blue-100 mt-2">
                             <div className="text-[10px] font-bold text-blue-800 mb-1 px-1">Özel Değer (Serbest Yazı):</div>
                             <input
                               type="text"
                               placeholder="Varsayılan metin girin..."
                               value={defaultMappings[attrId] || ""}
                               onChange={(e) => setDefaultMappings((prev) => ({...prev, [attrId]: e.target.value}))}
                               className="border border-blue-200 rounded px-2 py-1 text-xs w-full focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white"
                             />
                          </div>
                        ) : null}
                        {hasVals && (
                          <div className="space-y-1 p-1 bg-orange-50/50 rounded border border-orange-100 mt-2">
                            <div className="text-[10px] font-bold text-orange-800 mb-1 px-1">Listeden Seçin:</div>
                            <div className="relative">
                              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-orange-400" />
                              <input
                                type="text"
                                placeholder="Varsayılan Değer Ara..."
                                value={searchTerms[attrId] || ""}
                                onChange={(e) => setSearchTerms(prev => ({...prev, [attrId]: e.target.value}))}
                                className="w-full pl-6 pr-2 py-1 text-xs border-b border-transparent bg-transparent focus:bg-white focus:border-orange-300 outline-none rounded-t transition-colors"
                              />
                            </div>
                            <select
                              value={defaultMappings[attrId] || ""}
                              onChange={(e) => setDefaultMappings((prev) => ({...prev, [attrId]: e.target.value}))}
                              className="border rounded px-2 py-1 text-xs w-full focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white"
                            >
                              <option value="">Varsayılan Seçilmedi</option>
                              {attr.attributeValues
                                .filter(v => v.name.toLowerCase().includes((searchTerms[attrId] || "").toLowerCase()))
                                .map(v => (
                                <option key={v.id} value={v.id}>{v.name}</option>
                              ))}
                            </select>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {mapped || defaultMappings[attrId] ? (
                          <Check size={16} className="text-green-500 mx-auto" />
                        ) : attr.required ? (
                          <X size={16} className="text-red-400 mx-auto" />
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-3 border-t">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 border rounded text-sm hover:bg-gray-50"
          >
            İptal
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded text-sm hover:bg-orange-600 disabled:opacity-50"
          >
            {saving && <RefreshCw size={14} className="animate-spin" />}
            Eşleştirmeleri Kaydet
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Category Match Modal ─────────────────────────────────────────────────────
function CategoryMatchModal({ open, onClose, category }) {
  const [search, setSearch] = useState("");
  const [allCats, setAllCats] = useState([]);   // full list from API
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);

  // Load all Trendyol categories once when modal opens
  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setSearch("");
    setLoading(true);
    axios
      .get(`${API}/integrations/trendyol/categories?limit=5000`, { headers: authHeaders() })
      .then((res) => setAllCats(res.data?.categories || res.data || []))
      .catch(() => toast.error("Kategoriler alınamadı"))
      .finally(() => setLoading(false));
  }, [open]);

  // Client-side filter
  const filtered = search.trim()
    ? allCats.filter((c) =>
        c.name?.toLowerCase().includes(search.toLowerCase())
      )
    : allCats;

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await axios.post(
        `${API}/integrations/trendyol/category-mappings`,
        {
          local_category_id: category?.id,
          local_name: category?.local_name,
          trendyol_category_id: selected.id,
          trendyol_category_name: selected.name,
        },
        { headers: authHeaders() }
      );
      toast.success("Kategori eşleştirme kaydedildi");
      onClose(true);
    } catch {
      toast.error("Eşleştirme kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base">
            Trendyol Kategorisi Seç —{" "}
            <span className="text-gray-500">{category?.local_name}</span>
          </DialogTitle>
        </DialogHeader>

        {/* Search */}
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Kategori adıyla filtrele (ör. Gömlek)..."
            autoFocus
            className="w-full border rounded pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300"
          />
        </div>

        {/* Selected preview */}
        {selected && (
          <div className="flex items-center gap-2 px-3 py-2 bg-orange-50 border border-orange-200 rounded text-sm">
            <Check size={14} className="text-orange-500 shrink-0" />
            <span className="text-orange-700 font-medium truncate">{selected.name}</span>
            <span className="text-orange-400 font-mono text-xs ml-auto shrink-0">#{selected.id}</span>
          </div>
        )}

        {/* Category list */}
        <div className="flex-1 overflow-auto border rounded-lg">
          {loading ? (
            <div className="flex items-center justify-center py-10 gap-2 text-gray-400 text-sm">
              <RefreshCw size={18} className="animate-spin" /> Kategoriler yükleniyor...
            </div>
          ) : filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              "{search}" için sonuç bulunamadı
            </p>
          ) : (
            <div className="divide-y">
              {filtered.slice(0, 200).map((cat) => {
                const isSelected = selected?.id === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setSelected(cat)}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-2 ${
                      isSelected
                        ? "bg-orange-100 text-orange-800 font-semibold"
                        : "hover:bg-gray-50 text-gray-700"
                    }`}
                  >
                    <span className="font-mono text-xs text-gray-400 shrink-0 w-12">
                      #{cat.id}
                    </span>
                    <span className="flex-1 text-left">{cat.name}</span>
                    {isSelected && (
                      <Check size={15} className="text-orange-500 shrink-0" />
                    )}
                  </button>
                );
              })}
              {filtered.length > 200 && (
                <p className="text-center text-xs text-gray-400 py-2">
                  {filtered.length - 200} daha var — aramayı daraltın
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-3 border-t">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 border rounded text-sm hover:bg-gray-50"
          >
            İptal
          </button>
          <button
            onClick={handleSave}
            disabled={!selected || saving}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded text-sm hover:bg-orange-600 disabled:opacity-50"
          >
            {saving && <RefreshCw size={14} className="animate-spin" />}
            Eşleştir
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Value Match Modal ────────────────────────────────────────────────────────
function ValueMatchModal({ open, onClose, category }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [trendyolAttributes, setTrendyolAttributes] = useState([]);
  const [valueMappings, setValueMappings] = useState({});
  const [defaultMappings, setDefaultMappings] = useState({});
  const [selectedAttrId, setSelectedAttrId] = useState("");
  const [attrSearch, setAttrSearch] = useState("");
  const [optionSearch, setOptionSearch] = useState({});
  const [localValues, setLocalValues] = useState([]);

  const getAttrId = (attr) => attr.attribute?.id?.toString() || attr.id?.toString();
  const getAttrName = (attr) => attr.attribute?.name || attr.name || "İsimsiz";

  const fetchLocalValues = useCallback(async () => {
    if (!category) return;
    setLoading(true);
    console.log("Fetching values for category:", category.local_name, category.id);
    
    try {
      const [tyRes, lvRes] = await Promise.all([
        axios.get(`${API}/integrations/trendyol/categories/${category.trendyol_category_id}/attributes`, { headers: authHeaders() }).catch(() => ({ data: { categoryAttributes: [] } })),
        axios.get(`${API}/integrations/trendyol/category-values/${category.id}`, { headers: authHeaders() }).catch(() => ({ data: { local_values: [] } }))
      ]);

      const tyAtts = tyRes.data?.categoryAttributes || tyRes.data?.attributes || [];
      const validTyAtts = tyAtts.filter(a => a.attributeValues && a.attributeValues.length > 0);
      setTrendyolAttributes(validTyAtts);
      
      const lVals = lvRes.data?.local_values || [];
      console.log("Local values received:", lVals);
      setLocalValues(lVals);
      
      setValueMappings(category.value_mappings || {});
      setDefaultMappings(category.default_mappings || {});
      
      if (validTyAtts.length > 0 && !selectedAttrId) {
        setSelectedAttrId(getAttrId(validTyAtts[0]));
      }
    } catch (err) {
      console.error("Value fetch error:", err);
      toast.error("Değerler yüklenirken hata oluştu");
    } finally {
      setLoading(false);
    }
  }, [category, selectedAttrId]);

  useEffect(() => {
    if (open && category) {
      fetchLocalValues();
    }
  }, [open, category]);

  const handleAutoMatch = () => {
    if (!selectedAttrId) return;
    const tyAttr = trendyolAttributes.find(a => getAttrId(a) === selectedAttrId);
    if (!tyAttr) return;
    
    const localAttrName = category?.attribute_mappings?.find(m => m.trendyol_attr_id.toString() === selectedAttrId)?.local_attr;
    if (!localAttrName) {
      return toast.error("Seçili özellik henüz yerel bir özellikle eşleştirilmemiş.");
    }
    
    const localValsObj = localValues.find(v => v.attribute_name.toLowerCase() === localAttrName.toLowerCase());
    const localVals = localValsObj ? localValsObj.values : [];
    const tyVals = tyAttr.attributeValues || [];
    
    let matches = 0;
    const newMappings = { ...valueMappings };
    if (!newMappings[selectedAttrId]) newMappings[selectedAttrId] = {};
    
    const normalize = (s) => s.toString().toLowerCase().trim().replace(/[^a-z0-9]/g, '');

    localVals.forEach(lv => {
      const nLv = normalize(lv);
      // Try exact match first, then partial match
      const match = tyVals.find(tv => normalize(tv.name) === nLv) || 
                    tyVals.find(tv => normalize(tv.name).includes(nLv)) ||
                    tyVals.find(tv => nLv.includes(normalize(tv.name)));

      if (match) {
        if (newMappings[selectedAttrId][lv] !== match.id.toString()) {
            newMappings[selectedAttrId][lv] = match.id.toString();
            matches++;
        }
      }
    });
    
    setValueMappings(newMappings);
    if(matches > 0) toast.success(`${matches} değer otomatik eşleşti`);
    else toast.info("Otomatik eşleşen yeni değer bulunamadı");
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/integrations/trendyol/category-mappings/${category.id}/value-mappings`, {
        value_mappings: valueMappings,
        default_mappings: defaultMappings
      }, { headers: authHeaders() });
      toast.success("Değer ve varsayılan eşleştirmeleri kaydedildi");
      onClose(true);
    } catch {
      toast.error("Değer eşleştirmeleri kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const activeAttr = trendyolAttributes.find(a => getAttrId(a) === selectedAttrId);
  const mappedLocalAttrName = category?.attribute_mappings?.find(m => m.trendyol_attr_id.toString() === selectedAttrId)?.local_attr;
  const activeLocalValues = localValues.find(v => mappedLocalAttrName && v.attribute_name.toLowerCase() === mappedLocalAttrName.toLowerCase())?.values || [];

  return (
    <Dialog open={open} onOpenChange={() => onClose(false)}>
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Link size={18} className="text-orange-500" />
            Değer Eşleştirme — {category?.local_name}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <RefreshCw size={22} className="animate-spin text-gray-400" />
          </div>
        ) : trendyolAttributes.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-12 text-gray-400 text-sm gap-2">
            <AlertCircle size={32} />
            <p>Trendyol özellik değerleri bulunamadı.</p>
          </div>
        ) : (
          <div className="flex gap-4 flex-1 min-h-[400px]">
            {/* Sidebar with Trendyol Attributes */}
            <div className="w-1/3 border-r pr-2 flex flex-col">
              <div className="mb-3">
                <h3 className="font-semibold text-sm mb-2">Özellik Seçin</h3>
                <div className="relative">
                  <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input 
                    type="text"
                    placeholder="Özellik ara..."
                    value={attrSearch}
                    onChange={(e) => setAttrSearch(e.target.value)}
                    className="w-full pl-8 pr-2 py-1.5 text-xs border rounded-lg focus:ring-1 focus:ring-orange-300 outline-none"
                  />
                </div>
              </div>
              <div className="space-y-1 overflow-y-auto flex-1 max-h-[50vh]">
                {trendyolAttributes
                  .filter(a => getAttrName(a).toLowerCase().includes(attrSearch.toLowerCase()))
                  .map(attr => {
                    const aid = getAttrId(attr);
                    const isSelected = selectedAttrId === aid;
                    const isMapped = !!category?.attribute_mappings?.find(m => m.trendyol_attr_id.toString() === aid);
                    return (
                      <button
                        key={aid}
                        onClick={() => setSelectedAttrId(aid)}
                        className={`w-full text-left px-3 py-2 text-sm rounded transition-colors flex justify-between items-center ${isSelected ? "bg-orange-100 text-orange-800 font-medium border-l-4 border-orange-500" : "hover:bg-gray-100 text-gray-600"}`}
                      >
                        <span className={`truncate ${isMapped ? 'font-bold' : ''}`}>{getAttrName(attr)}</span>
                        {attr.required && (
                          <span className={`text-[10px] px-1.5 rounded-full ${isSelected ? 'bg-orange-500 text-white' : 'bg-red-50 text-red-500 border border-red-200'} font-black`}>
                            ZORUNLU
                          </span>
                        )}
                      </button>
                    );
                  })}
              </div>
            </div>

            {/* Main matching area */}
            <div className="w-2/3 pl-2 flex flex-col">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h3 className="font-bold text-gray-800 flex items-center gap-2">
                      {activeAttr ? getAttrName(activeAttr) : "Seçili Değer"}
                      {activeAttr?.required && <span className="text-[10px] bg-red-500 text-white px-2 py-0.5 rounded-full">ZORUNLU ÖZELLİK</span>}
                    </h3>
                    <p className="text-xs text-gray-500">
                      Önce özellik eşleştirdiğinizden emin olun (Seçili Local Özellik: {mappedLocalAttrName || <span className="text-red-500 font-bold underline">Yok</span>})
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={fetchLocalValues} 
                      title="Yerel değerleri sistemden yeniden çek"
                      className="px-3 py-1.5 bg-white hover:bg-gray-50 border rounded text-xs font-medium flex items-center gap-1 shadow-sm"
                    >
                      <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Yenile
                    </button>
                    <button onClick={handleAutoMatch} className="px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white border-orange-600 border rounded text-xs font-medium flex items-center gap-1 shadow-sm">
                      <Check size={12} /> Otomatik Eşleştir
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto max-h-[50vh] border rounded-lg p-0 bg-white">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium text-gray-500 w-2/5">Yerel Değer</th>
                        <th className="px-4 py-2 text-left font-medium text-gray-500 w-2/5">Trendyol Değeri</th>
                        <th className="px-4 py-2 text-left font-medium text-blue-500 w-1/5 bg-blue-50/30">Gönderilecek Veri</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Default value row ALWAYS visible */}
                      <tr className="bg-orange-50/50">
                        <td className="px-4 py-3 font-bold text-orange-700 italic flex items-center gap-2 border-r border-orange-100">
                          <Store size={14} /> VARSAYILAN DEĞER (FALLBACK)
                        </td>
                        <td className="px-4 py-3 border-r border-orange-100">
                          <div className="space-y-2">
                            {(activeAttr?.allowCustom || activeAttr?.attribute?.allowCustom) && (
                              <div className="bg-blue-50/80 p-1.5 rounded border border-blue-200">
                                <span className="text-[10px] font-bold text-blue-700 block mb-1">Özel Değer (Yazıyla):</span>
                                <input 
                                  type="text"
                                  placeholder="Varsayılan metin girin..."
                                  value={defaultMappings[selectedAttrId] || ""}
                                  onChange={(e) => setDefaultMappings({...defaultMappings, [selectedAttrId]: e.target.value})}
                                  className="w-full border rounded px-2 py-1 text-xs focus:ring-1 focus:ring-blue-300"
                                />
                              </div>
                            )}
                            <div className="bg-white p-1.5 rounded border border-gray-200">
                              <span className="text-[10px] font-bold text-gray-500 block mb-1">Listeden Seçin:</span>
                              <div className="relative mb-1">
                                <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                                <input 
                                  type="text"
                                  placeholder="Seçenek ara..."
                                  value={optionSearch[selectedAttrId + "_def"] || ""}
                                  onChange={(e) => setOptionSearch({...optionSearch, [selectedAttrId + "_def"]: e.target.value})}
                                  className="w-full pl-7 pr-2 py-1 text-[10px] border-b outline-none bg-transparent"
                                />
                              </div>
                              <select
                                className="w-full border rounded px-2 py-1 text-xs font-bold bg-white"
                                value={defaultMappings[selectedAttrId] || ""}
                                onChange={(e) => setDefaultMappings({...defaultMappings, [selectedAttrId]: e.target.value})}
                              >
                                <option value="">--- Varsayılan Seçilmedi ---</option>
                                {activeAttr?.attributeValues
                                  ?.filter(tv => tv.name.toLowerCase().includes((optionSearch[selectedAttrId + "_def"] || "").toLowerCase()))
                                  ?.map(tv => (
                                    <option key={tv.id} value={tv.id}>{tv.name}</option>
                                  ))}
                              </select>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 bg-blue-50/30 text-xs font-mono break-all text-blue-900 border-b border-orange-100">
                           {(() => {
                             const sel = defaultMappings[selectedAttrId];
                             if(!sel) return <span className="text-gray-400">Yok</span>;
                             const matched = activeAttr?.attributeValues?.find(tv => String(tv.id) === String(sel));
                             if(matched) return `ID: ${sel} (${matched.name})`;
                             return `Text: "${sel}"`;
                           })()}
                        </td>
                      </tr>

                      {activeLocalValues.length === 0 ? (
                        <tr>
                          <td colSpan={2} className="py-8 text-center text-gray-400 border-t">
                            {mappedLocalAttrName 
                              ? "Bu özelliğe ait ürünlerinizde bir değer bulunamadı." 
                              : "Bu Trendyol özelliğini henüz bir Yerel Özellik ile eşleştirmediniz."}
                          </td>
                        </tr>
                      ) : (
                        activeLocalValues.map(lv => (
                          <tr key={lv} className="border-t hover:bg-gray-50 transition-colors">
                            <td className="px-4 py-3 font-medium border-r border-gray-100">{lv}</td>
                            <td className="px-4 py-3 border-r border-gray-100">
                              <div className="space-y-2">
                                {(activeAttr?.allowCustom || activeAttr?.attribute?.allowCustom) && (
                                  <div className="bg-blue-50/80 p-1.5 rounded border border-blue-200">
                                    <input 
                                      type="text"
                                      placeholder="Serbest metin yazın..."
                                      value={valueMappings[selectedAttrId]?.[lv] || ""}
                                      onChange={(e) => {
                                        const val = e.target.value;
                                        setValueMappings(prev => {
                                          const next = {...prev};
                                          if(!next[selectedAttrId]) next[selectedAttrId] = {};
                                          next[selectedAttrId][lv] = val;
                                          return next;
                                        });
                                      }}
                                      className="w-full border rounded px-2 py-1 text-[11px] focus:ring-1 focus:ring-blue-300"
                                    />
                                  </div>
                                )}
                                <div className="bg-white p-1.5 rounded border border-gray-200">
                                  <div className="relative mb-1">
                                    <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                                    <input 
                                      type="text"
                                      placeholder="Listeden ara..."
                                      value={optionSearch[selectedAttrId + "_" + lv] || ""}
                                      onChange={(e) => setOptionSearch({...optionSearch, [selectedAttrId + "_" + lv]: e.target.value})}
                                      className="w-full pl-6 pr-2 py-0.5 text-[9px] border-b outline-none bg-transparent"
                                    />
                                  </div>
                                  <select
                                    className={`w-full border rounded px-2 py-1 text-[11px] transition-all focus:ring-1 focus:ring-orange-300 ${valueMappings[selectedAttrId]?.[lv] ? 'border-green-500 bg-green-50/20 font-semibold text-green-800' : ''}`}
                                    value={valueMappings[selectedAttrId]?.[lv] || ""}
                                    onChange={(e) => {
                                      const val = e.target.value;
                                      setValueMappings(prev => {
                                        const next = {...prev};
                                        if(!next[selectedAttrId]) next[selectedAttrId] = {};
                                        next[selectedAttrId][lv] = val;
                                        return next;
                                      });
                                    }}
                                  >
                                    <option value="">--- Seçiniz ---</option>
                                    {activeAttr?.attributeValues
                                      ?.filter(tv => tv.name.toLowerCase().includes((optionSearch[selectedAttrId + "_" + lv] || "").toLowerCase()))
                                      ?.map(tv => (
                                        <option key={tv.id} value={tv.id}>{tv.name}</option>
                                      ))}
                                  </select>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 bg-blue-50/30 text-xs font-mono break-all text-blue-900 border-b border-gray-100">
                               {(() => {
                                 const sel = valueMappings[selectedAttrId]?.[lv];
                                 if(!sel) return <span className="text-gray-400">Boş (Varsayılan Gönderilir)</span>;
                                 const matched = activeAttr?.attributeValues?.find(tv => String(tv.id) === String(sel));
                                 if(matched) return `ID: ${sel} (${matched.name})`;
                                 return `Text: "${sel}"`;
                               })()}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-4 border-t mt-2">
          <button onClick={() => onClose(false)} className="px-4 py-2 border rounded text-sm hover:bg-gray-50">Kapat</button>
          <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded text-sm hover:bg-orange-600">
            {saving && <RefreshCw size={14} className="animate-spin" />} Kaydet
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TrendyolEslestir() {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState("");
  const [hideParents, setHideParents] = useState(true);
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [matchModal, setMatchModal] = useState(null);
  const [attrModal, setAttrModal] = useState(null);
  const [valMatchModal, setValMatchModal] = useState(null);
  const [rowFilters, setRowFilters] = useState({});

  const fetchCategories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/integrations/trendyol/category-mappings`, {
        headers: authHeaders(),
      });
      setCategories(res.data?.mappings || res.data || []);
    } catch {
      // If endpoint doesn't exist yet, load local categories as base
      try {
        const res = await axios.get(`${API}/categories?limit=100`, {
          headers: authHeaders(),
        });
        const cats = (res.data?.categories || res.data || []).map((c) => ({
          id: c.id || c._id,
          local_name: c.name,
          trendyol_category_id: null,
          trendyol_category_name: null,
          attribute_mappings: [],
          is_matched: false,
        }));
        setCategories(cats);
      } catch {
        setCategories([]);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch fresh local categories from DB and merge any new ones into the list
  const syncLocalCategories = useCallback(async () => {
    setSyncing(true);
    try {
      const res = await axios.get(`${API}/categories?limit=500`, {
        headers: authHeaders(),
      });
      const localCats = res.data?.categories || res.data || [];
      setCategories((prev) => {
        const existing = new Set(prev.map((c) => String(c.id || c.local_category_id)));
        const newOnes = localCats
          .filter((c) => !existing.has(String(c.id || c._id)))
          .map((c) => ({
            id: c.id || c._id,
            local_name: c.name,
            trendyol_category_id: null,
            trendyol_category_name: null,
            attribute_mappings: [],
            has_children: c.has_children ?? (c.children_count > 0),
            is_matched: false,
          }));
        if (newOnes.length === 0) {
          toast.info("Eklenecek yeni kategori bulunamadı");
          return prev;
        }
        toast.success(`${newOnes.length} yeni kategori listeye eklendi`);
        return [...prev, ...newOnes];
      });
    } catch {
      toast.error("Kategoriler alınamadı");
    } finally {
      setSyncing(false);
    }
  }, []);

  // Delete a single mapping
  const handleDelete = async (cat) => {
    toast(`"${cat.local_name}" eşleştirmesi silinsin mi?`, {
      action: {
        label: 'Sil',
        onClick: async () => {
          try {
            await axios.delete(
              `${API}/integrations/trendyol/category-mappings/${cat.id}`,
              { headers: authHeaders() }
            );
            setCategories((prev) => prev.filter((c) => c.id !== cat.id));
            toast.success('Kategori listeden kaldırıldı');
          } catch {
            toast.error('İşlem başarısız oldu');
          }
        }
      },
      cancel: { label: 'İptal', onClick: () => {} },
      duration: 8000,
    });
  };

  const handleBulkDelete = async () => {
    if (selectedRows.size === 0) return;
    toast(`${selectedRows.size} kategoriyi listeden kaldırmak istediğinize emin misiniz?`, {
      action: {
        label: 'Sil',
        onClick: async () => {
          setLoading(true);
          try {
            await axios.post(
              `${API}/integrations/trendyol/category-mappings/bulk-delete`,
              { category_ids: Array.from(selectedRows) },
              { headers: authHeaders() }
            );
            setCategories((prev) => prev.filter((c) => !selectedRows.has(c.id)));
            setSelectedRows(new Set());
            toast.success('Seçili kategoriler kaldırıldı');
          } catch (err) {
            toast.error('Kategoriler silinemedi');
          } finally {
            setLoading(false);
          }
        }
      },
      cancel: { label: 'İptal', onClick: () => {} },
      duration: 8000,
    });
  };

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  const handleSyncSelected = async () => {
    if (selectedRows.size === 0) return;
    
    // Build payload mapping selected categories to their filters
    const categoryFiltersList = Array.from(selectedRows).map((catId) => ({
      category_id: catId,
      filters: rowFilters[catId] || {}
    }));

    toast(`${selectedRows.size} kategorideki ürünler Trendyol'a aktarılsın mı?`, {
      action: {
        label: 'Aktar',
        onClick: async () => {
          setLoading(true);
          try {
            await axios.post(
              `${API}/integrations/trendyol/products/sync`,
              { category_filters: categoryFiltersList },
              { headers: authHeaders() }
            );
            toast.success("Aktarım işlemi sıraya alındı ve başarıyla başlatıldı");
            setSelectedRows(new Set()); // Deselect all after start
          } catch (err) {
            toast.error("Aktarım başlatılamadı: " + (err.response?.data?.detail || ""));
          } finally {
            setLoading(false);
          }
        }
      },
      cancel: { label: 'İptal', onClick: () => {} },
      duration: 8000,
    });
  };

  const handleSyncInventorySelected = async () => {
    if (selectedRows.size === 0) return;
    const names = categories
      .filter((c) => selectedRows.has(c.id))
      .map((c) => c.local_name)
      .join(", ");

    toast(`${selectedRows.size} kategori için stok/fiyat güncellensin mi? (${names})`, {
      action: {
        label: 'Güncelle',
        onClick: async () => {
          try {
            await axios.post(
              `${API}/integrations/trendyol/products/inventory-sync`,
              {},
              { headers: authHeaders() }
            );
            toast.success('Stok ve fiyat güncelleme sıraya alındı');
          } catch (err) {
            toast.error('Güncelleme başlatılamadı: ' + (err.response?.data?.detail || ''));
          }
        }
      },
      cancel: { label: 'İptal', onClick: () => {} },
      duration: 8000,
    });
  };

  const filtered = categories.filter((c) => {
    if (hideParents && c.has_children) return false;
    if (!search) return true;
    return (
      c.local_name?.toLowerCase().includes(search.toLowerCase()) ||
      c.trendyol_category_name?.toLowerCase().includes(search.toLowerCase())
    );
  });

  const toggleRow = (id) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedRows.size === filtered.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(filtered.map((c) => c.id)));
    }
  };

  const matchedCount = categories.filter((c) => c.trendyol_category_id).length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-800">Trendyol Kategori Eşleştirme</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Kategori eşleştirmelerini yaparak, kategorideki ürünleri pazaryerine aktarabilirsiniz.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 bg-gray-100 border rounded px-3 py-1.5">
            {matchedCount} / {categories.length} eşleştirildi
          </span>
          <button
            onClick={syncLocalCategories}
            disabled={syncing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 text-white text-sm rounded hover:bg-orange-600 disabled:opacity-50"
          >
            <PlusCircle size={14} className={syncing ? "animate-spin" : ""} />
            Kategori Ekle
          </button>
          <button
            onClick={fetchCategories}
            className="flex items-center gap-1 px-3 py-1.5 border rounded text-sm hover:bg-gray-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Yenile
          </button>
        </div>
      </div>

      {/* Search Filter */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
        <div className="flex items-center gap-2 text-xs font-medium text-yellow-800 mb-2">
          <AlertCircle size={14} />
          ÜRÜNE GÖRE FİLTRELEME
        </div>
        <p className="text-xs text-yellow-700 mb-3">
          Bu alan aktarım yapılacak kategori içerisinde ürün filtreleme alanıdır.
        </p>
        <div className="relative w-full max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Tanımlarda Ara..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full border bg-white rounded pl-8 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-300"
          />
        </div>
        <label className="flex items-center gap-2 mt-3 cursor-pointer text-xs text-yellow-800 select-none">
          <input
            type="checkbox"
            checked={hideParents}
            onChange={(e) => setHideParents(e.target.checked)}
            className="rounded"
          />
          Sadece aktarım yapılabilir (yaprak) kategorileri göster
        </label>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selectedRows.size === filtered.length && filtered.length > 0}
                    onChange={toggleAll}
                    className="rounded"
                  />
                </th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium w-12">ID</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">Yerel Kategori</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium">Trendyol Kategorisi</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium w-48">Aktarım Filtreleri</th>
                <th className="px-4 py-3 text-center text-xs text-gray-500 font-medium w-20">Eşleşti</th>
                <th className="px-4 py-3 text-left text-xs text-gray-500 font-medium w-40">İşlemler</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center">
                    <RefreshCw size={20} className="animate-spin text-gray-300 mx-auto" />
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-16 text-center text-sm text-gray-400">
                    <Store size={36} className="mx-auto mb-2 text-gray-200" />
                    Kategori bulunamadı
                  </td>
                </tr>
              ) : (
                filtered.map((cat) => (
                  <tr
                    key={cat.id}
                    className={`hover:bg-gray-50 transition-colors ${
                      selectedRows.has(cat.id) ? "bg-orange-50" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedRows.has(cat.id)}
                        onChange={() => toggleRow(cat.id)}
                        className="rounded"
                      />
                    </td>
                    <td className="px-4 py-3 text-xs font-mono text-gray-400">{cat.id}</td>
                    <td className="px-4 py-3 font-medium text-gray-800">{cat.local_name}</td>
                    <td className="px-4 py-3">
                      {cat.trendyol_category_name ? (
                        <span className="text-gray-700">{cat.trendyol_category_name}</span>
                      ) : (
                        <span className="text-xs text-gray-400 italic">Eşleştirilmedi</span>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex xl:flex-row flex-col gap-1 w-full max-w-[200px]">
                        <input
                          type="text"
                          placeholder="Stok Kodu (Opsiyonel)"
                          className="w-full text-[10px] px-2 py-1 border border-gray-200 rounded outline-none focus:border-orange-400 bg-white"
                          value={rowFilters[cat.id]?.stock_code || ""}
                          onChange={(e) => setRowFilters({...rowFilters, [cat.id]: {...(rowFilters[cat.id] || {}), stock_code: e.target.value}})}
                        />
                        <input
                          type="date"
                          title="Bu tarihten (dahil) sonra eklenen ürünleri aktar"
                          className="w-full text-[10px] px-2 py-1 border border-gray-200 rounded outline-none focus:border-orange-400 bg-white"
                          value={rowFilters[cat.id]?.date_range || ""}
                          onChange={(e) => setRowFilters({...rowFilters, [cat.id]: {...(rowFilters[cat.id] || {}), date_range: e.target.value}})}
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {cat.trendyol_category_id ? (
                        <Check size={16} className="text-green-500 mx-auto" />
                      ) : (
                        <X size={16} className="text-red-300 mx-auto" />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setMatchModal(cat)}
                          className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                        >
                          Düzenle
                        </button>
                        {cat.trendyol_category_id && (
                          <>
                            <button
                              onClick={() => setAttrModal(cat)}
                              className="px-2.5 py-1 text-xs bg-orange-500 text-white rounded hover:bg-orange-600 transition-colors"
                            >
                              Özellikler
                            </button>
                            <button
                              onClick={() => setValMatchModal(cat)}
                              className="px-2.5 py-1 text-xs text-orange-600 bg-orange-100 border border-orange-200 rounded hover:bg-orange-200 transition-colors"
                              title="Değerleri Eşleştir"
                            >
                              <Key size={13} className="inline mr-1" /> Değerler
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => handleDelete(cat)}
                          className="px-2 py-1 text-xs text-red-400 border border-red-200 rounded hover:bg-red-50 hover:text-red-600 transition-colors"
                          title="Listeden Kaldır"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer actions */}
        {filtered.length > 0 && (
          <div className="border-t px-4 py-3 flex items-center gap-2 bg-gray-50">
            <button
              onClick={handleSyncSelected}
              disabled={selectedRows.size === 0}
              className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40"
            >
              Seçilenleri Aktar
            </button>
            <button
              onClick={handleSyncInventorySelected}
              disabled={selectedRows.size === 0}
              className="px-3 py-1.5 text-xs bg-orange-500 text-white rounded hover:bg-orange-600 disabled:opacity-40"
            >
              Stok / Fiyat Güncelle
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={selectedRows.size === 0}
              className="px-3 py-1.5 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50 disabled:opacity-40"
            >
              Seçilenleri Sil
            </button>
            <span className="text-xs text-gray-400 ml-auto">
              {selectedRows.size} seçili / {filtered.length} toplam
            </span>
          </div>
        )}
      </div>

      {/* Category Match Modal */}
      <CategoryMatchModal
        open={!!matchModal}
        category={matchModal}
        onClose={(refresh) => {
          setMatchModal(null);
          if (refresh) fetchCategories();
        }}
      />

      {/* Attribute Match Modal */}
      <AttributeMatchModal
        open={!!attrModal}
        category={attrModal}
        onClose={(refresh) => {
          setAttrModal(null);
          if (refresh) fetchCategories();
        }}
      />

      {/* Value Match Modal */}
      <ValueMatchModal
        open={!!valMatchModal}
        category={valMatchModal}
        onClose={(refresh) => {
          setValMatchModal(null);
          if (refresh) fetchCategories();
        }}
      />
    </div>
  );
}
