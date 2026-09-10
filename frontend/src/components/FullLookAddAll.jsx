import { useEffect, useMemo, useState } from "react";
import { ShoppingBag, Check } from "lucide-react";
import { toast } from "sonner";
import { useCart } from "../context/CartContext";
import { priceView, fmtTL } from "../lib/price";
import { sortLikeSize } from "../utils/sizeSort";

/**
 * FullLookAddAll — bir kombindeki TÜM parçaları tek tıkla sepete ekler.
 * Her parça için beden seçimi (stokta olanlar), kombin toplamı ve "Tüm Kombini Sepete Ekle" düğmesi.
 * Bedensiz ürün doğrudan eklenir; tek bedenli ürünlerde beden otomatik seçilir.
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
    <div className="mt-8 border border-stone-200 bg-white p-5 md:p-6" data-testid="full-look-add-all">
      <div className="flex items-baseline justify-between gap-3 mb-4">
        <div className="text-[11px] tracking-[0.18em] uppercase text-stone-500">Tüm kombini al</div>
        <div className="text-[11px] tracking-[0.12em] uppercase text-stone-400">{addable.length} parça</div>
      </div>
      <div className="divide-y divide-stone-100">
        {rows.map((r) => (
          <div key={r.p.id} className="py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="min-w-0 flex-1">
              <div className="text-[13px] text-stone-900 truncate">{r.p.name}</div>
              <div className="text-[12px] text-stone-500">
                {r.price.hasDiscount && <del className="mr-1.5 text-stone-400">{fmtTL(r.price.list)}</del>}
                <span className={r.price.hasDiscount ? "text-red-600" : ""}>{fmtTL(r.price.display)}</span>
              </div>
            </div>
            {r.soldOut ? (
              <span className="text-[11px] tracking-[0.1em] uppercase text-stone-400">Tükendi</span>
            ) : r.hasSizes ? (
              <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={`${r.p.name} beden`}>
                {r.sizes.map((s) => {
                  const active = sel[r.p.id] === s.size;
                  return (
                    <button key={s.size} type="button" disabled={s.stock <= 0}
                      onClick={() => setSel((prev) => ({ ...prev, [r.p.id]: s.size }))}
                      className={`min-w-[38px] px-2 py-1.5 text-[11px] tracking-[0.08em] border transition-colors ${
                        active ? "bg-stone-900 text-white border-stone-900"
                          : s.stock <= 0 ? "border-stone-200 text-stone-300 line-through cursor-not-allowed"
                          : "border-stone-300 text-stone-800 hover:border-stone-900"}`}
                      data-testid={`fl-size-${r.p.id}-${s.size}`}>
                      {s.size}
                    </button>
                  );
                })}
              </div>
            ) : (
              <span className="text-[11px] tracking-[0.1em] uppercase text-stone-400 inline-flex items-center gap-1"><Check size={12} /> Tek beden</span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] tracking-[0.12em] uppercase text-stone-500">Kombin toplamı</div>
          <div className="text-lg text-stone-900">
            {listTotal > total + 0.5 && <del className="mr-2 text-sm text-stone-400">{fmtTL(listTotal)}</del>}
            <span className={listTotal > total + 0.5 ? "text-red-600" : ""}>{fmtTL(total)}</span>
          </div>
        </div>
        <button type="button" onClick={addAll} disabled={!addable.length}
          className={`inline-flex items-center gap-2 px-6 py-3 text-[12px] tracking-[0.18em] uppercase transition-colors ${
            ready ? "bg-stone-900 text-white hover:bg-stone-700" : "bg-stone-200 text-stone-500"}`}
          data-testid="full-look-add-all-btn">
          <ShoppingBag size={15} /> Tüm Kombini Sepete Ekle
        </button>
      </div>
      {!ready && missing.length > 0 && (
        <div className="mt-2 text-[11px] text-stone-500">Devam etmek için beden seçin: {missing.map((r) => r.p.name).join(", ")}</div>
      )}
    </div>
  );
}
