/**
 * Footer.jsx — Admin'in `/api/footer-template` üzerinden tam yönetebildiği footer.
 * İki mod desteklenir:
 *   • mode = "html"        → custom_html alanı doğrudan render edilir
 *   • mode = "structured"  → columns + newsletter + social + copyright alanlarından
 *                            otomatik render edilir
 */
import { Link } from "react-router-dom";
import { sanitizeHtml } from "../lib/sanitizeHtml";
import { useEffect, useState } from "react";
import axios from "axios";
import { Instagram, Facebook, Twitter, ChevronDown, ArrowRight, Check } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SERIF = { fontFamily: 'Georgia, "Times New Roman", "Playfair Display", serif' };

/**
 * NewsletterBand — footer'ın hemen üstünde "Facette Kulübü seni bekliyor" bandı.
 * Metinler admin footer ayarındaki `newsletter` alanından okunur.
 */
function NewsletterBand({ nl }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [msg, setMsg] = useState("");

  const title = nl?.title || "Facette Kulübü seni bekliyor";
  const description =
    nl?.description ||
    "Yeni koleksiyonlar, özel kampanyalar ve sana özel fırsatlardan ilk sen haberdar ol.";
  const placeholder = nl?.placeholder || "E-posta adresin";

  const submit = async (e) => {
    e.preventDefault();
    const v = (email || "").trim();
    if (!v || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
      setState("error");
      setMsg("Lütfen geçerli bir e-posta adresi girin.");
      return;
    }
    setState("loading");
    try {
      const r = await axios.post(`${API}/newsletter/subscribe`, { email: v, source: "footer" });
      setState("done");
      setMsg(r?.data?.message || "Aramıza hoş geldin!");
      setEmail("");
    } catch (err) {
      setState("error");
      setMsg(err?.response?.data?.detail || "Bir sorun oluştu, tekrar dene.");
    }
  };

  return (
    <section className="bg-neutral-100 border-t border-neutral-200" data-testid="newsletter-band">
      <div className="container-main py-14 md:py-20">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-[11px] tracking-[0.35em] uppercase text-neutral-400 mb-4">Facette Kulübü</p>
          <h3 className="text-3xl md:text-5xl font-light tracking-tight text-neutral-900 leading-tight" style={SERIF}>
            {title}
          </h3>
          <p className="text-sm md:text-base text-neutral-500 mt-4 leading-relaxed">{description}</p>

          {state === "done" ? (
            <div className="mt-8 inline-flex items-center gap-2 text-sm text-neutral-900" data-testid="newsletter-done">
              <span className="w-6 h-6 rounded-full bg-neutral-900 text-white flex items-center justify-center">
                <Check size={13} strokeWidth={2.5} />
              </span>
              {msg}
            </div>
          ) : (
            <form onSubmit={submit} className="mt-8 max-w-md mx-auto" data-testid="newsletter-form">
              <div className="flex items-stretch border-b border-neutral-400 focus-within:border-neutral-900 transition-colors">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); if (state === "error") setState("idle"); }}
                  placeholder={placeholder}
                  className="flex-1 bg-transparent px-1 py-3 text-sm text-neutral-900 placeholder-neutral-400 outline-none"
                  aria-label="E-posta adresi"
                  data-testid="newsletter-email"
                />
                <button
                  type="submit"
                  disabled={state === "loading"}
                  className="px-2 text-neutral-900 hover:opacity-60 disabled:opacity-40 transition-opacity"
                  aria-label="Abone ol"
                  data-testid="newsletter-submit"
                >
                  <ArrowRight size={20} strokeWidth={1.5} />
                </button>
              </div>
              {state === "error" && (
                <p className="text-xs text-red-500 mt-3 text-left" data-testid="newsletter-error">{msg}</p>
              )}
              <p className="text-[11px] text-neutral-400 mt-3 leading-relaxed">
                Abone olarak Facette'ten e-posta ile ticari ileti almayı kabul edersin. Dilediğin zaman
                aboneliğinden çıkabilirsin.
              </p>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}

const DEFAULT_COLUMNS = [
  { title: "Alışveriş", links: [
    { to: "/kategori/en-yeniler", label: "En Yeniler" },
    { to: "/kategori/elbise", label: "Elbise" },
    { to: "/kategori/pantolon", label: "Pantolon" },
    { to: "/kategori/ceket", label: "Ceket" },
    { to: "/kategori/aksesuar", label: "Aksesuar" },
  ]},
  { title: "Yardım", links: [
    { to: "/siparis-takip", label: "Sipariş Takibi" },
    { to: "/iade-islemleri", label: "İade İşlemleri" },
    { to: "/sayfa/iade-kosullari", label: "İade & Değişim" },
    { to: "/sikca-sorulan-sorular", label: "Sıkça Sorulan Sorular" },
    { to: "/sayfa/iletisim", label: "İletişim" },
  ]},
  { title: "Kurumsal", links: [
    { to: "/sayfa/hakkimizda", label: "Hakkımızda" },
    { to: "/sayfa/mesafeli-satis", label: "Mesafeli Satış Sözleşmesi" },
    { to: "/sayfa/on-bilgilendirme", label: "Ön Bilgilendirme" },
    { to: "/sayfa/kvkk", label: "KVKK Aydınlatma Metni" },
    { to: "/sayfa/gizlilik", label: "Gizlilik Politikası" },
  ]},
  { title: "İletişim", static: [
    "info@facette.com.tr", "+90 543 330 03 10", "Pazartesi-Cumartesi 09:00 - 18:00",
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

  const newsletter = tpl?.newsletter;

  // HTML mode — admin tam serbest HTML yazdı
  if (tpl?.mode === "html" && tpl?.custom_html) {
    return (
      <>
        <NewsletterBand nl={newsletter} />
        <footer className="bg-black text-white" data-testid="footer-html">
          <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(tpl.custom_html) }} />
        </footer>
      </>
    );
  }

  // Structured mode — admin sütunları/sosyal/copyright güncelledi
  let columns = tpl?.columns || DEFAULT_COLUMNS;
  // "İade İşlemleri" linki her zaman görünür olsun (admin sütunları override etse bile)
  try {
    const hasReturn = columns.some((c) => (c.links || []).some((l) => l.to === "/iade-islemleri"));
    if (!hasReturn) {
      columns = columns.map((c) => c.links ? c : c); // shallow copy tetikleyici
      const svc = columns.find((c) => /müşteri|hizmet|iade|customer/i.test(c.title || ""));
      if (svc && svc.links) {
        svc.links = [...svc.links, { to: "/iade-islemleri", label: "İade İşlemleri" }];
      } else {
        columns = [...columns, { title: "İade İşlemleri", links: [{ to: "/iade-islemleri", label: "İade İşlemleri" }] }];
      }
    }
  } catch (_) { /* yoksay */ }
  const social = tpl?.social || { instagram: "https://instagram.com/facette" };
  const copyright = tpl?.copyright || `© ${new Date().getFullYear()} Facette Dış. Tic. A.Ş. – Tüm hakları saklıdır.`;

  return (
    <>
    <NewsletterBand nl={newsletter} />
    <footer className="bg-black text-white" data-testid="footer-structured">
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
        <div className="grid md:grid-cols-4 gap-x-10 md:border-t md:border-white/10 md:pt-12">
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
    </>
  );
}
