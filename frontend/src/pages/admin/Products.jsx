import { useState, useEffect, useRef } from "react";
import { Plus, Search, Edit, Trash2, Eye, EyeOff, Copy, Upload, Image, X, Link2, MoreHorizontal, Layers, Filter, ChevronDown, ChevronUp, Store, RefreshCw, Check, Globe, Download, FileSpreadsheet } from "lucide-react";
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
import SizeTablePanel from "./SizeTablePanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SearchableAttribute = ({ attr, value, onChange, isRequired }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const dropdownRef = useRef(null);
  
  const hasValue = !!value;
  const filteredValues = attr.values?.filter(v => v.toLowerCase().includes(searchTerm.toLowerCase())) || [];

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!attr.values || attr.values.length === 0) {
    return (
      <div className="space-y-2">
        <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest">{attr.name}</label>
        <input 
          type="text" 
          value={value || ""} 
          onChange={(e) => onChange(e.target.value)}
          placeholder="Serbest değer yazın..."
          className="w-full border-gray-100 border-2 px-4 py-3 rounded-lg bg-gray-50 focus:bg-white focus:border-orange-300 outline-none transition-all text-sm font-medium"
        />
      </div>
    );
  }

  return (
    <div className={`space-y-2 relative ${isRequired && !hasValue ? 'p-3 bg-red-50 rounded-xl border-2 border-red-200' : ''}`} ref={dropdownRef}>
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-1">
          <label className={`block text-[10px] font-black uppercase tracking-widest ${isRequired ? 'text-white bg-red-600 px-1 rounded' : 'text-gray-900'}`}>{attr.name}</label>
          {hasValue && <Check size={12} className="text-green-500 font-bold" strokeWidth={4} />}
          {isRequired && !hasValue && <span className="text-red-600 font-bold animate-pulse">*</span>}
        </div>
        {isRequired && !hasValue && (
          <span className="text-[10px] font-black text-white bg-red-600 px-2 py-0.5 rounded-full uppercase animate-pulse shadow-lg shadow-red-200 ring-2 ring-red-300">
             ZORUNLU (TRENDYOL)
          </span>
        )}
      </div>
      
      <div 
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full border-2 px-4 py-3 rounded-lg bg-gray-50 cursor-pointer flex justify-between items-center transition-all ${hasValue ? 'border-green-500' : isRequired ? 'border-red-300' : 'border-gray-100'}`}
      >
        <div className="flex items-center gap-2 overflow-hidden flex-1">
          <Search size={14} className="text-gray-400 shrink-0" />
          <span className={`text-sm truncate ${hasValue ? 'text-black font-bold' : 'text-gray-400 font-medium'}`}>
            {value || "Seçiniz..."}
          </span>
        </div>
        <ChevronDown size={14} className={`transition-transform shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
      </div>

      {isOpen && (
        <div className="absolute z-[100] top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="p-2 border-b bg-gray-50 flex items-center gap-2">
            <Search size={14} className="text-gray-400" />
            <input 
              autoFocus
              className="bg-transparent border-none outline-none text-xs w-full py-1 font-bold"
              placeholder="Kütüphanede ara..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          <div className="max-h-60 overflow-y-auto">
            {filteredValues.map((v, idx) => (
              <div 
                key={idx}
                className="px-4 py-3 text-sm hover:bg-orange-50 cursor-pointer border-b last:border-0 border-gray-50 transition-colors font-medium text-gray-700"
                onClick={() => {
                  onChange(v);
                  setIsOpen(false);
                }}
              >
                {v}
              </div>
            ))}
            {filteredValues.length === 0 && (
              <div className="px-4 py-8 text-center text-xs text-gray-400 uppercase font-bold tracking-widest">
                Sonuç bulunamadı
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

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
  const [variantsModalOpen, setVariantsModalOpen] = useState(false);
  const [selectedProductForVariants, setSelectedProductForVariants] = useState(null);
  const [globalTrendyolMarkup, setGlobalTrendyolMarkup] = useState(0);
  const [globalVatRate, setGlobalVatRate] = useState(10);
  const [activeTab, setActiveTab ] = useState("basic");
  const [attributeSearchTerm, setAttributeSearchTerm] = useState("");
  const [showAllAttributes, setShowAllAttributes] = useState(false);
  const [variantSearchTerm, setVariantSearchTerm] = useState("");
  const [categorySearchOpen, setCategorySearchOpen] = useState(false);
  const [categorySearchTerm, setCategorySearchTerm] = useState("");
  const [sizeSearchOpen, setSizeSearchOpen] = useState(false);
  const [sizeSearchTerm, setSizeSearchTerm] = useState("");
  const [colorSearchOpen, setColorSearchOpen] = useState(false);
  const [colorSearchTerm, setColorSearchTerm] = useState("");
  const fileInputRef = useRef(null);
  const techFileInputRef = useRef(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [techImportModalOpen, setTechImportModalOpen] = useState(false);
  const [techImportResults, setTechImportResults] = useState(null);
  const [techImporting, setTechImporting] = useState(false);
  const [techApplying, setTechApplying] = useState(false);

  const [filters, setFilters] = useState({
    status: "all",
    category: "",
    brand: "",
    stock_code: "",
    barcode: "",
    min_stock: "",
    max_stock: "",
    is_showcase: false,
    is_new: false,
    is_opportunity: false,
    is_free_shipping: false,
    date_from: "",
    date_to: ""
  });
  const [showFilters, setShowFilters] = useState(false);

  const [formData, setFormData] = useState({
    name: "", slug: "", description: "", short_description: "",
    price: 0, sale_price: null, category_name: "", brand: "FACETTE",
    images: [], is_active: true, is_featured: false, is_new: false,
    stock: 0, stock_code: "", barcode: "", sku: "",
    // Ticimax fields
    variation_code: "", gtip_code: "", unit: "ADET", keywords: "",
    supplier: "", manufacturer: "FACETTE", max_installment: 9, purchase_price: 0,
    vat_rate: 10,
    market_price: 0, vat_included: true, currency: "TRY",
    cargo_weight: 0, product_weight: 0, width: 0, depth: 0, height: 0,
    min_order_qty: 1, max_order_qty: 999, estimated_delivery: "2-3",
    is_free_shipping: false, is_showcase: false,
    meta_title: "", meta_description: "", meta_keywords: "",
    variants: [], newVariant: {},
    attributes: {},
    auto_barcode: false,
    trendyol_attributes: {},
    trendyol_category_id: "",
    trendyol_multiplier: 0,
    use_default_markup: true,
    markup_rate: 0,
    hepsiburada_attributes: {},
    temu_attributes: {}
  });

  const [trendyolAttributesList, setTrendyolAttributesList] = useState([]);
  const [trendyolCategories, setTrendyolCategories] = useState([]);
  const [globalAttributes, setGlobalAttributes] = useState([]);
  const [globalSizes, setGlobalSizes] = useState([]);
  const [globalColors, setGlobalColors] = useState([]);
  const [fetchingAttributes, setFetchingAttributes] = useState(false);
  const [attrSearch, setAttrSearch] = useState({});

  useEffect(() => {
    if (modalOpen) {
      const selectedCat = formData.category_name ? categories.find(c => c.name === formData.category_name || c.id === formData.category_name) : null;
      const targetTrendyolCatId = formData.trendyol_category_id || (selectedCat ? selectedCat.trendyol_category_id : null);
      
      if (targetTrendyolCatId) {
        setFetchingAttributes(true);
        const token = localStorage.getItem('token');
        axios.get(`${API}/integrations/trendyol/categories/${targetTrendyolCatId}/attributes`, {
          headers: { Authorization: `Bearer ${token}` }
        })
          .then(res => setTrendyolAttributesList(res.data.attributes || []))
          .catch(err => setTrendyolAttributesList([]))
          .finally(() => setFetchingAttributes(false));
      } else {
        setTrendyolAttributesList([]);
      }
    }
  }, [formData.trendyol_category_id, formData.category_name, modalOpen, categories]);

  useEffect(() => {
    if (modalOpen && !editingProduct) {
      axios.get(`${API}/settings`)
        .then(res => {
          if (res.data.default_vat_rate) {
            setFormData(prev => ({ ...prev, vat_rate: res.data.default_vat_rate }));
          }
        })
        .catch(console.error);
    }
  }, [modalOpen, editingProduct]);

  useEffect(() => {
    fetchProducts();
    fetchCategories();
    fetchTrendyolCategories();
    fetchGlobalTrendyolMarkup();
    fetchGlobalSettings();
  }, [page, search, JSON.stringify(filters)]);

  // Click outside handler to close dropdowns
  useEffect(() => {
    const handleClickOutside = (event) => {
      // Close size and color dropdowns when clicking outside
      if (!event.target.closest('.size-dropdown-container')) {
        setSizeSearchOpen(false);
      }
      if (!event.target.closest('.color-dropdown-container')) {
        setColorSearchOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchTrendyolCategories = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/integrations/trendyol/categories`, { headers: { Authorization: `Bearer ${token}` }});
      if (res.data?.categories) {
        setTrendyolCategories(res.data.categories);
      }
    } catch (err) {
      console.error("Trendyol categories fetch failed", err);
    }
  };

  const fetchGlobalTrendyolMarkup = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/integrations/trendyol/settings`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data && res.data.default_markup !== undefined) {
        setGlobalTrendyolMarkup(res.data.default_markup);
      }
    } catch (err) {
      console.error("Global markup fetch error:", err);
    }
  };

  const fetchGlobalSettings = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/settings`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data && res.data.default_vat_rate !== undefined) {
        setGlobalVatRate(res.data.default_vat_rate);
      }
    } catch (err) {
      console.error("Global settings fetch error:", err);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    toast.info("Excel dosyası hazırlanıyor...");
    try {
      const token = localStorage.getItem("token");
      const response = await axios.get(`${API}/products/export/excel`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `urunler_${new Date().toISOString().split('T')[0]}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success("Excel başarıyla indirildi");
    } catch (err) {
      console.error("Export error:", err);
      toast.error("Dosya indirilemedi");
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setImporting(true);
    const formData = new FormData();
    formData.append("file", file);

    const toastId = toast.loading("Excel içeriği aktarılıyor...");
    try {
      const token = localStorage.getItem("token");
      const response = await axios.post(`${API}/products/import/excel`, formData, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });

      if (response.data.success) {
        const { stats } = response.data;
        toast.success(`Aktarım tamamlandı! (${stats.created} yeni, ${stats.updated} güncellendi, ${stats.errors} hata)`, { id: toastId });
        fetchProducts();
      }
    } catch (err) {
      console.error("Import error:", err);
      toast.error(err.response?.data?.detail || "Dosya aktarılamadı", { id: toastId });
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleTechImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setTechImporting(true);
    const toastId = toast.loading("Excel dosyası analiz ediliyor...");
    try {
      const token = localStorage.getItem("token");
      const fd = new FormData();
      fd.append("file", file);
      const response = await axios.post(`${API}/products/attributes/import-technical-xlsx`, fd, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
      });
      if (response.data.success) {
        setTechImportResults(response.data);
        setTechImportModalOpen(true);
        toast.success(`${response.data.matched} ürün eşleştirildi, ${response.data.unmatched} eşleşmedi`, { id: toastId });
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Dosya analiz edilemedi", { id: toastId });
    } finally {
      setTechImporting(false);
      if (techFileInputRef.current) techFileInputRef.current.value = "";
    }
  };

  const handleApplyTechImport = async () => {
    if (!techImportResults?.results) return;
    setTechApplying(true);
    const toastId = toast.loading("Özellikler ürünlere uygulanıyor...");
    try {
      const token = localStorage.getItem("token");
      const updates = techImportResults.results
        .filter(r => r.matched_product_id)
        .map(r => ({
          product_id: r.matched_product_id,
          attributes: r.attributes,
          extra_colors: r.extra_colors
        }));
      const response = await axios.post(`${API}/products/attributes/apply-technical-xlsx`, { updates }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.data.success) {
        toast.success(response.data.message, { id: toastId });
        setTechImportModalOpen(false);
        setTechImportResults(null);
        fetchProducts();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Uygulama başarısız", { id: toastId });
    } finally {
      setTechApplying(false);
    }
  };

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `${API}/products?page=${page}&limit=20`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      if (filters.status && filters.status !== 'all') url += `&status=${filters.status}`;
      if (filters.category) url += `&category=${encodeURIComponent(filters.category)}`;
      if (filters.stock_code) url += `&stock_code=${encodeURIComponent(filters.stock_code)}`;
      if (filters.barcode) url += `&barcode=${encodeURIComponent(filters.barcode)}`;
      if (filters.date_from) url += `&date_from=${filters.date_from}`;
      if (filters.date_to) url += `&date_to=${filters.date_to}`;
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
      
      const token = localStorage.getItem('token');
      const attrRes = await axios.get(`${API}/attributes`, { headers: { Authorization: `Bearer ${token}` } });
      setGlobalAttributes(attrRes.data.attributes || []);
      
      const sizesRes = await axios.get(`${API}/variants/size`, { headers: { Authorization: `Bearer ${token}` } });
      const colorsRes = await axios.get(`${API}/variants/color`, { headers: { Authorization: `Bearer ${token}` } });
      setGlobalSizes(sizesRes.data.sort((a,b) => a.sort_order - b.sort_order) || []);
      setGlobalColors(colorsRes.data.sort((a,b) => a.sort_order - b.sort_order) || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleImageUpload = async (e) => {
    const files = e.target.files;
    if (!files.length) return;

    setUploading(true);
    console.log("Image upload started for", files.length, "files");
    const token = localStorage.getItem('token');
    const newImages = [...formData.images];

    for (let file of files) {
      try {
        console.log("Uploading file:", file.name, "Size:", file.size, "Type:", file.type);
        const fd = new FormData();
        fd.append('file', file);
        const res = await axios.post(`${API}/upload/image`, fd, {
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        });
        console.log("Upload response for", file.name, ":", res.data);
        if (res.data.url) {
          const fullUrl = `${API.replace('/api', '')}${res.data.url}`;
          console.log("Adding image URL:", fullUrl);
          newImages.push(fullUrl);
        }
      } catch (err) {
        console.error("Upload error for", file.name, ":", err.response?.data || err.message);
        toast.error(`${file.name} yüklenemedi: ${err.response?.data?.detail || err.message}`);
      }
    }

    setFormData({ ...formData, images: newImages });
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleTrendyolSync = async (productId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/products/${productId}/sync`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        toast.success(res.data.message || "Trendyol senkronizasyonu başlatıldı");
        fetchProducts();
      }
    } catch (err) {
      console.error("Trendyol sync error:", err);
      toast.error(err.response?.data?.detail || "Trendyol aktarımı başarısız");
    }
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
      
      // Build attributes array - auto-add Yaş Grubu and Menşei if missing
      const attrObj = { "Yaş Grubu": "Yetişkin", "Menşei": "TR", ...(formData.attributes || {}) };
      const attributesArray = Object.entries(attrObj)
        .filter(([_, v]) => v !== "" && v !== null && v !== undefined)
        .map(([k, v]) => ({ type: k, name: k, value: v }));

      const payload = {
        ...formData,
        attributes: attributesArray,
        variants: formData.variants?.map(v => ({
          ...v,
          stock_code: formData.stock_code || v.stock_code,
        })) || []
      };

      // Get unique colors from variants
      const uniqueColors = [...new Set((payload.variants || []).map(v => v.color).filter(Boolean))];
      
      if (uniqueColors.length > 1 && !editingProduct) {
        // Multi-color: create a separate product per color
        toast.info(`${uniqueColors.length} farklı renk için ayrı ürünler oluşturuluyor...`);
        
        for (const color of uniqueColors) {
          const colorVariants = payload.variants.filter(v => v.color === color);
          // Set Web Color and Renk to this color in attributes
          const colorAttrs = attributesArray
            .filter(a => a.type !== "Web Color" && a.type !== "Renk")
            .concat([
              { type: "Web Color", name: "Web Color", value: color },
              { type: "Renk", name: "Renk", value: color }
            ]);
          
          const colorPayload = {
            ...payload,
            name: `${formData.name} ${color}`,
            slug: generateSlug(`${formData.name} ${color}`) + `-${Date.now()}`,
            attributes: colorAttrs,
            variants: colorVariants,
          };
          delete colorPayload.newVariant;
          await axios.post(`${API}/products`, colorPayload, { headers });
        }
        toast.success(`${uniqueColors.length} ürün başarıyla oluşturuldu`);
      } else if (uniqueColors.length === 1 && !editingProduct) {
        // Single color: auto-set Web Color and Renk
        const color = uniqueColors[0];
        const colorAttrs = attributesArray
          .filter(a => a.type !== "Web Color" && a.type !== "Renk")
          .concat([
            { type: "Web Color", name: "Web Color", value: color },
            { type: "Renk", name: "Renk", value: color }
          ]);
        
        const singlePayload = {
          ...payload,
          name: formData.name.includes(color) ? formData.name : `${formData.name} ${color}`,
          slug: generateSlug(formData.name.includes(color) ? formData.name : `${formData.name} ${color}`) + `-${Date.now()}`,
          attributes: colorAttrs,
        };
        delete singlePayload.newVariant;
        await axios.post(`${API}/products`, singlePayload, { headers });
        toast.success("Ürün oluşturuldu");
      } else {
        // Edit mode or no variants
        delete payload.newVariant;
        if (editingProduct) {
          await axios.put(`${API}/products/${editingProduct.id}`, payload, { headers });
          toast.success("Ürün güncellendi");
        } else {
          await axios.post(`${API}/products`, payload, { headers });
          toast.success("Ürün oluşturuldu");
        }
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
      console.error("Silme hatası:", err);
      toast.error(err.response?.data?.detail || "Silme başarısız. Yetkinizi kontrol edin.");
    }
  };

  const handleTrendyolUpdate = async (product) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/products/${product.id}/sync-inventory`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(res.data.message || "Trendyol stok/fiyat güncellendi");
    } catch (err) {
      toast.error("Güncelleme başarısız: " + (err.response?.data?.detail || err.message));
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
      supplier: product.supplier || "",
      manufacturer: product.manufacturer || "FACETTE",
      max_installment: product.max_installment || 9,
      purchase_price: product.purchase_price || 0,
      market_price: product.market_price || 0,
      vat_rate: product.vat_rate || 10,
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
      use_default_markup: product.use_default_markup ?? true,
      markup_rate: product.markup_rate || 0,
      trendyol_attributes: product.trendyol_attributes || {},
      hepsiburada_attributes: product.hepsiburada_attributes || {},
      temu_attributes: product.temu_attributes || {},
      variants: product.variants || [],
      attributes: { "Yaş Grubu": "Yetişkin", "Menşei": "TR", ...(product.attributes || []).reduce((acc, curr) => ({...acc, [curr.type || curr.name]: curr.value}), {}) },
    });
    setModalOpen(true);
  };

  const resetForm = () => {
    setEditingProduct(null);
    setShowAllAttributes(false);
    setFormData({
      name: "", slug: "", description: "", short_description: "",
      price: 0, sale_price: null, category_name: "", brand: "FACETTE",
      images: [], is_active: true, is_featured: false, is_new: false,
      stock: 0, stock_code: "", barcode: "", sku: "",
      variation_code: "", gtip_code: "", unit: "ADET", keywords: "",
      supplier: "", manufacturer: "FACETTE", max_installment: 9, purchase_price: 0,
      market_price: 0, vat_rate: globalVatRate, vat_included: true, currency: "TRY",
      cargo_weight: 0, product_weight: 0, width: 0, depth: 0, height: 0,
      min_order_qty: 1, max_order_qty: 999, estimated_delivery: "2-3",
      is_free_shipping: false, is_showcase: false,
      meta_title: "", meta_description: "", meta_keywords: "",
      use_default_markup: true, markup_rate: 0,
      trendyol_attributes: {},
      hepsiburada_attributes: {},
      temu_attributes: {},
      variants: [], newVariant: {},
      attributes: { "Yaş Grubu": "Yetişkin", "Menşei": "TR" },
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

  const openVariantsModal = (product) => {
    setSelectedProductForVariants(product);
    setVariantsModalOpen(true);
  };

  const handleSaveVariants = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      await axios.put(`${API}/products/${selectedProductForVariants.id}`, selectedProductForVariants, { headers });
      
      toast.success("Varyantlar başarıyla güncellendi");
      setVariantsModalOpen(false);
      fetchProducts();
    } catch (err) {
      toast.error("Varyantlar güncellenirken hata oluştu");
    }
  };

  return (
    <div data-testid="admin-products">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Ürünler ({total})</h1>
        <div className="flex items-center gap-3">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImport}
            accept=".xlsx, .xls"
            className="hidden"
          />
          <input
            type="file"
            ref={techFileInputRef}
            onChange={handleTechImport}
            accept=".xlsx, .xls"
            className="hidden"
          />
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-all font-medium text-sm shadow-sm disabled:opacity-50"
          >
            {exporting ? <RefreshCw className="animate-spin" size={16} /> : <Download size={16} />}
            Excel İndir
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-all font-medium text-sm shadow-sm disabled:opacity-50"
          >
            {importing ? <RefreshCw className="animate-spin" size={16} /> : <Upload size={16} />}
            Excel Yükle
          </button>
          <button
            onClick={() => techFileInputRef.current?.click()}
            disabled={techImporting}
            data-testid="tech-import-btn"
            className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 transition-all font-medium text-sm shadow-sm disabled:opacity-50"
          >
            {techImporting ? <RefreshCw className="animate-spin" size={16} /> : <FileSpreadsheet size={16} />}
            Teknik Detay Yükle
          </button>
          <button 
            onClick={() => { resetForm(); setModalOpen(true); }}
            className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800 transition-all font-medium text-sm shadow-sm"
          >
            <Plus size={18} />
            Yeni Ürün
          </button>
        </div>
      </div>

      {/* Search & Filter Top Bar */}
      <div className="flex flex-col md:flex-row gap-4 mb-4">
        <div className="relative flex-1">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Ürün ara (ad, stok kodu, barkod)..."
            className="w-full pl-10 pr-4 py-2 border rounded focus:ring-1 focus:ring-black outline-none"
          />
        </div>
        <button 
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-4 py-2 border rounded transition-colors ${showFilters ? 'bg-black text-white' : 'bg-white hover:bg-gray-50'}`}
        >
          <Filter size={18} />
          <span>Gelişmiş Filtreleme</span>
          {showFilters ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* Advanced Filters Panel */}
      {showFilters && (
        <div className="bg-white p-4 rounded-lg shadow-sm border mb-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-gray-500 font-medium mb-1 uppercase tracking-wider">Durum</label>
            <select
              value={filters.status}
              onChange={(e) => { setFilters({...filters, status: e.target.value}); setPage(1); }}
              className="w-full border px-3 py-2 rounded text-sm focus:ring-1 focus:ring-black outline-none"
            >
              <option value="all">Tümü (Aktif & Pasif)</option>
              <option value="active">Sadece Aktifler</option>
              <option value="passive">Sadece Pasifler</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 font-medium mb-1 uppercase tracking-wider">Kategori</label>
            <select
              value={filters.category}
              onChange={(e) => { setFilters({...filters, category: e.target.value}); setPage(1); }}
              className="w-full border px-3 py-2 rounded text-sm focus:ring-1 focus:ring-black outline-none"
            >
              <option value="">Tüm Kategoriler</option>
              {categories.map(c => (
                <option key={c.id} value={c.slug}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs text-gray-500 font-medium mb-1 uppercase tracking-wider">Arama Detayı</label>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Stok Kodu"
                value={filters.stock_code}
                onChange={(e) => setFilters({...filters, stock_code: e.target.value})}
                className="w-full border px-3 py-2 rounded text-sm outline-none"
              />
              <input
                type="text"
                placeholder="Barkod"
                value={filters.barcode}
                onChange={(e) => setFilters({...filters, barcode: e.target.value})}
                className="w-full border px-3 py-2 rounded text-sm outline-none"
              />
            </div>
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs text-gray-500 font-medium mb-1 uppercase tracking-wider">Eklenme Tarihi Aralığı</label>
            <div className="flex gap-2 items-center">
              <input
                type="date"
                value={filters.date_from}
                onChange={(e) => { setFilters({...filters, date_from: e.target.value}); setPage(1); }}
                className="w-full border px-3 py-2 rounded text-sm outline-none focus:ring-1 focus:ring-black"
              />
              <span className="text-gray-400 text-xs">-</span>
              <input
                type="date"
                value={filters.date_to}
                onChange={(e) => { setFilters({...filters, date_to: e.target.value}); setPage(1); }}
                className="w-full border px-3 py-2 rounded text-sm outline-none focus:ring-1 focus:ring-black"
              />
            </div>
          </div>
        </div>
      )}

      {/* Products Table */}
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Görsel</th>
              <th>Ürün Adı</th>
              <th>Stok Kodu</th>
              <th>Barkod</th>
              <th>Bedenler</th>
              <th>Fiyat</th>
              <th>İşlemler</th>
              <th>Eklenme Tarihi</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="text-center py-8">Yükleniyor...</td></tr>
            ) : products.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-8 text-gray-500">Ürün bulunamadı</td></tr>
            ) : (
              products.map((product) => (
                <tr key={product.id}>
                  <td>
                    {product.images?.[0] ? (
                      <div className="relative group/img overflow-visible z-0 hover:z-50">
                        <img 
                          src={product.images[0]} 
                          alt="" 
                          className="w-12 h-16 object-cover rounded shadow-sm border border-gray-100 transition-all duration-300 group-hover/img:scale-[3.0] group-hover/img:shadow-xl group-hover/img:border-orange-200 cursor-zoom-in" 
                        />
                      </div>
                    ) : (
                      <div className="w-12 h-16 bg-gray-100 flex items-center justify-center rounded border border-gray-50 text-gray-400">
                        <Image size={16} />
                      </div>
                    )}
                  </td>
                  <td>
                    <a href={`/urun/${product.slug}`} target="_blank" rel="noopener noreferrer" className="font-medium line-clamp-1 text-orange-600 hover:text-orange-800 hover:underline">
                      {product.name}
                    </a>
                    <p className="text-xs text-gray-500">{product.category_name}</p>
                  </td>
                  <td className="text-sm font-mono whitespace-nowrap">{product.stock_code || '-'}</td>
                  <td className="text-xs text-gray-600 font-mono">
                    {product.variants?.find(v => v.barcode)?.barcode || '-'}
                  </td>
                  <td>
                    {product.variants?.length > 0 ? (
                      <button 
                        onClick={() => openVariantsModal(product)}
                        className="flex items-center gap-1 text-xs text-orange-600 hover:text-orange-800 hover:underline"
                      >
                        <Layers size={14} />
                        {product.variants.length} Beden
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400">-</span>
                    )}
                  </td>
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
                  <td>
                    <div className="flex flex-col gap-1">
                      <div className="flex gap-1 items-center">
                        <button
                          onClick={() => product.is_active ? toggleProductStatus(product) : null}
                          title="Aktif"
                          className={`w-6 h-6 text-xs font-bold rounded ${product.is_active ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-400 hover:bg-green-200'}`}
                        >
                          A
                        </button>
                        <button
                          onClick={() => !product.is_active ? toggleProductStatus(product) : null}
                          title="Pasif"
                          className={`w-6 h-6 text-xs font-bold rounded ${!product.is_active ? 'bg-red-400 text-white' : 'bg-gray-200 text-gray-400 hover:bg-red-200'}`}
                        >
                          P
                        </button>
                        <button onClick={() => openEditModal(product)} className="p-1.5 hover:bg-gray-100 rounded" title="Düzenle">
                          <Edit size={16} />
                        </button>
                        <button onClick={() => handleDuplicate(product)} className="p-1.5 hover:bg-gray-100 rounded" title="Kopyala">
                          <Copy size={16} />
                        </button>
                        <button
                          onClick={() => handleTrendyolSync(product.id)}
                          className="p-1.5 hover:bg-orange-100 rounded text-orange-600 transition-colors"
                          title="Trendyola Aktar (Yeni Ürün)"
                        >
                          <Store size={16} />
                        </button>
                        <button
                          onClick={() => handleTrendyolUpdate(product)}
                          className="p-1.5 hover:bg-orange-100 rounded text-orange-600 transition-colors"
                          title="Trendyol Stok/Fiyat Güncelle"
                        >
                          <RefreshCw size={16} />
                        </button>
                        <button
                          onClick={() => handleDelete(product.id)}
                          className="p-1.5 hover:bg-red-50 rounded text-red-500"
                          title="Sil"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                      <div className={`text-xs font-medium ${(product.variants?.length > 0 ? product.variants.reduce((s, v) => s + (v.stock || 0), 0) : product.stock || 0) < 5 ? 'text-red-600' : 'text-gray-500'}`}>
                        Stok: {product.variants?.length > 0 ? product.variants.reduce((s, v) => s + (v.stock || 0), 0) : (product.stock || 0)}
                      </div>
                    </div>
                  </td>
                  <td className="text-xs text-gray-400 whitespace-nowrap">
                    {product.created_at ? new Date(product.created_at).toLocaleDateString('tr-TR', {day: '2-digit', month: '2-digit', year: 'numeric'}) : '-'}
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
      <Dialog open={modalOpen} onOpenChange={(open) => { setModalOpen(open); if(!open) resetForm(); }}>
        <DialogContent className="max-w-5xl max-h-[95vh] overflow-y-auto p-0">
          <div className="flex flex-col h-full bg-slate-50">
            <div className="p-6 bg-white border-b sticky top-0 z-10 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{editingProduct ? "Ürün Düzenle" : "Yeni Ürün Oluştur"}</h2>
                <p className="text-sm text-gray-500">{formData.name || 'İsimsiz Ürün'}</p>
              </div>
              <div className="flex gap-2">
                <button 
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border rounded hover:bg-gray-50"
                >
                  İptal
                </button>
                <button 
                  onClick={handleSubmit}
                  className="px-6 py-2 text-sm font-medium text-white bg-black rounded hover:bg-gray-800 shadow-sm"
                >
                  {editingProduct ? "Değişiklikleri Kaydet" : "Ürünü Oluştur"}
                </button>
              </div>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col p-6">
              <TabsList className="bg-gray-100/50 p-1 rounded-xl mb-6 flex flex-wrap h-auto gap-1">
                 <TabsTrigger value="basic" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Temel</TabsTrigger>
                 <TabsTrigger value="pricing" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Fiyat</TabsTrigger>
                 <TabsTrigger value="images" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Görseller</TabsTrigger>
                 <TabsTrigger value="stock" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Stok</TabsTrigger>
                 <TabsTrigger value="variants" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Varyantlar</TabsTrigger>
                 <TabsTrigger value="seo" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">SEO</TabsTrigger>
                 <TabsTrigger value="attributes" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Özellikler</TabsTrigger>
                 <TabsTrigger value="sizetable" className="data-[state=active]:bg-white data-[state=active]:text-black data-[state=active]:shadow-sm px-6 py-2 text-sm font-medium rounded-lg transition-all">Ölçü Tablosu</TabsTrigger>
                 <TabsTrigger value="trendyol" className="data-[state=active]:bg-orange-500 data-[state=active]:text-white px-6 py-2 text-sm font-medium rounded-lg transition-all ml-auto flex gap-2">
                   <Store size={16} /> Trendyol Ayarları
                 </TabsTrigger>
               </TabsList>

              {/* Basic Info Tab */}
              <TabsContent value="basic" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="md:col-span-2 space-y-6">
                    <div className="bg-white p-6 rounded-xl border shadow-sm space-y-4">
                      <h3 className="font-semibold text-gray-900 border-b pb-2 mb-4">Genel Bilgiler</h3>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="col-span-2">
                          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Ürün Adı *</label>
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
                            className="w-full border-gray-200 border px-3 py-2.5 rounded-lg focus:border-black outline-none transition-all"
                            placeholder="Örn: V Yaka Saten Elbise"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Kategori</label>
                          <div className="relative">
                            <div 
                              className="w-full border-gray-200 border px-3 py-2.5 rounded-lg focus-within:border-black bg-white flex items-center justify-between cursor-pointer transition-all"
                              onClick={() => setCategorySearchOpen(!categorySearchOpen)}
                            >
                              <span className={formData.category_name ? "text-black text-sm" : "text-gray-400 text-sm"}>
                                {formData.category_name ? (categories.find(c => c.name === formData.category_name)?.full_name || formData.category_name) : "Seçiniz"}
                              </span>
                              <ChevronDown size={16} className="text-gray-400" />
                            </div>
                            
                            {categorySearchOpen && (
                              <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-xl max-h-60 overflow-y-auto">
                                <div className="p-2 sticky top-0 bg-white border-b">
                                  <input 
                                    type="text" 
                                    placeholder="Kategori ara..." 
                                    className="w-full border border-gray-200 rounded px-2 py-1.5 text-sm outline-none focus:border-black bg-gray-50 focus:bg-white transition-colors"
                                    value={categorySearchTerm}
                                    onChange={(e) => setCategorySearchTerm(e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                    autoFocus
                                  />
                                </div>
                                <div className="p-1">
                                  <div 
                                    className="px-3 py-2 text-sm hover:bg-gray-100 cursor-pointer rounded text-gray-500"
                                    onClick={() => { setFormData({...formData, category_name: ""}); setCategorySearchOpen(false); }}
                                  >
                                    Seçiniz
                                  </div>
                                  {categories.filter(c => (c.full_name || c.name).toLowerCase().includes(categorySearchTerm.toLowerCase())).map(c => (
                                    <div 
                                      key={c.id}
                                      className="px-3 py-2 text-sm hover:bg-gray-100 cursor-pointer rounded truncate"
                                      title={c.full_name || c.name}
                                      onClick={() => { setFormData({...formData, category_name: c.name}); setCategorySearchOpen(false); setCategorySearchTerm(""); }}
                                    >
                                      {c.full_name || c.name}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Marka</label>
                          <input
                            type="text"
                            value={formData.brand}
                            onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                            className="w-full border-gray-200 border px-3 py-2.5 rounded-lg focus:border-black outline-none transition-all"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Açıklama</label>
                        <textarea
                          value={formData.description}
                          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                          rows={6}
                          className="w-full border-gray-200 border px-3 py-2.5 rounded-lg focus:border-black outline-none transition-all text-sm"
                          placeholder="Ürün detaylarını buraya yazın..."
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-6">
                    <div className="bg-white p-6 rounded-xl border shadow-sm space-y-4">
                      <h3 className="font-semibold text-gray-900 border-b pb-2 mb-4">Envanter & Kimlik</h3>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Stok Kodu (Model Kodu)</label>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={formData.stock_code}
                            onChange={(e) => setFormData({ ...formData, stock_code: e.target.value })}
                            className="w-full border-gray-200 border px-3 py-2 rounded-lg bg-gray-50 focus:bg-white focus:border-black outline-none transition-all font-mono text-sm uppercase"
                          />
                        </div>
                        <div className="flex gap-2 mt-2">
                          <button
                            type="button"
                            onClick={() => {
                              const randomNum = Math.floor(100000 + Math.random() * 900000);
                              setFormData({ ...formData, stock_code: `FCFW${randomNum}` });
                            }}
                            className="px-3 py-2 bg-orange-100 text-orange-800 border-none rounded-lg text-[10px] font-black tracking-widest uppercase whitespace-nowrap hover:bg-orange-200 transition-colors"
                          >
                            Üret (FCFW)
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              const randomNum = Math.floor(100000 + Math.random() * 900000);
                              setFormData({ ...formData, stock_code: `FCSS${randomNum}` });
                            }}
                            className="px-3 py-2 bg-blue-100 text-blue-800 border-none rounded-lg text-[10px] font-black tracking-widest uppercase whitespace-nowrap hover:bg-blue-200 transition-colors"
                          >
                            Üret (FCSS)
                          </button>
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">SKU</label>
                        <input
                          type="text"
                          value={formData.sku}
                          onChange={(e) => setFormData({ ...formData, sku: e.target.value })}
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg bg-gray-50 focus:bg-white focus:border-black outline-none transition-all font-mono text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Tedarikçi</label>
                        <input
                          type="text"
                          value={formData.supplier}
                          onChange={(e) => setFormData({ ...formData, supplier: e.target.value })}
                          placeholder="Boş bırakılabilir"
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg focus:border-black outline-none transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Üretici</label>
                        <input
                          type="text"
                          value={formData.manufacturer}
                          onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                          placeholder="FACETTE"
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg focus:border-black outline-none transition-all"
                        />
                      </div>
                    </div>

                    <div className="bg-white p-6 rounded-xl border shadow-sm">
                      <h3 className="font-semibold text-gray-900 border-b pb-2 mb-4">Özellikler</h3>
                      <div className="space-y-3">
                        <label className="flex items-center gap-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded border-gray-300 text-black focus:ring-black"
                            checked={formData.is_active}
                            onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                          />
                          <span className="text-sm font-medium text-gray-700 group-hover:text-black transition-colors">Mağazada Aktif</span>
                        </label>
                        <label className="flex items-center gap-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded border-gray-300 text-black focus:ring-black"
                            checked={formData.is_new}
                            onChange={(e) => setFormData({ ...formData, is_new: e.target.checked })}
                          />
                          <span className="text-sm font-medium text-gray-700 group-hover:text-black transition-colors">Yeni Ürün Etiketi</span>
                        </label>
                        <label className="flex items-center gap-3 cursor-pointer group">
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                            checked={formData.is_opportunity}
                            onChange={(e) => setFormData({ ...formData, is_opportunity: e.target.checked })}
                          />
                          <span className="text-sm font-medium text-gray-700 group-hover:text-black transition-colors">Fırsat Ürünü</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Pricing Tab */}
              <TabsContent value="pricing" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-white p-6 rounded-xl border shadow-sm space-y-4">
                    <h3 className="font-semibold text-gray-900 border-b pb-2 mb-4">Fiyatlandırma</h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Normal Fiyat (TL)</label>
                        <input
                          type="number"
                          value={formData.price}
                          onChange={(e) => setFormData({ ...formData, price: parseFloat(e.target.value) || 0 })}
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg focus:border-black outline-none transition-all font-bold"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">İndirimli Fiyat (TL)</label>
                        <input
                          type="number"
                          value={formData.sale_price || ""}
                          onChange={(e) => setFormData({ ...formData, sale_price: parseFloat(e.target.value) || null })}
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg focus:border-black outline-none transition-all font-bold text-green-600"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Alış Fiyatı (TL)</label>
                        <input
                          type="number"
                          value={formData.purchase_price}
                          onChange={(e) => setFormData({ ...formData, purchase_price: parseFloat(e.target.value) || 0 })}
                          className="w-full border-gray-200 border px-3 py-2 rounded-lg focus:border-black outline-none transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase mb-1 text-orange-600">KDV ORANI (%)</label>
                        <input
                          type="number"
                          value={formData.vat_rate || 10}
                          onChange={(e) => setFormData({ ...formData, vat_rate: parseInt(e.target.value) || 0 })}
                          className="w-full border-orange-200 border-2 px-3 py-2 rounded-lg focus:border-orange-500 outline-none transition-all font-bold text-orange-700"
                          placeholder="10"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="bg-white p-6 rounded-xl border shadow-sm space-y-4">
                    <h3 className="font-semibold text-gray-900 border-b pb-2 mb-4">Ürün Durumları</h3>
                    <div className="grid grid-cols-2 gap-4">
                      {[
                        { label: "Mağazada Aktif", key: "is_active" },
                        { label: "Yeni Ürün Etiketi", key: "is_new" },
                        { label: "Öne Çıkan Ürün", key: "is_featured" },
                        { label: "Vitrin Ürünü", key: "is_showcase" },
                        { label: "Fırsat Ürünü", key: "is_opportunity" },
                        { label: "Ücretsiz Kargo", key: "is_free_shipping" }
                      ].map(item => (
                        <label key={item.key} className="flex items-center gap-3 cursor-pointer group p-2 hover:bg-orange-50 rounded-lg transition-all">
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                            checked={formData[item.key]}
                            onChange={(e) => setFormData({ ...formData, [item.key]: e.target.checked })}
                          />
                          <span className="text-sm font-medium text-gray-700 group-hover:text-orange-900">{item.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-orange-50 p-8 rounded-xl border border-orange-200 shadow-sm">
                  <h3 className="font-semibold text-lg text-orange-900 mb-6 flex items-center gap-2">
                    <span className="w-8 h-8 rounded-full bg-orange-500 text-white flex items-center justify-center text-sm font-bold">2</span>
                    Trendyol Fiyatlandırma Ayarları
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="space-y-4">
                      <div className="bg-white p-4 rounded-lg border border-orange-100 flex items-start gap-3">
                        <input
                          type="checkbox"
                          id="use_default_markup"
                          checked={formData.use_default_markup}
                          onChange={(e) => setFormData({ ...formData, use_default_markup: e.target.checked })}
                          className="mt-1 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                        />
                        <label htmlFor="use_default_markup" className="cursor-pointer">
                          <span className="block text-sm font-bold text-orange-900 leading-tight">Global Kâr Oranını Kullan</span>
                          <span className="block text-xs text-orange-600 mt-0.5">Ayarlar sayfasındaki global oranı (%{globalTrendyolMarkup}) baz alır.</span>
                        </label>
                      </div>

                      {!formData.use_default_markup && (
                        <div className="bg-white p-4 rounded-lg border border-orange-100 animate-in slide-in-from-top-2">
                          <label className="block text-xs font-bold text-orange-900 uppercase mb-2">Bu Ürüne Özel Trendyol Fark Oranı (%)</label>
                          <input
                            type="number"
                            value={formData.markup_rate}
                            onChange={(e) => setFormData({ ...formData, markup_rate: parseFloat(e.target.value) || 0 })}
                            placeholder="Örn: 25"
                            className="w-full border-orange-200 border-2 px-4 py-3 rounded-xl focus:border-orange-500 outline-none transition-all text-xl font-bold text-orange-700"
                          />
                        </div>
                      )}
                    </div>

                    <div className="bg-white p-6 rounded-lg border border-orange-100 flex flex-col justify-center">
                      <p className="text-xs font-bold text-gray-500 uppercase mb-4 tracking-widest text-center">Tahmini Trendyol Satış Fiyatı</p>
                      <div className="text-center">
                        <span className="text-4xl font-black text-orange-600">
                          {((formData.sale_price || formData.price || 0) * (1 + (formData.use_default_markup ? globalTrendyolMarkup : (formData.markup_rate || 0)) / 100)).toFixed(2)}
                        </span>
                        <span className="text-xl font-bold text-orange-400 ml-1">TL</span>
                      </div>
                      <p className="text-[10px] text-gray-400 text-center mt-4">
                        * KDV ve kargo masrafları fiyata dahildir. {formData.use_default_markup ? 'Global' : 'Özel'} markup uygulanmıştır.
                      </p>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Attributes Tab */}
              <TabsContent value="attributes" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                {(() => {
                  const selectedCat = categories.find(c => c.name === formData.category_name || c.id === formData.category_name);
                  const attrMappings = selectedCat?.attribute_mappings || [];
                  const hiddenAttrNames = ["beden", "renk", "web color"];

                  const baseList = globalAttributes
                    .filter(a => !hiddenAttrNames.includes(a.name.toLowerCase()))
                    .filter(a => a.name.toLowerCase().includes(attributeSearchTerm.toLowerCase()));

                  // Determine required attrs from Trendyol mapping
                  const getIsRequired = (attr) => {
                    const mapping = attrMappings.find(m => m.local_attr?.toLowerCase() === attr.name.toLowerCase());
                    let tyAttr = null;
                    if (mapping?.trendyol_attr_id) {
                      tyAttr = trendyolAttributesList.find(ta => (ta.attribute?.id || ta.id) === mapping.trendyol_attr_id);
                    }
                    if (!tyAttr) {
                      tyAttr = trendyolAttributesList.find(ta => {
                        const taName = (ta.attribute?.name || ta.name || "").toLowerCase().trim();
                        return taName === (attr.name || "").toLowerCase().trim();
                      });
                    }
                    return !!tyAttr?.required;
                  };

                  // Auto-sync: when Trendyol attribute changes, if value matches an allowed value
                  // in that attribute's value library, auto-apply to HB + Temu maps (only if those
                  // are currently empty for that attr, to respect manual overrides).
                  const setTrendyolAttr = (attr, val) => {
                    const newAttrs = { ...(formData.attributes || {}), [attr.name]: val };
                    const newHb = { ...(formData.hepsiburada_attributes || {}) };
                    const newTemu = { ...(formData.temu_attributes || {}) };
                    const valuesLower = (attr.values || []).map(v => (v || "").toLowerCase());
                    const valOk = !val || !attr.values?.length || valuesLower.includes((val || "").toLowerCase());
                    if (valOk) {
                      if (!newHb[attr.name]) newHb[attr.name] = val;
                      if (!newTemu[attr.name]) newTemu[attr.name] = val;
                    }
                    setFormData({ ...formData, attributes: newAttrs, hepsiburada_attributes: newHb, temu_attributes: newTemu });
                  };

                  const renderSection = (marketplace, title, accent, logo) => {
                    const mapKey = marketplace === 'trendyol' ? 'attributes'
                                 : marketplace === 'hepsiburada' ? 'hepsiburada_attributes'
                                 : 'temu_attributes';
                    const valuesMap = formData[mapKey] || {};

                    const processed = baseList.map(attr => {
                      const isReq = marketplace === 'trendyol' ? getIsRequired(attr) : false;
                      const hasVal = !!valuesMap[attr.name];
                      return { attr, isRequired: isReq, hasValue: hasVal };
                    });
                    const filledAttrs = processed.filter(a => a.hasValue).sort((a, b) => a.attr.name.localeCompare(b.attr.name));
                    const requiredEmpty = processed.filter(a => a.isRequired && !a.hasValue).sort((a, b) => a.attr.name.localeCompare(b.attr.name));
                    const otherEmpty = processed.filter(a => !a.isRequired && !a.hasValue).sort((a, b) => a.attr.name.localeCompare(b.attr.name));
                    const isSearching = attributeSearchTerm.length > 0;

                    const handleChange = (attr, val) => {
                      if (marketplace === 'trendyol') {
                        setTrendyolAttr(attr, val);
                      } else {
                        setFormData({
                          ...formData,
                          [mapKey]: { ...(formData[mapKey] || {}), [attr.name]: val }
                        });
                      }
                    };

                    const renderAttr = ({ attr, isRequired }) => (
                      <SearchableAttribute
                        key={`${marketplace}-${attr.id}`}
                        attr={attr}
                        value={valuesMap[attr.name]}
                        isRequired={isRequired}
                        onChange={(val) => handleChange(attr, val)}
                      />
                    );

                    return (
                      <div
                        data-testid={`attributes-section-${marketplace}`}
                        className={`bg-white p-8 rounded-xl border-2 shadow-sm`}
                        style={{ borderColor: accent.border }}
                      >
                        <div className="flex justify-between items-center mb-6">
                          <div className="flex items-center gap-3 flex-1 mr-4">
                            <span
                              className="inline-flex items-center justify-center text-white text-xs font-black px-3 py-1.5 rounded-md tracking-wider"
                              style={{ background: accent.bg }}
                            >
                              {logo}
                            </span>
                            <div>
                              <h3 className="font-bold text-xl mb-0" style={{ color: accent.text }}>{title}</h3>
                              <p className="text-xs text-gray-500 leading-relaxed max-w-2xl">
                                {marketplace === 'trendyol'
                                  ? "Trendyol için ürün özellikleri. Seçilen değer HB ve Temu'da da otomatik set edilir (boş ise)."
                                  : `${marketplace === 'hepsiburada' ? 'Hepsiburada' : 'Temu'} için ürün özellikleri. Gerekirse Trendyol'dan bağımsız düzenleyin.`}
                              </p>
                            </div>
                          </div>
                          {marketplace === 'trendyol' && (
                            <div className="flex items-center gap-3">
                              <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
                                <input
                                  type="text"
                                  placeholder="Özellik ara..."
                                  className="pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs font-bold outline-none focus:border-orange-500 focus:bg-white transition-all w-48"
                                  value={attributeSearchTerm}
                                  onChange={(e) => setAttributeSearchTerm(e.target.value)}
                                />
                              </div>
                            </div>
                          )}
                        </div>

                        {filledAttrs.length > 0 && (
                          <div className="mb-6">
                            <div className="flex items-center gap-2 mb-4">
                              <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                              <h4 className="text-sm font-bold text-green-700">Dolu Özellikler ({filledAttrs.length})</h4>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                              {filledAttrs.map(renderAttr)}
                            </div>
                          </div>
                        )}

                        {requiredEmpty.length > 0 && (
                          <div className="mb-6">
                            <div className="flex items-center gap-2 mb-4">
                              <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                              <h4 className="text-sm font-bold text-red-700">Zorunlu - Boş ({requiredEmpty.length})</h4>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                              {requiredEmpty.map(renderAttr)}
                            </div>
                          </div>
                        )}

                        {otherEmpty.length > 0 && (isSearching || showAllAttributes) && (
                          <div className="mb-6">
                            <div className="flex items-center gap-2 mb-4">
                              <div className="w-3 h-3 bg-gray-300 rounded-full"></div>
                              <h4 className="text-sm font-bold text-gray-500">Diğer Özellikler ({otherEmpty.length})</h4>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                              {otherEmpty.map(renderAttr)}
                            </div>
                          </div>
                        )}

                        {otherEmpty.length > 0 && !isSearching && marketplace === 'trendyol' && (
                          <div className="text-center pt-4 border-t border-dashed border-gray-200">
                            <button
                              type="button"
                              onClick={() => setShowAllAttributes(!showAllAttributes)}
                              className="px-6 py-2 text-sm font-bold text-orange-600 bg-orange-50 hover:bg-orange-100 rounded-lg transition-colors"
                              data-testid="toggle-all-attributes-btn"
                            >
                              {showAllAttributes ? `Boş Özellikleri Gizle (${otherEmpty.length})` : `Tüm Özellikleri Göster (+${otherEmpty.length} boş)`}
                            </button>
                          </div>
                        )}

                        {globalAttributes.length === 0 && (
                          <div className="col-span-full py-20 text-center text-gray-400 bg-gray-50 rounded-2xl border-2 border-dashed border-gray-200">
                            <Layers className="mx-auto mb-4 opacity-10" size={64} />
                            <p className="text-sm font-bold uppercase tracking-widest">Henüz özellik kütüphanesi boş.</p>
                          </div>
                        )}
                      </div>
                    );
                  };

                  return (
                    <div className="space-y-6">
                      {renderSection('trendyol', 'Trendyol için Özellikler', { border: '#F27A1A', bg: '#F27A1A', text: '#9A3412' }, 'TRENDYOL')}
                      {renderSection('hepsiburada', 'Hepsiburada için Özellikler', { border: '#FF6000', bg: '#FF6000', text: '#7F1D1D' }, 'HEPSIBURADA')}
                      {renderSection('temu', 'Temu için Özellikler', { border: '#111827', bg: '#111827', text: '#111827' }, 'TEMU')}
                    </div>
                  );
                })()}
              </TabsContent>

              {/* Size Table Tab */}
              <TabsContent value="sizetable" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <SizeTablePanel
                  productId={editingProduct?.id}
                  variants={formData.variants}
                  onToast={(m, t) => (t === 'err' ? toast.error(m) : toast.success(m))}
                />
              </TabsContent>

              {/* Variants Tab */}
              <TabsContent value="variants" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="bg-white p-6 rounded-xl border shadow-sm space-y-6">
                  <div className="flex justify-between items-center border-b pb-4">
                    <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                      <Layers size={20} className="text-orange-500" />
                      Varyant Yönetimi
                    </h3>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
                        <input 
                          type="text"
                          placeholder="Varyant ara (beden/renk/kod)..."
                          className="pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs font-bold outline-none focus:border-orange-500 focus:bg-white transition-all w-64"
                          value={variantSearchTerm}
                          onChange={(e) => setVariantSearchTerm(e.target.value)}
                        />
                    </div>
                  </div>

                  {/* Existing Variants Table */}
                  {formData.variants?.length > 0 && (
                    <div className="border rounded-xl overflow-hidden shadow-sm">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50 border-b">
                          <tr>
                            <th className="text-left px-4 py-3 font-bold text-gray-600">Beden / Renk</th>
                            <th className="text-left px-4 py-3 font-bold text-gray-600">Stok Kodu</th>
                            <th className="text-left px-4 py-3 font-bold text-gray-600">Barkod</th>
                            <th className="text-center px-4 py-3 font-bold text-gray-600">Stok</th>
                            <th className="text-center px-4 py-3 font-bold text-gray-600 w-20">Sil</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {formData.variants
                            ?.map((v, originalIdx) => ({ ...v, originalIdx }))
                            ?.filter(v => 
                              !variantSearchTerm || 
                              v.size?.toLowerCase().includes(variantSearchTerm.toLowerCase()) ||
                              v.color?.toLowerCase().includes(variantSearchTerm.toLowerCase()) ||
                              v.stock_code?.toLowerCase().includes(variantSearchTerm.toLowerCase()) ||
                              v.barcode?.toLowerCase().includes(variantSearchTerm.toLowerCase())
                            )
                            ?.map((v) => (
                            <tr key={v.id || v.originalIdx} className="hover:bg-orange-50/30 transition-colors">
                              <td className="px-4 py-3">
                                <div className="flex flex-col">
                                  <span className="font-bold text-gray-900 text-lg">{v.size || "-"}</span>
                                  {v.color && <span className="text-xs text-gray-500">{v.color}</span>}
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <input
                                  type="text"
                                  value={v.stock_code || ""}
                                  onChange={(e) => {
                                    const updated = [...formData.variants];
                                    updated[v.originalIdx].stock_code = e.target.value;
                                    setFormData({...formData, variants: updated});
                                  }}
                                  className="w-full border-gray-200 border px-2 py-1.5 rounded bg-gray-50 focus:bg-white focus:border-black outline-none font-mono text-xs"
                                  placeholder="Stok kodu..."
                                />
                              </td>
                              <td className="px-4 py-3">
                                <input
                                  type="text"
                                  value={v.barcode || ""}
                                  onChange={(e) => {
                                    const updated = [...formData.variants];
                                    updated[v.originalIdx].barcode = e.target.value;
                                    setFormData({...formData, variants: updated});
                                  }}
                                  className="w-full border-gray-200 border px-2 py-1.5 rounded bg-gray-50 focus:bg-white focus:border-black outline-none font-mono text-xs"
                                  placeholder="Barkod girin..."
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <input
                                  type="number"
                                  value={v.stock || 0}
                                  onChange={(e) => {
                                    const updated = [...formData.variants];
                                    updated[v.originalIdx].stock = parseInt(e.target.value) || 0;
                                    setFormData({...formData, variants: updated});
                                  }}
                                  className={`w-20 border-gray-200 border px-2 py-1.5 rounded text-center font-bold ${v.stock < 5 ? 'text-red-600 bg-red-50 border-red-200' : 'text-gray-900'}`}
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setFormData({ ...formData, variants: formData.variants.filter((_, i) => i !== v.originalIdx) });
                                  }}
                                  className="text-red-400 hover:text-red-600 p-2 hover:bg-red-50 rounded-full transition-colors"
                                >
                                  <Trash2 size={18} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot className="bg-gray-50 border-t">
                          <tr>
                            <td colSpan={2} className="px-4 py-3 text-sm font-bold text-gray-500 text-right">Toplam Stok:</td>
                            <td className="px-4 py-3 text-center text-lg font-black text-black">
                              {formData.variants.reduce((sum, v) => sum + (v.stock || 0), 0)}
                            </td>
                            <td></td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  )}

                  {/* Add New Variant Section */}
                  <div className="bg-orange-50 rounded-xl p-6 border border-orange-100">
                    <h4 className="text-sm font-bold text-orange-900 mb-4 uppercase tracking-wider">Hızlı Varyant Ekle</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 items-end">
                      <div>
                        <label className="block text-xs font-bold text-orange-700 mb-1 uppercase">Beden *</label>
                        <div className="relative size-dropdown-container">
                          <input 
                            type="text" 
                            placeholder="Beden ara veya seç..." 
                            className="w-full border-orange-200 border-2 px-3 py-2 rounded-lg focus:border-orange-500 outline-none text-sm font-bold bg-white"
                            value={sizeSearchTerm || formData.newVariant?.size || ""}
                            onChange={(e) => { setSizeSearchTerm(e.target.value); setSizeSearchOpen(true); }}
                            onFocus={() => setSizeSearchOpen(true)}
                          />
                          {sizeSearchOpen && (
                            <div className="absolute z-[9999] w-full mt-1 bg-white border-2 border-orange-300 rounded-xl shadow-2xl" style={{maxHeight: '320px', overflowY: 'auto'}}>
                              <div className="p-2">
                                {globalSizes
                                  .filter(s => s.value.toLowerCase().includes((sizeSearchTerm || "").toLowerCase()))
                                  .slice(0, 30)
                                  .map(s => (
                                  <div 
                                    key={s.id}
                                    className="px-4 py-3 text-sm hover:bg-orange-100 cursor-pointer rounded-lg font-semibold transition-colors border-b border-gray-100 last:border-b-0"
                                    onClick={() => { 
                                      setFormData({...formData, newVariant: {...(formData.newVariant || {}), size: s.value}}); 
                                      setSizeSearchOpen(false); 
                                      setSizeSearchTerm(""); 
                                    }}
                                  >
                                    {s.value}
                                  </div>
                                ))}
                                {globalSizes.filter(s => s.value.toLowerCase().includes((sizeSearchTerm || "").toLowerCase())).length === 0 && (
                                  <div className="px-4 py-3 text-sm text-gray-400 italic">Sonuç bulunamadı</div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-orange-700 mb-1 uppercase">Renk</label>
                        <div className="relative color-dropdown-container">
                          <input 
                            type="text" 
                            placeholder="Renk ara veya seç..." 
                            className="w-full border-orange-200 border-2 px-3 py-2 rounded-lg focus:border-orange-500 outline-none text-sm font-bold bg-white"
                            value={colorSearchTerm || formData.newVariant?.color || ""}
                            onChange={(e) => { setColorSearchTerm(e.target.value); setColorSearchOpen(true); }}
                            onFocus={() => setColorSearchOpen(true)}
                          />
                          {colorSearchOpen && (
                            <div className="absolute z-[9999] w-full mt-1 bg-white border-2 border-orange-300 rounded-xl shadow-2xl" style={{maxHeight: '320px', overflowY: 'auto'}}>
                              <div className="p-2">
                                {globalColors
                                  .filter(c => c.value.toLowerCase().includes((colorSearchTerm || "").toLowerCase()))
                                  .slice(0, 30)
                                  .map(c => (
                                  <div 
                                    key={c.id}
                                    className="px-4 py-3 text-sm hover:bg-orange-100 cursor-pointer rounded-lg font-semibold transition-colors border-b border-gray-100 last:border-b-0"
                                    onClick={() => { 
                                      setFormData({...formData, newVariant: {...(formData.newVariant || {}), color: c.value}}); 
                                      setColorSearchOpen(false); 
                                      setColorSearchTerm(""); 
                                    }}
                                  >
                                    {c.value}
                                  </div>
                                ))}
                                {globalColors.filter(c => c.value.toLowerCase().includes((colorSearchTerm || "").toLowerCase())).length === 0 && (
                                  <div className="px-4 py-3 text-sm text-gray-400 italic">Sonuç bulunamadı</div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-orange-700 mb-1 uppercase">Stok Adedi</label>
                        <input
                          type="number"
                          value={formData.newVariant?.stock || ""}
                          onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), stock: parseInt(e.target.value) || 0}})}
                          className="w-full border-orange-200 border-2 px-3 py-2 rounded-lg focus:border-orange-500 outline-none text-sm font-bold"
                          placeholder="0"
                        />
                      </div>
                      <div className="md:col-span-1">
                        <label className="block text-xs font-bold text-orange-700 mb-1 uppercase">Barkod</label>
                        <div className="flex gap-1">
                          <input
                            type="text"
                            value={formData.newVariant?.barcode || ""}
                            onChange={(e) => setFormData({...formData, newVariant: {...(formData.newVariant || {}), barcode: e.target.value}})}
                            className="w-full border-orange-200 border-2 px-3 py-2 rounded-lg focus:border-orange-500 outline-none text-xs font-mono"
                            placeholder="Otomatik..."
                          />
                        </div>
                      </div>
                      <div className="md:col-span-1">
                        <button
                          type="button"
                          onClick={() => {
                            if (!formData.newVariant?.size) {
                              toast.error("Beden seçimi zorunludur");
                              return;
                            }
                            const newVar = {
                              id: `var-${Date.now()}`,
                              size: formData.newVariant.size,
                              stock: formData.newVariant.stock || 0,
                              barcode: formData.newVariant.barcode || "",
                              stock_code: formData.stock_code || "",
                              color: formData.newVariant.color || ""
                            };
                            setFormData({
                              ...formData,
                              variants: [...(formData.variants || []), newVar],
                              newVariant: {}
                            });
                          }}
                          className="w-full bg-orange-600 text-white font-bold py-2.5 rounded-lg hover:bg-orange-700 shadow-md shadow-orange-200 transition-all flex items-center justify-center gap-2"
                        >
                          <Plus size={18} /> Varyantı Ekle
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Trendyol Tab */}
              <TabsContent value="trendyol" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="bg-white p-8 rounded-xl border-t-4 border-t-orange-500 shadow-sm">
                  <div className="flex justify-between items-center mb-8">
                    <div>
                      <h3 className="text-xl font-black text-gray-900 uppercase tracking-tight flex items-center gap-2">
                        <Store className="text-orange-500" size={24} />
                        Trendyol Entegrasyon Ayarları
                      </h3>
                      <p className="text-sm text-gray-500">Bu ürünün Trendyol'da nasıl görüneceğini ve eşleşeceğini ayarlayın.</p>
                    </div>
                    <div className="flex items-center gap-3 bg-orange-50 px-4 py-2 rounded-full">
                      <span className="text-xs font-bold text-orange-700 uppercase">Durum:</span>
                      <span className="flex items-center gap-1.5 text-xs font-bold text-orange-600">
                        <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
                        Yayına Hazır
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="space-y-6">
                      <div className="space-y-2">
                        <label className="block text-xs font-black text-gray-400 uppercase tracking-widest">Trendyol Kategorisi</label>
                        <select
                          value={formData.trendyol_category_id}
                          onChange={(e) => setFormData({ ...formData, trendyol_category_id: e.target.value })}
                          className="w-full border-gray-200 border-2 px-4 py-3 rounded-xl focus:border-orange-500 outline-none transition-all font-bold text-gray-700 bg-gray-50 focus:bg-white"
                        >
                          <option value="">Kategori Seçin</option>
                          {trendyolCategories.map(cat => (
                            <option key={cat.id} value={cat.id}>{cat.name}</option>
                          ))}
                        </select>
                      </div>

                      <div className="bg-gray-50 p-6 rounded-2xl border border-gray-100 space-y-4">
                        <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest mb-2">Kategori Bilgisi</h4>
                        <div className="text-sm font-bold text-gray-600 italic">
                          {formData.category_name || "Kategori seçilmemiş"}
                        </div>
                        <p className="text-[10px] text-gray-400 font-medium leading-relaxed">
                          Ürün özellikleri ve Trendyol eşleştirmeleri kategori düzeyinde yönetilmektedir. 
                          Değişiklik yapmak için Kategori Ayarları sayfasını ziyaret edin.
                        </p>
                      </div>
                    </div>

                    <div className="space-y-6">
                      <div className="bg-gray-900 rounded-3xl p-8 text-white shadow-2xl shadow-orange-200 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500 rounded-full blur-[80px] opacity-20 group-hover:opacity-40 transition-opacity" />
                        <div className="relative z-10">
                          <p className="text-[10px] font-black text-orange-400 uppercase tracking-[4px] mb-6">Satış Özeti</p>
                          
                          <div className="space-y-4">
                            <div className="flex justify-between items-baseline border-b border-gray-800 pb-4">
                              <span className="text-gray-400 text-xs font-bold uppercase">Mağaza Fiyatı</span>
                              <span className="text-xl font-bold">{formData.sale_price || formData.price || 0} TL</span>
                            </div>
                            <div className="flex justify-between items-baseline border-b border-gray-800 pb-4">
                              <span className="text-gray-400 text-xs font-bold uppercase">Markup (%{formData.use_default_markup ? globalTrendyolMarkup : formData.markup_rate})</span>
                              <span className="text-green-400 font-bold">
                                +{(((formData.sale_price || formData.price || 0) * (formData.use_default_markup ? globalTrendyolMarkup : formData.markup_rate)) / 100).toFixed(2)} TL
                              </span>
                            </div>
                            <div className="flex justify-between items-center pt-2">
                              <span className="text-white text-sm font-black uppercase tracking-widest">Trendyol Fiyatı</span>
                              <div className="text-right">
                                <span className="text-3xl font-black text-orange-500">
                                  {((formData.sale_price || formData.price || 0) * (1 + (formData.use_default_markup ? globalTrendyolMarkup : formData.markup_rate) / 100)).toFixed(2)}
                                </span>
                                <span className="text-orange-300 font-bold ml-1">TL</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div 
                        className="bg-white p-6 rounded-2xl border-2 border-dashed border-gray-100 flex flex-col items-center justify-center text-center group cursor-pointer hover:border-orange-300 transition-all active:scale-95"
                        onClick={() => editingProduct && handleTrendyolSync(editingProduct.id)}
                      >
                        <div className="w-16 h-16 rounded-full bg-orange-50 flex items-center justify-center mb-4 group-hover:bg-orange-100 transition-colors">
                          <Store className="text-orange-500" size={32} />
                        </div>
                        <h4 className="text-sm font-black text-gray-900 uppercase mb-1">Şimdi Trendyol'a Aktar</h4>
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-tighter">Ürünü anlık olarak Trendyol kataloğuna gönderin</p>
                      </div>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Images Tab */}
              <TabsContent value="images" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="bg-white p-8 rounded-xl border shadow-sm">
                  <div className="flex justify-between items-center mb-6">
                    <div>
                      <h3 className="font-bold text-gray-900 uppercase tracking-widest text-sm">Ürün Galerisi</h3>
                      <p className="text-xs text-gray-400 mt-1">Sürükleyip bırakarak sıralayabilirsiniz.</p>
                    </div>
                    <label className="bg-black text-white px-6 py-2 rounded-full text-xs font-bold uppercase tracking-widest cursor-pointer hover:bg-gray-800 transition-all flex items-center gap-2">
                      <Upload size={16} /> Görsel Yükle
                      <input 
                        ref={fileInputRef}
                        type="file" 
                        multiple 
                        accept="image/*" 
                        onChange={handleImageUpload} 
                        className="hidden" 
                      />
                    </label>
                  </div>

                  {uploading && (
                    <div className="mb-6 bg-orange-50 p-4 rounded-lg flex items-center gap-3 animate-pulse">
                      <RefreshCw className="animate-spin text-orange-500" size={20} />
                      <span className="text-sm font-bold text-orange-700 uppercase">Görseller İşleniyor...</span>
                    </div>
                  )}

                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-6">
                    {formData.images.map((img, idx) => (
                      <div key={idx} className="relative group aspect-[3/4] rounded-2xl overflow-hidden border-4 border-white shadow-md hover:shadow-xl transition-all">
                        <img src={img} className="w-full h-full object-cover" alt="" />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <button 
                            type="button"
                            onClick={() => removeImage(idx)} 
                            className="w-10 h-10 rounded-full bg-red-500 text-white flex items-center justify-center hover:bg-red-600 transition-colors"
                          >
                            <Trash2 size={20} />
                          </button>
                        </div>
                        {idx === 0 && (
                          <div className="absolute top-2 left-2 px-3 py-1 bg-black text-white text-[10px] font-black uppercase tracking-tighter rounded-full">Kapak</div>
                        )}
                        <div className="absolute bottom-2 right-2 w-6 h-6 rounded-full bg-white/90 text-black flex items-center justify-center text-[10px] font-black">{idx + 1}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </TabsContent>

              {/* SEO Tab */}
              <TabsContent value="seo" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="bg-white p-8 rounded-xl border shadow-sm space-y-6">
                  <h3 className="font-semibold text-lg text-gray-900 border-b pb-4 mb-6 flex items-center gap-2">
                    <Globe size={20} className="text-purple-500" />
                    Google Arama Görünümü (SEO)
                  </h3>
                  <div className="space-y-6 max-w-2xl">
                    <div>
                      <label className="block text-xs font-black text-gray-400 uppercase tracking-widest mb-2">Meta Başlık</label>
                      <input
                        type="text"
                        value={formData.meta_title}
                        onChange={(e) => setFormData({ ...formData, meta_title: e.target.value })}
                        className="w-full border-gray-200 border-2 px-4 py-3 rounded-xl focus:border-black outline-none font-bold"
                        placeholder="Örn: En Şık Gece Elbiseleri | Facette"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-black text-gray-400 uppercase tracking-widest mb-2">Meta Açıklama</label>
                      <textarea
                        value={formData.meta_description}
                        onChange={(e) => setFormData({ ...formData, meta_description: e.target.value })}
                        rows={4}
                        className="w-full border-gray-200 border-2 px-4 py-3 rounded-xl focus:border-black outline-none font-medium text-sm"
                        placeholder="Sayfa açıklamasını buraya yazın..."
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Stock Tab */}
              <TabsContent value="stock" className="space-y-6 m-0 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="bg-white p-8 rounded-xl border shadow-sm">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="font-bold text-xl text-gray-900 uppercase">Hızlı Stok Yönetimi</h3>
                    <div className="flex items-center gap-4">
                      <span className="text-xs font-bold text-gray-400 uppercase">Toplam Stok:</span>
                      <span className="px-4 py-1 bg-black text-white rounded-full text-lg font-black">
                        {formData.variants.reduce((sum, v) => sum + (v.stock || 0), 0)}
                      </span>
                    </div>
                  </div>
                  
                  <div className="border rounded-2xl overflow-hidden shadow-sm">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 border-b">
                        <tr>
                          <th className="text-left px-6 py-4 font-black text-gray-500 uppercase tracking-widest">Varyant</th>
                          <th className="text-left px-6 py-4 font-black text-gray-500 uppercase tracking-widest">Stok</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {formData.variants.map((v, idx) => (
                          <tr key={idx} className="hover:bg-orange-50/20 transition-colors">
                            <td className="px-6 py-4">
                              <span className="font-bold text-black">{v.size} {v.color && `/ ${v.color}`}</span>
                              <p className="text-[10px] text-gray-400 font-mono mt-1">{v.stock_code || v.barcode}</p>
                            </td>
                            <td className="px-6 py-4">
                              <input
                                type="number"
                                value={v.stock || 0}
                                onChange={(e) => {
                                  const updated = [...formData.variants];
                                  updated[idx].stock = parseInt(e.target.value) || 0;
                                  setFormData({...formData, variants: updated});
                                }}
                                className="w-24 text-center border-2 border-gray-100 px-4 py-2 rounded-xl text-lg font-black"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </div>
        </DialogContent>
      </Dialog>

      {/* Variants Modal */}
      <Dialog open={variantsModalOpen} onOpenChange={setVariantsModalOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader className="flex flex-row items-center justify-between border-b pb-4 mb-4">
            <DialogTitle>
              Beden Varyantları - {selectedProductForVariants?.name}
            </DialogTitle>
            <button
              onClick={handleSaveVariants}
              className="px-6 py-2 bg-black text-white rounded-lg text-sm font-bold hover:bg-gray-800 transition-colors shadow-sm"
            >
              KAYDET
            </button>
          </DialogHeader>
          
          {selectedProductForVariants && (
            <div>
              {/* Summary */}
              <div className="grid grid-cols-3 gap-4 mb-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Renk</p>
                  <p className="text-xl font-black text-gray-900">{selectedProductForVariants.variants?.[0]?.color || selectedProductForVariants.color || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Toplam Beden</p>
                  <p className="text-xl font-black text-gray-900">{selectedProductForVariants.variants?.length || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-1">Toplam Stok</p>
                  <p className="text-xl font-black text-gray-900">
                    {selectedProductForVariants.variants?.reduce((sum, v) => sum + (v.stock || 0), 0) || 0}
                  </p>
                </div>
              </div>

              {/* Variants Table */}
              <div className="border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-bold text-gray-600">Beden / Renk</th>
                    <th className="text-left px-4 py-3 font-bold text-gray-600">Stok Kodu</th>
                    <th className="text-left px-4 py-3 font-bold text-gray-600">Barkod</th>
                    <th className="text-center px-4 py-3 font-bold text-gray-600 w-24">Stok</th>
                    <th className="text-right px-4 py-3 font-bold text-gray-600 w-32">Fiyat (TL)</th>
                    <th className="text-center px-4 py-3 font-bold text-gray-600 w-24">Durum</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {selectedProductForVariants.variants?.map((variant, idx) => (
                    <tr key={variant.id || idx} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex flex-col">
                          <span className="font-bold text-gray-900 text-lg">{variant.size || "-"}</span>
                          {variant.color && <span className="text-xs text-gray-500">{variant.color}</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={variant.stock_code || ""}
                          onChange={(e) => {
                           const newVariants = [...selectedProductForVariants.variants];
                           newVariants[idx] = { ...variant, stock_code: e.target.value };
                           setSelectedProductForVariants({ ...selectedProductForVariants, variants: newVariants });
                          }}
                          className="w-full border-gray-200 border px-2 py-1.5 rounded bg-white focus:border-black outline-none font-mono text-xs"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={variant.barcode || ""}
                          onChange={(e) => {
                           const newVariants = [...selectedProductForVariants.variants];
                           newVariants[idx] = { ...variant, barcode: e.target.value };
                           setSelectedProductForVariants({ ...selectedProductForVariants, variants: newVariants });
                          }}
                          className="w-full border-gray-200 border px-2 py-1.5 rounded bg-white focus:border-black outline-none font-mono text-xs"
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <input
                          type="number"
                          value={variant.stock || 0}
                          onChange={(e) => {
                           const newVariants = [...selectedProductForVariants.variants];
                           newVariants[idx] = { ...variant, stock: parseInt(e.target.value) || 0 };
                           setSelectedProductForVariants({ ...selectedProductForVariants, variants: newVariants });
                          }}
                          className={`w-20 border-gray-200 border px-2 py-1.5 rounded text-center font-bold bg-white focus:border-black outline-none ${variant.stock < 5 ? 'text-red-600 border-red-200' : 'text-gray-900'}`}
                        />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <input
                          type="number"
                          value={variant.sale_price !== undefined && variant.sale_price !== null ? variant.sale_price : (variant.price || selectedProductForVariants.price || 0)}
                          onChange={(e) => {
                           const newVariants = [...selectedProductForVariants.variants];
                           newVariants[idx] = { ...variant, sale_price: parseFloat(e.target.value) || 0 };
                           setSelectedProductForVariants({ ...selectedProductForVariants, variants: newVariants });
                          }}
                          className="w-24 border-gray-200 border px-2 py-1.5 rounded text-right font-bold bg-white focus:border-black outline-none text-red-600"
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => {
                           const newVariants = [...selectedProductForVariants.variants];
                           newVariants[idx] = { ...variant, is_active: variant.is_active === false ? true : false };
                           setSelectedProductForVariants({ ...selectedProductForVariants, variants: newVariants });
                          }}
                          className={`px-3 py-1.5 text-xs font-bold rounded w-full transition-colors ${variant.is_active !== false ? 'bg-green-100 text-green-800 hover:bg-green-200' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'}`}
                        >
                          {variant.is_active !== false ? 'Aktif' : 'Pasif'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>

              {(!selectedProductForVariants.variants || selectedProductForVariants.variants.length === 0) && (
                <p className="text-center text-gray-500 py-8">Bu ürünün beden varyantı bulunmuyor</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Technical Details Import Modal */}
      <Dialog open={techImportModalOpen} onOpenChange={setTechImportModalOpen}>
        <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto" data-testid="tech-import-modal">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Teknik Detay Eşleştirme Sonuçları</DialogTitle>
          </DialogHeader>
          {techImportResults && (
            <div className="space-y-4">
              <div className="flex gap-4 text-sm">
                <div className="bg-green-50 border border-green-200 px-4 py-2 rounded-lg">
                  <span className="font-bold text-green-700">{techImportResults.matched}</span>
                  <span className="text-green-600 ml-1">Eşleşen</span>
                </div>
                <div className="bg-red-50 border border-red-200 px-4 py-2 rounded-lg">
                  <span className="font-bold text-red-700">{techImportResults.unmatched}</span>
                  <span className="text-red-600 ml-1">Eşleşmeyen</span>
                </div>
                <div className="bg-gray-50 border border-gray-200 px-4 py-2 rounded-lg">
                  <span className="font-bold text-gray-700">{techImportResults.total_excel_products}</span>
                  <span className="text-gray-600 ml-1">Toplam</span>
                </div>
              </div>

              <div className="border rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="text-left px-3 py-2 font-bold text-gray-600 w-8">#</th>
                      <th className="text-left px-3 py-2 font-bold text-gray-600">Excel Ürün Adı</th>
                      <th className="text-left px-3 py-2 font-bold text-gray-600">Eşleşen Ürün</th>
                      <th className="text-center px-3 py-2 font-bold text-gray-600 w-16">Skor</th>
                      <th className="text-center px-3 py-2 font-bold text-gray-600 w-20">Özellik</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {techImportResults.results.map((r, idx) => (
                      <tr key={idx} className={r.matched_product_id ? "bg-white" : "bg-red-50"}>
                        <td className="px-3 py-2 text-gray-400">{idx + 1}</td>
                        <td className="px-3 py-2 font-medium">{r.excel_name}</td>
                        <td className="px-3 py-2">
                          {r.matched_product_name ? (
                            <span className="text-green-700 font-medium">{r.matched_product_name}</span>
                          ) : (
                            <span className="text-red-500 italic">Eşleşme bulunamadı</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${
                            r.match_score >= 80 ? 'bg-green-100 text-green-700' :
                            r.match_score >= 50 ? 'bg-yellow-100 text-yellow-700' :
                            r.match_score > 0 ? 'bg-orange-100 text-orange-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            %{r.match_score}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-center text-gray-600">{r.attributes.length}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  onClick={() => { setTechImportModalOpen(false); setTechImportResults(null); }}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium text-sm hover:bg-gray-200 transition-colors"
                >
                  İptal
                </button>
                <button
                  onClick={handleApplyTechImport}
                  disabled={techApplying || techImportResults.matched === 0}
                  data-testid="apply-tech-import-btn"
                  className="px-6 py-2 bg-orange-600 text-white rounded-lg font-bold text-sm hover:bg-orange-700 transition-colors disabled:opacity-50 shadow-sm"
                >
                  {techApplying ? "Uygulanıyor..." : `${techImportResults.matched} Ürüne Uygula`}
                </button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
