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
import { RefreshCw, CheckCircle2, Circle, Save, Search, Trash2 } from "lucide-react";
import SearchableMapSelect from "../../components/admin/SearchableMapSelect";

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
              <th className="w-36">İşlemler</th>
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
                        <div className="flex gap-1">
                          <button onClick={() => {
                            setEditRow(row.category_id);
                            setEditVal({ id: row.marketplace_category_id || "", name: row.marketplace_category_name || "" });
                          }} className="text-xs text-orange-600 hover:underline"
                            data-testid={`cat-edit-${row.category_id}`}>Düzenle</button>
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
    </div>
  );
}
