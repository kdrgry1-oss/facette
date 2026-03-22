import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CreditCard, Building, Truck } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Checkout() {
  const navigate = useNavigate();
  const { items, total, clearCart } = useCart();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [couponCode, setCouponCode] = useState("");
  const [discount, setDiscount] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState("credit_card");
  const [acceptTerms, setAcceptTerms] = useState(false);
  
  const [formData, setFormData] = useState({
    first_name: user?.first_name || "",
    last_name: user?.last_name || "",
    email: user?.email || "",
    phone: user?.phone || "",
    address: "",
    city: "",
    district: "",
    postal_code: "",
  });

  const freeShippingLimit = 500;
  const shippingCost = total >= freeShippingLimit ? 0 : 29.90;
  const grandTotal = total + shippingCost - discount;

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleApplyCoupon = async () => {
    if (!couponCode.trim()) return;
    
    try {
      const res = await axios.post(`${API}/campaigns/validate?code=${couponCode}&total=${total}`);
      setDiscount(res.data.discount);
      toast.success(`Kupon uygulandı: ${res.data.discount.toFixed(2)} TL indirim`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kupon geçersiz");
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!acceptTerms) {
      toast.error("Lütfen sözleşmeleri kabul ediniz");
      return;
    }

    if (items.length === 0) {
      toast.error("Sepetiniz boş");
      return;
    }

    setLoading(true);
    try {
      const orderData = {
        user_id: user?.id || null,
        items: items.map(item => ({
          product_id: item.productId,
          variant_id: item.variantId,
          quantity: item.quantity,
          price: item.price,
          name: item.name,
          image: item.image,
          size: item.size,
          color: item.color,
        })),
        shipping_address: formData,
        subtotal: total,
        shipping_cost: shippingCost,
        discount: discount,
        total: grandTotal,
        payment_method: paymentMethod,
      };

      const res = await axios.post(`${API}/orders`, orderData);
      clearCart();
      toast.success("Siparişiniz alındı!");
      navigate(`/hesabim?order=${res.data.order_number}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sipariş oluşturulamadı");
    } finally {
      setLoading(false);
    }
  };

  if (items.length === 0) {
    navigate("/sepet");
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50" data-testid="checkout-page">
      <Header />

      <div className="container-main py-8">
        <h1 className="text-2xl font-medium mb-8">Ödeme</h1>

        <form onSubmit={handleSubmit}>
          <div className="grid lg:grid-cols-3 gap-8">
            {/* Form */}
            <div className="lg:col-span-2 space-y-6">
              {/* Shipping Address */}
              <div className="bg-white p-6">
                <h2 className="text-lg font-medium mb-4">Teslimat Bilgileri</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm mb-1">Ad *</label>
                    <input
                      type="text"
                      name="first_name"
                      value={formData.first_name}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                  <div>
                    <label className="block text-sm mb-1">Soyad *</label>
                    <input
                      type="text"
                      name="last_name"
                      value={formData.last_name}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                  <div>
                    <label className="block text-sm mb-1">E-posta *</label>
                    <input
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                  <div>
                    <label className="block text-sm mb-1">Telefon *</label>
                    <input
                      type="tel"
                      name="phone"
                      value={formData.phone}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm mb-1">Adres *</label>
                    <textarea
                      name="address"
                      value={formData.address}
                      onChange={handleInputChange}
                      required
                      rows={3}
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black resize-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm mb-1">İl *</label>
                    <input
                      type="text"
                      name="city"
                      value={formData.city}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                  <div>
                    <label className="block text-sm mb-1">İlçe *</label>
                    <input
                      type="text"
                      name="district"
                      value={formData.district}
                      onChange={handleInputChange}
                      required
                      className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black"
                    />
                  </div>
                </div>
              </div>

              {/* Payment Method */}
              <div className="bg-white p-6">
                <h2 className="text-lg font-medium mb-4">Ödeme Yöntemi</h2>
                <div className="space-y-3">
                  <label className={`flex items-center gap-3 p-4 border cursor-pointer transition-colors ${paymentMethod === "credit_card" ? "border-black" : "border-gray-200"}`}>
                    <input
                      type="radio"
                      name="payment"
                      value="credit_card"
                      checked={paymentMethod === "credit_card"}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="sr-only"
                    />
                    <CreditCard size={20} />
                    <span className="text-sm">Kredi Kartı / Banka Kartı</span>
                    <span className={`ml-auto w-4 h-4 rounded-full border ${paymentMethod === "credit_card" ? "bg-black border-black" : "border-gray-300"}`} />
                  </label>
                  
                  <label className={`flex items-center gap-3 p-4 border cursor-pointer transition-colors ${paymentMethod === "bank_transfer" ? "border-black" : "border-gray-200"}`}>
                    <input
                      type="radio"
                      name="payment"
                      value="bank_transfer"
                      checked={paymentMethod === "bank_transfer"}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="sr-only"
                    />
                    <Building size={20} />
                    <span className="text-sm">Havale / EFT</span>
                    <span className={`ml-auto w-4 h-4 rounded-full border ${paymentMethod === "bank_transfer" ? "bg-black border-black" : "border-gray-300"}`} />
                  </label>
                  
                  <label className={`flex items-center gap-3 p-4 border cursor-pointer transition-colors ${paymentMethod === "cash_on_delivery" ? "border-black" : "border-gray-200"}`}>
                    <input
                      type="radio"
                      name="payment"
                      value="cash_on_delivery"
                      checked={paymentMethod === "cash_on_delivery"}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="sr-only"
                    />
                    <Truck size={20} />
                    <span className="text-sm">Kapıda Ödeme (+10 TL)</span>
                    <span className={`ml-auto w-4 h-4 rounded-full border ${paymentMethod === "cash_on_delivery" ? "bg-black border-black" : "border-gray-300"}`} />
                  </label>
                </div>

                {paymentMethod === "credit_card" && (
                  <div className="mt-4 p-4 bg-gray-50 text-sm text-gray-600">
                    <p>Test modunda çalışıyorsunuz. Ödeme işlemi simüle edilecektir.</p>
                  </div>
                )}
              </div>

              {/* Terms */}
              <div className="bg-white p-6">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acceptTerms}
                    onChange={(e) => setAcceptTerms(e.target.checked)}
                    className="mt-1"
                  />
                  <span className="text-sm text-gray-600">
                    <a href="/sayfa/mesafeli-satis" className="underline">Mesafeli Satış Sözleşmesi</a> ve{" "}
                    <a href="/sayfa/kvkk" className="underline">KVKK Aydınlatma Metni</a>'ni okudum, kabul ediyorum.
                  </span>
                </label>
              </div>
            </div>

            {/* Order Summary */}
            <div className="lg:col-span-1">
              <div className="bg-white p-6 sticky top-24">
                <h2 className="text-lg font-medium mb-4">Sipariş Özeti</h2>
                
                {/* Items */}
                <div className="space-y-3 max-h-60 overflow-y-auto mb-4">
                  {items.map((item) => (
                    <div key={item.id} className="flex gap-3">
                      <img src={item.image} alt={item.name} className="w-16 h-20 object-cover bg-gray-100" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{item.name}</p>
                        {item.size && <p className="text-xs text-gray-500">Beden: {item.size}</p>}
                        <p className="text-xs text-gray-500">Adet: {item.quantity}</p>
                        <p className="text-sm font-medium mt-1">{(item.price * item.quantity).toFixed(2)} TL</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Coupon */}
                <div className="flex gap-2 mb-4">
                  <input
                    type="text"
                    value={couponCode}
                    onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
                    placeholder="Kupon Kodu"
                    className="flex-1 border px-3 py-2 text-sm"
                  />
                  <button 
                    type="button"
                    onClick={handleApplyCoupon}
                    className="btn-secondary text-xs px-4"
                  >
                    Uygula
                  </button>
                </div>

                {/* Totals */}
                <div className="space-y-2 text-sm border-t pt-4">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Ara Toplam</span>
                    <span>{total.toFixed(2)} TL</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Kargo</span>
                    <span className={shippingCost === 0 ? "text-green-600" : ""}>
                      {shippingCost === 0 ? "Ücretsiz" : `${shippingCost.toFixed(2)} TL`}
                    </span>
                  </div>
                  {discount > 0 && (
                    <div className="flex justify-between text-green-600">
                      <span>İndirim</span>
                      <span>-{discount.toFixed(2)} TL</span>
                    </div>
                  )}
                  {paymentMethod === "cash_on_delivery" && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Kapıda Ödeme</span>
                      <span>+10.00 TL</span>
                    </div>
                  )}
                  <div className="flex justify-between text-lg font-medium pt-2 border-t">
                    <span>Toplam</span>
                    <span>{(grandTotal + (paymentMethod === "cash_on_delivery" ? 10 : 0)).toFixed(2)} TL</span>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary w-full mt-6 disabled:opacity-50"
                  data-testid="place-order-btn"
                >
                  {loading ? "İşleniyor..." : "Siparişi Tamamla"}
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>

      <Footer />
    </div>
  );
}
