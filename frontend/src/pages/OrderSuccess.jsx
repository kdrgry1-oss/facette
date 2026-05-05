import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Check, Package, Truck, Home, Mail, Phone, MapPin } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function OrderSuccess() {
  const { orderNumber } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orderNumber) {
      navigate("/");
      return;
    }
    let cancel = false;
    (async () => {
      try {
        const token = localStorage.getItem("token");
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const r = await axios.get(`${API}/orders/by-number/${orderNumber}`, { headers });
        if (!cancel) setOrder(r.data);
      } catch (_) {
        if (!cancel) setOrder(null);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [orderNumber, navigate]);
  if (loading) {
    return (
      <div className="min-h-screen bg-white">
        <Header />
        <div className="container-main py-32 text-center">
          <div className="animate-spin h-12 w-12 border-2 border-black border-t-transparent rounded-full mx-auto" />
        </div>
      </div>
    );
  }

  const ship = order?.shipping_address || {};
  const items = order?.items || [];
  const isCorporate = order?.billing_info?.is_corporate;

  return (
    <div className="min-h-screen bg-white" data-testid="order-success-page">
      <Header />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
        {/* Hero */}
        <div className="text-center mb-16">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-stone-100 mb-6">
            <Check size={32} className="text-stone-700" strokeWidth={1.5} />
          </div>
          <h1 className="text-3xl sm:text-4xl font-light tracking-[0.3em] text-stone-900 mb-4" data-testid="order-success-title">
            TEŞEKKÜR EDERİZ
          </h1>
          <p className="text-stone-500 text-sm tracking-wide max-w-md mx-auto leading-relaxed">
            Siparişiniz başarıyla alındı. Sipariş detayları ve takip bilgileri e-posta adresinize gönderildi.
          </p>
        </div>

        {/* Order Number Card */}
        <div className="border border-stone-200 mb-12">
          <div className="px-6 sm:px-10 py-8 text-center">
            <p className="text-[10px] tracking-[0.2em] text-stone-400 uppercase mb-2">Sipariş Numarası</p>
            <p className="text-2xl font-light text-stone-900 tracking-wider" data-testid="order-success-number">
              {orderNumber}
            </p>
            {order?.created_at && (
              <p className="text-xs text-stone-400 mt-3">
                {new Date(order.created_at).toLocaleString("tr-TR", {
                  day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
                })}
              </p>
            )}
          </div>
        </div>

        {/* Step indicator */}
        <div className="mb-16">
          <div className="flex items-center justify-between max-w-2xl mx-auto">
            {[
              { icon: Check, label: "Onaylandı", active: true },
              { icon: Package, label: "Hazırlanıyor", active: false },
              { icon: Truck, label: "Kargoda", active: false },
              { icon: Home, label: "Teslim", active: false },
            ].map((step, i, arr) => (
              <div key={i} className="flex-1 flex items-center">
                <div className="flex flex-col items-center">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${step.active ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-400"}`}>
                    <step.icon size={16} strokeWidth={1.5} />
                  </div>
                  <span className={`text-[10px] tracking-wider uppercase mt-2 ${step.active ? "text-stone-900 font-medium" : "text-stone-400"}`}>
                    {step.label}
                  </span>
                </div>
                {i < arr.length - 1 && (
                  <div className={`flex-1 h-px mx-2 ${i === 0 ? "bg-stone-300" : "bg-stone-100"}`} />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Items */}
        {items.length > 0 && (
          <div className="mb-12">
            <p className="text-[10px] tracking-[0.2em] text-stone-400 uppercase mb-6">Ürünler ({items.length})</p>
            <div className="space-y-4">
              {items.map((it, idx) => (
                <div key={idx} className="flex gap-5 pb-4 border-b border-stone-100 last:border-0">
                  <img src={it.image} alt={it.name} className="w-16 h-20 object-cover bg-stone-50" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-stone-900 truncate">{it.name}</p>
                    <p className="text-xs text-stone-400 mt-1">
                      {[it.size && `Beden: ${it.size}`, it.color && `Renk: ${it.color}`, `Adet: ${it.quantity}`].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <div className="text-sm text-stone-900 whitespace-nowrap">
                    {(it.price * it.quantity).toFixed(2)} TL
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Totals */}
        <div className="mb-12 pb-12 border-b border-stone-100">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between text-stone-500"><span>Ara Toplam</span><span>{(order?.subtotal || 0).toFixed(2)} TL</span></div>
            <div className="flex justify-between text-stone-500"><span>Kargo</span><span>{(order?.shipping_cost || 0) === 0 ? "Ücretsiz" : `${(order?.shipping_cost || 0).toFixed(2)} TL`}</span></div>
            {(order?.discount || 0) > 0 && (
              <div className="flex justify-between text-stone-700"><span>İndirim{order.coupon_code ? ` · ${order.coupon_code}` : ""}</span><span>-{order.discount.toFixed(2)} TL</span></div>
            )}
            <div className="flex justify-between pt-3 mt-3 border-t border-stone-200 text-stone-900 font-medium">
              <span>Toplam</span><span>{(order?.total || 0).toFixed(2)} TL</span>
            </div>
          </div>
        </div>

        {/* Address & Contact */}
        <div className="grid sm:grid-cols-2 gap-12 mb-16">
          <div>
            <p className="text-[10px] tracking-[0.2em] text-stone-400 uppercase mb-4 flex items-center gap-2">
              <MapPin size={12} /> Teslimat Adresi
            </p>
            <p className="text-sm text-stone-900 mb-1">{ship.first_name} {ship.last_name}</p>
            <p className="text-sm text-stone-500 leading-relaxed">{ship.address}</p>
            <p className="text-sm text-stone-500">{ship.district} / {ship.city}</p>
            <p className="text-sm text-stone-500 mt-2 flex items-center gap-2">
              <Phone size={12} /> {ship.phone}
            </p>
            {ship.email && (
              <p className="text-sm text-stone-500 flex items-center gap-2">
                <Mail size={12} /> {ship.email}
              </p>
            )}
          </div>
          {isCorporate && (
            <div>
              <p className="text-[10px] tracking-[0.2em] text-stone-400 uppercase mb-4">Kurumsal Fatura</p>
              <p className="text-sm text-stone-900 mb-1">{order.billing_info.company_name}</p>
              <p className="text-sm text-stone-500">VKN: {order.billing_info.tax_number}</p>
              <p className="text-sm text-stone-500">Vergi Dairesi: {order.billing_info.tax_office}</p>
              {order.billing_info.e_invoice_user && (
                <p className="text-xs text-stone-400 mt-2">e-Fatura mükellefi</p>
              )}
            </div>
          )}
        </div>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link to="/hesabim" data-testid="view-orders-btn"
            className="inline-block text-center bg-stone-900 hover:bg-stone-800 text-white px-10 py-4 text-xs tracking-[0.2em] uppercase transition-colors">
            Siparişlerimi Gör
          </Link>
          <Link to="/" data-testid="continue-shopping-btn"
            className="inline-block text-center border border-stone-900 hover:bg-stone-50 text-stone-900 px-10 py-4 text-xs tracking-[0.2em] uppercase transition-colors">
            Alışverişe Devam Et
          </Link>
        </div>

        {/* Help */}
        <div className="text-center mt-16 pt-12 border-t border-stone-100">
          <p className="text-xs text-stone-400 tracking-wide">
            Sorularınız için: <a href="mailto:destek@facette.com.tr" className="underline hover:text-stone-900">destek@facette.com.tr</a>
          </p>
        </div>
      </div>
      <Footer />
    </div>
  );
}
