/**
 * SearchableMapSelect.jsx
 *
 * Pazaryeri eşleştirme ekranlarında "ID yazmak" yerine kullanılır:
 * kullanıcı arama kutusuna yazar, backend'den (options endpoint'inden) gelen
 * öneriler dropdown'da gösterilir; tıklayınca `id + name` döner.
 *
 * Props:
 *   - optionsUrl:  "/brand-mapping/trendyol/options" gibi — q parametresi
 *                  eklenerek backend'e istek atılır
 *   - value:       { id, name }
 *   - onChange:    (val) => void
 *   - placeholder: giriş kutusu placeholder
 *   - hint:        alttaki yardım mesajı
 *   - "data-testid"
 */
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { Search, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

export default function SearchableMapSelect({
  optionsUrl,
  value,
  onChange,
  placeholder = "Ara...",
  hint = "",
  ...rest
}) {
  const [q, setQ] = useState(value?.name || "");
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [noCache, setNoCache] = useState(false);
  const wrapRef = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    setQ(value?.name || "");
  }, [value?.name]);

  const fetchOpts = async (query) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}${optionsUrl}?q=${encodeURIComponent(query || "")}&limit=50`, auth());
      setOptions(r.data?.items || []);
      setNoCache(!!r.data?.hint && (r.data?.items || []).length === 0);
    } catch {
      setOptions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    function handle(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  const onInput = (v) => {
    setQ(v);
    setOpen(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => fetchOpts(v), 200);
  };

  const pick = (opt) => {
    onChange?.({ id: String(opt.id ?? ""), name: opt.full_path || opt.name });
    setQ(opt.full_path || opt.name);
    setOpen(false);
  };

  const clear = () => {
    onChange?.({ id: "", name: "" });
    setQ("");
    setOpen(false);
  };

  return (
    <div className="relative w-full" ref={wrapRef}>
      <div className="flex items-center gap-1">
        <div className="relative flex-1">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onFocus={() => { setOpen(true); if (!options.length) fetchOpts(""); }}
            onChange={(e) => onInput(e.target.value)}
            placeholder={placeholder}
            className="w-full border border-gray-200 rounded-lg pl-7 pr-7 py-1.5 text-sm bg-white"
            data-testid={rest["data-testid"] || "searchable-input"}
          />
          {q && (
            <button type="button" onClick={clear}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-black">
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {loading ? (
            <div className="px-3 py-3 text-xs text-gray-400">Yükleniyor...</div>
          ) : options.length === 0 ? (
            <div className="px-3 py-3 text-xs text-gray-400">
              {noCache
                ? "Bu pazaryeri için henüz önbellek yok — manuel ID/ad girebilirsiniz."
                : "Sonuç yok"}
            </div>
          ) : (
            options.map((o, i) => (
              <button
                key={`${o.id}-${i}`}
                type="button"
                onClick={() => pick(o)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-orange-50 border-b last:border-b-0 border-gray-100"
                data-testid={`map-option-${i}`}
              >
                <div className="font-medium text-gray-900">{o.full_path || o.name}</div>
                <div className="text-[10px] text-gray-400 font-mono">ID: {o.id}</div>
              </button>
            ))
          )}
        </div>
      )}
      {hint && !open && <p className="text-[11px] text-gray-400 mt-1">{hint}</p>}
      {value?.id && !open && (
        <p className="text-[10px] text-gray-500 mt-0.5 font-mono">Seçili ID: {value.id}</p>
      )}
    </div>
  );
}
