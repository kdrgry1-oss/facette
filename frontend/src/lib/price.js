// TEK KAYNAK — ürün fiyat/indirim görünümü. Vitrin kartı, arama, menü, kombin, öneri,
// kasa-önü, ürün detay… HER YER burayı kullanır ki indirimler tutarlı görünsün.
//
// İndirim sırası (sepet motoruyla AYNI mantık):
//   1) Liste fiyatı (price)
//   2) Ürünün kendi indirimli fiyatı (sale_price) — varsa ve < price
//   3) Sepette otomatik kampanya (campaign_discount_percent) — sale_price üzerine uygulanır
//
// NOT: Kupon kodu / hoşgeldin / havale gibi SEPET-seviyesi indirimler ürün kartında
// gösterilmez (sepette/siparişte ayrı satır olarak görünür); kartta yalnızca ürüne
// bağlı indirim (sale_price + otomatik kampanya) yansır.
export function priceView(product) {
  const p = product || {};
  const list = Number(p.price || 0);
  const spRaw = Number(p.sale_price || 0);
  const sale = spRaw > 0 && spRaw < list ? spRaw : null;
  const campPct = Number(p.campaign_discount_percent || 0);
  const preCampaign = sale != null ? sale : list;
  const display = campPct > 0
    ? Math.round(preCampaign * (1 - campPct / 100) * 100) / 100
    : preCampaign;
  const hasDiscount = (sale != null) || (campPct > 0 && display < list);
  const discountPct = list > 0 && display < list
    ? Math.round(((list - display) / list) * 100)
    : 0;
  return {
    list,                       // üstü çizili liste fiyatı
    display,                    // gösterilecek nihai fiyat
    hasDiscount,                // indirim var mı
    discountPct,                // toplam indirim yüzdesi (rozet)
    salePrice: sale,            // ürünün kendi indirimi (yoksa null)
    campaignPct: campPct,       // otomatik kampanya yüzdesi
    campaignLabel: p.campaign_label || "",
  };
}

// Kısa yardımcı: TL biçimi (virgüllü).
export function fmtTL(n) {
  return (Number(n) || 0).toFixed(2).replace(".", ",") + " TL";
}
