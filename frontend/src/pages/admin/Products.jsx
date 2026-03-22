import { useState, useEffect } from "react";
import { Plus, Search, Edit, Trash2, Eye, EyeOff, Copy, Upload } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminProducts() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    slug: "",
    description: "",
    price: 0,
    sale_price: null,
    category_id: "",
    category_name: "",
    brand: "FACETTE",
    images: [],
    is_active: true,
    is_featured: false,
    is_new: false,
    stock: 0,
    sku: "",
    barcode: "",
  });

  useEffect(() => {
    fetchProducts();
    fetchCategories();
  }, [page, search]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      let url = `${API}/admin/products?page=${page}&limit=20`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      const res = await axios.get(url);
      setProducts(res.data?.products || []);
      setTotal(res.data?.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await axios.get(`${API}/categories`);
      setCategories(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editingProduct) {
        await axios.put(`${API}/products/${editingProduct.id}`, formData);
        toast.success("Ürün güncellendi");
      } else {
        await axios.post(`${API}/products`, formData);
        toast.success("Ürün eklendi");
      }
      setModalOpen(false);
      resetForm();
      fetchProducts();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Hata oluştu");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Ürünü silmek istediğinize emin misiniz?")) return;
    try {
      await axios.delete(`${API}/products/${id}`);
      toast.success("Ürün silindi");
      fetchProducts();
    } catch (err) {
      toast.error("Silme başarısız");
    }
  };

  const handleToggleActive = async (product) => {
    try {
      await axios.put(`${API}/products/${product.id}`, { ...product, is_active: !product.is_active });
      toast.success(product.is_active ? "Ürün gizlendi" : "Ürün yayınlandı");
      fetchProducts();
    } catch (err) {
      toast.error("Güncelleme başarısız");
    }
  };

  const handleDuplicate = async (product) => {
    try {
      const newProduct = { ...product, name: `${product.name} (Kopya)`, slug: `${product.slug}-copy-${Date.now()}` };
      delete newProduct.id;
      delete newProduct.created_at;
      delete newProduct.updated_at;
      await axios.post(`${API}/products`, newProduct);
      toast.success("Ürün kopyalandı");
      fetchProducts();
    } catch (err) {
      toast.error("Kopyalama başarısız");
    }
  };

  const handleImport = async () => {
    if (!importUrl) return;
    setImporting(true);
    try {
      const res = await axios.post(`${API}/import/xml?url=${encodeURIComponent(importUrl)}`);
      toast.success(`${res.data.imported} ürün import edildi`);
      setImportModalOpen(false);
      setImportUrl("");
      fetchProducts();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import başarısız");
    } finally {
      setImporting(false);
    }
  };

  const openEditModal = (product) => {
    setEditingProduct(product);
    setFormData({
      name: product.name,
      slug: product.slug,
      description: product.description || "",
      price: product.price,
      sale_price: product.sale_price,
      category_id: product.category_id || "",
      category_name: product.category_name || "",
      brand: product.brand || "FACETTE",
      images: product.images || [],
      is_active: product.is_active,
      is_featured: product.is_featured,
      is_new: product.is_new,
      stock: product.stock || 0,
      sku: product.sku || "",
      barcode: product.barcode || "",
    });
    setModalOpen(true);
  };

  const resetForm = () => {
    setEditingProduct(null);
    setFormData({
      name: "", slug: "", description: "", price: 0, sale_price: null,
      category_id: "", category_name: "", brand: "FACETTE", images: [],
      is_active: true, is_featured: false, is_new: false, stock: 0, sku: "", barcode: ""
    });
  };

  const generateSlug = (name) => {
    return name.toLowerCase()
      .replace(/ğ/g, 'g').replace(/ü/g, 'u').replace(/ş/g, 's')
      .replace(/ı/g, 'i').replace(/ö/g, 'o').replace(/ç/g, 'c')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  };

  return (
    <div data-testid="admin-products">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Ürünler</h1>
        <div className="flex gap-2">
          <button 
            onClick={() => setImportModalOpen(true)}
            className="flex items-center gap-2 bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700"
          >
            <Upload size={18} />
            XML Import
          </button>
          <button 
            onClick={() => { resetForm(); setModalOpen(true); }}
            className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
          >
            <Plus size={18} />
            Yeni Ürün
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="bg-white p-4 rounded-lg shadow-sm mb-4">
        <div className="flex gap-4">
          <div className="flex-1 relative">
            <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Ürün ara..."
              className="w-full pl-10 pr-4 py-2 border rounded focus:outline-none focus:border-black"
            />
          </div>
        </div>
      </div>

      {/* Products Table */}
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Resim</th>
              <th>ID</th>
              <th>Stok Kodu</th>
              <th>Ürün Adı</th>
              <th>Kategori</th>
              <th>Stok</th>
              <th>Fiyat</th>
              <th>Durum</th>
              <th>İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="text-center py-8">Yükleniyor...</td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center py-8 text-gray-500">Ürün bulunamadı</td>
              </tr>
            ) : (
              products.map((product) => (
                <tr key={product.id}>
                  <td>
                    {product.images?.[0] ? (
                      <img src={product.images[0]} alt="" className="w-12 h-16 object-cover bg-gray-100" />
                    ) : (
                      <div className="w-12 h-16 bg-gray-100" />
                    )}
                  </td>
                  <td className="text-xs text-gray-500">{product.id.slice(0, 8)}</td>
                  <td>{product.sku || "-"}</td>
                  <td className="font-medium max-w-[200px] truncate">{product.name}</td>
                  <td>{product.category_name || "-"}</td>
                  <td>{product.stock}</td>
                  <td>
                    {product.sale_price ? (
                      <div>
                        <span className="line-through text-gray-400 text-xs">{product.price} TL</span>
                        <br />
                        <span className="text-red-500">{product.sale_price} TL</span>
                      </div>
                    ) : (
                      `${product.price} TL`
                    )}
                  </td>
                  <td>
                    <span className={`px-2 py-1 text-xs rounded ${product.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                      {product.is_active ? "Aktif" : "Pasif"}
                    </span>
                  </td>
                  <td>
                    <div className="flex items-center gap-1">
                      <button onClick={() => handleToggleActive(product)} className="p-1 hover:bg-gray-100 rounded" title={product.is_active ? "Gizle" : "Yayınla"}>
                        {product.is_active ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                      <button onClick={() => openEditModal(product)} className="p-1 hover:bg-gray-100 rounded text-blue-600" title="Düzenle">
                        <Edit size={16} />
                      </button>
                      <button onClick={() => handleDuplicate(product)} className="p-1 hover:bg-gray-100 rounded text-green-600" title="Kopyala">
                        <Copy size={16} />
                      </button>
                      <button onClick={() => handleDelete(product.id)} className="p-1 hover:bg-gray-100 rounded text-red-500" title="Sil">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-4">
          {[...Array(Math.ceil(total / 20))].map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`w-8 h-8 rounded ${page === i + 1 ? "bg-black text-white" : "bg-white hover:bg-gray-100"}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}

      {/* Product Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Ürün Düzenle" : "Yeni Ürün"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Ürün Adı *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value, slug: generateSlug(e.target.value) })}
                  required
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Slug</label>
                <input
                  type="text"
                  value={formData.slug}
                  onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Fiyat *</label>
                <input
                  type="number"
                  value={formData.price}
                  onChange={(e) => setFormData({ ...formData, price: parseFloat(e.target.value) })}
                  required
                  step="0.01"
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">İndirimli Fiyat</label>
                <input
                  type="number"
                  value={formData.sale_price || ""}
                  onChange={(e) => setFormData({ ...formData, sale_price: e.target.value ? parseFloat(e.target.value) : null })}
                  step="0.01"
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Kategori</label>
                <select
                  value={formData.category_name}
                  onChange={(e) => setFormData({ ...formData, category_name: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                >
                  <option value="">Seçiniz</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.name}>{cat.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Stok</label>
                <input
                  type="number"
                  value={formData.stock}
                  onChange={(e) => setFormData({ ...formData, stock: parseInt(e.target.value) })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">SKU</label>
                <input
                  type="text"
                  value={formData.sku}
                  onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Barkod</label>
                <input
                  type="text"
                  value={formData.barcode}
                  onChange={(e) => setFormData({ ...formData, barcode: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Açıklama</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={4}
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Görsel URL'leri (satır satır)</label>
              <textarea
                value={formData.images.join("\n")}
                onChange={(e) => setFormData({ ...formData, images: e.target.value.split("\n").filter(Boolean) })}
                rows={3}
                placeholder="https://example.com/image1.jpg&#10;https://example.com/image2.jpg"
                className="w-full border px-3 py-2 rounded text-sm font-mono"
              />
            </div>

            <div className="flex gap-6">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                />
                <span className="text-sm">Aktif</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_featured}
                  onChange={(e) => setFormData({ ...formData, is_featured: e.target.checked })}
                />
                <span className="text-sm">Vitrin Ürünü</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_new}
                  onChange={(e) => setFormData({ ...formData, is_new: e.target.checked })}
                />
                <span className="text-sm">Yeni Ürün</span>
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t">
              <button type="button" onClick={() => setModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50">
                İptal
              </button>
              <button type="submit" className="px-4 py-2 bg-black text-white rounded hover:bg-gray-800">
                {editingProduct ? "Güncelle" : "Ekle"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Import Modal */}
      <Dialog open={importModalOpen} onOpenChange={setImportModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>XML Import</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Google Shopping / Ticimax XML formatındaki ürünleri import edin.
            </p>
            <div>
              <label className="block text-sm font-medium mb-1">XML URL</label>
              <input
                type="url"
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                placeholder="https://example.com/products.xml"
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button 
                onClick={() => setImportModalOpen(false)} 
                className="px-4 py-2 border rounded hover:bg-gray-50"
              >
                İptal
              </button>
              <button 
                onClick={handleImport}
                disabled={importing || !importUrl}
                className="px-4 py-2 bg-black text-white rounded hover:bg-gray-800 disabled:opacity-50"
              >
                {importing ? "İmport ediliyor..." : "Import Et"}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
