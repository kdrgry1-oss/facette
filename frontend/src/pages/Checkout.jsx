import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CreditCard, Building, Truck, CheckCircle, AlertCircle } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProvinceDistrictSelect from "../components/ProvinceDistrictSelect";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import { trackInitiateCheckout, trackPurchase } from "../utils/pixelEvents";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Checkout() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { items, total, clearCart } = useCart();
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [couponCode, setCouponCode] = useState("");
  const [discount, setDiscount] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState("credit_card");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [paymentStep, setPaymentStep] = useState("form"); // form, processing, iframe, success, error
  const [paymentUrl, setPaymentUrl] = useState("");
  const [orderId, setOrderId] = useState(null);
  const iframeRef = useRef(null);
  
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

  // FAZ 4 — hediye notu + hediye paketi + uygulanabilir kupon listesi
  const GIFT_WRAP_PRICE = 130;
  const [giftNote, setGiftNote] = useState("");
  const [giftWrap, setGiftWrap] = useState(false);
  const [availableCoupons, setAvailableCoupons] = useState([]);
  const [appliedCoupon, setAppliedCoupon] = useState(null);

  // Uygulanabilir kuponları sepete göre tetikle
  useEffect(() => {
    if (items.length === 0) { setAvailableCoupons([]); return; }
    // FAZ 9+ — InitiateCheckout pixel event (ilk giriş)
    trackInitiateCheckout({
      total,
      items: items.map((it) => ({
        product_id: it.productId, name: it.name,
        price: it.price, quantity: it.quantity,
      })),
    });
    axios.post(`${API}/coupons/available`, {
      cart_total: total,
      user_id: user?.id || null,
      items: items.map((it) => ({
        product_id: it.productId, category_id: it.categoryId,
        price: it.price, qty: it.quantity,
      })),
    }).then((r) => setAvailableCoupons(r.data?.items || []))
      .catch(() => setAvailableCoupons([]));
  }, [items, total, user?.id]);

  // Handle payment callback
  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      handlePaymentCallback(token);
    }
  }, [searchParams]);

  const handlePaymentCallback = async (token) => {
    setPaymentStep("processing");
    try {
      const res = await axios.post(`${API}/payment/callback?token=${token}`);
      if (res.data.success) {
        // FAZ 9+ — Purchase pixel event (callback flow)
        trackPurchase({
          order_id: res.data.orderNumber,
          total: res.data.amount || grandTotal,
          items: items.map((it) => ({
            product_id: it.productId, name: it.name,
            price: it.price, quantity: it.quantity,
          })),
        });
        clearCart();
        setPaymentStep("success");
        toast.success("Ödemeniz başarıyla tamamlandı!");
        setTimeout(() => {
          navigate(`/hesabim?order=${res.data.orderNumber}`);
        }, 3000);
      } else {
        setPaymentStep("error");
        toast.error(res.data.error || "Ödeme başarısız");
      }
    } catch (err) {
      setPaymentStep("error");
      toast.error("Ödeme doğrulanamadı");
    }
  };

  const freeShippingLimit = 500;
  const shippingCost = total >= freeShippingLimit ? 0 : 29.90;
  const giftWrapTotal = giftWrap ? GIFT_WRAP_PRICE : 0;
  const grandTotal = total + shippingCost - discount + giftWrapTotal;

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleApplyCoupon = async () => {
    if (!couponCode.trim()) return;
    
    try {
      const res = await axios.post(`${API}/campaigns/validate?code=${couponCode}&total=${total}`);
      setDiscount(res.data.discount);
      setAppliedCoupon({ code: couponCode.toUpperCase(), discount: res.data.discount });
      toast.success(`Kupon uygulandı: ${res.data.discount.toFixed(2)} TL indirim`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kupon geçersiz");
    }
  };

  // Trendyol Go stili: kart listesinden kupon seçimi
  const handlePickCoupon = (c) => {
    setCouponCode(c.code);
    setDiscount(c.discount);
    setAppliedCoupon({ code: c.code, discount: c.discount, title: c.title });
    toast.success(`${c.code} uygulandı: ${c.discount.toFixed(2)} TL indirim`);
  };

  const handleRemoveCoupon = () => {
    setAppliedCoupon(null);
    setCouponCode("");
    setDiscount(0);
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
      // First create the order
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
        coupon_code: appliedCoupon?.code || "",
        gift_note: giftNote || "",
        gift_wrap: giftWrap,
        gift_wrap_price: giftWrap ? GIFT_WRAP_PRICE : 0,
        total: grandTotal + (paymentMethod === "cash_on_delivery" ? 10 : 0),
        payment_method: paymentMethod,
        attribution_session_id:
          (typeof window !== "undefined" && (window.__FACETTE_SID__ || localStorage.getItem("facette_sid"))) || null,
      };

      const orderRes = await axios.post(`${API}/orders`, orderData);
      const newOrderId = orderRes.data.order_id;
      setOrderId(newOrderId);

      // If credit card payment, initialize Iyzico
      if (paymentMethod === "credit_card") {
        const callbackUrl = `${window.location.origin}/odeme`;
        const paymentRes = await axios.post(
          `${API}/payment/initialize?order_id=${newOrderId}&callback_url=${encodeURIComponent(callbackUrl)}`
        );

        if (paymentRes.data.success && paymentRes.data.paymentPageUrl) {
          // Redirect to Iyzico payment page
          window.location.href = paymentRes.data.paymentPageUrl;
        } else if (paymentRes.data.checkoutFormContent) {
          // Show embedded checkout form
          setPaymentUrl(paymentRes.data.checkoutFormContent);
          setPaymentStep("iframe");
        } else {
          toast.error(paymentRes.data.error || "Ödeme başlatılamadı");
        }
      } else {
        // For other payment methods, complete order directly
        // FAZ 9+ — Purchase conversion event
        trackPurchase({
          order_id: orderRes.data.order_number,
          total: grandTotal,
          shipping: shippingCost,
          items: items.map((it) => ({
            product_id: it.productId, name: it.name,
            price: it.price, quantity: it.quantity,
          })),
        });
        clearCart();
        toast.success("Siparişiniz alındı!");
        navigate(`/hesabim?order=${orderRes.data.order_number}`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sipariş oluşturulamadı");
    } finally {
      setLoading(false);
    }
  };

  if (items.length === 0 && paymentStep === "form") {
    navigate("/sepet");
    return null;
  }

  // Payment Success Screen
  if (paymentStep === "success") {
    return (
      <div className="min-h-screen bg-gray-50" data-testid="checkout-page">
        <Header />
        <div className="container-main py-16 text-center">
          <CheckCircle size={64} className="mx-auto text-green-500 mb-4" />
          <h1 className="text-2xl font-medium mb-2">Ödemeniz Başarılı!</h1>
          <p className="text-gray-600 mb-4">Siparişiniz alındı. Yönlendiriliyorsunuz...</p>
        </div>
        <Footer />
      </div>
    );
  }

  // Payment Error Screen
  if (paymentStep === "error") {
    return (
      <div className="min-h-screen bg-gray-50" data-testid="checkout-page">
        <Header />
        <div className="container-main py-16 text-center">
          <AlertCircle size={64} className="mx-auto text-red-500 mb-4" />
          <h1 className="text-2xl font-medium mb-2">Ödeme Başarısız</h1>
          <p className="text-gray-600 mb-4">Ödeme işlemi tamamlanamadı. Lütfen tekrar deneyin.</p>
          <button 
            onClick={() => setPaymentStep("form")}
            className="btn-primary"
          >
            Tekrar Dene
          </button>
        </div>
        <Footer />
      </div>
    );
  }

  // Processing Screen
  if (paymentStep === "processing") {
    return (
      <div className="min-h-screen bg-gray-50" data-testid="checkout-page">
        <Header />
        <div className="container-main py-16 text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-black mx-auto mb-4"></div>
          <h1 className="text-2xl font-medium mb-2">Ödeme Doğrulanıyor...</h1>
          <p className="text-gray-600">Lütfen bekleyin</p>
        </div>
        <Footer />
      </div>
    );
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
                  <div className="md:col-span-2">
                    <ProvinceDistrictSelect
                      city={formData.city}
                      district={formData.district}
                      onChange={({ city, district }) => setFormData((p) => ({ ...p, city, district }))}
                      testIdPrefix="checkout-addr"
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

              {/* Hediye Seçenekleri — FAZ 4 */}
              <div className="bg-white p-6" data-testid="gift-options-section">
                <h2 className="text-lg font-medium mb-4">Hediye Seçenekleri</h2>
                <label className="flex items-start gap-3 cursor-pointer border rounded p-3 mb-3 hover:border-black transition-colors"
                  style={{ borderColor: giftWrap ? "#000" : undefined }}>
                  <input type="checkbox" checked={giftWrap}
                    onChange={(e) => setGiftWrap(e.target.checked)}
                    className="mt-1" data-testid="gift-wrap-toggle" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Hediye paketi</span>
                      <span className="text-sm font-semibold">+{GIFT_WRAP_PRICE.toFixed(2)} TL</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">Siparişiniz özel hediye ambalajıyla kurdele ve kartla gönderilir.</p>
                  </div>
                </label>
                <div>
                  <label className="block text-sm text-gray-600 mb-1">Hediye Notu (opsiyonel)</label>
                  <textarea value={giftNote} onChange={(e) => setGiftNote(e.target.value.slice(0, 300))}
                    rows={2} placeholder="Kartta yer almasını istediğiniz mesaj (max 300 karakter)"
                    className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-black resize-none"
                    data-testid="gift-note-input" />
                  {giftNote && <div className="text-xs text-gray-400 mt-1">{giftNote.length}/300</div>}
                </div>
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
                        <div className="text-xs text-gray-500 space-y-0.5">
                          {item.size && <p>Beden: <span className="font-medium text-gray-700">{item.size}</span></p>}
                          {item.color && <p>Renk: <span className="font-medium text-gray-700">{item.color}</span></p>}
                          <p>Adet: {item.quantity}</p>
                        </div>
                        <p className="text-sm font-medium mt-1">{(item.price * item.quantity).toFixed(2)} TL</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Trendyol Go stili uygulanabilir kupon listesi — FAZ 4 */}
                {availableCoupons.length > 0 && (
                  <div className="mb-4" data-testid="available-coupons-block">
                    <div className="text-xs font-medium text-gray-600 mb-2">Kullanılabilir kuponlar</div>
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {availableCoupons.slice(0, 6).map((c) => {
                        const selected = appliedCoupon?.code === c.code;
                        return (
                          <button type="button" key={c.id} onClick={() => handlePickCoupon(c)}
                            className={`w-full text-left border rounded p-2 flex items-center justify-between transition-colors ${selected ? "border-black bg-black text-white" : "border-dashed border-gray-300 hover:border-black"}`}
                            data-testid={`coupon-card-${c.code}`}>
                            <div className="min-w-0">
                              <div className={`text-xs font-semibold tracking-wide ${selected ? "text-white" : "text-black"}`}>{c.code}</div>
                              <div className={`text-[11px] truncate ${selected ? "text-white/80" : "text-gray-500"}`}>
                                {c.title || (c.type === "percent" ? `%${c.value} indirim` : `${c.value} TL indirim`)}
                              </div>
                            </div>
                            <div className={`text-sm font-semibold shrink-0 ml-2 ${selected ? "text-white" : "text-green-600"}`}>
                              -{c.discount.toFixed(2)} TL
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Coupon */}
                <div className="flex gap-2 mb-4">
                  <input
                    type="text"
                    value={couponCode}
                    onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
                    placeholder="Kupon Kodu"
                    className="flex-1 border px-3 py-2 text-sm"
                    data-testid="manual-coupon-input"
                  />
                  {appliedCoupon ? (
                    <button type="button" onClick={handleRemoveCoupon}
                      className="btn-secondary text-xs px-4" data-testid="remove-coupon-btn">
                      Kaldır
                    </button>
                  ) : (
                    <button 
                      type="button"
                      onClick={handleApplyCoupon}
                      className="btn-secondary text-xs px-4"
                      data-testid="apply-coupon-btn"
                    >
                      Uygula
                    </button>
                  )}
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
                      <span>İndirim{appliedCoupon ? ` (${appliedCoupon.code})` : ""}</span>
                      <span>-{discount.toFixed(2)} TL</span>
                    </div>
                  )}
                  {giftWrap && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Hediye paketi</span>
                      <span>+{GIFT_WRAP_PRICE.toFixed(2)} TL</span>
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
