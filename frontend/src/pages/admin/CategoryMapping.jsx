/**
 * CategoryMapping.jsx — Multi-Marketplace Kategori Eşleştirme
 *
 * Sistem kategorilerini her pazaryerindeki kategori ID'leriyle eşleştirir.
 * BrandMapping.jsx ile aynı üst yapı (13 pazaryeri sekmesi + tablo).
 *
 * Bağlantılar:
 *   - /api/category-mapping/{marketplace}
 *   - /api/categories (sistem kategorileri)
 */
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, CheckCircle2, Circle, Save, Search, Trash2, Settings, Sliders, Zap } from "lucide-react";
import SearchableMapSelect from "../../components/admin/SearchableMapSelect";
import {
  AdvancedAttributeMatchModal,
  AdvancedValueMatchModal,
} from "../../components/admin/MarketplaceAdvancedMatch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CategoryMapping() {
  const [marketplaces, setMarketplaces] = useState([]);
  const [active, setActive] = useState("trendyol");
  const [data, setData] = useState({ items: [], total: 0, matched: 0, unmatched: 0 });
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [editRow, setEditRow] = useState(null);
  const [editVal, setEditVal] = useState({ id: "", name: "" });
  const [selected, setSelected] = useState(new Set());
  const [attrMatchFor, setAttrMatchFor] = useState(null);
  const [valueMatchFor, setValueMatchFor] = useState(null);
  const [bulkAttrLoading, setBulkAttrLoading] = useState(false);
  const [bulkAttrReport, setBulkAttrReport] = useState(null);

  const token = useMemo(() => localStorage.getItem("token"), []);
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  useEffect(() => {
    axios.get(`${API}/marketplace-hub/marketplaces`, auth)
      .then((r) => setMarketplaces(r.data?.marketplaces || []))
      .catch(() => {});
    // eslint-disable-next-line
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/category-mapping/${active}`, auth);
      setData(r.data);
    } catch { toast.error("Liste yüklenemedi"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (active) load(); /* eslint-disable-next-line */ }, [active]);

  const saveRow = async (row) => {
    if (!editVal.name) { toast.info("Pazaryeri kategorisi seçin"); return; }
    try {
      await axios.post(`${API}/category-mapping/${active}/${row.category_id}`,
        { marketplace_category_id: editVal.id || null, marketplace_category_name: editVal.name }, auth);
      toast.success("Kaydedildi");
      setEditRow(null); load();
    } catch { toast.error("Kaydedilemedi"); }
  };

  const clearRow = async (row) => {
    if (!window.confirm(`"${row.category_name}" eşleşmesi silinsin mi?`)) return;
    await axios.delete(`${API}/category-mapping/${active}/${row.category_id}`, auth);
    toast.success("Silindi"); load();
  };

  const bulkDelete = async () => {
    const ids = Array.from(selected);
    if (!ids.length) { toast.info("Kayıt seçin"); return; }
    if (!window.confirm(`${ids.length} kategori eşleşmesi silinsin mi?`)) return;
    try {
      const r = await axios.post(`${API}/category-mapping/${active}/bulk-delete`, { category_ids: ids }, auth);
      toast.success(`${r.data?.deleted || 0} eşleşme silindi`);
      setSelected(new Set());
      load();
    } catch { toast.error("Toplu silme başarısız"); }
  };
  const toggleOne = (id) => {
    setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  };
  const toggleAll = (items) => {
    const allIds = items.map((r) => r.category_id);
    const allSelected = allIds.every((id) => selected.has(id)) && allIds.length;
    setSelected((s) => {
      const n = new Set(s);
      if (allSelected) allIds.forEach((id) => n.delete(id));
      else allIds.forEach((id) => n.add(id));
      return n;
    });
  };

  const resetAll = async () => {
    if (!window.confirm(`${active} için TÜM kategori eşleşmeleri silinecek.`)) return;
    const r = await axios.post(`${API}/category-mapping/${active}/reset-all`, {}, auth);
    toast.success(`${r.data.deleted} kayıt silindi`); load();
  };

  const bulkAutoMatchAttributes = async () => {
    if (!window.confirm(
      `${active} için matched tüm kategorilerin özellik eşleştirmesi otomatik yapılacak.\n\n` +
      `• Mevcut manuel eşleştirmeler korunur (ezilmez), sadece BOŞ olanlar doldurulur.\n` +
      `• Trendyol için canlı API'den attribute'lar çekilir, diğer pazaryerleri için yerel cache kullanılır.\n\n` +
      `Devam edilsin mi?`
    )) return;
    setBulkAttrLoading(true);
    setBulkAttrReport(null);
    try {
      const r = await axios.post(`${API}/category-mapping/${active}/bulk-auto-match-attributes`, {}, auth);
      setBulkAttrReport(r.data);
      toast.success(r.data?.message || "Otomatik eşleştirme tamamlandı");
      load();
    } catch (e) {
      toast.error("Otomatik eşleştirme hatası: " + (e.response?.data?.detail || e.message));
    } finally {
      setBulkAttrLoading(false);
    }
  };

  const filtered = useMemo(() => {
    if (!search) return data.items;
    const s = search.toLocaleLowerCase("tr");
    return data.items.filter((i) =>
      (i.category_name || "").toLocaleLowerCase("tr").includes(s) ||
      (i.marketplace_category_name || "").toLocaleLowerCase("tr").includes(s)
    );
  }, [data.items, search]);

  return (
    <div data-testid="category-mapping-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">Kategori Eşleştirme</h1>
          <p className="text-sm text-gray-500 mt-1">
            Sistem kategorilerinizi pazaryerlerinin kategori ağacıyla eşleştirin. Her pazaryeri için ayrı sekme.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={bulkAutoMatchAttributes}
            disabled={bulkAttrLoading || data.matched === 0}
            className="flex items-center gap-1 px-3 py-2 bg-gradient-to-r from-orange-500 to-amber-500 text-white rounded-lg text-sm font-semibold hover:from-orange-600 hover:to-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Matched tüm kategorilerdeki özellikleri sistem özellikleriyle otomatik eşleştir"
            data-testid="cat-bulk-auto-match">
            {bulkAttrLoading ? <RefreshCw size={14} className="animate-spin" /> : <Zap size={14} />}
            {bulkAttrLoading ? "Eşleşiyor..." : "Tümünü Otomatik Eşleştir"}
          </button>
          <button onClick={resetAll}
            className="flex items-center gap-1 px-3 py-2 border border-red-300 text-red-600 rounded-lg text-sm hover:bg-red-50"
            data-testid="cat-reset-all">
            <Trash2 size={14} /> Hepsini Sıfırla
          </button>
          <button onClick={load}
            className="flex items-center gap-1 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
            <RefreshCw size={14} /> Yenile
          </button>
        </div>
      </div>

      <div className="flex items-center gap-1 border-b border-gray-200 mb-4 overflow-x-auto">
        {marketplaces.map((m) => {
          const isActive = m.key === active;
          return (
            <button key={m.key} onClick={() => setActive(m.key)}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                isActive ? "border-orange-500 text-orange-600" : "border-transparent text-gray-600 hover:text-black"
              }`} data-testid={`cat-mp-tab-${m.key}`}>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-4 h-4 rounded-full flex items-center justify-center text-white text-[8px] font-black"
                      style={{ backgroundColor: m.color || "#6b7280" }}>
                  {m.name.slice(0, 1).toUpperCase()}
                </span>
                {m.name}
              </span>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-white border rounded-xl p-4">
          <div className="text-xs text-gray-500 uppercase">Toplam Kategori</div>
          <div className="text-2xl font-black mt-1">{data.total}</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="text-xs text-green-700 uppercase">Eşleşti</div>
          <div className="text-2xl font-black text-green-800 mt-1">{data.matched}</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="text-xs text-red-700 uppercase">Eşleşmedi</div>
          <div className="text-2xl font-black text-red-800 mt-1">{data.unmatched}</div>
        </div>
      </div>

      <div className="relative max-w-md mb-3">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Kategori ara..."
          className="w-full border border-gray-200 rounded-lg pl-8 pr-3 py-1.5 text-sm"
          data-testid="cat-search" />
      </div>

      {/* Toplu seçim bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 bg-orange-50 border border-orange-200 rounded-lg px-3 py-2 mb-3">
          <span className="text-sm font-semibold text-orange-900">{selected.size} seçili</span>
          <button onClick={bulkDelete}
            className="text-xs bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-lg font-medium"
            data-testid="cat-bulk-delete">
            <Trash2 size={11} className="inline mr-1" /> Seçilileri Sil
          </button>
          <button onClick={() => setSelected(new Set())}
            className="text-xs text-gray-700 hover:text-black">Seçimi Temizle</button>
        </div>
      )}

      <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
        <table className="admin-table admin-table-compact">
          <thead>
            <tr>
              <th className="w-8">
                <input type="checkbox"
                  checked={filtered.length > 0 && filtered.every((r) => selected.has(r.category_id))}
                  onChange={() => toggleAll(filtered)}
                  data-testid="cat-toggle-all" />
              </th>
              <th>Durum</th>
              <th>Sistem Kategorisi</th>
              <th>Pazaryeri Kategorisi</th>
              <th className="w-56">İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="text-center py-8 text-sm text-gray-400">Yükleniyor...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={5} className="text-center py-10 text-sm text-gray-400">Kayıt yok</td></tr>
            ) : (
              filtered.map((row) => {
                const isEditing = editRow === row.category_id;
                return (
                  <tr key={row.category_id}>
                    <td>
                      <input type="checkbox"
                        checked={selected.has(row.category_id)}
                        onChange={() => toggleOne(row.category_id)}
                        data-testid={`cat-select-${row.category_id}`} />
                    </td>
                    <td>
                      {row.status === "matched" ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                          <CheckCircle2 size={10} /> Eşleşti
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                          <Circle size={10} /> Bekliyor
                        </span>
                      )}
                    </td>
                    <td className="font-semibold text-sm">{row.category_name}</td>
                    <td>
                      {isEditing ? (
                        <SearchableMapSelect
                          optionsUrl={`/category-mapping/${active}/options`}
                          value={editVal}
                          onChange={(v) => setEditVal(v)}
                          placeholder={`${active} kategorisi ara...`}
                          data-testid={`cat-search-${row.category_id}`}
                        />
                      ) : (
                        <div className="text-sm">
                          {row.marketplace_category_name || <span className="text-gray-400">-</span>}
                          {row.marketplace_category_id && (
                            <span className="text-[10px] text-gray-400 font-mono ml-2">#{row.marketplace_category_id}</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td>
                      {isEditing ? (
                        <div className="flex gap-1">
                          <button onClick={() => saveRow(row)} className="p-1.5 bg-black text-white rounded hover:bg-gray-800">
                            <Save size={14} />
                          </button>
                          <button onClick={() => setEditRow(null)} className="px-2 text-xs text-gray-500 hover:text-black">İptal</button>
                        </div>
                      ) : (
                        <div className="flex gap-1 flex-wrap">
                          <button onClick={() => {
                            setEditRow(row.category_id);
                            setEditVal({ id: row.marketplace_category_id || "", name: row.marketplace_category_name || "" });
                          }} className="text-xs text-orange-600 hover:underline"
                            data-testid={`cat-edit-${row.category_id}`}>Düzenle</button>

                          {row.status === "matched" && row.marketplace_category_id && (
                            <>
                              <button
                                onClick={() => setAttrMatchFor(row)}
                                className="text-xs text-blue-600 hover:underline flex items-center gap-0.5"
                                title="Özellik Eşle (Zorunlu Trendyol özellikleri ile sistem özelliklerinin bağlanması)"
                                data-testid={`cat-attr-${row.category_id}`}
                              >
                                <Settings size={10} /> Özellik
                              </button>
                              <button
                                onClick={() => setValueMatchFor(row)}
                                className="text-xs text-purple-600 hover:underline flex items-center gap-0.5"
                                title="Değer Eşle (Kırmızı ↔ Red gibi)"
                                data-testid={`cat-val-${row.category_id}`}
                              >
                                <Sliders size={10} /> Değer
                              </button>
                            </>
                          )}
                          <button onClick={() => clearRow(row)}
                            className="text-xs text-red-600 hover:underline"
                            data-testid={`cat-clear-${row.category_id}`}>Sil</button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Gelişmiş Eşleştirme Modalları — tüm pazaryerleri için çalışır */}
      <AdvancedAttributeMatchModal
        open={!!attrMatchFor}
        onClose={(ok) => { setAttrMatchFor(null); if (ok) load(); }}
        marketplace={active}
        category={attrMatchFor}
      />
      <AdvancedValueMatchModal
        open={!!valueMatchFor}
        onClose={(ok) => { setValueMatchFor(null); if (ok) load(); }}
        marketplace={active}
        category={valueMatchFor}
      />

      {/* Bulk Auto-Match Raporu */}
      <Dialog open={!!bulkAttrReport} onOpenChange={() => setBulkAttrReport(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Zap size={18} className="text-orange-500" />
              Otomatik Özellik Eşleştirme Raporu — {bulkAttrReport?.marketplace}
            </DialogTitle>
          </DialogHeader>

          {bulkAttrReport && (
            <>
              <div className="grid grid-cols-3 gap-3 mt-2">
                <div className="bg-white border rounded-lg p-3">
                  <div className="text-[10px] text-gray-500 uppercase">İşlenen Kategori</div>
                  <div className="text-xl font-black mt-1">{bulkAttrReport.processed}</div>
                </div>
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                  <div className="text-[10px] text-green-700 uppercase">Yeni Eşleşme</div>
                  <div className="text-xl font-black text-green-800 mt-1">{bulkAttrReport.total_new_mappings}</div>
                </div>
                <div className="bg-gray-50 border rounded-lg p-3">
                  <div className="text-[10px] text-gray-500 uppercase">Toplam Matched</div>
                  <div className="text-xl font-black mt-1">{bulkAttrReport.total_categories}</div>
                </div>
              </div>

              <div className="mt-3 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs text-blue-800">
                {bulkAttrReport.message}
              </div>

              <div className="flex-1 overflow-auto border rounded-lg mt-3">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0 border-b">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium text-gray-600">Kategori</th>
                      <th className="text-right px-3 py-2 font-medium text-gray-600 w-20">MP Özellik</th>
                      <th className="text-right px-3 py-2 font-medium text-gray-600 w-20">Yeni</th>
                      <th className="text-center px-3 py-2 font-medium text-gray-600 w-16">Kaynak</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(bulkAttrReport.details || []).length === 0 ? (
                      <tr><td colSpan={4} className="text-center py-6 text-gray-400">Kayıt yok</td></tr>
                    ) : (
                      bulkAttrReport.details.map((d) => (
                        <tr key={d.category_id} className="border-b hover:bg-gray-50">
                          <td className="px-3 py-2">
                            <div className="font-medium">{d.category_name}</div>
                            {d.note && <div className="text-[10px] text-amber-600">{d.note}</div>}
                          </td>
                          <td className="px-3 py-2 text-right text-gray-600">{d.total_mp_attrs}</td>
                          <td className="px-3 py-2 text-right font-semibold">
                            {d.new > 0 ? (
                              <span className="text-green-600">+{d.new}</span>
                            ) : (
                              <span className="text-gray-300">0</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {d.fetched ? (
                              <span className="text-[9px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded">CANLI</span>
                            ) : d.total_mp_attrs ? (
                              <span className="text-[9px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">CACHE</span>
                            ) : (
                              <span className="text-[9px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">YOK</span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end pt-3 border-t mt-3">
                <button onClick={() => setBulkAttrReport(null)}
                  className="px-4 py-2 bg-black text-white rounded text-sm hover:bg-gray-800"
                  data-testid="bulk-report-close">
                  Kapat
                </button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
