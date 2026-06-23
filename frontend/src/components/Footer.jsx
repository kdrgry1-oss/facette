/**
 * Footer.jsx — Admin'in `/api/footer-template` üzerinden tam yönetebildiği footer.
 * İki mod desteklenir:
 *   • mode = "html"        → custom_html alanı doğrudan render edilir
 *   • mode = "structured"  → columns + newsletter + social + copyright alanlarından
 *                            otomatik render edilir
 */
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import axios from "axios";
import { Instagram, Facebook, Twitter, ChevronDown } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DEFAULT_COLUMNS = [
  { title: "Alışveriş", links: [
    { to: "/en-yeniler", label: "En Yeniler" },
    { to: "/elbise", label: "Elbise" },
    { to: "/pantolon", label: "Pantolon" },
    { to: "/ceket", label: "Ceket" },
    { to: "/aksesuar", label: "Aksesuar" },
  ]},
  { title: "Müşteri Hizmetleri", links: [
    { to: "/siparis-takip", label: "Sipariş Takibi" },
    { to: "/sayfa/hakkimizda", label: "Hakkımızda" },
    { to: "/sayfa/iade-kosullari", label: "İade & Değişim" },
    { to: "/sayfa/kvkk", label: "KVKK" },
    { to: "/sayfa/gizlilik", label: "Gizlilik Politikası" },
    { to: "/sayfa/iletisim", label: "İletişim" },
  ]},
  { title: "İletişim", static: [
    "info@facette.com.tr", "+90 850 000 00 00", "Pazartesi-Cumartesi 09:00 - 18:00",
  ]},
];

function FooterColumn({ col, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-white/10 md:border-b-0">
      <button
        type="button"
        className="w-full flex items-center justify-between py-4 md:py-0 md:cursor-default md:pointer-events-none"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        data-testid={`footer-col-toggle-${col.title}`}
      >
        <h4 className="text-[10px] tracking-[0.3em] uppercase text-white">{col.title}</h4>
        <ChevronDown size={14} className={`md:hidden transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
      </button>
      <ul
        className={`grid transition-all duration-300 ease-out overflow-hidden md:!grid-rows-[1fr] md:!opacity-100 md:mt-5 ${
          open ? "grid-rows-[1fr] opacity-100 pb-4" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <li className="min-h-0">
          <ul className="space-y-3">
            {col.links?.map((l) => (
              <li key={l.to}>
                <Link to={l.to} className="text-xs text-white/55 hover:text-white transition-colors duration-300">
                  {l.label}
                </Link>
              </li>
            ))}
            {col.static?.map((s, i) => (
              <li key={i} className="text-xs text-white/55">{s}</li>
            ))}
          </ul>
        </li>
      </ul>
    </div>
  );
}

export default function Footer() {
  const [tpl, setTpl] = useState(null);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/footer-template`)
      .then((r) => { if (!cancel) setTpl(r.data); })
      .catch(() => { if (!cancel) setTpl(null); });
    return () => { cancel = true; };
  }, []);

  // HTML mode — admin tam serbest HTML yazdı
  if (tpl?.mode === "html" && tpl?.custom_html) {
    return (
      <footer className="bg-black text-white mt-16 md:mt-24" data-testid="footer-html">
        <div dangerouslySetInnerHTML={{ __html: tpl.custom_html }} />
      </footer>
    );
  }

  // Structured mode — admin sütunları/sosyal/copyright güncelledi
  const columns = tpl?.columns || DEFAULT_COLUMNS;
  const social = tpl?.social || { instagram: "https://instagram.com/facette" };
  const copyright = tpl?.copyright || `© ${new Date().getFullYear()} Facette Dış. Tic. A.Ş. – Tüm hakları saklıdır.`;

  return (
    <footer className="bg-black text-white mt-16 md:mt-24" data-testid="footer-structured">
      {/* #FACETTE X YOU — premium imza bandı (footer kolonlarının hemen üstünde) */}
      <div className="border-b border-white/10">
        <div className="container-main py-12 md:py-16 text-center">
          <p className="text-[10px] md:text-[11px] tracking-[0.42em] uppercase text-white/45 mb-3.5">Stilini Paylaş</p>
          <h3 className="text-2xl md:text-[2.6rem] leading-none font-extralight tracking-[0.22em]">
            #FACETTE <span className="text-white/35 mx-1">×</span> YOU
          </h3>
          <p className="mt-4 text-xs md:text-sm font-light text-white/55 max-w-md mx-auto leading-relaxed">
            Tarzını <span className="text-white/80">@facette</span> etiketiyle paylaş, koleksiyonun bir parçası ol.
          </p>
        </div>
      </div>

      <div className="container-main pt-14 md:pt-20 pb-8">
        {/* Brand strip */}
        <div className="md:flex md:items-end md:justify-between mb-12 md:mb-16">
          <div className="max-w-md">
            <Link to="/" className="inline-block mb-5">
              <span className="text-2xl tracking-[0.45em] font-light">FACETTE</span>
            </Link>
            <p className="text-sm text-white/60 leading-relaxed">
              Farkı hisset. Kadın modasında yeni koleksiyon, zamansız parçalar.
            </p>
          </div>
          <div className="flex gap-5 mt-8 md:mt-0">
            {social.instagram && (
              <a href={social.instagram} target="_blank" rel="noreferrer noopener" className="text-white/70 hover:text-white transition-colors" aria-label="Instagram">
                <Instagram size={18} strokeWidth={1.4} />
              </a>
            )}
            {social.facebook && (
              <a href={social.facebook} target="_blank" rel="noreferrer noopener" className="text-white/70 hover:text-white transition-colors" aria-label="Facebook">
                <Facebook size={18} strokeWidth={1.4} />
              </a>
            )}
            {social.twitter && (
              <a href={social.twitter} target="_blank" rel="noreferrer noopener" className="text-white/70 hover:text-white transition-colors" aria-label="Twitter">
                <Twitter size={18} strokeWidth={1.4} />
              </a>
            )}
          </div>
        </div>

        {/* Columns */}
        <div className="grid md:grid-cols-3 gap-x-12 md:border-t md:border-white/10 md:pt-12">
          {columns.map((col, i) => (
            <FooterColumn key={col.title || i} col={col} defaultOpen={i === 0} />
          ))}
        </div>

        {/* Bottom */}
        <div className="border-t border-white/10 mt-12 pt-8 flex flex-col-reverse md:flex-row justify-between items-center gap-6">
          <p className="text-[10px] tracking-[0.2em] uppercase text-white/40">{copyright}</p>
          <div className="flex items-center gap-3 opacity-60">
            <img src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" alt="Visa" className="h-5 invert" />
            <img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" alt="Mastercard" className="h-5" />
          </div>
        </div>
      </div>
    </footer>
  );
}
