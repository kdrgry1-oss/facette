import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ShoppingBag, Check } from "lucide-react";
import { toast } from "sonner";
import { useCart } from "../context/CartContext";
import { priceView, fmtTL } from "../lib/price";
import { sortLikeSize } from "../utils/sizeSort";

/**
 * FullLookAddAll — kombinin parçaları satır satır (küçük görsel · ad · renk · fiyat/indirim · beden seçimi)
 * ve altında "Tüm Kombini Al" özeti + tek tıkla sepete ekleme.
 * Bedensiz ürün doğrudan eklenir; tek bedenli üründe beden otomatik seçilir.
 */
export default function FullLookAddAll({ products = [] }) {
  const { addItem, setIsOpen } = useCart();
  const rows = useMemo(() => (products || []).map((p) => {
    const vs = Array.isArray(p.variants) ? p.variants : [];
    const map = new Map();
    for (const v of vs) {
      const s = String(v?.size || "").trim();
      if (!s) continue;
      if (!map.has(s)) map.set(s, { size: s, variant: v, stock: Number(v.stock) || 0 });
      else map.get(s).stock += Number(v.stock) || 0;
    }
    const sizes = sortLikeSize(Array.from(map.values()), (x) => x.size);
    const inStock = sizes.filter((x) => x.stock > 0);
    const totalStock = vs.length ? vs.reduce((a, v) => a + (Number(v.stock) || 0), 0) : Number(p.stock) || 0;
    return { p, sizes, inStock, hasSizes: sizes.length > 0, soldOut: totalStock <= 0, price: priceView(p) };
  }), [products]);

  const [sel, setSel] = useState({});
  useEffect(() => {
    // Tek stoklu beden varsa otomatik seç
    const next = {};
    for (const r of rows) {
      if (r.hasSizes && r.inStock.length === 1) next[r.p.id] = r.inStock[0].size;
    }
    setSel((prev) => ({ ...next, ...prev }));
  }, [rows]);

  if (!rows.length) return null;

  const addable = rows.filter((r) => !r.soldOut);
  const missing = addable.filter((r) => r.hasSizes && !sel[r.p.id]);
  const ready = addable.length > 0 && missing.length === 0;
  const total = addable.reduce((a, r) => a + (Number(r.price.display) || 0), 0);
  const listTotal = addable.reduce((a, r) => a + (Number(r.price.list) || 0), 0);
  const totalPct = listTotal > 0 && listTotal > total + 0.5 ? Math.round((1 - total / listTotal) * 100) : 0;

  const addAll = () => {
    if (!ready) {
      toast.error(missing.length ? `Beden seçin: ${missing.map((r) => r.p.name).join(", ")}` : "Bu kombinde stokta ürün yok");
      return;
    }
    let n = 0;
    for (const r of addable) {
      if (r.hasSizes) {
        const s = r.sizes.find((x) => x.size === sel[r.p.id]);
        if (!s || s.stock <= 0) continue;
        addItem(r.p, s.variant);
      } else {
        addItem(r.p);
      }
      n += 1;
    }
    if (n) {
      toast.success(`${n} parça sepete eklendi`);
      try { setIsOpen(true); } catch { /* çekmece yoksa */ }
    }
  };

  return (
    <div className="full-look-shop" data-testid="full-look-add-all">
      {/* Parçalar — satır düzeni: sol küçük görsel, sağ bilgi + beden */}
      <div className="divide-y divide-stone-200">
        {rows.map((r) => {
          const href = `/urun/${encodeURIComponent(r.p.slug || r.p.id)}`;
          const pct = r.price.hasDiscount ? (Number(r.price.discountPct) || Math.round((1 - r.price.display / r.price.list) * 100)) : 0;
          return (
            <div key={r.p.id} className="py-6 flex gap-5 md:gap-7" data-testid={`fl-row-${r.p.id}`}>
              <Link to={href} className="block shrink-0 w-[112px] md:w-[150px] bg-[#f4f3f0] overflow-hidden" aria-label={r.p.name}>
                {r.p.images?.[0]
                  ? <img src={r.p.images[0]} alt={r.p.name} loading="lazy" className="w-full aspect-[3/4] object-contain" />
                  : <span className="block w-full aspect-[3/4]" />}
              </Link>
              <div className="min-w-0 flex-1">
                <Link to={href} className="block text-[17px] md:text-[19px] leading-snug text-stone-900 hover:underline underline-offset-4">{r.p.name}</Link>
                {r.p.color && <div className="mt-1 text-[13px] text-stone-500">{r.p.color}</div>}
                <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                  {r.price.hasDiscount && <del className="text-[13px] text-stone-400">{fmtTL(r.price.list)}</del>}
                  <span className={`text-[18px] md:text-[20px] font-medium ${r.price.hasDiscount ? "text-red-700" : "text-stone-900"}`}>{fmtTL(r.price.display)}</span>
                  {pct > 0 && <span className="text-[12px] px-2 py-0.5 bg-red-50 text-red-700 rounded-sm">%{pct}</span>}
                </div>
                <div className="mt-4 pt-4 border-t border-stone-200">
                  {r.soldOut ? (
                    <span className="text-[11px] tracking-[0.1em] uppercase text-stone-400">Tükendi</span>
                  ) : r.hasSizes ? (
                    <>
                      <div className="text-[13px] text-stone-500 mb-2">Beden</div>
                      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={`${r.p.name} beden`}>
                        {r.sizes.map((s) => {
                          const active = sel[r.p.id] === s.size;
                          return (
                            <button key={s.size} type="button" disabled={s.stock <= 0}
                              onClick={() => setSel((prev) => ({ ...prev, [r.p.id]: s.size }))}
                              className={`min-w-[52px] md:min-w-[64px] px-3 py-2.5 text-[13px] border rounded-sm transition-colors ${
                                active ? "bg-stone-900 text-white border-stone-900"
                                  : s.stock <= 0 ? "border-stone-200 text-stone-300 line-through cursor-not-allowed"
                                  : "border-stone-200 bg-white text-stone-800 hover:border-stone-900"}`}
                              data-testid={`fl-size-${r.p.id}-${s.size}`}>
                              {s.size}
                            </button>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <span className="text-[11px] tracking-[0.1em] uppercase text-stone-400 inline-flex items-center gap-1"><Check size={12} /> Tek beden</span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Tüm kombini al — özet kutusu */}
      <div className="mt-6 bg-[#f4f3f0] rounded-md p-5 md:p-6" data-testid="full-look-summary">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-full bg-stone-900 text-white inline-flex items-center justify-center shrink-0"><Check size={16} /></span>
            <span className="text-[15px] md:text-[17px] tracking-[0.16em] uppercase text-stone-900">Tüm Kombini Al</span>
            <span className="text-[11px] tracking-[0.1em] uppercase px-2.5 py-1 bg-white/80 text-stone-600 rounded-sm">{addable.length} parça</span>
          </div>
          <div className="text-right">
            {listTotal > total + 0.5 && <div className="text-[13px] text-stone-400"><del>{fmtTL(listTotal)}</del></div>}
            <div className="text-[22px] md:text-[26px] font-medium text-stone-900 leading-tight">{fmtTL(total)}</div>
            {totalPct > 0 && <span className="inline-block mt-1 text-[12px] px-2 py-0.5 bg-red-50 text-red-700 rounded-sm">%{totalPct}</span>}
          </div>
        </div>
        <button type="button" onClick={addAll} disabled={!addable.length}
          className={`mt-5 w-full inline-flex items-center justify-center gap-3 px-6 py-4 text-[13px] tracking-[0.2em] uppercase rounded-md transition-colors ${
            ready ? "bg-stone-900 text-white hover:bg-stone-700" : "bg-stone-300 text-stone-600"}`}
          data-testid="full-look-add-all-btn">
          <ShoppingBag size={16} /> Tüm Kombini Sepete Ekle
        </button>
        {!ready && missing.length > 0 && (
          <div className="mt-2 text-[12px] text-stone-500">Devam etmek için beden seçin: {missing.map((r) => r.p.name).join(", ")}</div>
        )}
      </div>
    </div>
  );
}
