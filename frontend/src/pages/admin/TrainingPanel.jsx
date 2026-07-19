/**
 * Eğitim / Yardım paneli — sistemdeki tüm özellikler için "Ne / Nerede / Nasıl"
 * rehberi. İçerik lib/trainingContent.js'ten gelir; aranabilir ve kategori bazlıdır.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  GraduationCap, Search, ChevronRight, MapPin, ExternalLink, Lightbulb,
  LayoutDashboard, ShoppingCart, Package, TrendingUp, Factory, PenTool,
  Users, Megaphone, FileText, Cable, Settings,
} from "lucide-react";
import { TRAINING, trainingSearchIndex } from "../../lib/trainingContent";

const ICONS = {
  LayoutDashboard, ShoppingCart, Package, TrendingUp, Factory, PenTool,
  Users, Megaphone, FileText, Cable, Settings,
};

export default function TrainingPanel() {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(TRAINING[0]?.key || "");
  const index = useMemo(() => trainingSearchIndex(), []);

  const query = q.trim().toLocaleLowerCase("tr");
  const searchResults = useMemo(() => {
    if (!query) return null;
    return index.filter((r) => r.hay.includes(query));
  }, [query, index]);

  const activeSection = TRAINING.find((s) => s.key === active) || TRAINING[0];

  const Card = ({ it, sectionTitle }) => (
    <div className="bg-white border rounded-xl p-4 mb-3">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold text-gray-900">{it.title}</h3>
        {it.path && (
          <Link to={it.path}
            className="shrink-0 inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 border border-blue-100 rounded-lg px-2 py-1">
            Aç <ExternalLink size={12} />
          </Link>
        )}
      </div>
      {sectionTitle && <div className="text-[11px] uppercase tracking-wide text-gray-400 mt-0.5">{sectionTitle}</div>}
      <p className="text-sm text-gray-700 mt-2">{it.what}</p>
      {it.where && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 mt-2">
          <MapPin size={13} className="text-gray-400" /> <span><b>Nerede:</b> {it.where}</span>
        </div>
      )}
      {Array.isArray(it.how) && it.how.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-semibold text-gray-600 mb-1">Nasıl yapılır</div>
          <ol className="list-decimal list-inside space-y-0.5 text-sm text-gray-700">
            {it.how.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
        </div>
      )}
      {Array.isArray(it.tips) && it.tips.length > 0 && (
        <div className="mt-2 space-y-1">
          {it.tips.map((tip, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1.5">
              <Lightbulb size={13} className="text-amber-500 mt-0.5 shrink-0" /> <span>{tip}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-5" data-testid="training-panel-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><GraduationCap /> Eğitim & Yardım</h1>
        <p className="text-sm text-gray-500 mt-1">
          Sistemdeki her özellik için <b>ne işe yarar</b>, <b>nerede bulunur</b> ve <b>nasıl yapılır</b>.
          Aramak istediğini yaz veya soldan bir bölüm seç.
        </p>
      </div>

      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Özellik ara… (ör. iade, fatura, kupon, koleksiyon, satış hızı)"
          className="w-full border rounded-xl pl-9 pr-3 py-2.5 text-sm"
        />
      </div>

      {searchResults ? (
        <div>
          <div className="text-xs text-gray-500 mb-2">{searchResults.length} sonuç</div>
          {searchResults.length === 0 && (
            <div className="text-sm text-gray-400 bg-white border rounded-xl p-6 text-center">
              Sonuç yok. Farklı bir kelime deneyin.
            </div>
          )}
          {searchResults.map((r, i) => <Card key={i} it={r.item} sectionTitle={r.sectionTitle} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          {/* Kategori listesi */}
          <aside className="lg:col-span-1">
            <div className="bg-white border rounded-xl p-2 sticky top-4">
              {TRAINING.map((s) => {
                const Icon = ICONS[s.icon] || FileText;
                const isActive = s.key === active;
                return (
                  <button
                    key={s.key}
                    onClick={() => setActive(s.key)}
                    className={`w-full flex items-center gap-2 text-left px-3 py-2 rounded-lg text-sm mb-0.5 ${
                      isActive ? "bg-blue-50 text-blue-700 font-semibold" : "text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <Icon size={16} className={isActive ? "text-blue-600" : "text-gray-400"} />
                    <span className="flex-1">{s.title}</span>
                    <span className="text-[10px] text-gray-400">{s.items.length}</span>
                    {isActive && <ChevronRight size={14} />}
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Aktif bölüm içeriği */}
          <section className="lg:col-span-3">
            <div className="bg-gradient-to-r from-blue-50 to-white border border-blue-100 rounded-xl p-4 mb-4">
              <h2 className="font-bold text-gray-900">{activeSection.title}</h2>
              <p className="text-sm text-gray-600 mt-0.5">{activeSection.intro}</p>
            </div>
            {activeSection.items.map((it, i) => <Card key={i} it={it} />)}
          </section>
        </div>
      )}
    </div>
  );
}
