import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { SlidersHorizontal, Grid2X2, Grid3X3, LayoutGrid, X } from "lucide-react";
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
  const [filterOpen, setFilterOpen] = useState(false);
  const [gridCols, setGridCols] = useState(4); // 2, 3, or 4 columns

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
      let url = `${API}/products?page=${page}&limit=24&sort=${sort}&order=${order}`;
      if (slug && slug !== 'all') url += `&category=${slug}`;
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
  };

  const currentCategory = categories.find(c => c.slug === slug);
  const categoryName = currentCategory?.name || slug?.replace(/-/g, ' ').toUpperCase() || 'TÜM ÜRÜNLER';

  const sortOptions = [
    { label: "En Yeniler", sort: "created_at", order: "desc" },
    { label: "Fiyat: Düşükten Yükseğe", sort: "price", order: "asc" },
    { label: "Fiyat: Yüksekten Düşüğe", sort: "price", order: "desc" },
    { label: "İsim: A-Z", sort: "name", order: "asc" },
  ];

  const gridClass = {
    2: "grid-cols-2",
    3: "grid-cols-2 md:grid-cols-3",
    4: "grid-cols-2 md:grid-cols-4"
  };

  return (
    <div className="min-h-screen bg-white" data-testid="category-page">
      <Header />

      <div className="container-main">
        {/* Category Title */}
        <div className="py-8 text-center border-b">
          <h1 className="text-2xl md:text-3xl tracking-wider uppercase font-light">
            {categoryName}
          </h1>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between py-4 border-b">
          {/* Left: Filter */}
          <button 
            onClick={() => setFilterOpen(true)}
            className="flex items-center gap-2 text-sm hover:opacity-60 transition-opacity"
            data-testid="filter-btn"
          >
            <SlidersHorizontal size={16} strokeWidth={1.5} />
            <span>Filtreleme</span>
          </button>

          {/* Center: Product Count */}
          <span className="text-sm text-gray-500 hidden md:block">
            {total} Ürün
          </span>

          {/* Right: Grid Options */}
          <div className="flex items-center gap-3">
            <button 
              onClick={() => setGridCols(2)}
              className={`p-1 ${gridCols === 2 ? 'text-black' : 'text-gray-400'}`}
              data-testid="grid-2"
            >
              <Grid2X2 size={18} strokeWidth={1.5} />
            </button>
            <button 
              onClick={() => setGridCols(3)}
              className={`p-1 ${gridCols === 3 ? 'text-black' : 'text-gray-400'}`}
              data-testid="grid-3"
            >
              <Grid3X3 size={18} strokeWidth={1.5} />
            </button>
            <button 
              onClick={() => setGridCols(4)}
              className={`p-1 ${gridCols === 4 ? 'text-black' : 'text-gray-400'}`}
              data-testid="grid-4"
            >
              <LayoutGrid size={18} strokeWidth={1.5} />
            </button>
          </div>
        </div>

        {/* Products Grid */}
        <div className="py-8">
          {loading ? (
            <div className={`grid ${gridClass[gridCols]} gap-4 gap-y-8`}>
              {[...Array(8)].map((_, i) => (
                <div key={i} className="animate-pulse">
                  <div className="aspect-[3/4] bg-gray-100 mb-3" />
                  <div className="h-3 bg-gray-100 w-1/3 mb-2" />
                  <div className="h-4 bg-gray-100 w-3/4 mb-2" />
                  <div className="h-4 bg-gray-100 w-1/4" />
                </div>
              ))}
            </div>
          ) : products.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-gray-500">Bu kategoride ürün bulunamadı</p>
            </div>
          ) : (
            <div className={`grid ${gridClass[gridCols]} gap-x-4 gap-y-8`}>
              {products.map((product) => (
                <ProductCard key={product.id} product={product} />
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
                    page === i + 1 
                      ? 'bg-black text-white' 
                      : 'border border-gray-300 hover:border-black'
                  }`}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Filter Sidebar */}
      {filterOpen && (
        <>
          <div 
            className="fixed inset-0 bg-black/40 z-40"
            onClick={() => setFilterOpen(false)}
          />
          <div className="fixed left-0 top-0 bottom-0 w-80 bg-white z-50 overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="text-sm font-medium uppercase tracking-wider">Filtreler</h3>
              <button onClick={() => setFilterOpen(false)}>
                <X size={20} />
              </button>
            </div>

            <div className="p-4">
              {/* Sort */}
              <div className="mb-6">
                <h4 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Sıralama</h4>
                <div className="space-y-2">
                  {sortOptions.map((option, index) => (
                    <button
                      key={index}
                      onClick={() => handleSort(option.sort, option.order)}
                      className={`block w-full text-left text-sm py-2 px-3 transition-colors ${
                        sort === option.sort && order === option.order
                          ? 'bg-black text-white'
                          : 'hover:bg-gray-100'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Categories */}
              <div className="mb-6">
                <h4 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Kategoriler</h4>
                <div className="space-y-1">
                  {categories.map((cat) => (
                    <a
                      key={cat.id}
                      href={`/kategori/${cat.slug}`}
                      className={`block text-sm py-2 px-3 transition-colors ${
                        slug === cat.slug
                          ? 'bg-black text-white'
                          : 'hover:bg-gray-100'
                      }`}
                    >
                      {cat.name}
                    </a>
                  ))}
                </div>
              </div>

              {/* Price Range */}
              <div className="mb-6">
                <h4 className="text-xs uppercase tracking-wider text-gray-500 mb-3">Fiyat Aralığı</h4>
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="Min"
                    value={minPrice}
                    onChange={(e) => {
                      if (e.target.value) {
                        searchParams.set("min_price", e.target.value);
                      } else {
                        searchParams.delete("min_price");
                      }
                      setSearchParams(searchParams);
                    }}
                    className="w-1/2 border px-3 py-2 text-sm"
                  />
                  <input
                    type="number"
                    placeholder="Max"
                    value={maxPrice}
                    onChange={(e) => {
                      if (e.target.value) {
                        searchParams.set("max_price", e.target.value);
                      } else {
                        searchParams.delete("max_price");
                      }
                      setSearchParams(searchParams);
                    }}
                    className="w-1/2 border px-3 py-2 text-sm"
                  />
                </div>
              </div>

              {/* Clear Filters */}
              <button
                onClick={() => {
                  setSearchParams({});
                  setFilterOpen(false);
                }}
                className="w-full border border-black py-3 text-sm uppercase tracking-wider hover:bg-black hover:text-white transition-colors"
              >
                Filtreleri Temizle
              </button>
            </div>
          </div>
        </>
      )}

      <Footer />
    </div>
  );
}
