/**
 * =============================================================================
 * SearchableAttribute.jsx — Aranabilir özellik seçici
 * =============================================================================
 *
 * AMAÇ:
 *   Products.jsx ürün modalının "Özellikler" sekmesinde, pazaryerlerinin
 *   (özellikle Trendyol) zorunlu tuttuğu özelliklerin (Kumaş Tipi, Yaka, Boy,
 *   Desen vb.) kütüphaneden aranarak hızlıca seçilmesini sağlar. Kütüphanede
 *   tanımlı değeri olmayan (serbest metin) özellikler için düz input'a düşer.
 *
 * PROPS:
 *   - attr       : { id, name, values: string[] } — /api/attributes'tan gelir.
 *   - value      : Mevcut seçili değer.
 *   - onChange   : (v) => void — Üst formun setFormData'sına bağlanır.
 *   - isRequired : Trendyol zorunlu mu? → kırmızı "ZORUNLU" rozetiyle vurgulanır.
 *
 * KULLANIM YERİ:
 *   Products.jsx > ürün modalı > "Özellikler" (attributes) sekmesi içindeki map.
 *
 * NEDEN AYRI DOSYA?
 *   Products.jsx 2500+ satıra ulaştığı için bağımsız küçük parçalar
 *   dış dosyalara taşınıyor (P2 refactor). Bu bileşen tek başına taşınabilir
 *   çünkü yalnızca props'a bağımlı, hiçbir parent-only closure içermiyor.
 * =============================================================================
 */
import { useState, useEffect, useRef } from "react";
import { Search, Check, ChevronDown } from "lucide-react";

const SearchableAttribute = ({ attr, value, onChange, isRequired }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const dropdownRef = useRef(null);

  const hasValue = !!value;
  const filteredValues =
    attr.values?.filter((v) =>
      v.toLowerCase().includes(searchTerm.toLowerCase())
    ) || [];

  // Dışarı tıklayınca kapat
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Kütüphanede değer yoksa düz input'a düş
  if (!attr.values || attr.values.length === 0) {
    return (
      <div className="space-y-2">
        <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest">
          {attr.name}
        </label>
        <input
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Serbest değer yazın..."
          className="w-full border-gray-100 border-2 px-4 py-3 rounded-lg bg-gray-50 focus:bg-white focus:border-orange-300 outline-none transition-all text-sm font-medium"
        />
      </div>
    );
  }

  return (
    <div
      className={`space-y-2 relative ${
        isRequired && !hasValue
          ? "p-3 bg-red-50 rounded-xl border-2 border-red-200"
          : ""
      }`}
      ref={dropdownRef}
    >
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-1">
          <label
            className={`block text-[10px] font-black uppercase tracking-widest ${
              isRequired ? "text-white bg-red-600 px-1 rounded" : "text-gray-900"
            }`}
          >
            {attr.name}
          </label>
          {hasValue && (
            <Check size={12} className="text-green-500 font-bold" strokeWidth={4} />
          )}
          {isRequired && !hasValue && (
            <span className="text-red-600 font-bold animate-pulse">*</span>
          )}
        </div>
        {isRequired && !hasValue && (
          <span className="text-[10px] font-black text-white bg-red-600 px-2 py-0.5 rounded-full uppercase animate-pulse shadow-lg shadow-red-200 ring-2 ring-red-300">
            ZORUNLU (TRENDYOL)
          </span>
        )}
      </div>

      <div
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full border-2 px-4 py-3 rounded-lg bg-gray-50 cursor-pointer flex justify-between items-center transition-all ${
          hasValue
            ? "border-green-500"
            : isRequired
            ? "border-red-300"
            : "border-gray-100"
        }`}
      >
        <div className="flex items-center gap-2 overflow-hidden flex-1">
          <Search size={14} className="text-gray-400 shrink-0" />
          <span
            className={`text-sm truncate ${
              hasValue ? "text-black font-bold" : "text-gray-400 font-medium"
            }`}
          >
            {value || "Seçiniz..."}
          </span>
        </div>
        <ChevronDown
          size={14}
          className={`transition-transform shrink-0 ${isOpen ? "rotate-180" : ""}`}
        />
      </div>

      {isOpen && (
        <div className="absolute z-[100] top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="p-2 border-b bg-gray-50 flex items-center gap-2">
            <Search size={14} className="text-gray-400" />
            <input
              autoFocus
              className="bg-transparent border-none outline-none text-xs w-full py-1 font-bold"
              placeholder="Kütüphanede ara..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
          <div className="max-h-60 overflow-y-auto">
            {filteredValues.map((v, idx) => (
              <div
                key={idx}
                className="px-4 py-3 text-sm hover:bg-orange-50 cursor-pointer border-b last:border-0 border-gray-50 transition-colors font-medium text-gray-700"
                onClick={() => {
                  onChange(v);
                  setIsOpen(false);
                }}
              >
                {v}
              </div>
            ))}
            {filteredValues.length === 0 && (
              <div className="px-4 py-8 text-center text-xs text-gray-400 uppercase font-bold tracking-widest">
                Sonuç bulunamadı
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchableAttribute;
