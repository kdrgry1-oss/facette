import { useState, useEffect, useRef } from "react";
import { Plus, Search, Edit, Trash2, Eye, EyeOff, Copy, Upload, Image, X, Link2, MoreHorizontal } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../components/ui/tabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminProducts() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const [formData, setFormData] = useState({
    name: "", slug: "", description: "", short_description: "",
    price: 0, sale_price: null, category_name: "", brand: "FACETTE",
    images: [], is_active: true, is_featured: false, is_new: false,
    stock: 0, stock_code: "", barcode: "", sku: "",
    // Ticimax fields
    variation_code: "", gtip_code: "", unit: "ADET", keywords: "",
    supplier: "FACETTE", max_installment: 9, purchase_price: 0,
    market_price: 0, vat_rate: 20, vat_included: true, currency: "TRY",
    cargo_weight: 0, product_weight: 0, width: 0, depth: 0, height: 0,
    min_order_qty: 1, max_order_qty: 999, estimated_delivery: "2-3",
    is_free_shipping: false, is_showcase: false,
    meta_title: "", meta_description: "", meta_keywords: "",
  });

  useEffect(() => {
    fetchProducts();
    fetchCategories();
  }, [page, search]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `${API}/products?page=${page}&limit=20`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
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

  const handleImageUpload = async (e) => {
    const files = e.target.files;
    if (!files.length) return;

    setUploading(true);
    const token = localStorage.getItem('token');
    const newImages = [...formData.images];

    for (let file of files) {
      try {
        const fd = new FormData();
        fd.append('file', file);
        const res = await axios.post(`${API}/upload/image`, fd, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        });
        if (res.data.path) {
          newImages.push(`${API.replace('/api', '')}/api/files/${res.data.path}`);
        }
      } catch (err) {
        toast.error(`${file.name} yüklenemedi`);
      }
    }

    setFormData({ ...formData, images: newImages });
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeImage = (index) => {
    const newImages = [...formData.images];
    newImages.splice(index, 1);
    setFormData({ ...formData, images: newImages });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      if (editingProduct) {
        await axios.put(`${API}/products/${editingProduct.id}`, formData, { headers });
        toast.success("Ürün güncellendi");
      } else {
        await axios.post(`${API}/products`, formData, { headers });
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
      const token = localStorage.getItem('token');
      await axios.delete(`${API}/products/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      toast.success("Ürün silindi");
      fetchProducts();
    } catch (err) {
      toast.error("Silme başarısız");
    }
  };

  const openEditModal = (product) => {
    setEditingProduct(product);
    setFormData({
      name: product.name || "",
      slug: product.slug || "",
      description: product.description || "",
      short_description: product.short_description || "",
      price: product.price || 0,
      sale_price: product.sale_price || null,
      category_name: product.category_name || "",
      brand: product.brand || "FACETTE",
      images: product.images || [],
      is_active: product.is_active ?? true,
      is_featured: product.is_featured ?? false,
      is_new: product.is_new ?? false,
      stock: product.stock || 0,
      stock_code: product.stock_code || "",
      barcode: product.barcode || "",
      sku: product.sku || "",
      variation_code: product.variation_code || "",
      gtip_code: product.gtip_code || "",
      unit: product.unit || "ADET",
      keywords: product.keywords || "",
      supplier: product.supplier || "FACETTE",
      max_installment: product.max_installment || 9,
      purchase_price: product.purchase_price || 0,
      market_price: product.market_price || 0,
      vat_rate: product.vat_rate || 20,
      vat_included: product.vat_included ?? true,
      currency: product.currency || "TRY",
      cargo_weight: product.cargo_weight || 0,
      product_weight: product.product_weight || 0,
      width: product.width || 0,
      depth: product.depth || 0,
      height: product.height || 0,
      min_order_qty: product.min_order_qty || 1,
      max_order_qty: product.max_order_qty || 999,
      estimated_delivery: product.estimated_delivery || "2-3",
      is_free_shipping: product.is_free_shipping ?? false,
      is_showcase: product.is_showcase ?? false,
      meta_title: product.meta_title || "",
      meta_description: product.meta_description || "",
      meta_keywords: product.meta_keywords || "",
    });
    setModalOpen(true);
  };

  const resetForm = () => {
    setEditingProduct(null);
    setFormData({
      name: "", slug: "", description: "", short_description: "",
      price: 0, sale_price: null, category_name: "", brand: "FACETTE",
      images: [], is_active: true, is_featured: false, is_new: false,
      stock: 0, stock_code: "", barcode: "", sku: "",
      variation_code: "", gtip_code: "", unit: "ADET", keywords: "",
      supplier: "FACETTE", max_installment: 9, purchase_price: 0,
      market_price: 0, vat_rate: 20, vat_included: true, currency: "TRY",
      cargo_weight: 0, product_weight: 0, width: 0, depth: 0, height: 0,
      min_order_qty: 1, max_order_qty: 999, estimated_delivery: "2-3",
      is_free_shipping: false, is_showcase: false,
      meta_title: "", meta_description: "", meta_keywords: "",
    });
  };

  const generateSlug = (name) => {
    return name.toLowerCase()
      .replace(/ğ/g, 'g').replace(/ü/g, 'u').replace(/ş/g, 's')
      .replace(/ı/g, 'i').replace(/ö/g, 'o').replace(/ç/g, 'c')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  };

  const handleDuplicate = async (product) => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      const newProduct = {
        ...product,
        name: `${product.name} (Kopya)`,
        slug: `${product.slug}-kopya-${Date.now()}`,
        stock_code: product.stock_code ? `${product.stock_code}-COPY` : '',
        barcode: '',
      };
      delete newProduct.id;
      delete newProduct._id;
      
      await axios.post(`${API}/products`, newProduct, { headers });
      toast.success("Ürün kopyalandı");
      fetchProducts();
    } catch (err) {
      toast.error("Kopyalama başarısız");
    }
  };

  const toggleProductStatus = async (product) => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      await axios.put(`${API}/products/${product.id}`, {
        ...product,
        is_active: !product.is_active
      }, { headers });
      
      toast.success(product.is_active ? "Ürün pasife alındı" : "Ürün aktifleştirildi");
      fetchProducts();
    } catch (err) {
      toast.error("İşlem başarısız");
    }
  };

  return (
    <div data-testid="admin-products">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Ürünler ({total})</h1>
        <button 
          onClick={() => { resetForm(); setModalOpen(true); }}
          className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
        >
          <Plus size={18} />
          Yeni Ürün
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="Ürün ara (ad, stok kodu, barkod)..."
          className="w-full pl-10 pr-4 py-2 border rounded"
        />
      </div>

      {/* Products Table */}
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Görsel</th>
              <th>Ürün Adı</th>
              <th>Stok Kodu</th>
              <th>Barkod</th>
              <th>Fiyat</th>
              <th>Stok</th>
              <th>Durum</th>
              <th>İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8">Yükleniyor...</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-8 text-gray-500">Ürün bulunamadı</td></tr>
            ) : (
              products.map((product) => (
                <tr key={product.id}>
                  <td>
                    {product.images?.[0] ? (
                      <img src={product.images[0]} alt="" className="w-12 h-16 object-cover" />
                    ) : (
                      <div className="w-12 h-16 bg-gray-100 flex items-center justify-center">
                        <Image size={16} className="text-gray-400" />
                      </div>
                    )}
                  </td>
                  <td>
                    <p className="font-medium line-clamp-1">{product.name}</p>
                    <p className="text-xs text-gray-500">{product.category_name}</p>
                  </td>
                  <td className="text-sm">{product.stock_code || '-'}</td>
                  <td className="text-sm">{product.barcode || '-'}</td>
                  <td>
                    {product.sale_price ? (
                      <div>
                        <span className="text-red-600">{product.sale_price?.toFixed(2)} TL</span>
                        <span className="text-xs text-gray-400 line-through block">{product.price?.toFixed(2)} TL</span>
                      </div>
                    ) : (
                      <span>{product.price?.toFixed(2)} TL</span>
                    )}
                  </td>
                  <td className={product.stock < 5 ? "text-red-600 font-medium" : ""}>{product.stock}</td>
                  <td>
                    <span className={`px-2 py-1 text-xs rounded ${product.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                      {product.is_active ? 'Aktif' : 'Pasif'}
                    </span>
                  </td>
                  <td>
                    <div className="flex gap-1">
                      <button onClick={() => openEditModal(product)} className="p-1.5 hover:bg-gray-100 rounded" title="Düzenle">
                        <Edit size={16} />
                      </button>
                      <button onClick={() => handleDuplicate(product)} className="p-1.5 hover:bg-gray-100 rounded" title="Kopyala">
                        <Copy size={16} />
                      </button>
                      <button onClick={() => toggleProductStatus(product)} className="p-1.5 hover:bg-gray-100 rounded" title={product.is_active ? "Pasife Al" : "Aktifleştir"}>
                        {product.is_active ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                      <DropdownMenu>
                        <DropdownMenuTrigger className="p-1.5 hover:bg-gray-100 rounded">
                          <MoreHorizontal size={16} />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => window.open(`/urun/${product.slug}`, '_blank')}>
                            <Eye size={14} className="mr-2" /> Ürünü Görüntüle
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => navigator.clipboard.writeText(`${window.location.origin}/urun/${product.slug}`)}>
                            <Link2 size={14} className="mr-2" /> Link Kopyala
                          </DropdownMenuItem>
                          <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(product.id)}>
                            <Trash2 size={14} className="mr-2" /> Sil
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
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

      {/* Product Modal with Tabs */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Ürün Düzenle" : "Yeni Ürün"}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit}>
            <Tabs defaultValue="basic" className="w-full">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="basic">Temel</TabsTrigger>
                <TabsTrigger value="pricing">Fiyat</TabsTrigger>
                <TabsTrigger value="images">Görseller</TabsTrigger>
                <TabsTrigger value="inventory">Stok</TabsTrigger>
                <TabsTrigger value="variants">Varyantlar</TabsTrigger>
                <TabsTrigger value="seo">SEO</TabsTrigger>
              </TabsList>

              {/* Basic Info Tab */}
              <TabsContent value="basic" className="space-y-4 mt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Ürün Adı *</label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => {
                        setFormData({ 
                          ...formData, 
                          name: e.target.value,
                          slug: generateSlug(e.target.value)
                        });
                      }}
                      className="w-full border px-3 py-2 rounded"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Slug</label>
                    <input
                      type="text"
                      value={formData.slug}
                      onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Kategori</label>
                    <select
                      value={formData.category_name}
                      onChange={(e) => setFormData({ ...formData, category_name: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    >
                      <option value="">Seçiniz</option>
                      <option value="EN YENİLER">EN YENİLER</option>
                      <option value="Elbise">Elbise</option>
                      <option value="Bluz">Bluz</option>
                      <option value="Gömlek">Gömlek</option>
                      <option value="Pantolon">Pantolon</option>
                      <option value="Etek">Etek</option>
                      <option value="Ceket">Ceket</option>
                      <option value="Kazak">Kazak</option>
                      <option value="Aksesuar">Aksesuar</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Marka</label>
                    <input
                      type="text"
                      value={formData.brand}
                      onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">Kısa Açıklama</label>
                  <input
                    type="text"
                    value={formData.short_description}
                    onChange={(e) => setFormData({ ...formData, short_description: e.target.value })}
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1">Açıklama</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    rows={4}
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>

                <div className="flex gap-4">
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
                      checked={formData.is_new}
                      onChange={(e) => setFormData({ ...formData, is_new: e.target.checked })}
                    />
                    <span className="text-sm">Yeni Ürün</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={formData.is_featured}
                      onChange={(e) => setFormData({ ...formData, is_featured: e.target.checked })}
                    />
                    <span className="text-sm">Öne Çıkan</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={formData.is_showcase}
                      onChange={(e) => setFormData({ ...formData, is_showcase: e.target.checked })}
                    />
                    <span className="text-sm">Vitrin</span>
                  </label>
                </div>
              </TabsContent>

              {/* Pricing Tab */}
              <TabsContent value="pricing" className="space-y-4 mt-4">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Satış Fiyatı *</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.price}
                      onChange={(e) => setFormData({ ...formData, price: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">İndirimli Fiyat</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.sale_price || ''}
                      onChange={(e) => setFormData({ ...formData, sale_price: e.target.value ? parseFloat(e.target.value) : null })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Alış Fiyatı</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.purchase_price}
                      onChange={(e) => setFormData({ ...formData, purchase_price: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Piyasa Fiyatı</label>
                    <input
                      type="number"
                      step="0.01"
                      value={formData.market_price}
                      onChange={(e) => setFormData({ ...formData, market_price: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">KDV Oranı (%)</label>
                    <input
                      type="number"
                      value={formData.vat_rate}
                      onChange={(e) => setFormData({ ...formData, vat_rate: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Para Birimi</label>
                    <select
                      value={formData.currency}
                      onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    >
                      <option value="TRY">TRY</option>
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                    </select>
                  </div>
                </div>

                <div className="flex gap-4">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={formData.vat_included}
                      onChange={(e) => setFormData({ ...formData, vat_included: e.target.checked })}
                    />
                    <span className="text-sm">KDV Dahil</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={formData.is_free_shipping}
                      onChange={(e) => setFormData({ ...formData, is_free_shipping: e.target.checked })}
                    />
                    <span className="text-sm">Ücretsiz Kargo</span>
                  </label>
                </div>
              </TabsContent>

              {/* Images Tab */}
              <TabsContent value="images" className="space-y-4 mt-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Ürün Görselleri</label>
                  <div className="grid grid-cols-5 gap-3 mb-4">
                    {formData.images.map((img, index) => (
                      <div key={index} className="relative aspect-[3/4] bg-gray-100">
                        <img src={img} alt="" className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => removeImage(index)}
                          className="absolute top-1 right-1 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600"
                        >
                          <X size={14} />
                        </button>
                        {index === 0 && (
                          <span className="absolute bottom-1 left-1 text-[10px] bg-black text-white px-1 py-0.5">Ana Görsel</span>
                        )}
                      </div>
                    ))}
                    
                    {/* Upload Button */}
                    <label className="aspect-[3/4] border-2 border-dashed border-gray-300 flex flex-col items-center justify-center cursor-pointer hover:border-black transition-colors">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={handleImageUpload}
                        className="hidden"
                      />
                      {uploading ? (
                        <span className="text-xs text-gray-500">Yükleniyor...</span>
                      ) : (
                        <>
                          <Upload size={24} className="text-gray-400 mb-2" />
                          <span className="text-xs text-gray-500">Görsel Yükle</span>
                        </>
                      )}
                    </label>
                  </div>
                  <p className="text-xs text-gray-500">İlk görsel ana görsel olarak kullanılır. Son görsel beden tablosu olarak ayarlanabilir.</p>
                </div>
              </TabsContent>

              {/* Inventory Tab */}
              <TabsContent value="inventory" className="space-y-4 mt-4">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Stok Kodu</label>
                    <input
                      type="text"
                      value={formData.stock_code}
                      onChange={(e) => setFormData({ ...formData, stock_code: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Barkod</label>
                    <input
                      type="text"
                      value={formData.barcode}
                      onChange={(e) => setFormData({ ...formData, barcode: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">SKU</label>
                    <input
                      type="text"
                      value={formData.sku}
                      onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Stok Adedi</label>
                    <input
                      type="number"
                      value={formData.stock}
                      onChange={(e) => setFormData({ ...formData, stock: parseInt(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Min. Sipariş Adedi</label>
                    <input
                      type="number"
                      value={formData.min_order_qty}
                      onChange={(e) => setFormData({ ...formData, min_order_qty: parseInt(e.target.value) || 1 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Max. Sipariş Adedi</label>
                    <input
                      type="number"
                      value={formData.max_order_qty}
                      onChange={(e) => setFormData({ ...formData, max_order_qty: parseInt(e.target.value) || 999 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Kargo Ağırlığı (kg)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.cargo_weight}
                      onChange={(e) => setFormData({ ...formData, cargo_weight: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Genişlik (cm)</label>
                    <input
                      type="number"
                      value={formData.width}
                      onChange={(e) => setFormData({ ...formData, width: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Derinlik (cm)</label>
                    <input
                      type="number"
                      value={formData.depth}
                      onChange={(e) => setFormData({ ...formData, depth: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Yükseklik (cm)</label>
                    <input
                      type="number"
                      value={formData.height}
                      onChange={(e) => setFormData({ ...formData, height: parseFloat(e.target.value) || 0 })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium mb-1">Tedarikçi</label>
                    <input
                      type="text"
                      value={formData.supplier}
                      onChange={(e) => setFormData({ ...formData, supplier: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Tahmini Teslimat (gün)</label>
                    <input
                      type="text"
                      value={formData.estimated_delivery}
                      onChange={(e) => setFormData({ ...formData, estimated_delivery: e.target.value })}
                      className="w-full border px-3 py-2 rounded"
                    />
                  </div>
                </div>
              </TabsContent>

              {/* SEO Tab */}
              <TabsContent value="seo" className="space-y-4 mt-4">
                <div>
                  <label className="block text-sm font-medium mb-1">SEO Başlık</label>
                  <input
                    type="text"
                    value={formData.meta_title}
                    onChange={(e) => setFormData({ ...formData, meta_title: e.target.value })}
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">SEO Açıklama</label>
                  <textarea
                    value={formData.meta_description}
                    onChange={(e) => setFormData({ ...formData, meta_description: e.target.value })}
                    rows={3}
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">SEO Anahtar Kelimeler</label>
                  <input
                    type="text"
                    value={formData.meta_keywords}
                    onChange={(e) => setFormData({ ...formData, meta_keywords: e.target.value })}
                    placeholder="kelime1, kelime2, kelime3"
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Anahtar Kelimeler</label>
                  <input
                    type="text"
                    value={formData.keywords}
                    onChange={(e) => setFormData({ ...formData, keywords: e.target.value })}
                    className="w-full border px-3 py-2 rounded"
                  />
                </div>
              </TabsContent>

              {/* Variants Tab */}
              <TabsContent value="variants" className="space-y-4 mt-4">
                <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm mb-4">
                  <p className="font-medium text-amber-800">Varyant Yönetimi</p>
                  <p className="text-amber-700 text-xs mt-1">Renk ve beden kombinasyonları için stok ve fiyat bilgilerini yönetebilirsiniz.</p>
                </div>
                
                {/* Add New Variant */}
                <div className="border rounded-lg p-4">
                  <h4 className="text-sm font-medium mb-3">Yeni Varyant Ekle</h4>
                  <div className="grid grid-cols-6 gap-3">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Beden</label>
                      <select
                        value={formData.newVariant?.size || ""}
                        onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), size: e.target.value}})}
                        className="w-full border px-2 py-1.5 text-sm rounded"
                      >
                        <option value="">Seçin</option>
                        {["XS", "S", "M", "L", "XL", "XXL", "36", "38", "40", "42", "44"].map(s => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Renk</label>
                      <input
                        type="text"
                        value={formData.newVariant?.color || ""}
                        onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), color: e.target.value}})}
                        placeholder="Siyah"
                        className="w-full border px-2 py-1.5 text-sm rounded"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Barkod</label>
                      <input
                        type="text"
                        value={formData.newVariant?.barcode || ""}
                        onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), barcode: e.target.value}})}
                        className="w-full border px-2 py-1.5 text-sm rounded"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Stok</label>
                      <input
                        type="number"
                        value={formData.newVariant?.stock || ""}
                        onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), stock: parseInt(e.target.value) || 0}})}
                        className="w-full border px-2 py-1.5 text-sm rounded"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Fiyat Farkı</label>
                      <input
                        type="number"
                        value={formData.newVariant?.price_adjustment || ""}
                        onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), price_adjustment: parseFloat(e.target.value) || 0}})}
                        placeholder="0"
                        className="w-full border px-2 py-1.5 text-sm rounded"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={() => {
                          if (!formData.newVariant?.size) return;
                          const newVar = {
                            id: `var-${Date.now()}`,
                            ...formData.newVariant
                          };
                          setFormData({
                            ...formData,
                            variants: [...(formData.variants || []), newVar],
                            newVariant: {}
                          });
                        }}
                        className="w-full bg-black text-white py-1.5 text-sm rounded hover:bg-gray-800"
                      >
                        Ekle
                      </button>
                    </div>
                  </div>
                </div>

                {/* Existing Variants */}
                {formData.variants?.length > 0 && (
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-3 py-2">Beden</th>
                          <th className="text-left px-3 py-2">Renk</th>
                          <th className="text-left px-3 py-2">Barkod</th>
                          <th className="text-left px-3 py-2">Stok</th>
                          <th className="text-left px-3 py-2">Fiyat Farkı</th>
                          <th className="text-center px-3 py-2">İşlem</th>
                        </tr>
                      </thead>
                      <tbody>
                        {formData.variants.map((v, idx) => (
                          <tr key={v.id || idx} className="border-t">
                            <td className="px-3 py-2">{v.size}</td>
                            <td className="px-3 py-2">{v.color || "-"}</td>
                            <td className="px-3 py-2">{v.barcode || "-"}</td>
                            <td className="px-3 py-2">
                              <input
                                type="number"
                                value={v.stock || 0}
                                onChange={(e) => {
                                  const updated = [...formData.variants];
                                  updated[idx].stock = parseInt(e.target.value) || 0;
                                  setFormData({...formData, variants: updated});
                                }}
                                className="w-16 border px-2 py-1 rounded"
                              />
                            </td>
                            <td className="px-3 py-2">
                              <input
                                type="number"
                                value={v.price_adjustment || 0}
                                onChange={(e) => {
                                  const updated = [...formData.variants];
                                  updated[idx].price_adjustment = parseFloat(e.target.value) || 0;
                                  setFormData({...formData, variants: updated});
                                }}
                                className="w-20 border px-2 py-1 rounded"
                              />
                            </td>
                            <td className="px-3 py-2 text-center">
                              <button
                                type="button"
                                onClick={() => {
                                  setFormData({
                                    ...formData,
                                    variants: formData.variants.filter((_, i) => i !== idx)
                                  });
                                }}
                                className="text-red-500 hover:text-red-700"
                              >
                                <Trash2 size={16} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {(!formData.variants || formData.variants.length === 0) && (
                  <p className="text-sm text-gray-500 text-center py-4">Henüz varyant eklenmemiş</p>
                )}
              </TabsContent>
            </Tabs>

            <div className="flex justify-end gap-2 mt-6 pt-4 border-t">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 border rounded hover:bg-gray-50"
              >
                İptal
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-black text-white rounded hover:bg-gray-800"
              >
                {editingProduct ? "Güncelle" : "Kaydet"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
