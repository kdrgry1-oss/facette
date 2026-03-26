import { useState, useEffect } from "react";
import { Plus, Edit, Trash2, GripVertical, Image, Upload, X, Eye, EyeOff, ChevronUp, ChevronDown } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BLOCK_TYPES = [
  { value: "hero_slider", label: "Hero Slider", icon: "🎠", description: "Ana sayfa slider - Dönen görseller" },
  { value: "rotating_text", label: "Dönen Yazı", icon: "📢", description: "Üst banner'da dönen metin" },
  { value: "full_banner", label: "Tam Genişlik Banner", icon: "🖼️", description: "Tek görsel tam genişlik" },
  { value: "half_banners", label: "Yarı Yarıya Banner", icon: "◧", description: "İki görsel yan yana" },
  { value: "product_slider", label: "Ürün Slider", icon: "🛍️", description: "Yatay ürün listesi" },
  { value: "instashop", label: "InstaShop", icon: "📸", description: "Instagram tarzı görseller" },
  { value: "text_block", label: "Yazı Bloğu", icon: "📝", description: "Başlık ve açıklama" },
  { value: "video_banner", label: "Video Banner", icon: "🎬", description: "Video arka planlı banner" },
];

// Sortable Block Item Component
function SortableBlockItem({ block, onEdit, onDelete, onToggleActive, getBlockTypeInfo }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: block.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 1000 : 1,
  };

  const typeInfo = getBlockTypeInfo(block.type);

  return (
    <div 
      ref={setNodeRef}
      style={style}
      className={`bg-white rounded-lg shadow-sm border-2 transition-all ${
        isDragging ? 'border-blue-500 shadow-lg' : 'border-transparent hover:border-gray-200'
      } ${!block.is_active ? 'opacity-60' : ''}`}
    >
      <div className="flex items-start p-4 gap-4">
        {/* Drag Handle */}
        <div 
          {...attributes} 
          {...listeners}
          className="pt-2 cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600"
        >
          <GripVertical size={20} />
        </div>

        {/* Preview */}
        <div className="flex-shrink-0 w-40">
          {block.images?.[0] ? (
            <img 
              src={block.images[0]} 
              alt="" 
              className="w-full h-20 object-cover rounded"
            />
          ) : (
            <div className="w-full h-20 bg-gray-100 rounded flex items-center justify-center text-2xl">
              {typeInfo.icon || "📦"}
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-xs bg-gray-100 px-2 py-0.5 rounded font-medium">
              {typeInfo.icon} {typeInfo.label}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${
              block.is_active ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-600'
            }`}>
              {block.is_active ? 'Yayında' : 'Taslak'}
            </span>
          </div>
          <h3 className="font-medium truncate">{block.title || "Başlıksız"}</h3>
          <p className="text-sm text-gray-500">
            {block.type === "product_slider"
              ? block.settings?.product_ids?.length
                ? `${block.settings.product_ids.length} ürün seçili`
                : `En yeni ürünler gösterilir`
              : block.type === "text_block"
              ? block.settings?.text
                ? block.settings.text.slice(0, 60) + (block.settings.text.length > 60 ? "…" : "")
                : "Metin girilmemiş"
              : block.type === "video_banner"
              ? block.settings?.video_url ? "Video eklendi ✓" : "Video eklenmemiş"
              : block.type === "rotating_text"
              ? `${block.settings?.texts?.length || 0} metin`
              : `${block.images?.length || 0} görsel`
            }
          </p>
          {block.links?.[0] && (
            <p className="text-xs text-gray-400 mt-1 truncate">
              → {block.links[0]}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1">
          <button 
            onClick={() => onToggleActive(block)}
            className={`p-2 rounded transition-colors ${
              block.is_active ? 'hover:bg-gray-100' : 'hover:bg-green-50 text-green-600'
            }`}
            title={block.is_active ? 'Taslağa Al' : 'Yayınla'}
          >
            {block.is_active ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
          <button 
            onClick={() => onEdit(block)}
            className="p-2 hover:bg-gray-100 rounded"
            title="Düzenle"
          >
            <Edit size={16} />
          </button>
          <button 
            onClick={() => onDelete(block.id)}
            className="p-2 hover:bg-red-50 rounded text-red-600"
            title="Sil"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PageDesign() {
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingBlock, setEditingBlock] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [previewMode, setPreviewMode] = useState("mobile"); // "mobile" | "desktop"
  
  const refreshPreview = () => {
    const iframe = document.getElementById('preview-frame');
    if (iframe) iframe.src = iframe.src;
  };
  
  const [formData, setFormData] = useState({
    type: "hero_slider",
    title: "",
    images: [],
    links: [],
    settings: { texts: [""] },
    sort_order: 0,
    is_active: true,
    page: "home"
  });

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  useEffect(() => {
    fetchBlocks();
  }, []);

  const fetchBlocks = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/page-blocks?page=home`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      // Sort by sort_order
      const sorted = (res.data || []).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      setBlocks(sorted);
    } catch (err) {
      // Default blocks if API fails
      setBlocks([
        {
          id: "hero",
          type: "hero_slider",
          title: "Hero Slider",
          images: [
            "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/en-yeniler-dc2e.jpg",
            "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/ae79c961-ba0b-49e3-b274-2c6cc78ab700.jpg"
          ],
          links: ["/kategori/en-yeniler", "/kategori/sale"],
          is_active: true,
          sort_order: 1
        },
        {
          id: "full",
          type: "full_banner",
          title: "Bloom Together",
          images: ["https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-cb23757c-6.jpg"],
          links: ["/kategori/en-yeniler"],
          is_active: true,
          sort_order: 2
        },
        {
          id: "half",
          type: "half_banners",
          title: "Kategori Bannerları",
          images: [
            "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-65777bd3-0.jpg",
            "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-7b3e27f9-5.jpg"
          ],
          links: ["/kategori/gomlek", "/kategori/aksesuar"],
          is_active: true,
          sort_order: 3
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleDragEnd = (event) => {
    const { active, over } = event;

    if (active.id !== over?.id) {
      setBlocks((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);
        const newItems = arrayMove(items, oldIndex, newIndex);
        // Update sort_order
        return newItems.map((item, index) => ({ ...item, sort_order: index + 1 }));
      });
      setHasChanges(true);
    }
  };

  const handleSaveOrder = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      // Update each block's sort_order
      await Promise.all(blocks.map((block, index) => 
        axios.put(`${API}/page-blocks/${block.id}`, {
          ...block,
          sort_order: index + 1
        }, { headers }).catch(() => {})
      ));
      
      toast.success("Sıralama kaydedildi");
      setHasChanges(false);
      refreshPreview();
    } catch (err) {
      toast.error("Kaydetme başarısız");
    } finally {
      setSaving(false);
    }
  };

  const handleImageUpload = async (e, index = null) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    try {
      const token = localStorage.getItem('token');
      const fd = new FormData();
      fd.append('file', file);
      const res = await axios.post(`${API}/upload/image`, fd, {
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      if (res.data.path) {
        const url = `${API.replace('/api', '')}/api/files/${res.data.path}`;
        const newImages = [...formData.images];
        const newLinks = [...formData.links];
        
        if (index !== null) {
          newImages[index] = url;
        } else {
          newImages.push(url);
          newLinks.push("/");
        }
        
        setFormData({ ...formData, images: newImages, links: newLinks });
        toast.success("Görsel yüklendi");
      }
    } catch (err) {
      toast.error("Görsel yüklenemedi");
    } finally {
      setUploading(false);
    }
  };

  const removeImage = (index) => {
    const newImages = [...formData.images];
    const newLinks = [...formData.links];
    newImages.splice(index, 1);
    newLinks.splice(index, 1);
    setFormData({ ...formData, images: newImages, links: newLinks });
  };

  const [productSearch, setProductSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchingProducts, setSearchingProducts] = useState(false);
  const [selectedProductDetails, setSelectedProductDetails] = useState([]);

  // Load details for already selected products when editing
  useEffect(() => {
    if (modalOpen && editingBlock && editingBlock.type === "product_slider" && editingBlock.settings?.product_ids?.length > 0) {
      loadSelectedProducts(editingBlock.settings.product_ids);
    } else if (modalOpen && !editingBlock) {
      setSelectedProductDetails([]);
    }
  }, [modalOpen, editingBlock]);

  const loadSelectedProducts = async (ids) => {
    try {
      const token = localStorage.getItem('token');
      // A quick parallel fetch for each id (since we don't have a bulk endpoint in admin by default)
      const details = [];
      for (const id of ids) {
        const res = await axios.get(`${API}/products/${id}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (res.data) details.push(res.data);
      }
      setSelectedProductDetails(details);
    } catch (err) {
      console.error(err);
    }
  };

  const handleProductSearch = async (e) => {
    e.preventDefault();
    if (!productSearch.trim()) return;
    setSearchingProducts(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/products?search=${productSearch}&limit=10`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSearchResults(res.data.products || []);
    } catch (err) {
      toast.error("Arama yapılamadı");
    } finally {
      setSearchingProducts(false);
    }
  };

  const addProductToBlock = (product) => {
    const currentIds = formData.settings?.product_ids || [];
    if (currentIds.includes(product._id)) {
      return toast.error("Bu ürün zaten ekli");
    }
    const newIds = [...currentIds, product._id];
    setFormData({ 
      ...formData, 
      settings: { ...formData.settings, product_ids: newIds } 
    });
    setSelectedProductDetails([...selectedProductDetails, product]);
  };

  const removeProductFromBlock = (index) => {
    const currentIds = [...(formData.settings?.product_ids || [])];
    currentIds.splice(index, 1);
    setFormData({ 
      ...formData, 
      settings: { ...formData.settings, product_ids: currentIds } 
    });
    const newDetails = [...selectedProductDetails];
    newDetails.splice(index, 1);
    setSelectedProductDetails(newDetails);
  };


  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      const payload = {
        ...formData,
        sort_order: editingBlock ? formData.sort_order : blocks.length + 1
      };
      
      if (editingBlock) {
        await axios.put(`${API}/page-blocks/${editingBlock.id}`, payload, { headers });
        toast.success("Blok güncellendi");
      } else {
        await axios.post(`${API}/page-blocks`, payload, { headers });
        toast.success("Blok eklendi");
      }
      setModalOpen(false);
      resetForm();
      fetchBlocks();
      refreshPreview();
    } catch (err) {
      toast.error("İşlem başarısız");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Bloğu silmek istediğinize emin misiniz?")) return;
    try {
      const token = localStorage.getItem('token');
      await axios.delete(`${API}/page-blocks/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Blok silindi");
      fetchBlocks();
      refreshPreview();
    } catch (err) {
      toast.error("Silme başarısız");
    }
  };

  const handleToggleActive = async (block) => {
    try {
      const token = localStorage.getItem('token');
      await axios.put(`${API}/page-blocks/${block.id}`, {
        ...block,
        is_active: !block.is_active
      }, { headers: { Authorization: `Bearer ${token}` } });
      
      setBlocks(blocks.map(b => 
        b.id === block.id ? { ...b, is_active: !b.is_active } : b
      ));
      toast.success(block.is_active ? "Blok taslağa alındı" : "Blok yayınlandı");
      refreshPreview();
    } catch (err) {
      toast.error("İşlem başarısız");
    }
  };

  const moveBlock = (index, direction) => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= blocks.length) return;
    
    const newBlocks = arrayMove(blocks, index, newIndex).map((item, i) => ({
      ...item,
      sort_order: i + 1
    }));
    setBlocks(newBlocks);
    setHasChanges(true);
  };

  const openEditModal = (block) => {
    setEditingBlock(block);
    setFormData({
      type: block.type,
      title: block.title || "",
      images: block.images || [],
      links: block.links || [],
      settings: block.settings || {},
      sort_order: block.sort_order || 0,
      is_active: block.is_active ?? true,
      page: block.page || "home"
    });
    setModalOpen(true);
  };

  const resetForm = () => {
    setEditingBlock(null);
    setFormData({
      type: "hero_slider",
      title: "",
      images: [],
      links: [],
      settings: { texts: [""] },
      sort_order: 0,
      is_active: true,
      page: "home"
    });
    setProductSearch("");
    setSearchResults([]);
    setSelectedProductDetails([]);
  };

  const getBlockTypeInfo = (type) => {
    return BLOCK_TYPES.find(t => t.value === type) || { label: type, icon: "📦" };
  };

  const needsImages = ["hero_slider", "full_banner", "half_banners", "instashop", "video_banner"].includes(formData.type);


  return (
    <div data-testid="page-design" className="flex flex-col lg:flex-row gap-8 h-screen pb-20">
      {/* Sol Panel: Yönetim */}
      <div className="flex-1 overflow-y-auto pr-4">
        <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Sayfa Tasarımı</h1>
          <p className="text-sm text-gray-500 mt-1">Ana sayfa blokları - Sürükle bırak ile sırala</p>
        </div>
        <div className="flex items-center gap-3">
          {hasChanges && (
            <button 
              onClick={handleSaveOrder}
              disabled={saving}
              className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
            >
              {saving ? "Kaydediliyor..." : "Sıralamayı Kaydet"}
            </button>
          )}
          <button 
            onClick={() => { resetForm(); setModalOpen(true); }}
            className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
          >
            <Plus size={18} />
            Yeni Blok
          </button>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4 mb-6">
        <div className="flex items-start gap-3">
          <div className="text-2xl">💡</div>
          <div>
            <p className="text-sm font-medium text-blue-900">Sürükle & Bırak ile Düzenle</p>
            <p className="text-xs text-blue-700 mt-1">
              Blokları sol taraftaki tutma noktasından sürükleyerek sıralayabilirsiniz. 
              Değişikliklerinizi kaydetmek için yeşil "Sıralamayı Kaydet" butonuna tıklayın.
            </p>
          </div>
        </div>
      </div>

      {/* Blocks List with Drag & Drop */}
      <DndContext 
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext 
          items={blocks.map(b => b.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-3">
            {loading ? (
              <div className="text-center py-8">Yükleniyor...</div>
            ) : blocks.length === 0 ? (
              <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                <div className="text-4xl mb-3">📦</div>
                <p className="text-gray-500 mb-4">Henüz blok eklenmemiş</p>
                <button 
                  onClick={() => { resetForm(); setModalOpen(true); }}
                  className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
                >
                  <Plus size={16} /> İlk Bloğu Ekle
                </button>
              </div>
            ) : (
              blocks.map((block, index) => (
                <SortableBlockItem
                  key={block.id}
                  block={block}
                  onEdit={openEditModal}
                  onDelete={handleDelete}
                  onToggleActive={handleToggleActive}
                  getBlockTypeInfo={getBlockTypeInfo}
                />
              ))
            )}
          </div>
        </SortableContext>
      </DndContext>

      {/* Block Types Legend */}
      {blocks.length > 0 && (
        <div className="mt-8 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium mb-3">Blok Tipleri</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {BLOCK_TYPES.map(type => (
              <div key={type.value} className="flex items-center gap-2 text-xs text-gray-600">
                <span>{type.icon}</span>
                <span>{type.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      </div>

      {/* Sağ Panel: Canlı Önizleme */}
      <div 
        className={`hidden lg:flex flex-col shrink-0 border-[6px] border-gray-900 bg-gray-100 overflow-hidden shadow-2xl relative mb-8 transition-all duration-300 ${
          previewMode === "mobile" 
            ? "w-[375px] xl:w-[414px] rounded-[2.5rem]" 
            : "flex-1 rounded-xl max-w-4xl"
        }`}
      >
        <div className="bg-gray-900 text-white py-2 px-6 flex justify-between items-center text-xs font-medium">
          <div className="flex items-center gap-4">
            <span>Canlı Önizleme</span>
            <div className="flex bg-gray-800 rounded p-1">
              <button 
                onClick={() => setPreviewMode("mobile")}
                className={`px-3 py-1 rounded transition-colors ${previewMode === "mobile" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
              >
                Mobil
              </button>
              <button 
                onClick={() => setPreviewMode("desktop")}
                className={`px-3 py-1 rounded transition-colors ${previewMode === "desktop" ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
              >
                Masaüstü
              </button>
            </div>
          </div>
          <button 
            type="button"
            onClick={refreshPreview} 
            className="text-gray-300 hover:text-white transition-colors flex items-center gap-1"
          >
            Yenile
          </button>
        </div>
        <div className="flex-1 w-full bg-white relative">
          <iframe
            id="preview-frame"
            src="/?preview=true"
            title="Canlı Önizleme"
            className="w-full h-full border-0 absolute inset-0 bg-white"
          />
        </div>
      </div>

      {/* Block Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingBlock ? "Blok Düzenle" : "Yeni Blok Ekle"}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Block Type Selection */}
            <div>
              <label className="block text-sm font-medium mb-2">Blok Tipi</label>
              <div className="grid grid-cols-2 gap-2">
                {BLOCK_TYPES.map(type => (
                  <button
                    key={type.value}
                    type="button"
                    onClick={() => setFormData({ ...formData, type: type.value })}
                    className={`p-3 border rounded-lg text-left transition-all ${
                      formData.type === type.value 
                        ? 'border-black bg-gray-50 ring-1 ring-black' 
                        : 'border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{type.icon}</span>
                      <div>
                        <p className="text-sm font-medium">{type.label}</p>
                        <p className="text-xs text-gray-500">{type.description}</p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Title */}
            <div>
              <label className="block text-sm font-medium mb-1">Başlık</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="Blok başlığı (opsiyonel)"
                className="w-full border px-3 py-2 rounded"
              />
            </div>

            {/* Active Toggle */}
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="w-4 h-4"
                />
                <span className="text-sm">Yayında (Ana sayfada müşterilere göster)</span>
              </label>
              <p className="text-xs text-gray-500 ml-6 block w-full">- Seçilmezse "Taslak" olur, sadece önizlemede görünür.</p>
            </div>

            {/* Dynamic Block Settings */}
            
            {needsImages && (
              <div>
                <label className="block text-sm font-medium mb-2">Görseller</label>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  {formData.images.map((img, index) => (
                    <div key={index} className="relative group">
                      <img src={img} alt="" className="w-full aspect-video object-cover rounded border" />
                      <button
                        type="button"
                        onClick={() => removeImage(index)}
                        className="absolute top-1 right-1 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X size={14} />
                      </button>
                      <input
                        type="text"
                        value={formData.links[index] || ""}
                        onChange={(e) => {
                          const newLinks = [...formData.links];
                          newLinks[index] = e.target.value;
                          setFormData({ ...formData, links: newLinks });
                        }}
                        placeholder="/kategori/..."
                        className="w-full text-xs border px-2 py-1.5 rounded mt-2"
                      />
                    </div>
                  ))}
                  
                  {/* Upload */}
                  <label className="aspect-video border-2 border-dashed border-gray-300 flex flex-col items-center justify-center cursor-pointer hover:border-black hover:bg-gray-50 rounded transition-colors">
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => handleImageUpload(e)}
                      className="hidden"
                    />
                    {uploading ? (
                      <div className="text-center">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-black mx-auto mb-2"></div>
                        <span className="text-xs text-gray-500">Yükleniyor...</span>
                      </div>
                    ) : (
                      <>
                        <Upload size={24} className="text-gray-400 mb-1" />
                        <span className="text-xs text-gray-500">Görsel Ekle</span>
                      </>
                    )}
                  </label>
                </div>
              </div>
            )}

            {formData.type === "text_block" && (
              <div>
                <label className="block text-sm font-medium mb-1">Açıklama Metni</label>
                <textarea
                  value={formData.settings?.text || ""}
                  onChange={(e) => setFormData({ ...formData, settings: { ...formData.settings, text: e.target.value } })}
                  placeholder="Yazı bloğu içeriği..."
                  className="w-full border px-3 py-2 rounded h-24"
                />
                <div className="mt-2 text-xs text-gray-500">Buton Linki eklemek isterseniz Görseller altındaki link yapısını veya doğrudan buraya buton şeklinde eklemeyi desteklemediğimiz için, text bloklarında ilk link URL'i buton linki olarak kullanılır.</div>
                <input
                  type="text"
                  value={formData.links[0] || ""}
                  onChange={(e) => {
                    const newLinks = [...formData.links];
                    newLinks[0] = e.target.value;
                    setFormData({ ...formData, links: newLinks });
                  }}
                  placeholder="Buton Linki URL (örn: /iletisim)"
                  className="w-full border px-3 py-2 rounded mt-2 text-sm"
                />
              </div>
            )}

            {formData.type === "video_banner" && (
              <div>
                <label className="block text-sm font-medium mb-1">Video URL (m3u8 veya mp4)</label>
                <input
                  type="text"
                  value={formData.settings?.video_url || ""}
                  onChange={(e) => setFormData({ ...formData, settings: { ...formData.settings, video_url: e.target.value } })}
                  placeholder="https://.../video.mp4"
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
            )}

            {formData.type === "rotating_text" && (
              <div>
                <label className="block text-sm font-medium mb-1">Dönen Metinler</label>
                <div className="space-y-2">
                  {(formData.settings?.texts || []).map((txt, index) => (
                    <div key={index} className="flex gap-2">
                      <input
                        type="text"
                        value={txt}
                        onChange={(e) => {
                          const newTexts = [...(formData.settings.texts || [])];
                          newTexts[index] = e.target.value;
                          setFormData({ ...formData, settings: { ...formData.settings, texts: newTexts } });
                        }}
                        className="flex-1 border px-3 py-1.5 rounded text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const newTexts = [...(formData.settings.texts || [])];
                          newTexts.splice(index, 1);
                          setFormData({ ...formData, settings: { ...formData.settings, texts: newTexts } });
                        }}
                        className="px-2 bg-red-50 text-red-600 rounded hover:bg-red-100"
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      const newTexts = [...(formData.settings?.texts || []), "Yeni Metin"];
                      setFormData({ ...formData, settings: { ...formData.settings, texts: newTexts } });
                    }}
                    className="text-sm text-blue-600 font-medium"
                  >
                    + Yeni Metin Ekle
                  </button>
                </div>
              </div>
            )}

            {formData.type === "product_slider" && (
              <div>
                <label className="block text-sm font-medium mb-2">Ürün Seçimi</label>
                <div className="bg-gray-50 p-4 rounded-lg border">
                  
                  {/* Search */}
                  <div className="flex gap-2 mb-4">
                    <input
                      type="text"
                      value={productSearch}
                      onChange={(e) => setProductSearch(e.target.value)}
                      placeholder="Ürün adı veya barkod ile ara..."
                      className="flex-1 border px-3 py-2 rounded text-sm"
                      onKeyDown={(e) => e.key === 'Enter' && handleProductSearch(e)}
                    />
                    <button
                      type="button"
                      onClick={handleProductSearch}
                      disabled={searchingProducts}
                      className="px-4 py-2 bg-black text-white rounded text-sm disabled:opacity-50"
                    >
                      {searchingProducts ? "Aranıyor..." : "Ara"}
                    </button>
                  </div>

                  {/* Search Results */}
                  {searchResults.length > 0 && (
                    <div className="mb-4 max-h-40 overflow-y-auto border bg-white rounded shadow-sm">
                      {searchResults.map(p => (
                        <div key={p._id} className="flex items-center justify-between p-2 border-b last:border-0 hover:bg-gray-50 text-sm">
                          <div className="flex items-center gap-2">
                            <img src={p.images?.[0]?.url || ""} alt="" className="w-8 h-8 rounded object-cover bg-gray-100" />
                            <span className="truncate max-w-[200px]">{p.name}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => addProductToBlock(p)}
                            className="text-blue-600 text-xs font-semibold px-2 py-1 bg-blue-50 rounded hover:bg-blue-100"
                          >
                            Ekle
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Selected Products */}
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Seçili Ürünler ({selectedProductDetails.length})</h4>
                    <div className="space-y-2">
                      {selectedProductDetails.length === 0 && (
                        <p className="text-sm text-gray-400 italic">Henüz ürün seçilmedi. (Boş bırakılırsa en yeni ürünler gösterilir)</p>
                      )}
                      {selectedProductDetails.map((p, index) => (
                        <div key={`${p._id}-${index}`} className="flex items-center justify-between p-2 bg-white border rounded shadow-sm text-sm">
                          <div className="flex items-center gap-2">
                            <span className="text-gray-400 font-mono text-xs">{index + 1}.</span>
                            <img src={p.images?.[0]?.url || ""} alt="" className="w-8 h-8 rounded object-cover bg-gray-100" />
                            <span className="truncate max-w-[200px]">{p.name}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeProductFromBlock(index)}
                            className="text-red-500 hover:text-red-700 p-1"
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                  
                </div>
              </div>
            )}


            {/* Footer */}
            <div className="flex justify-end gap-2 pt-4 border-t">
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
                {editingBlock ? "Güncelle" : "Ekle"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
