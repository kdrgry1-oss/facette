import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Check } from "lucide-react";
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
              <Link to={href} className="block shrink-0 w-[112px] md:w-[150px] overflow-hidden" aria-label={r.p.name}>
                {r.p.images?.[0]
                  ? <img src={r.p.images[0]} alt={r.p.name} loading="lazy" className="block w-full aspect-[3/4] object-cover" />
                  : <span className="block w-full aspect-[3/4] bg-white" />}
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

      {/* Tüm kombini al — site geneliyle uyumlu sade özet: ince üst çizgi, büyük harf/aralıklı başlık, kare siyah düğme */}
      <div className="mt-8 pt-6 border-t border-stone-200" data-testid="full-look-summary">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <div className="text-[12px] md:text-[13px] tracking-[0.2em] uppercase text-stone-900">Tüm Kombini Al</div>
            <div className="mt-1 text-[11px] tracking-[0.12em] uppercase text-stone-400">{addable.length} parça</div>
          </div>
          <div className="flex items-baseline gap-3 md:justify-end md:text-right">
            {listTotal > total + 0.5 && <del className="text-[13px] text-stone-400">{fmtTL(listTotal)}</del>}
            <span className={`text-[20px] md:text-[22px] font-medium leading-none ${listTotal > total + 0.5 ? "text-red-700" : "text-stone-900"}`}>{fmtTL(total)}</span>
            {totalPct > 0 && <span className="text-[12px] px-2 py-0.5 bg-red-50 text-red-700">%{totalPct}</span>}
          </div>
        </div>
        <button type="button" onClick={addAll} disabled={!addable.length}
          className="mt-5 w-full px-6 py-3.5 text-[11px] md:text-xs uppercase tracking-[0.2em] bg-black text-white hover:bg-black/85 transition-colors disabled:opacity-40"
          data-testid="full-look-add-all-btn">
          Tüm Kombini Sepete Ekle
        </button>
      </div>
    </div>
  );
}
