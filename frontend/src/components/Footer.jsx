import { Link } from "react-router-dom";
import { useState } from "react";
import { Instagram, Facebook, Twitter, ChevronDown } from "lucide-react";

const COLUMNS = [
  {
    title: "Alışveriş",
    links: [
      { to: "/kategori/en-yeniler", label: "En Yeniler" },
      { to: "/kategori/elbise", label: "Elbise" },
      { to: "/kategori/pantolon", label: "Pantolon" },
      { to: "/kategori/ceket", label: "Ceket" },
      { to: "/kategori/aksesuar", label: "Aksesuar" },
    ],
  },
  {
    title: "Müşteri Hizmetleri",
    links: [
      { to: "/siparis-takip", label: "Sipariş Takibi" },
      { to: "/sayfa/hakkimizda", label: "Hakkımızda" },
      { to: "/sayfa/iade-kosullari", label: "İade & Değişim" },
      { to: "/sayfa/kvkk", label: "KVKK" },
      { to: "/sayfa/gizlilik", label: "Gizlilik Politikası" },
      { to: "/sayfa/iletisim", label: "İletişim" },
    ],
  },
  {
    title: "İletişim",
    static: [
      "info@facette.com.tr",
      "+90 212 000 00 00",
      "Pazartesi – Cumartesi",
      "10:00 – 18:00",
    ],
  },
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
        <h4 className="text-[10px] tracking-[0.3em] uppercase text-white">
          {col.title}
        </h4>
        <ChevronDown
          size={14}
          className={`md:hidden transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
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
                <Link
                  to={l.to}
                  className="text-xs text-white/55 hover:text-white transition-colors duration-300"
                >
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
  return (
    <footer className="bg-black text-white mt-16 md:mt-24">
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
            <a href="https://instagram.com/facette" target="_blank" rel="noreferrer noopener"
               className="text-white/70 hover:text-white transition-colors" aria-label="Instagram">
              <Instagram size={18} strokeWidth={1.4} />
            </a>
            <a href="https://facebook.com/facette" target="_blank" rel="noreferrer noopener"
               className="text-white/70 hover:text-white transition-colors" aria-label="Facebook">
              <Facebook size={18} strokeWidth={1.4} />
            </a>
            <a href="https://twitter.com/facette" target="_blank" rel="noreferrer noopener"
               className="text-white/70 hover:text-white transition-colors" aria-label="Twitter">
              <Twitter size={18} strokeWidth={1.4} />
            </a>
          </div>
        </div>

        {/* Columns */}
        <div className="grid md:grid-cols-3 gap-x-12 md:border-t md:border-white/10 md:pt-12">
          {COLUMNS.map((col, i) => (
            <FooterColumn key={col.title} col={col} defaultOpen={i === 0} />
          ))}
        </div>

        {/* Bottom */}
        <div className="border-t border-white/10 mt-12 pt-8 flex flex-col-reverse md:flex-row justify-between items-center gap-6">
          <p className="text-[10px] tracking-[0.2em] uppercase text-white/40">
            © {new Date().getFullYear()} Facette Dış. Tic. A.Ş. – Tüm hakları saklıdır.
          </p>
          <div className="flex items-center gap-3 opacity-60">
            <img src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" alt="Visa" className="h-5 invert" />
            <img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" alt="Mastercard" className="h-5" />
          </div>
        </div>
      </div>
    </footer>
  );
}
