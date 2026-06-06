import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CreditCard, Building, Truck, CheckCircle, AlertCircle, ChevronDown, ChevronUp, ChevronLeft, MapPin, Plus, ShieldCheck, Lock, X, Pencil } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProvinceDistrictSelect from "../components/ProvinceDistrictSelect";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import { trackInitiateCheckout, trackPurchase, trackAddPaymentInfo } from "../utils/pixelEvents";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const emptyAddress = {
  id: "",
  title: "",
  first_name: "",
  last_name: "",
  phone: "",
  address: "",
  city: "",
  district: "",
  postal_code: "",
};

export default function Checkout() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { items, total, clearCart } = useCart();
  const { user } = useAuth();

  // Cart collapse + payment flow
  const [cartCollapsed, setCartCollapsed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [paymentStep, setPaymentStep] = useState("form"); // form | processing | iframe | success | error
  const [paymentUrl, setPaymentUrl] = useState("");
  const [orderId, setOrderId] = useState(null);
  const iframeRef = useRef(null);

  // Addresses
  const [savedAddresses, setSavedAddresses] = useState([]);
  const [shippingAddress, setShippingAddress] = useState({ ...emptyAddress, email: user?.email || "" });
  const [billingAddress, setBillingAddress] = useState({ ...emptyAddress });
  const [billingSameAsShipping, setBillingSameAsShipping] = useState(true);
  const [addressModal, setAddressModal] = useState(null); // null | 'shipping' | 'billing'
  const [addressForm, setAddressForm] = useState({ ...emptyAddress });

  // Coupons
  const [couponCode, setCouponCode] = useState("");
  const [discount, setDiscount] = useState(0);
  const [appliedCoupon, setAppliedCoupon] = useState(null);
  const [availableCoupons, setAvailableCoupons] = useState([]);

  // Payment options
  const [paymentMethod, setPaymentMethod] = useState("credit_card");
  const [use3DSecure, setUse3DSecure] = useState(true);
  const [usePoints, setUsePoints] = useState(false);
  const [userPoints] = useState(0); // future: fetch from /api/users/me

  // Gift options + terms + quick signup
  const GIFT_WRAP_PRICE = 130;
  const [giftNote, setGiftNote] = useState("");
  const [giftWrap, setGiftWrap] = useState(false);
  const [acceptTerms, setAcceptTerms] = useState(false);
  // Quick-signup state — OrderSuccess sayfasına taşındı, burada artık kullanılmıyor

  // KURUMSAL FATURA
  const [corporateInvoice, setCorporateInvoice] = useState(false);
  const [corporateData, setCorporateData] = useState({
    company_name: "",
    tax_office: "",
    tax_number: "",  // VKN (10) veya TCKN (11)
    eInvoice_user: false,  // E-Fatura mükellefi mi
  });

  // Load saved addresses for logged-in users
  useEffect(() => {
    if (!user) return;
    const token = localStorage.getItem("token");
    axios.get(`${API}/customer/my-addresses`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        const list = r.data?.addresses || [];
        setSavedAddresses(list);
        const def = list.find((a) => a.is_default) || list[0];
        if (def) {
          setShippingAddress({ ...def, email: user.email || "" });
          setBillingAddress({ ...def });
        }
      })
      .catch(() => {});
  }, [user]);

  // Available coupons + InitiateCheckout pixel
  useEffect(() => {
    if (items.length === 0) { setAvailableCoupons([]); return; }
    trackInitiateCheckout({
      total: grandTotal,
      items: items.map((it) => ({
        product_id: it.productId, name: it.name, price: it.price, quantity: it.quantity,
        category: it.category || it.categoryName || "",
        sku: it.sku || it.stockCode || "",
        size: it.size || "", color: it.color || "",
        list_price: it.list_price || it.price,
        sale_price: it.sale_price || it.price,
        brand: it.brand || "FACETTE",
        breadcrumb: it.breadcrumb || "",
      })),
      discount, shipping_cost: shippingCost,
      coupon: appliedCoupon?.code || "",
    });
    axios.post(`${API}/coupons/available`, {
      cart_total: total,
      user_id: user?.id || null,
      items: items.map((it) => ({ product_id: it.productId, category_id: it.categoryId, price: it.price, qty: it.quantity })),
    }).then((r) => setAvailableCoupons(r.data?.items || []))
      .catch(() => setAvailableCoupons([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, total, user?.id, discount, shippingCost, appliedCoupon?.code]);

  // Payment callback — iyzico → backend → storefront'a ?status=success|fail&order=.. ile döner
  useEffect(() => {
    const status = searchParams.get("status");
    const orderNum = searchParams.get("order");
    if (status === "success") {
      handlePaymentSuccess(orderNum);
    } else if (status === "fail") {
      setPaymentStep("error");
      toast.error("Ödeme tamamlanamadı. Lütfen tekrar deneyin.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handlePaymentSuccess = async (orderNumber) => {
    if (!orderNumber) return;
    setPaymentStep("processing");
    let amount = grandTotal;
    try {
      const r = await axios.get(`${API}/orders/by-number/${orderNumber}`);
      amount = r.data?.total || grandTotal;
    } catch (e) { /* sessiz */ }
    const _userInfo = {
      email: shippingAddress.email || user?.email || "",
      phone: shippingAddress.phone || user?.phone || "",
      first_name: shippingAddress.first_name || "",
      last_name: shippingAddress.last_name || "",
      city: shippingAddress.city || "",
      state: shippingAddress.district || shippingAddress.state || "",
      country: shippingAddress.country || "TR",
      zipcode: shippingAddress.zipcode || shippingAddress.postal_code || "",
      street: shippingAddress.address || "",
      external_id: user?.id || "",
    };
    trackPurchase({
      order_id: orderNumber,
      total: amount,
      items: items.map((it) => ({
        product_id: it.productId, name: it.name, price: it.price, quantity: it.quantity,
        category: it.category || it.categoryName || "",
        sku: it.sku || it.stockCode || "",
        size: it.size || "", color: it.color || "",
        list_price: it.list_price || it.price,
        sale_price: it.sale_price || it.price,
        brand: it.brand || "FACETTE",
        breadcrumb: it.breadcrumb || "",
      })),
      coupon: appliedCoupon?.code || "",
      discount, shipping: shippingCost, tax: 0,
      payment_type: paymentMethod,
      shipping_tier: shippingCost > 0 ? "Standart Kargo" : "Ücretsiz",
      user: _userInfo,
    });
    clearCart();
    setPaymentStep("success");
    toast.success("Ödemeniz başarıyla tamamlandı!");
    setTimeout(() => navigate(`/order-success/${orderNumber}`), 1200);
  };

  const freeShippingLimit = 500;
  const shippingCost = total >= freeShippingLimit ? 0 : 29.90;
  const giftWrapTotal = giftWrap ? GIFT_WRAP_PRICE : 0;
  const codFee = paymentMethod === "cash_on_delivery" ? 10 : 0;
  const pointsDeduction = usePoints ? Math.min(userPoints, total * 0.1) : 0;
  const grandTotal = Math.max(0, total + shippingCost - discount - pointsDeduction + giftWrapTotal + codFee);

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

  // ----- Address Modal -----
  const openAddressModal = (which) => {
    setAddressModal(which);
    const current = which === "shipping" ? shippingAddress : billingAddress;
    setAddressForm({ ...emptyAddress, ...current });
  };

  const closeAddressModal = () => { setAddressModal(null); setAddressForm({ ...emptyAddress }); };

  const handleSaveAddress = async () => {
    // Validate
    const required = ["first_name","last_name","phone","address","city","district"];
    for (const k of required) {
      if (!addressForm[k]) { toast.error("Tüm zorunlu alanları doldurun"); return; }
    }
    // Persist for logged in users (async, page does not reload)
    if (user) {
      const token = localStorage.getItem("token");
      try {
        if (addressForm.id) {
          await axios.put(`${API}/customer/addresses/${addressForm.id}`, addressForm, { headers: { Authorization: `Bearer ${token}` } });
        } else {
          const r = await axios.post(`${API}/customer/addresses`, addressForm, { headers: { Authorization: `Bearer ${token}` } });
          addressForm.id = r.data?.address_id;
        }
        // Refresh list
        const list = await axios.get(`${API}/customer/my-addresses`, { headers: { Authorization: `Bearer ${token}` } });
        setSavedAddresses(list.data?.addresses || []);
      } catch (e) {
        // Hatayı kullanıcıya bildir (önceden silently catch ediliyordu)
        const msg = e?.response?.data?.detail || e?.message || "Adres kaydedilemedi";
        toast.error(`Adres kayıt hatası: ${msg}`);
        if (e?.response?.status === 401) {
          toast.warning("Oturumunuz sonlanmış olabilir. Lütfen tekrar giriş yapın.");
        }
        // Local state ile devam et — checkout akışını bozmasın
      }
    }
    if (addressModal === "shipping") {
      setShippingAddress({ ...addressForm, email: user?.email || addressForm.email || "" });
      if (billingSameAsShipping) setBillingAddress({ ...addressForm });
    } else {
      setBillingAddress({ ...addressForm });
    }
    closeAddressModal();
    toast.success("Adres kaydedildi");
  };

  const pickSavedAddress = (a) => {
    if (addressModal === "shipping") {
      setShippingAddress({ ...a, email: user?.email || "" });
      if (billingSameAsShipping) setBillingAddress({ ...a });
    } else {
      setBillingAddress({ ...a });
    }
    closeAddressModal();
  };

  // ----- Submit -----
  const validateAddresses = () => {
    const ok = (a) => a && a.first_name && a.last_name && a.phone && a.address && a.city && a.district;
    if (!ok(shippingAddress)) { toast.error("Lütfen teslimat adresi seçin / ekleyin"); return false; }
    if (!billingSameAsShipping && !ok(billingAddress)) { toast.error("Lütfen fatura adresi seçin / ekleyin"); return false; }
    if (corporateInvoice) {
      if (!corporateData.company_name?.trim()) { toast.error("Firma Ünvanı gereklidir"); return false; }
      if (!corporateData.tax_office?.trim()) { toast.error("Vergi Dairesi gereklidir"); return false; }
      const tn = (corporateData.tax_number || "").replace(/\D/g, "");
      if (tn.length !== 10 && tn.length !== 11) { toast.error("VKN (10 hane) veya TCKN (11 hane) hatalı"); return false; }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    if (!validateAddresses()) return;
    if (!acceptTerms) { toast.error("Lütfen sözleşmeleri onaylayın"); return; }
    if (items.length === 0) { toast.error("Sepetiniz boş"); return; }
    setLoading(true);
    try {
      const orderData = {
        user_id: user?.id || null,
        items: items.map((item) => ({
          product_id: item.productId, variant_id: item.variantId, quantity: item.quantity,
          price: item.price, name: item.name, image: item.image, size: item.size, color: item.color,
        })),
        shipping_address: { ...shippingAddress, email: shippingAddress.email || user?.email || "" },
        billing_address: billingSameAsShipping ? { ...shippingAddress } : { ...billingAddress },
        billing_same_as_shipping: billingSameAsShipping,
        billing_info: corporateInvoice ? {
          is_corporate: true,
          company_name: corporateData.company_name,
          tax_office: corporateData.tax_office,
          tax_number: corporateData.tax_number,
          e_invoice_user: corporateData.eInvoice_user,
        } : { is_corporate: false },
        subtotal: total,
        shipping_cost: shippingCost,
        discount, coupon_code: appliedCoupon?.code || "",
        gift_note: giftNote || "", gift_wrap: giftWrap, gift_wrap_price: giftWrapTotal,
        use_points: usePoints, points_used: pointsDeduction,
        use_3d_secure: use3DSecure,
        total: grandTotal,
        payment_method: paymentMethod,
        attribution_session_id:
          (typeof window !== "undefined" && (window.__FACETTE_SID__ || localStorage.getItem("facette_sid"))) || null,
      };

      const orderRes = await axios.post(`${API}/orders`, orderData);
      const newOrderId = orderRes.data.order_id;
      setOrderId(newOrderId);

      if (paymentMethod === "credit_card") {
        const callbackUrl = `${API}/payment/callback`;
        const returnUrl = `${window.location.origin}/odeme`;
        const paymentRes = await axios.post(
          `${API}/payment/initialize?order_id=${newOrderId}&callback_url=${encodeURIComponent(callbackUrl)}&return_url=${encodeURIComponent(returnUrl)}`
        );
        if (paymentRes.data.success && paymentRes.data.paymentPageUrl) {
          window.location.href = paymentRes.data.paymentPageUrl;
        } else if (paymentRes.data.success && paymentRes.data.checkoutFormContent) {
          setPaymentUrl(paymentRes.data.checkoutFormContent);
          setPaymentStep("iframe");
        } else {
          setLoading(false);
          toast.error(paymentRes.data.error || "Ödeme başlatılamadı");
        }
      } else {
        const _userInfo = {
          email: shippingAddress.email || user?.email || "",
          phone: shippingAddress.phone || user?.phone || "",
          first_name: shippingAddress.first_name || "",
          last_name: shippingAddress.last_name || "",
          city: shippingAddress.city || "",
          state: shippingAddress.district || shippingAddress.state || "",
          country: shippingAddress.country || "TR",
          zipcode: shippingAddress.zipcode || shippingAddress.postal_code || "",
          street: shippingAddress.address || "",
          external_id: user?.id || "",
        };
        trackPurchase({
          order_id: orderRes.data.order_number, total: grandTotal,
          items: items.map((it) => ({
            product_id: it.productId, name: it.name, price: it.price, quantity: it.quantity,
            category: it.category || it.categoryName || "",
            sku: it.sku || it.stockCode || "",
            size: it.size || "", color: it.color || "",
            list_price: it.list_price || it.price,
            sale_price: it.sale_price || it.price,
            brand: it.brand || "FACETTE",
            breadcrumb: it.breadcrumb || "",
          })),
          coupon: appliedCoupon?.code || "",
          discount, shipping: shippingCost, tax: 0,
          payment_type: paymentMethod,
          shipping_tier: shippingCost > 0 ? "Standart Kargo" : "Ücretsiz",
          user: _userInfo,
        });
        // ÖNCE paymentStep'i "success"'e çevir (useEffect'in /sepet'e yönlendirmesini önler)
        setPaymentStep("success");
        clearCart();
        toast.success("Siparişiniz alındı!");
        // Guest veya logged-in: doğrudan OrderSuccess sayfasına yönlendir.
        navigate(`/order-success/${orderRes.data.order_number}`, { replace: true });
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Sipariş oluşturulamadı");
    } finally {
      setLoading(false);
    }
  };

  // Boş sepet → /sepet'e yönlendir (render içinde değil, useEffect'te)
  // Ödeme dönüşünde (?status=...) yönlendirme yapma — başarı/başarısızlık ekranı gösterilecek
  useEffect(() => {
    if (items.length === 0 && paymentStep === "form" && !searchParams.get("status")) {
      navigate("/sepet");
    }
  }, [items.length, paymentStep, navigate, searchParams]);

  if (items.length === 0 && paymentStep === "form" && !searchParams.get("status")) return null;

  if (paymentStep === "success") {
    return (
      <div className="min-h-screen bg-stone-50" data-testid="checkout-page">
        <Header />
        <div className="container-main py-16 text-center">
          <CheckCircle size={64} className="mx-auto text-green-500 mb-4" />
          <h1 className="text-2xl font-medium mb-2">Ödemeniz Başarılı!</h1>
          <p className="text-gray-600">Siparişiniz alındı. Yönlendiriliyorsunuz...</p>
        </div>
        <Footer />
      </div>
    );
  }
  if (paymentStep === "error") {
    return (
      <div className="min-h-screen bg-stone-50" data-testid="checkout-page">
        <Header />
        <div className="container-main py-16 text-center">
          <AlertCircle size={64} className="mx-auto text-red-500 mb-4" />
          <h1 className="text-2xl font-medium mb-2">Ödeme Başarısız</h1>
          <button onClick={() => setPaymentStep("form")} className="btn-primary">Tekrar Dene</button>
        </div>
        <Footer />
      </div>
    );
  }
  if (paymentStep === "processing") {
    return (
      <div className="min-h-screen bg-stone-50">
        <Header />
        <div className="container-main py-16 text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-black mx-auto mb-4"></div>
          <h1 className="text-2xl font-medium">Ödeme Doğrulanıyor...</h1>
        </div>
        <Footer />
      </div>
    );
  }

  // ───────── Render ─────────
  const addressCardContent = (a, label) => (
    <div className="text-xs text-gray-700 leading-relaxed">
      <div className="font-semibold text-sm">{a.title || label}</div>
      <div className="text-gray-500">{a.first_name} {a.last_name} {a.phone && <span>· {a.phone}</span>}</div>
      <div className="mt-1 line-clamp-2">{a.address}</div>
      <div className="text-gray-500">{a.district} / {a.city}</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-white" data-testid="checkout-page">
      <Header />

      <div className="container-main py-6 md:py-10">
        {/* Top bar with SSL badge */}
        <div className="flex items-center justify-between mb-8 md:mb-10">
          <div className="flex items-center gap-3 md:gap-4">
            <button type="button" onClick={() => navigate(-1)}
              data-testid="checkout-back-btn"
              aria-label="Geri Dön"
              className="w-9 h-9 md:w-10 md:h-10 border border-black flex items-center justify-center hover:bg-black hover:text-white transition-colors flex-shrink-0">
              <ChevronLeft size={16} strokeWidth={2} />
            </button>
            <div>
              <p className="text-[10px] tracking-[0.3em] uppercase text-black/60 mb-1.5">Ödeme</p>
              <h1 className="text-xl md:text-2xl font-light tracking-tight text-black">Sipariş Onayı</h1>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-black/70">
            <ShieldCheck size={13} className="text-black" strokeWidth={1.6} />
            <span>SSL Güvenli</span>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="grid lg:grid-cols-12 gap-6">
            {/* SOL — %75 */}
            <div className="lg:col-span-9 space-y-4">
              {/* 1) Sepetimdeki Ürünler — collapsible */}
              <div className="bg-white border border-black/10" data-testid="cart-summary-block">
                <button type="button" onClick={() => setCartCollapsed((v) => !v)}
                  className="w-full flex items-center justify-between px-4 md:px-5 py-3.5 md:py-4 hover:bg-stone-50 transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-light tracking-[0.05em]">Sepetimdeki Ürünler ({items.length})</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {cartCollapsed && (
                      <div className="flex -space-x-1.5">
                        {items.slice(0, 4).map((it) => (
                          <img key={it.id} src={it.image} alt="" className="w-7 h-9 border border-white object-contain" />
                        ))}
                        {items.length > 4 && (
                          <div className="w-7 h-9 bg-stone-100 border border-white text-[10px] flex items-center justify-center font-light">+{items.length - 4}</div>
                        )}
                      </div>
                    )}
                    {cartCollapsed ? <ChevronDown size={16} strokeWidth={1.4} /> : <ChevronUp size={16} strokeWidth={1.4} />}
                  </div>
                </button>
                {!cartCollapsed && (
                  <div className="px-4 md:px-5 pb-5 border-t border-black/10 pt-4 space-y-3">
                    {items.map((item) => (
                      <div key={item.id} className="flex gap-3 items-center">
                        <img src={item.image} alt={item.name} className="w-12 h-14 object-contain bg-gray-50" />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-light truncate">{item.name}</p>
                          <p className="text-[11px] text-black/55 mt-0.5">
                            {item.size && <>Beden: {item.size} · </>}
                            {item.color && <>Renk: {item.color} · </>}
                            Adet: {item.quantity}
                          </p>
                        </div>
                        <div className="text-sm font-light tabular-nums whitespace-nowrap">{(item.price * item.quantity).toFixed(2)} TL</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 2) Adres */}
              <div className="bg-white border border-black/10" data-testid="address-block">
                <div className="px-5 py-4 border-b flex items-center gap-3">
                  <MapPin size={18} className="text-black" />
                  <span className="font-medium">Teslimat Adresi</span>
                </div>
                <div className="grid md:grid-cols-2 gap-4 p-5">
                  {/* Teslimat */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">Teslimat Adresi</span>
                      <button type="button" onClick={() => openAddressModal("shipping")}
                        data-testid="edit-shipping-addr-btn"
                        className="inline-flex items-center gap-1 text-xs text-black border border-stone-900 px-3 py-1 hover:bg-stone-50 transition">
                        <Plus size={14} /> Adres Ekle / Değiştir
                      </button>
                    </div>
                    <button type="button" onClick={() => openAddressModal("shipping")}
                      className={`w-full text-left rounded p-3 transition-colors border ${shippingAddress.first_name ? "bg-stone-50 border-stone-200" : "bg-stone-50 border-dashed border-gray-300 hover:border-stone-400"}`}>
                      {shippingAddress.first_name
                        ? addressCardContent(shippingAddress, "Teslimat Adresi")
                        : <span className="text-xs text-gray-500">Henüz teslimat adresi seçilmedi. Eklemek için tıklayın.</span>}
                    </button>
                  </div>
                  {/* Fatura */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">Fatura Adresi</span>
                      <button type="button" onClick={() => openAddressModal("billing")}
                        data-testid="edit-billing-addr-btn"
                        disabled={billingSameAsShipping}
                        className={`inline-flex items-center gap-1 text-xs rounded px-3 py-1 transition ${billingSameAsShipping ? "border border-gray-200 text-gray-300 cursor-not-allowed" : "text-black border border-stone-900 hover:bg-stone-50"}`}>
                        <Plus size={14} /> Adres Ekle / Değiştir
                      </button>
                    </div>
                    <div className={`rounded p-3 border ${billingSameAsShipping ? "bg-stone-50 border-gray-200" : (billingAddress.first_name ? "bg-stone-50 border-stone-200" : "bg-stone-50 border-dashed border-gray-300")}`}>
                      {billingSameAsShipping
                        ? <span className="text-xs text-gray-500 italic">Teslimat adresi ile aynı</span>
                        : (billingAddress.first_name
                            ? addressCardContent(billingAddress, "Fatura Adresi")
                            : <span className="text-xs text-gray-500">Fatura adresi seçilmedi</span>)}
                    </div>
                  </div>
                </div>
                <div className="px-5 pb-4">
                  <label className="inline-flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={billingSameAsShipping}
                      onChange={(e) => {
                        setBillingSameAsShipping(e.target.checked);
                        if (e.target.checked) setBillingAddress({ ...shippingAddress });
                      }}
                      className="accent-black"
                      data-testid="same-billing-checkbox" />
                    <span>Faturamı Aynı Adrese Gönder</span>
                  </label>
                </div>
              </div>

              {/* 2.b) Kurumsal Fatura */}
              <div className="bg-white border border-black/10" data-testid="corporate-invoice-block">
                <label className="flex items-center gap-3 px-5 py-4 cursor-pointer hover:bg-stone-50 transition-colors">
                  <input type="checkbox" checked={corporateInvoice}
                    onChange={(e) => setCorporateInvoice(e.target.checked)}
                    className="accent-black" data-testid="corporate-invoice-checkbox" />
                  <Building size={18} className="text-black" />
                  <div className="flex-1">
                    <div className="font-medium text-sm">Kurumsal Fatura İstiyorum</div>
                    <div className="text-xs text-gray-500">Şirket adına fatura kesilecekse VKN ve vergi dairesi bilgilerinizi girin.</div>
                  </div>
                </label>
                {corporateInvoice && (
                  <div className="px-5 pb-5 border-t pt-4 space-y-3" data-testid="corporate-invoice-fields">
                    <div className="grid md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-700 mb-1">Firma Ünvanı *</label>
                        <input value={corporateData.company_name}
                          onChange={(e) => setCorporateData({ ...corporateData, company_name: e.target.value })}
                          placeholder="Örn. Facette Tekstil A.Ş."
                          className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-stone-900"
                          data-testid="corp-company-name-input" />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-700 mb-1">VKN / TCKN *</label>
                        <input value={corporateData.tax_number}
                          onChange={(e) => setCorporateData({ ...corporateData, tax_number: e.target.value.replace(/\D/g, "").slice(0, 11) })}
                          placeholder="10 hane VKN veya 11 hane TCKN"
                          className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-stone-900"
                          data-testid="corp-tax-number-input" />
                      </div>
                      <div className="md:col-span-2">
                        <label className="block text-xs text-gray-700 mb-1">Vergi Dairesi *</label>
                        <input value={corporateData.tax_office}
                          onChange={(e) => setCorporateData({ ...corporateData, tax_office: e.target.value })}
                          placeholder="Örn. Beşiktaş Vergi Dairesi"
                          className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-stone-900"
                          data-testid="corp-tax-office-input" />
                      </div>
                    </div>
                    <label className="inline-flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                      <input type="checkbox" checked={corporateData.eInvoice_user}
                        onChange={(e) => setCorporateData({ ...corporateData, eInvoice_user: e.target.checked })}
                        className="accent-black" data-testid="corp-einvoice-user" />
                      Şirketim e-Fatura mükellefidir (e-Fatura kesilsin)
                    </label>
                  </div>
                )}
              </div>

              {/* 3) Ödeme Seçenekleri */}
              <div className="bg-white border border-black/10" data-testid="payment-block">
                <div className="px-5 py-4 border-b">
                  <span className="font-medium">Ödeme Seçenekleri</span>
                </div>
                <div className="p-5 space-y-3">
                  {/* Method radios */}
                  <div className="grid sm:grid-cols-3 gap-2">
                    {[
                      { key: "credit_card", label: "Banka & Kredi Kartı ile Öde", icon: CreditCard },
                      { key: "bank_transfer", label: "Havale / EFT", icon: Building },
                      { key: "cash_on_delivery", label: "Kapıda Ödeme (+10₺)", icon: Truck },
                    ].map(({ key, label, icon: Icon }) => (
                      <label key={key} className={`flex items-center gap-2 p-3 border rounded cursor-pointer transition-colors text-sm ${paymentMethod === key ? "border-stone-900 bg-stone-50" : "border-gray-200 hover:border-gray-400"}`}>
                        <input type="radio" name="payment" value={key}
                          checked={paymentMethod === key}
                          onChange={(e) => {
                            setPaymentMethod(e.target.value);
                            // GA4 + CAPI: add_payment_info — zengin payload
                            try {
                              const mappedItems = (items || []).map((it) => ({
                                item_id: String(it.product_id || it.productId || it.id || it.sku || ""),
                                item_name: it.name || "",
                                item_brand: it.brand || "FACETTE",
                                item_category: it.category || it.categoryName || "",
                                item_variant: `${it.size || ""} ${it.color || ""}`.trim(),
                                price: Number(it.price) || 0,
                                list_price: Number(it.list_price || it.price) || 0,
                                sale_price: Number(it.sale_price || it.price) || 0,
                                discount: Math.max(0, Number(it.list_price || it.price) - Number(it.price)),
                                sku: it.sku || it.stockCode || "",
                                size: it.size || "", color: it.color || "",
                                quantity: Number(it.quantity) || 1,
                                coupon: appliedCoupon?.code || "",
                              }));
                              trackAddPaymentInfo({
                                items: mappedItems,
                                value: grandTotal,
                                currency: "TRY",
                                coupon: appliedCoupon?.code || "",
                                discount, shipping: shippingCost, tax: 0,
                                payment_type: key,
                              });
                            } catch (_) { /* silent */ }
                          }}
                          className="accent-black" />
                        <Icon size={16} className={paymentMethod === key ? "text-black" : "text-gray-500"} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>

                  {paymentMethod === "credit_card" && (
                    <div className="grid md:grid-cols-2 gap-4 mt-3 pt-3 border-t">
                      <div>
                        <div className="text-xs font-medium text-gray-700 mb-2">Kart Bilgileri</div>
                        <div className="rounded border p-3 bg-stone-50 text-xs text-gray-500 leading-relaxed">
                          <Lock size={12} className="inline mr-1 text-green-600" />
                          Kart bilgileri <b>iyzico</b> güvenli ödeme sayfasında güvenle alınacaktır. Bu sayfaya yönlendirileceksiniz.
                        </div>
                      </div>
                      <div>
                        <div className="text-xs font-medium text-gray-700 mb-2">Taksit Seçenekleri</div>
                        <div className="rounded border p-3 bg-stone-50 text-xs">
                          <div className="flex items-center justify-between">
                            <span>Tek Çekim</span><span className="font-semibold">{grandTotal.toFixed(2)} TL</span>
                          </div>
                          <div className="text-[11px] text-gray-500 mt-1">Banka kartınıza özel taksit seçenekleri ödeme sayfasında listelenecektir.</div>
                        </div>
                      </div>
                      <label className="inline-flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={use3DSecure} onChange={(e) => setUse3DSecure(e.target.checked)} className="accent-black" />
                        <ShieldCheck size={14} className="text-green-600" /> 3D Secure ile ödemek istiyorum
                      </label>
                      {userPoints > 0 && (
                        <label className="inline-flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={usePoints} onChange={(e) => setUsePoints(e.target.checked)} className="accent-black" />
                          <span className="text-black font-semibold">{userPoints.toFixed(2)} ₺</span> Puan Kullan
                        </label>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* 4) Hediye */}
              <div className="bg-white border border-black/10" data-testid="gift-options-section">
                <div className="px-5 py-4 border-b"><span className="font-medium">Hediye Seçenekleri</span></div>
                <div className="p-5 space-y-3">
                  <label className={`flex items-start gap-3 cursor-pointer border rounded p-3 transition-colors ${giftWrap ? "border-stone-900 bg-stone-50" : "border-gray-200 hover:border-gray-400"}`}>
                    <input type="checkbox" checked={giftWrap} onChange={(e) => setGiftWrap(e.target.checked)}
                      className="mt-1 accent-black" data-testid="gift-wrap-toggle" />
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">Hediye paketi</span>
                        <span className="text-sm font-semibold text-black">+{GIFT_WRAP_PRICE.toFixed(2)} TL</span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">Siparişiniz özel hediye ambalajı + kurdele + el yazılı kart ile gönderilir.</p>
                    </div>
                  </label>
                  <textarea value={giftNote} onChange={(e) => setGiftNote(e.target.value.slice(0, 300))}
                    rows={2} placeholder="Hediye Notu (opsiyonel) — kart üzerine yazılır, max 300 karakter"
                    className="w-full border px-3 py-2 text-sm focus:outline-none focus:border-stone-900 resize-none"
                    data-testid="gift-note-input" />
                </div>
              </div>
            </div>

            {/* SAĞ — %25 — Sticky Order Summary */}
            <div className="lg:col-span-3">
              <div className="bg-white border border-black/10 sticky top-24">
                <div className="px-5 py-4 border-b">
                  <span className="font-medium">Sipariş Özeti</span>
                </div>

                {/* Available Coupons */}
                {availableCoupons.length > 0 && (
                  <div className="px-5 pt-4" data-testid="available-coupons-block">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-600 mb-2">Sana Özel Kuponlar</div>
                    <div className="space-y-1.5 max-h-40 overflow-y-auto -mx-1 px-1">
                      {availableCoupons.slice(0, 5).map((c) => {
                        const selected = appliedCoupon?.code === c.code;
                        return (
                          <button type="button" key={c.id} onClick={() => handlePickCoupon(c)}
                            className={`w-full text-left border rounded p-2 flex items-center justify-between transition-colors ${selected ? "border-stone-900 bg-stone-900 text-white" : "border-dashed border-gray-300 hover:border-stone-900"}`}
                            data-testid={`coupon-card-${c.code}`}>
                            <div className="min-w-0">
                              <div className={`text-[11px] font-semibold tracking-wide ${selected ? "text-white" : "text-black"}`}>{c.code}</div>
                              <div className={`text-[10px] truncate ${selected ? "text-white/80" : "text-gray-500"}`}>{c.title || (c.type === "percent" ? `%${c.value} indirim` : `${c.value} TL indirim`)}</div>
                            </div>
                            <div className={`text-xs font-bold shrink-0 ml-2 ${selected ? "text-white" : "text-green-600"}`}>-{c.discount.toFixed(2)} ₺</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Manual coupon */}
                <div className="px-5 pt-4">
                  <div className="flex gap-2">
                    <input type="text" value={couponCode}
                      onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
                      placeholder="Kupon Kodu"
                      className="flex-1 border rounded px-3 py-2 text-xs"
                      data-testid="manual-coupon-input" />
                    {appliedCoupon
                      ? <button type="button" onClick={handleRemoveCoupon} className="text-xs px-3 border rounded hover:bg-stone-50" data-testid="remove-coupon-btn">Kaldır</button>
                      : <button type="button" onClick={handleApplyCoupon} className="text-xs px-3 border rounded hover:bg-stone-50" data-testid="apply-coupon-btn">Uygula</button>}
                  </div>
                </div>

                {/* Totals */}
                <div className="px-5 py-4 mt-3 border-t space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-gray-600">Ara Toplam</span><span>{total.toFixed(2)} TL</span></div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Kargo Tutarı</span>
                    {shippingCost === 0
                      ? <span><s className="text-gray-400">59,99 TL</s> <span className="ml-1 inline-block bg-green-50 text-green-700 px-1.5 py-0.5 text-[10px] font-semibold rounded">Bedava</span></span>
                      : <span>{shippingCost.toFixed(2)} TL</span>}
                  </div>
                  {discount > 0 && <div className="flex justify-between text-green-600"><span>Kupon{appliedCoupon?.code ? ` (${appliedCoupon.code})` : ""}</span><span>-{discount.toFixed(2)} TL</span></div>}
                  {pointsDeduction > 0 && <div className="flex justify-between text-black"><span>Puan Kullanımı</span><span>-{pointsDeduction.toFixed(2)} TL</span></div>}
                  {giftWrap && <div className="flex justify-between"><span className="text-gray-600">Hediye paketi</span><span>+{GIFT_WRAP_PRICE.toFixed(2)} TL</span></div>}
                  {codFee > 0 && <div className="flex justify-between"><span className="text-gray-600">Kapıda Ödeme</span><span>+{codFee.toFixed(2)} TL</span></div>}
                  <div className="flex justify-between text-base font-semibold pt-2 border-t">
                    <span>Toplam</span><span className="text-black">{grandTotal.toFixed(2)} TL</span>
                  </div>
                </div>

                {/* Submit */}
                <div className="px-5 pb-5">
                  <button type="submit" disabled={loading || !acceptTerms}
                    className={`w-full py-3 rounded font-semibold text-sm transition-colors ${(loading || !acceptTerms) ? "bg-gray-300 text-white cursor-not-allowed" : "bg-stone-900 hover:bg-stone-800 text-white"}`}
                    data-testid="place-order-btn">
                    {loading ? "İşleniyor..." : "Ödeme Yap"}
                  </button>

                  {/* Sözleşme — Trendyol style: Ödeme Yap'ın altında */}
                  <label className="flex items-start gap-2 mt-3 text-[11px] text-gray-700 cursor-pointer leading-relaxed">
                    <input type="checkbox" checked={acceptTerms}
                      onChange={(e) => setAcceptTerms(e.target.checked)}
                      className="mt-0.5 accent-black" data-testid="accept-terms-checkbox" />
                    <span>
                      <a href="/sayfa/on-bilgilendirme" target="_blank" rel="noreferrer" className="underline hover:text-black">Ön Bilgilendirme Koşulları</a>{"'"}nı ve{" "}
                      <a href="/sayfa/mesafeli-satis" target="_blank" rel="noreferrer" className="underline hover:text-black">Mesafeli Satış Sözleşmesi</a>{"'"}ni okudum, onaylıyorum.
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </form>
      </div>

      {/* Address Modal */}
      {addressModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" data-testid="address-modal">
          <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-3 border-b sticky top-0 bg-white">
              <h2 className="font-semibold text-base">{addressModal === "shipping" ? "Teslimat Adresi" : "Fatura Adresi"} {addressForm.id ? "Düzenle" : "Ekle"}</h2>
              <button type="button" onClick={closeAddressModal} className="p-1 hover:bg-gray-100 rounded" data-testid="close-address-modal">
                <X size={18} />
              </button>
            </div>

            {/* Saved addresses (if user logged in) */}
            {user && savedAddresses.length > 0 && (
              <div className="px-5 py-4 border-b bg-stone-50">
                <div className="text-xs font-semibold text-gray-700 mb-2">Kayıtlı Adreslerim</div>
                <div className="grid sm:grid-cols-2 gap-2">
                  {savedAddresses.map((a) => (
                    <button key={a.id} type="button" onClick={() => pickSavedAddress(a)}
                      className="text-left p-3 border rounded text-xs bg-white hover:border-stone-900 transition-colors">
                      <div className="font-semibold text-sm">{a.title || `${a.first_name} ${a.last_name}`}</div>
                      <div className="text-gray-500 mt-0.5 line-clamp-2">{a.address}</div>
                      <div className="text-gray-500">{a.district} / {a.city}</div>
                    </button>
                  ))}
                </div>
                <div className="text-[11px] text-gray-500 mt-2">— veya yeni adres oluşturun:</div>
              </div>
            )}

            {/* Address form */}
            <div className="p-5 grid md:grid-cols-2 gap-3">
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-700 mb-1">Adres Başlığı (örn. Ev, İş)</label>
                <input value={addressForm.title} onChange={(e) => setAddressForm({ ...addressForm, title: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-700 mb-1">Ad *</label>
                <input value={addressForm.first_name} onChange={(e) => setAddressForm({ ...addressForm, first_name: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm" required />
              </div>
              <div>
                <label className="block text-xs text-gray-700 mb-1">Soyad *</label>
                <input value={addressForm.last_name} onChange={(e) => setAddressForm({ ...addressForm, last_name: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm" required />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-700 mb-1">Telefon *</label>
                <input value={addressForm.phone} onChange={(e) => setAddressForm({ ...addressForm, phone: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm" required />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-700 mb-1">Adres *</label>
                <textarea value={addressForm.address} onChange={(e) => setAddressForm({ ...addressForm, address: e.target.value })}
                  rows={3}
                  className="w-full border rounded px-3 py-2 text-sm resize-none" required />
              </div>
              <div className="md:col-span-2">
                <ProvinceDistrictSelect
                  city={addressForm.city}
                  district={addressForm.district}
                  onChange={({ city, district }) => setAddressForm((p) => ({ ...p, city, district }))}
                  testIdPrefix="address-modal"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-gray-700 mb-1">Posta Kodu</label>
                <input value={addressForm.postal_code} onChange={(e) => setAddressForm({ ...addressForm, postal_code: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm" />
              </div>
            </div>
            <div className="px-5 py-3 border-t flex justify-end gap-2 sticky bottom-0 bg-white">
              <button type="button" onClick={closeAddressModal} className="px-4 py-2 text-sm border rounded hover:bg-stone-50">İptal</button>
              <button type="button" onClick={handleSaveAddress}
                className="px-4 py-2 text-sm bg-stone-900 hover:bg-stone-800 text-white rounded font-medium"
                data-testid="save-address-btn">Kaydet ve Kullan</button>
            </div>
          </div>
        </div>
      )}

      {/* Hızlı Üyelik Modal — KALDIRILDI: OrderSuccess sayfasında inline CTA olarak gösteriliyor */}

      <Footer />
    </div>
  );
}
