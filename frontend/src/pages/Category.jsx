import { useState, useEffect, useRef, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { SlidersHorizontal, Square, Columns2, Grid2X2, X, Check } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { trackViewItemList } from "../lib/dataLayer";
import { slugify } from "../lib/slug";
import { dedupeColorGroups } from "../lib/colorGroups";
import { sortLikeSize } from "../utils/sizeSort";
import { resolveColor, needsBorder, MULTI_GRADIENT } from "../lib/colorMap";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Bir ürünün kendi renk adını çözer (facet listesi için): variants[].color →
// attributes(Web Color/Renk/Color) → color. Backend _pc_color ile aynı mantık.
function pColor(p) {
  const v = (p.variants || []).find((x) => (x.color || "").trim());
  if (v) return v.color.trim();
  const a = (p.attributes || []).find((x) =>
    ["web color", "renk", "color"].includes((x.name || "").trim().toLowerCase())
  );
  if (a && (a.value || "").trim()) return a.value.trim();
  return (p.color || "").trim();
}

export default function Category() {
  const { slug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [filterOpen, setFilterOpen] = useState(false);

  // Grid sütun tercihi localStorage'a kaydedilir. Seçenekler: 1 / 2 / 4
  const [gridCols, setGridColsState] = useState(() => {
    const saved = parseInt(localStorage.getItem("facette_plp_grid") || "", 10);
    return [1, 2, 4].includes(saved) ? saved : 4;
  });
  const setGridCols = (n) => {
    setGridColsState(n);
    try { localStorage.setItem("facette_plp_grid", String(n)); } catch (e) {}
  };

  // --- Uygulanmış (URL'deki) filtreler ---
  const sort = searchParams.get("sort") || "created_at";
  const order = searchParams.get("order") || "desc";
  const minPrice = searchParams.get("min_price") || "";
  const maxPrice = searchParams.get("max_price") || "";
  const sizesParam = searchParams.get("sizes") || "";
  const colorsParam = searchParams.get("colors") || "";

  // --- Taslak (drawer içinde, henüz uygulanmamış) seçimler ---
  const [stSort, setStSort] = useState(`${sort}:${order}`);
  const [stMin, setStMin] = useState(minPrice);
  const [stMax, setStMax] = useState(maxPrice);
  const [stSizes, setStSizes] = useState(sizesParam ? sizesParam.split(",") : []);
  const [stColors, setStColors] = useState(colorsParam ? colorsParam.split(",") : []);

  // --- Facet (mevcut beden/renk seçenekleri) ---
  const [facetSizes, setFacetSizes] = useState([]);
  const [facetColors, setFacetColors] = useState([]);
  const facetCacheRef = useRef({}); // slug -> { sizes, colors }

  useEffect(() => {
    fetchProducts();
    fetchCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, sort, order, minPrice, maxPrice, sizesParam, colorsParam, page]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [page]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      let url = `${API}/products?page=${page}&limit=24&sort=${sort}&order=${order}`;
      if (slug && slug !== "all") url += `&category=${slug}`;
      if (minPrice) url += `&min_price=${minPrice}`;
      if (maxPrice) url += `&max_price=${maxPrice}`;
      if (sizesParam) url += `&sizes=${encodeURIComponent(sizesParam)}`;
      if (colorsParam) url += `&colors=${encodeURIComponent(colorsParam)}`;

      const res = await axios.get(url);
      const fetched = res.data?.products || [];
      setProducts(fetched);
      setTotal(res.data?.total || 0);
      setPages(res.data?.pages || 1);
      if (fetched.length > 0) {
        try {
          trackViewItemList({ products: fetched.slice(0, 24), listName: slug || "all" });
        } catch (_) { /* silent */ }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await axios.get(`${API}/categories?visible_only=true`);
      setCategories(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  // Drawer açıldığında: taslakları URL'den senkronla + facet'leri yükle.
  const openFilter = async () => {
    setStSort(`${sort}:${order}`);
    setStMin(minPrice);
    setStMax(maxPrice);
    setStSizes(sizesParam ? sizesParam.split(",") : []);
    setStColors(colorsParam ? colorsParam.split(",") : []);
    setFilterOpen(true);
    loadFacets();
  };

  const loadFacets = async () => {
    const key = slug || "all";
    if (facetCacheRef.current[key]) {
      setFacetSizes(facetCacheRef.current[key].sizes);
      setFacetColors(facetCacheRef.current[key].colors);
      return;
    }
    try {
      let url = `${API}/products?page=1&limit=120&sort=created_at&order=desc`;
      if (slug && slug !== "all") url += `&category=${slug}`;
      const res = await axios.get(url);
      const items = res.data?.products || [];
      // Bedenler
      const sizeMap = new Map();
      for (const p of items) {
        for (const v of p.variants || []) {
          const s = (v.size || "").toString().trim();
          if (s) sizeMap.set(s, true);
        }
      }
      let sizes = [...sizeMap.keys()];
      try { sizes = sortLikeSize(sizes.map((s) => ({ size: s })), (x) => x.size).map((x) => x.size); } catch (_) {}
      // Renkler (benzersiz, ilk yazımı korunur)
      const colorMap = new Map();
      for (const p of items) {
        const c = pColor(p);
        if (c && !colorMap.has(c.toLowerCase())) colorMap.set(c.toLowerCase(), c);
      }
      const colors = [...colorMap.values()];
      facetCacheRef.current[key] = { sizes, colors };
      setFacetSizes(sizes);
      setFacetColors(colors);
    } catch (err) {
      setFacetSizes([]);
      setFacetColors([]);
    }
  };

  const toggleSize = (s) =>
    setStSizes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  const toggleColor = (c) =>
    setStColors((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));

  // "Ürünleri Göster" — taslakları tek seferde URL'e yaz, listeyi yenile.
  const applyFilters = () => {
    const next = new URLSearchParams(searchParams);
    const [sk, so] = stSort.split(":");
    next.set("sort", sk); next.set("order", so);
    if (stMin) next.set("min_price", stMin); else next.delete("min_price");
    if (stMax) next.set("max_price", stMax); else next.delete("max_price");
    if (stSizes.length) next.set("sizes", stSizes.join(",")); else next.delete("sizes");
    if (stColors.length) next.set("colors", stColors.join(",")); else next.delete("colors");
    setPage(1);
    setSearchParams(next);
    setFilterOpen(false);
  };

  const clearFilters = () => {
    setStSort("created_at:desc");
    setStMin(""); setStMax("");
    setStSizes([]); setStColors([]);
  };

  const currentCategory = categories.find((c) => c.slug === slug);
  const categoryName =
    currentCategory?.name ||
    slug?.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) ||
    "Tüm Ürünler";

  const sortOptions = [
    { label: "En Yeniler", value: "created_at:desc" },
    { label: "Fiyat: Düşükten Yükseğe", value: "price:asc" },
    { label: "Fiyat: Yüksekten Düşüğe", value: "price:desc" },
    { label: "İsim: A-Z", value: "name:asc" },
  ];

  const gridClass = {
    1: "grid-cols-1",
    2: "grid-cols-2",
    4: "grid-cols-4",
  };

  // Aktif (uygulanmış) filtre sayısı — toolbar rozetinde gösterilir.
  const activeCount = useMemo(() => {
    let n = 0;
    if (minPrice || maxPrice) n += 1;
    if (sizesParam) n += sizesParam.split(",").filter(Boolean).length;
    if (colorsParam) n += colorsParam.split(",").filter(Boolean).length;
    if (!(sort === "created_at" && order === "desc")) n += 1;
    return n;
  }, [minPrice, maxPrice, sizesParam, colorsParam, sort, order]);

  return (
    <div className="min-h-screen bg-white" data-testid="category-page">
      <Header />

      <div className="w-full px-2 md:px-4">
        {/* Category Title — Mango usulü sade başlık */}
        <div className="pt-8 pb-4 md:pt-10">
          <h1 className="text-xl md:text-2xl font-normal tracking-tight text-stone-900">
            {categoryName}
          </h1>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between py-4 border-b">
          <button
            onClick={openFilter}
            className="flex items-center gap-2 text-sm hover:opacity-60 transition-opacity"
            data-testid="filter-btn"
          >
            <SlidersHorizontal size={16} strokeWidth={1.5} />
            <span>Filtrele{activeCount > 0 ? ` (${activeCount})` : ""}</span>
          </button>

          <span className="text-sm text-gray-500 hidden md:block">{total} Ürün</span>

          <div className="flex items-center gap-3">
            <button onClick={() => setGridCols(1)} className={`p-1 ${gridCols === 1 ? "text-black" : "text-gray-400"}`} data-testid="grid-1" aria-label="Tekli görünüm">
              <Square size={18} strokeWidth={1.5} />
            </button>
            <button onClick={() => setGridCols(2)} className={`p-1 ${gridCols === 2 ? "text-black" : "text-gray-400"}`} data-testid="grid-2" aria-label="İkili görünüm">
              <Columns2 size={18} strokeWidth={1.5} />
            </button>
            <button onClick={() => setGridCols(4)} className={`p-1 ${gridCols === 4 ? "text-black" : "text-gray-400"}`} data-testid="grid-4" aria-label="Dörtlü görünüm">
              <Grid2X2 size={18} strokeWidth={1.5} />
            </button>
          </div>
        </div>

        {/* Products Grid */}
        <div className="py-8">
          {loading ? (
            <div className={`grid ${gridClass[gridCols]} gap-x-2 md:gap-x-3 gap-y-8 md:gap-y-10`}>
              {[...Array(8)].map((_, i) => (
                <div key={i} className="animate-pulse">
                  <div className="aspect-[2/3] bg-gray-100 mb-3" />
                  <div className="h-3 bg-gray-100 w-1/3 mb-2" />
                  <div className="h-4 bg-gray-100 w-3/4 mb-2" />
                  <div className="h-4 bg-gray-100 w-1/4" />
                </div>
              ))}
            </div>
          ) : products.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-gray-500">Bu kategoride ürün bulunamadı</p>
              {activeCount > 0 && (
                <button
                  onClick={() => { setSearchParams({}); }}
                  className="mt-4 text-sm underline hover:no-underline"
                >
                  Filtreleri temizle
                </button>
              )}
            </div>
          ) : (
            <div className={`grid ${gridClass[gridCols]} gap-x-2 md:gap-x-3 gap-y-8 md:gap-y-10`}>
              {dedupeColorGroups(products).map((product, idx) => (
                <ProductCard key={product.id} product={product} listName={slug || "all"} index={idx} />
              ))}
            </div>
          )}

          {/* Pagination */}
          {pages > 1 && (
            <div className="flex justify-center items-center gap-2 mt-12">
              {[...Array(pages)].map((_, i) => (
                <button
                  key={i}
                  onClick={() => setPage(i + 1)}
                  className={`w-10 h-10 text-sm transition-colors ${
                    page === i + 1 ? "bg-black text-white" : "border border-gray-300 hover:border-black"
                  }`}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Filter Drawer (Mango usulü) — soldan açılır, taslak seçim + alt "Ürünleri Göster" */}
      <div
        className={`fixed inset-0 z-40 transition-opacity duration-300 ${
          filterOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
      >
        <div className="absolute inset-0 bg-black/40" onClick={() => setFilterOpen(false)} />
      </div>
      <aside
        className={`fixed left-0 top-0 bottom-0 w-[88%] max-w-sm bg-white z-50 flex flex-col transition-transform duration-300 ease-out ${
          filterOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-hidden={!filterOpen}
        data-testid="filter-drawer"
      >
        {/* Başlık */}
        <div className="flex items-center justify-between px-5 h-14 border-b shrink-0">
          <h3 className="text-sm font-medium tracking-wide">Filtrele</h3>
          <button onClick={() => setFilterOpen(false)} aria-label="Kapat">
            <X size={20} strokeWidth={1.5} />
          </button>
        </div>

        {/* İçerik */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-8">
          {/* Sıralama */}
          <section>
            <h4 className="text-[11px] uppercase tracking-[0.18em] text-gray-500 mb-3">Sırala</h4>
            <div className="flex flex-wrap gap-2">
              {sortOptions.map((o) => (
                <button
                  key={o.value}
                  onClick={() => setStSort(o.value)}
                  className={`px-3 h-9 text-xs border transition-colors ${
                    stSort === o.value ? "border-black bg-black text-white" : "border-gray-300 hover:border-black"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </section>

          {/* Beden */}
          {facetSizes.length > 0 && (
            <section>
              <h4 className="text-[11px] uppercase tracking-[0.18em] text-gray-500 mb-3">Beden</h4>
              <div className="flex flex-wrap gap-2">
                {facetSizes.map((s) => {
                  const on = stSizes.includes(s);
                  return (
                    <button
                      key={s}
                      onClick={() => toggleSize(s)}
                      className={`min-w-[44px] h-9 px-3 text-xs border transition-colors ${
                        on ? "border-black bg-black text-white" : "border-gray-300 hover:border-black"
                      }`}
                    >
                      {s}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Renk */}
          {facetColors.length > 0 && (
            <section>
              <h4 className="text-[11px] uppercase tracking-[0.18em] text-gray-500 mb-3">Renk</h4>
              <div className="flex flex-wrap gap-3">
                {facetColors.map((c) => {
                  const on = stColors.includes(c);
                  const col = resolveColor(c);
                  let style, fb = false;
                  if (col?.type === "solid") style = { backgroundColor: col.value };
                  else if (col?.type === "multi") style = { background: MULTI_GRADIENT };
                  else { fb = true; style = { background: "linear-gradient(135deg,#f3f4f6,#d1d5db)" }; }
                  const light = col?.type === "solid" && needsBorder(col.value);
                  return (
                    <button
                      key={c}
                      onClick={() => toggleColor(c)}
                      className="flex flex-col items-center gap-1.5 w-14"
                      title={c}
                    >
                      <span
                        className={`w-8 h-8 rounded-full transition-all ${
                          on ? "ring-2 ring-offset-2 ring-black" : light ? "border border-gray-300" : "border border-black/10"
                        }`}
                        style={style}
                      >
                        {fb && <span className="block w-full h-full" />}
                      </span>
                      <span className={`text-[10px] leading-tight text-center line-clamp-1 ${on ? "text-black font-medium" : "text-gray-500"}`}>
                        {c}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Fiyat */}
          <section>
            <h4 className="text-[11px] uppercase tracking-[0.18em] text-gray-500 mb-3">Fiyat Aralığı</h4>
            <div className="flex items-center gap-2">
              <input
                type="number" inputMode="numeric" placeholder="Min ₺"
                value={stMin}
                onChange={(e) => setStMin(e.target.value)}
                className="w-1/2 border border-gray-300 px-3 h-10 text-sm focus:border-black outline-none"
              />
              <span className="text-gray-400">–</span>
              <input
                type="number" inputMode="numeric" placeholder="Max ₺"
                value={stMax}
                onChange={(e) => setStMax(e.target.value)}
                className="w-1/2 border border-gray-300 px-3 h-10 text-sm focus:border-black outline-none"
              />
            </div>
          </section>

          {/* Kategoriler */}
          {categories.length > 0 && (
            <section>
              <h4 className="text-[11px] uppercase tracking-[0.18em] text-gray-500 mb-3">Kategoriler</h4>
              <div className="space-y-1">
                {categories.map((cat) => (
                  <a
                    key={cat.id}
                    href={`/${slugify(cat.name || cat.slug || "")}`}
                    className={`block text-sm py-2 px-3 transition-colors ${
                      slug === cat.slug ? "bg-black text-white" : "hover:bg-gray-100"
                    }`}
                  >
                    {cat.name}
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Alt çubuk — Temizle + Ürünleri Göster */}
        <div className="border-t px-5 py-3 flex items-center gap-3 shrink-0">
          <button
            onClick={clearFilters}
            className="text-sm text-gray-600 hover:text-black underline underline-offset-2"
          >
            Temizle
          </button>
          <button
            onClick={applyFilters}
            className="flex-1 h-11 bg-black text-white text-sm tracking-wide hover:bg-gray-900 transition-colors inline-flex items-center justify-center gap-2"
            data-testid="apply-filters-btn"
          >
            <Check size={16} strokeWidth={2} /> Ürünleri Göster
          </button>
        </div>
      </aside>

      <Footer />
    </div>
  );
}
