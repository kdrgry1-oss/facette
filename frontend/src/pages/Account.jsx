import { useState, useEffect } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { User, Package, MapPin, Heart, Settings, LogOut, ChevronRight, Eye, Truck, CheckCircle, Clock, X } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProvinceDistrictSelect from "../components/ProvinceDistrictSelect";
import { useAuth } from "../context/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MENU_ITEMS = [
  { id: "profile", label: "Profil Bilgileri", icon: User },
  { id: "orders", label: "Siparişlerim", icon: Package },
  { id: "addresses", label: "Adreslerim", icon: MapPin },
  { id: "favorites", label: "Favorilerim", icon: Heart },
];

const ORDER_STATUS = {
  pending: { label: "Beklemede", color: "bg-yellow-100 text-yellow-700", icon: Clock },
  confirmed: { label: "Onaylandı", color: "bg-blue-100 text-blue-700", icon: CheckCircle },
  shipped: { label: "Kargoda", color: "bg-purple-100 text-purple-700", icon: Truck },
  delivered: { label: "Teslim Edildi", color: "bg-green-100 text-green-700", icon: CheckCircle },
  cancelled: { label: "İptal Edildi", color: "bg-red-100 text-red-700", icon: X },
};

export default function Account() {
  const { user, logout, loading: authLoading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get("tab") || "profile");
  const [orders, setOrders] = useState([]);
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [editingProfile, setEditingProfile] = useState(false);
  const [editingAddress, setEditingAddress] = useState(null);
  
  const [profileForm, setProfileForm] = useState({
    first_name: "",
    last_name: "",
    phone: "",
  });

  const [addressForm, setAddressForm] = useState({
    title: "",
    first_name: "",
    last_name: "",
    phone: "",
    address: "",
    city: "",
    district: "",
    postal_code: "",
    is_default: false,
  });

  useEffect(() => {
    if (user) {
      setProfileForm({
        first_name: user.first_name || "",
        last_name: user.last_name || "",
        phone: user.phone || "",
      });
    }
  }, [user]);

  useEffect(() => {
    if (activeTab === "orders") {
      fetchOrders();
    } else if (activeTab === "addresses") {
      fetchAddresses();
    }
  }, [activeTab]);

  useEffect(() => {
    // Check if redirected from checkout with order number
    const orderNum = searchParams.get("order");
    if (orderNum) {
      setActiveTab("orders");
      toast.success(`Siparişiniz oluşturuldu: ${orderNum}`);
      setSearchParams({});
    }
  }, [searchParams]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/my-orders`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setOrders(res.data.orders || []);
    } catch (err) {
      console.error(err);
      // Mock data for demo
      setOrders([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAddresses = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/my-addresses`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setAddresses(res.data.addresses || []);
    } catch (err) {
      // Demo addresses
      setAddresses([]);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem("token");
      await axios.put(`${API}/users/me`, profileForm, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Profil güncellendi");
      setEditingProfile(false);
    } catch (err) {
      toast.error("Güncelleme başarısız");
    }
  };

  const handleSaveAddress = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem("token");
      const headers = { Authorization: `Bearer ${token}` };
      
      if (editingAddress?.id) {
        await axios.put(`${API}/addresses/${editingAddress.id}`, addressForm, { headers });
        toast.success("Adres güncellendi");
      } else {
        await axios.post(`${API}/addresses`, addressForm, { headers });
        toast.success("Adres eklendi");
      }
      
      setEditingAddress(null);
      setAddressForm({
        title: "", first_name: "", last_name: "", phone: "",
        address: "", city: "", district: "", postal_code: "", is_default: false
      });
      fetchAddresses();
    } catch (err) {
      toast.error("İşlem başarısız");
    }
  };

  const handleDeleteAddress = async (id) => {
    if (!await window.appConfirm("Adresi silmek istediğinize emin misiniz?")) return;
    try {
      const token = localStorage.getItem("token");
      await axios.delete(`${API}/addresses/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Adres silindi");
      fetchAddresses();
    } catch (err) {
      toast.error("Silme başarısız");
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container-main py-16 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black mx-auto"></div>
          <p className="mt-4 text-gray-500">Yükleniyor...</p>
        </div>
        <Footer />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/giris" />;
  }

  const renderProfile = () => (
    <div className="space-y-6">
      <div className="bg-white border rounded-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-medium">Profil Bilgileri</h2>
          {!editingProfile && (
            <button
              onClick={() => setEditingProfile(true)}
              className="text-sm text-blue-600 hover:underline"
            >
              Düzenle
            </button>
          )}
        </div>

        {editingProfile ? (
          <form onSubmit={handleUpdateProfile} className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-600 mb-1">Ad</label>
                <input
                  type="text"
                  value={profileForm.first_name}
                  onChange={(e) => setProfileForm({ ...profileForm, first_name: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Soyad</label>
                <input
                  type="text"
                  value={profileForm.last_name}
                  onChange={(e) => setProfileForm({ ...profileForm, last_name: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">E-posta</label>
                <input
                  type="email"
                  value={user.email}
                  disabled
                  className="w-full border px-3 py-2 rounded text-sm bg-gray-50 text-gray-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Telefon</label>
                <input
                  type="tel"
                  value={profileForm.phone}
                  onChange={(e) => setProfileForm({ ...profileForm, phone: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm px-6">
                Kaydet
              </button>
              <button
                type="button"
                onClick={() => setEditingProfile(false)}
                className="btn-secondary text-sm px-6"
              >
                İptal
              </button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-500 mb-1">Ad Soyad</label>
                <p className="font-medium">{user.first_name || "-"} {user.last_name || ""}</p>
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">E-posta</label>
                <p className="font-medium">{user.email}</p>
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Telefon</label>
                <p className="font-medium">{user.phone || "-"}</p>
              </div>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Üyelik Tarihi</label>
                <p className="font-medium">
                  {user.created_at ? new Date(user.created_at).toLocaleDateString("tr-TR") : "-"}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Change Password */}
      <div className="bg-white border rounded-lg p-6">
        <h3 className="font-medium mb-4">Şifre Değiştir</h3>
        <p className="text-sm text-gray-500 mb-4">
          Şifrenizi değiştirmek için mevcut şifrenizi ve yeni şifrenizi girin.
        </p>
        <button className="btn-secondary text-sm">Şifre Değiştir</button>
      </div>
    </div>
  );

  const renderOrders = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Siparişlerim</h2>
        <a href="/siparis-takip" className="text-sm text-blue-600 hover:underline">
          Sipariş Takip
        </a>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black mx-auto"></div>
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-white border rounded-lg p-12 text-center">
          <Package size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 mb-4">Henüz siparişiniz bulunmuyor</p>
          <a href="/" className="btn-primary text-sm inline-block">
            Alışverişe Başla
          </a>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => {
            const status = ORDER_STATUS[order.status] || ORDER_STATUS.pending;
            const StatusIcon = status.icon;
            
            return (
              <div key={order.id} className="bg-white border rounded-lg overflow-hidden">
                <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
                  <div>
                    <p className="font-medium">{order.order_number}</p>
                    <p className="text-sm text-gray-500">
                      {new Date(order.created_at).toLocaleDateString("tr-TR", {
                        day: "numeric", month: "long", year: "numeric"
                      })}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2.5 py-1 rounded-full flex items-center gap-1 ${status.color}`}>
                      <StatusIcon size={12} />
                      {status.label}
                    </span>
                    <button
                      onClick={() => setSelectedOrder(selectedOrder?.id === order.id ? null : order)}
                      className="p-2 hover:bg-gray-100 rounded"
                    >
                      <Eye size={18} />
                    </button>
                  </div>
                </div>
                
                {selectedOrder?.id === order.id && (
                  <div className="p-4 space-y-4">
                    {/* Order Items */}
                    <div className="space-y-3">
                      {order.items?.map((item, idx) => (
                        <div key={idx} className="flex gap-3">
                          <img
                            src={item.image || "/placeholder.jpg"}
                            alt={item.name}
                            className="w-16 h-20 object-cover bg-gray-100 rounded"
                          />
                          <div className="flex-1">
                            <p className="text-sm font-medium">{item.name}</p>
                            {item.size && <p className="text-xs text-gray-500">Beden: {item.size}</p>}
                            <p className="text-xs text-gray-500">Adet: {item.quantity}</p>
                            <p className="text-sm font-medium mt-1">{item.price?.toFixed(2)} TL</p>
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {/* Shipping Info */}
                    {order.shipping_address && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium mb-2">Teslimat Adresi</p>
                        <p className="text-sm text-gray-600">
                          {order.shipping_address.first_name} {order.shipping_address.last_name}<br />
                          {order.shipping_address.address}<br />
                          {order.shipping_address.district} / {order.shipping_address.city}
                        </p>
                      </div>
                    )}
                    
                    {/* Cargo Info */}
                    {order.cargo?.tracking_number && (
                      <div className="border-t pt-4">
                        <p className="text-sm font-medium mb-2">Kargo Bilgisi</p>
                        <p className="text-sm text-gray-600">
                          {order.cargo.company}: {order.cargo.tracking_number}
                        </p>
                        {order.cargo.tracking_url && (
                          <a
                            href={order.cargo.tracking_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-blue-600 hover:underline"
                          >
                            Kargo Takip
                          </a>
                        )}
                      </div>
                    )}
                    
                    {/* Order Total */}
                    <div className="border-t pt-4 flex justify-between">
                      <span className="font-medium">Toplam</span>
                      <span className="font-medium">{order.total?.toFixed(2)} TL</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  const renderAddresses = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Adreslerim</h2>
        <button
          onClick={() => setEditingAddress({})}
          className="btn-primary text-sm"
        >
          + Yeni Adres
        </button>
      </div>

      {/* Address Form Modal */}
      {editingAddress !== null && (
        <div className="bg-white border rounded-lg p-6">
          <h3 className="font-medium mb-4">
            {editingAddress?.id ? "Adres Düzenle" : "Yeni Adres"}
          </h3>
          <form onSubmit={handleSaveAddress} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Adres Başlığı *</label>
              <input
                type="text"
                value={addressForm.title}
                onChange={(e) => setAddressForm({ ...addressForm, title: e.target.value })}
                placeholder="Ev, İş, vb."
                required
                className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
              />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-600 mb-1">Ad *</label>
                <input
                  type="text"
                  value={addressForm.first_name}
                  onChange={(e) => setAddressForm({ ...addressForm, first_name: e.target.value })}
                  required
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Soyad *</label>
                <input
                  type="text"
                  value={addressForm.last_name}
                  onChange={(e) => setAddressForm({ ...addressForm, last_name: e.target.value })}
                  required
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Telefon *</label>
                <input
                  type="tel"
                  value={addressForm.phone}
                  onChange={(e) => setAddressForm({ ...addressForm, phone: e.target.value })}
                  required
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
              <div className="md:col-span-2">
                <ProvinceDistrictSelect
                  city={addressForm.city}
                  district={addressForm.district}
                  onChange={({ city, district }) => setAddressForm({ ...addressForm, city, district })}
                  selectClass="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black bg-white"
                  labelClass="block text-sm text-gray-600 mb-1"
                  cityLabel="Şehir"
                  testIdPrefix="account-addr"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">Posta Kodu</label>
                <input
                  type="text"
                  value={addressForm.postal_code}
                  onChange={(e) => setAddressForm({ ...addressForm, postal_code: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Adres *</label>
              <textarea
                value={addressForm.address}
                onChange={(e) => setAddressForm({ ...addressForm, address: e.target.value })}
                rows={3}
                required
                className="w-full border px-3 py-2 rounded text-sm focus:outline-none focus:border-black"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={addressForm.is_default}
                onChange={(e) => setAddressForm({ ...addressForm, is_default: e.target.checked })}
              />
              <span className="text-sm">Varsayılan adres olarak ayarla</span>
            </label>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm px-6">Kaydet</button>
              <button
                type="button"
                onClick={() => setEditingAddress(null)}
                className="btn-secondary text-sm px-6"
              >
                İptal
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Addresses List */}
      {addresses.length === 0 && editingAddress === null ? (
        <div className="bg-white border rounded-lg p-12 text-center">
          <MapPin size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 mb-4">Henüz kayıtlı adresiniz yok</p>
          <button onClick={() => setEditingAddress({})} className="btn-primary text-sm">
            Adres Ekle
          </button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {addresses.map((addr) => (
            <div key={addr.id} className="bg-white border rounded-lg p-4 relative">
              {addr.is_default && (
                <span className="absolute top-2 right-2 text-xs bg-black text-white px-2 py-0.5 rounded">
                  Varsayılan
                </span>
              )}
              <p className="font-medium mb-1">{addr.title}</p>
              <p className="text-sm text-gray-600">
                {addr.first_name} {addr.last_name}<br />
                {addr.address}<br />
                {addr.district} / {addr.city}
                {addr.postal_code && ` - ${addr.postal_code}`}
              </p>
              <p className="text-sm text-gray-500 mt-1">{addr.phone}</p>
              <div className="flex gap-3 mt-3">
                <button
                  onClick={() => {
                    setAddressForm(addr);
                    setEditingAddress(addr);
                  }}
                  className="text-xs text-blue-600 hover:underline"
                >
                  Düzenle
                </button>
                <button
                  onClick={() => handleDeleteAddress(addr.id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Sil
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const renderFavorites = () => (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">Favorilerim</h2>
      <div className="bg-white border rounded-lg p-12 text-center">
        <Heart size={48} className="mx-auto text-gray-300 mb-4" />
        <p className="text-gray-500 mb-4">Henüz favori ürününüz yok</p>
        <a href="/" className="btn-primary text-sm inline-block">
          Ürünleri Keşfet
        </a>
      </div>
    </div>
  );

  const renderContent = () => {
    switch (activeTab) {
      case "orders": return renderOrders();
      case "addresses": return renderAddresses();
      case "favorites": return renderFavorites();
      default: return renderProfile();
    }
  };

  return (
    <div className="min-h-screen bg-gray-50" data-testid="account-page">
      <Header />

      <div className="max-w-screen-xl mx-auto px-4 py-8">
        {/* Mobile Tab Selector */}
        <div className="md:hidden mb-6">
          <select
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value)}
            className="w-full border px-4 py-3 rounded-lg bg-white"
          >
            {MENU_ITEMS.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>

        <div className="grid md:grid-cols-4 gap-8">
          {/* Sidebar */}
          <div className="hidden md:block md:col-span-1">
            <div className="bg-white border rounded-lg overflow-hidden">
              {/* User Info */}
              <div className="p-4 border-b bg-gray-50">
                <p className="font-medium">{user.first_name || user.email.split("@")[0]}</p>
                <p className="text-sm text-gray-500 truncate">{user.email}</p>
              </div>
              
              {/* Menu */}
              <nav className="p-2">
                {MENU_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setActiveTab(item.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                        activeTab === item.id
                          ? "bg-black text-white"
                          : "hover:bg-gray-100"
                      }`}
                    >
                      <Icon size={18} />
                      {item.label}
                      <ChevronRight size={16} className="ml-auto opacity-50" />
                    </button>
                  );
                })}
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-red-600 hover:bg-red-50 mt-2"
                >
                  <LogOut size={18} />
                  Çıkış Yap
                </button>
              </nav>
            </div>
          </div>

          {/* Content */}
          <div className="md:col-span-3">
            {renderContent()}
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
