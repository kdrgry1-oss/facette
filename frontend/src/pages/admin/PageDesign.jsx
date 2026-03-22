import { useState, useEffect } from "react";
import { Plus, Edit, Trash2, GripVertical, Image, Upload, X } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BLOCK_TYPES = [
  { value: "hero_slider", label: "Hero Slider", description: "Ana sayfa slider" },
  { value: "full_banner", label: "Tam Genişlik Banner", description: "Tek görsel tam genişlik" },
  { value: "half_banners", label: "Yarı Yarıya Banner", description: "İki görsel yan yana" },
  { value: "product_grid", label: "Ürün Grid", description: "Ürün listesi" },
  { value: "instashop", label: "InstaShop", description: "Instagram tarzı görseller" },
  { value: "text_block", label: "Yazı Bloğu", description: "Başlık ve açıklama" },
];

export default function PageDesign() {
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingBlock, setEditingBlock] = useState(null);
  const [uploading, setUploading] = useState(false);
  
  const [formData, setFormData] = useState({
    type: "hero_slider",
    title: "",
    images: [],
    links: [],
    settings: {},
    sort_order: 0,
    is_active: true,
    page: "home"
  });

  useEffect(() => {
    fetchBlocks();
  }, []);

  const fetchBlocks = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/page-blocks`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setBlocks(res.data || []);
    } catch (err) {
      // If API doesn't exist yet, use default blocks
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };
      
      if (editingBlock) {
        await axios.put(`${API}/page-blocks/${editingBlock.id}`, formData, { headers });
        toast.success("Blok güncellendi");
      } else {
        await axios.post(`${API}/page-blocks`, formData, { headers });
        toast.success("Blok eklendi");
      }
      setModalOpen(false);
      resetForm();
      fetchBlocks();
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
    } catch (err) {
      toast.error("Silme başarısız");
    }
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
      settings: {},
      sort_order: 0,
      is_active: true,
      page: "home"
    });
  };

  const getBlockTypeInfo = (type) => {
    return BLOCK_TYPES.find(t => t.value === type) || { label: type };
  };

  return (
    <div data-testid="page-design">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Sayfa Tasarımı</h1>
        <button 
          onClick={() => { resetForm(); setModalOpen(true); }}
          className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
        >
          <Plus size={18} />
          Yeni Blok
        </button>
      </div>

      {/* Info */}
      <div className="bg-blue-50 border border-blue-200 rounded p-4 mb-6">
        <p className="text-sm text-blue-800">
          Sayfa tasarımını buradan yönetebilirsiniz. Blokları sürükle-bırak ile sıralayabilir, 
          görselleri değiştirebilir ve bağlantıları düzenleyebilirsiniz.
        </p>
      </div>

      {/* Blocks List */}
      <div className="space-y-4">
        {loading ? (
          <div className="text-center py-8">Yükleniyor...</div>
        ) : blocks.length === 0 ? (
          <div className="text-center py-8 text-gray-500">Henüz blok eklenmemiş</div>
        ) : (
          blocks.map((block, index) => (
            <div 
              key={block.id} 
              className={`bg-white rounded-lg shadow-sm border ${!block.is_active ? 'opacity-50' : ''}`}
            >
              <div className="flex items-start p-4 gap-4">
                {/* Drag Handle */}
                <div className="pt-2 cursor-move text-gray-400">
                  <GripVertical size={20} />
                </div>

                {/* Preview */}
                <div className="flex-shrink-0 w-48">
                  {block.images?.[0] ? (
                    <img 
                      src={block.images[0]} 
                      alt="" 
                      className="w-full h-24 object-cover rounded"
                    />
                  ) : (
                    <div className="w-full h-24 bg-gray-100 rounded flex items-center justify-center">
                      <Image size={24} className="text-gray-400" />
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                      {getBlockTypeInfo(block.type).label}
                    </span>
                    {!block.is_active && (
                      <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded">
                        Pasif
                      </span>
                    )}
                  </div>
                  <h3 className="font-medium">{block.title || "Başlıksız"}</h3>
                  <p className="text-sm text-gray-500">
                    {block.images?.length || 0} görsel • Sıra: {block.sort_order}
                  </p>
                  {block.links?.[0] && (
                    <p className="text-xs text-gray-400 mt-1">
                      Bağlantı: {block.links[0]}
                    </p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <button 
                    onClick={() => openEditModal(block)}
                    className="p-2 hover:bg-gray-100 rounded"
                    title="Düzenle"
                  >
                    <Edit size={18} />
                  </button>
                  <button 
                    onClick={() => handleDelete(block.id)}
                    className="p-2 hover:bg-gray-100 rounded text-red-600"
                    title="Sil"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Block Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingBlock ? "Blok Düzenle" : "Yeni Blok"}</DialogTitle>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Blok Tipi</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                  className="w-full border px-3 py-2 rounded"
                >
                  {BLOCK_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Başlık</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full border px-3 py-2 rounded"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Sıra</label>
                <input
                  type="number"
                  value={formData.sort_order}
                  onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value) || 0 })}
                  className="w-full border px-3 py-2 rounded"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                  <span className="text-sm">Aktif</span>
                </label>
              </div>
            </div>

            {/* Images */}
            <div>
              <label className="block text-sm font-medium mb-2">Görseller</label>
              <div className="grid grid-cols-4 gap-3">
                {formData.images.map((img, index) => (
                  <div key={index} className="relative">
                    <img src={img} alt="" className="w-full aspect-video object-cover rounded" />
                    <button
                      type="button"
                      onClick={() => removeImage(index)}
                      className="absolute top-1 right-1 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center"
                    >
                      <X size={12} />
                    </button>
                    <input
                      type="text"
                      value={formData.links[index] || ""}
                      onChange={(e) => {
                        const newLinks = [...formData.links];
                        newLinks[index] = e.target.value;
                        setFormData({ ...formData, links: newLinks });
                      }}
                      placeholder="Bağlantı"
                      className="w-full text-xs border px-2 py-1 rounded mt-1"
                    />
                  </div>
                ))}
                
                {/* Upload */}
                <label className="aspect-video border-2 border-dashed border-gray-300 flex flex-col items-center justify-center cursor-pointer hover:border-black rounded">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleImageUpload(e)}
                    className="hidden"
                  />
                  {uploading ? (
                    <span className="text-xs text-gray-500">Yükleniyor...</span>
                  ) : (
                    <>
                      <Upload size={20} className="text-gray-400 mb-1" />
                      <span className="text-xs text-gray-500">Ekle</span>
                    </>
                  )}
                </label>
              </div>
            </div>

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
                {editingBlock ? "Güncelle" : "Kaydet"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
