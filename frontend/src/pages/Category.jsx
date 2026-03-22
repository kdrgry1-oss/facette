import { useState, useEffect } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { SlidersHorizontal, ChevronDown, Grid, List } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Category() {
  const { slug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [sortOpen, setSortOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [viewMode, setViewMode] = useState("grid");

  const sort = searchParams.get("sort") || "created_at";
  const order = searchParams.get("order") || "desc";
  const minPrice = searchParams.get("min_price") || "";
  const maxPrice = searchParams.get("max_price") || "";

  useEffect(() => {
    fetchProducts();
    fetchCategories();
  }, [slug, sort, order, minPrice, maxPrice, page]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      let url = `${API}/products?page=${page}&limit=20&sort=${sort}&order=${order}`;
      if (slug) url += `&category=${slug}`;
      if (minPrice) url += `&min_price=${minPrice}`;
      if (maxPrice) url += `&max_price=${maxPrice}`;
      
      const res = await axios.get(url);
      setProducts(res.data?.products || []);
      setTotal(res.data?.total || 0);
      setPages(res.data?.pages || 1);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await axios.get(`${API}/categories`);
      setCategories(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSort = (newSort, newOrder) => {
    searchParams.set("sort", newSort);
    searchParams.set("order", newOrder);
    setSearchParams(searchParams);
    setSortOpen(false);
  };

  const currentCategory = categories.find(c => c.slug === slug);
  const sortOptions = [
    { label: "En Yeniler", sort: "created_at", order: "desc" },
    { label: "Fiyat: Düşükten Yükseğe", sort: "price", order: "asc" },
    { label: "Fiyat: Yüksekten Düşüğe", sort: "price", order: "desc" },
    { label: "İsim: A-Z", sort: "name", order: "asc" },
  ];

  const currentSortLabel = sortOptions.find(o => o.sort === sort && o.order === order)?.label || "En Yeniler";

  return (
    <div className="min-h-screen" data-testid="category-page">
      <Header />

      {/* Breadcrumb */}
      <div className="container-main py-4 border-b">
        <nav className="text-xs">
          <Link to="/" className="text-gray-500 hover:text-black">Ana Sayfa</Link>
          <span className="mx-2 text-gray-300">/</span>
          <span className="text-black">{currentCategory?.name || slug || "Tüm Ürünler"}</span>
        </nav>
      </div>

      <div className="container-main py-8">
        <div className="flex gap-8">
          {/* Sidebar Filters - Desktop */}
          <aside className="hidden lg:block w-64 flex-shrink-0">
            <h2 className="text-lg font-medium mb-6">Kategoriler</h2>
            <ul className="space-y-2">
              {categories.map((cat) => (
                <li key={cat.id}>
                  <Link 
                    to={`/kategori/${cat.slug}`}
                    className={`block py-1 text-sm hover:text-black transition-colors ${cat.slug === slug ? "font-medium" : "text-gray-600"}`}
                  >
                    {cat.name}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="mt-8 pt-8 border-t">
              <h3 className="text-sm font-medium mb-4">Fiyat Aralığı</h3>
              <div className="flex gap-2 items-center">
                <input
                  type="number"
                  placeholder="Min"
                  value={minPrice}
                  onChange={(e) => {
                    if (e.target.value) searchParams.set("min_price", e.target.value);
                    else searchParams.delete("min_price");
                    setSearchParams(searchParams);
                  }}
                  className="w-20 px-2 py-1 border text-sm"
                />
                <span>-</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={maxPrice}
                  onChange={(e) => {
                    if (e.target.value) searchParams.set("max_price", e.target.value);
                    else searchParams.delete("max_price");
                    setSearchParams(searchParams);
                  }}
                  className="w-20 px-2 py-1 border text-sm"
                />
              </div>
            </div>
          </aside>

          {/* Main Content */}
          <div className="flex-1">
            {/* Toolbar */}
            <div className="flex items-center justify-between mb-6 pb-4 border-b">
              <div className="flex items-center gap-4">
                <button 
                  className="lg:hidden flex items-center gap-2 text-sm"
                  onClick={() => setFilterOpen(!filterOpen)}
                >
                  <SlidersHorizontal size={16} />
                  Filtreler
                </button>
                <span className="text-sm text-gray-500">{total} ürün</span>
              </div>

              <div className="flex items-center gap-4">
                {/* View Mode */}
                <div className="hidden md:flex items-center gap-1 border-r pr-4">
                  <button 
                    onClick={() => setViewMode("grid")}
                    className={`p-1 ${viewMode === "grid" ? "text-black" : "text-gray-400"}`}
                  >
                    <Grid size={18} />
                  </button>
                  <button 
                    onClick={() => setViewMode("list")}
                    className={`p-1 ${viewMode === "list" ? "text-black" : "text-gray-400"}`}
                  >
                    <List size={18} />
                  </button>
                </div>

                {/* Sort */}
                <div className="relative">
                  <button 
                    className="flex items-center gap-2 text-sm"
                    onClick={() => setSortOpen(!sortOpen)}
                    data-testid="sort-btn"
                  >
                    {currentSortLabel}
                    <ChevronDown size={16} className={`transition-transform ${sortOpen ? "rotate-180" : ""}`} />
                  </button>
                  
                  {sortOpen && (
                    <div className="absolute right-0 top-full mt-2 bg-white border shadow-lg py-2 min-w-[200px] z-10 animate-fade-in">
                      {sortOptions.map((option) => (
                        <button
                          key={`${option.sort}-${option.order}`}
                          onClick={() => handleSort(option.sort, option.order)}
                          className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${sort === option.sort && order === option.order ? "font-medium" : ""}`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Products Grid */}
            {loading ? (
              <div className={`grid ${viewMode === "grid" ? "grid-cols-2 md:grid-cols-3" : "grid-cols-1"} gap-4 md:gap-6`}>
                {[...Array(9)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-[3/4] bg-gray-200" />
                    <div className="mt-3 space-y-2">
                      <div className="h-3 bg-gray-200 w-1/3" />
                      <div className="h-4 bg-gray-200 w-2/3" />
                      <div className="h-4 bg-gray-200 w-1/4" />
                    </div>
                  </div>
                ))}
              </div>
            ) : products.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-gray-500">Bu kategoride ürün bulunamadı.</p>
              </div>
            ) : (
              <div className={`grid ${viewMode === "grid" ? "grid-cols-2 md:grid-cols-3" : "grid-cols-1"} gap-4 md:gap-6`}>
                {products.map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            )}

            {/* Pagination */}
            {pages > 1 && (
              <div className="flex justify-center gap-2 mt-12">
                {[...Array(pages)].map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setPage(i + 1)}
                    className={`w-10 h-10 flex items-center justify-center text-sm border ${page === i + 1 ? "bg-black text-white border-black" : "hover:border-black"}`}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
