/**
 * Miu Miu theme — full storefront home page (Phase 1).
 * - Sticky header with logo, mega menu (hover), account/search/wish/bag icons
 * - Full-screen scrollable blocks (hero, editorial cards)
 * - Product scroller (loads from /api/products?category=…)
 * - Newsletter
 * - Minimal footer
 *
 * Editable from /admin/temalar
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Link, useParams } from "react-router-dom";
import { Search, User, Heart, ShoppingBag, X, Menu, ChevronDown } from "lucide-react";
import "./miumiu.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MiuMiuTheme() {
  const { slug } = useParams();
  const [theme, setTheme] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mobileMenu, setMobileMenu] = useState(false);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const url = slug ? `${API}/storefront/themes/${slug}` : `${API}/storefront/themes/active`;
        const r = await axios.get(url);
        if (!cancel) setTheme(r.data);
      } catch (e) {
        if (!cancel) setTheme(null);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [slug]);

  if (loading) return <div className="mm-loading">Loading…</div>;
  if (!theme) return <div className="mm-loading">Tema bulunamadı.</div>;

  const blocks = theme.blocks || [];
  const announcement = blocks.find(b => b.type === "announcement_bar");
  const otherBlocks = blocks.filter(b => b.type !== "announcement_bar");
  const totalScreens = otherBlocks.filter(b => ["hero_fullscreen", "editorial_card"].includes(b.type)).length;

  return (
    <div className="mm-root">
      {announcement && (
        <div className="mm-announcement" style={{ background: announcement.settings?.bg || "#000", color: announcement.settings?.color || "#fff" }}>
          {announcement.title}
        </div>
      )}

      <Header theme={theme} onToggleMobile={() => setMobileMenu(v => !v)} mobileOpen={mobileMenu} />
      {mobileMenu && <MobileMenu theme={theme} onClose={() => setMobileMenu(false)} />}

      <main>
        {otherBlocks.map((b, idx) => (
          <BlockRenderer key={b.id} block={b} idx={idx} total={totalScreens} themeSlug={theme.slug} />
        ))}
      </main>

      <Footer theme={theme} />
    </div>
  );
}

/* ---------- Header ---------- */
function Header({ theme, onToggleMobile, mobileOpen }) {
  const menu = theme.menu || [];
  const brand = theme.settings?.brand_name || "miu miu";
  const [openIdx, setOpenIdx] = useState(null);

  return (
    <header className="mm-header" data-testid="storefront-header">
      <div className="mm-header-inner">
        <button className="mm-burger" onClick={onToggleMobile} aria-label="Menu" data-testid="btn-mobile-menu">
          {mobileOpen ? <X size={22}/> : <Menu size={22}/>}
        </button>
        <Link to={`/tema/${theme.slug}`} className="mm-logo" data-testid="brand-logo">{brand}</Link>
        <nav className="mm-nav">
          {menu.map((m, i) => (
            <div key={i} className="mm-nav-item" onMouseEnter={() => setOpenIdx(i)} onMouseLeave={() => setOpenIdx(null)}>
              <a href={m.url} className={`mm-nav-link${m.accent ? ' mm-accent' : ''}`}>{m.label}</a>
              {openIdx === i && (m.columns || []).length > 0 && (
                <div className="mm-megamenu">
                  {(m.columns || []).map((col, j) => (
                    <div key={j} className="mm-mega-col">
                      {col.title && <h4>{col.title}</h4>}
                      <ul>
                        {(col.links || []).map((l, k) => (
                          <li key={k}><a href={l.url}>{l.label}</a></li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
        <div className="mm-icons">
          <a href="/giris" aria-label="Account"><User size={18}/></a>
          <button aria-label="Search"><Search size={18}/></button>
          <a href="/hesabim" aria-label="Wishlist"><Heart size={18}/></a>
          <a href="/sepet" aria-label="Bag"><ShoppingBag size={18}/></a>
        </div>
      </div>
    </header>
  );
}

function MobileMenu({ theme, onClose }) {
  const menu = theme.menu || [];
  const [expanded, setExpanded] = useState(null);
  return (
    <div className="mm-mobile-menu" data-testid="mobile-menu">
      {menu.map((m, i) => (
        <div key={i} className="mm-mobile-item">
          <div className="mm-mobile-link" onClick={() => setExpanded(expanded === i ? null : i)}>
            <a href={m.url} className={m.accent ? 'mm-accent' : ''} onClick={onClose}>{m.label}</a>
            {(m.columns || []).length > 0 && <ChevronDown size={16} className={expanded === i ? 'rot' : ''}/>}
          </div>
          {expanded === i && (m.columns || []).length > 0 && (
            <div className="mm-mobile-sub">
              {(m.columns || []).map((col, j) => (
                <div key={j}>
                  {col.title && <h5>{col.title}</h5>}
                  {(col.links || []).map((l, k) => (
                    <a key={k} href={l.url} onClick={onClose}>{l.label}</a>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
      <div className="mm-mobile-foot">
        <a href="/giris" onClick={onClose}>Account</a>
        <a href="/hesabim" onClick={onClose}>Wishlist</a>
        <a href="/sepet" onClick={onClose}>Bag</a>
      </div>
    </div>
  );
}

/* ---------- Block Renderer ---------- */
function BlockRenderer({ block, idx, total, themeSlug }) {
  switch (block.type) {
    case "hero_fullscreen":
    case "editorial_card":
      return <FullScreenBlock block={block} idx={idx} total={total} />;
    case "product_scroller":
      return <ProductScroller block={block} themeSlug={themeSlug} />;
    case "newsletter":
      return <Newsletter block={block} />;
    case "text_section":
      return (
        <section className="mm-text">
          <h2>{block.title}</h2>
          {block.subtitle && <p>{block.subtitle}</p>}
        </section>
      );
    default:
      return null;
  }
}

function FullScreenBlock({ block, idx, total }) {
  const overlay = block.settings?.overlay ?? 0.3;
  const align = block.settings?.align || "center";
  const color = block.settings?.text_color || "#fff";
  return (
    <section className="mm-fs" data-testid={`block-${block.type}-${block.id}`}>
      <picture>
        {block.mobile_image && <source media="(max-width: 768px)" srcSet={block.mobile_image} />}
        <img src={block.image} alt={block.title || ""} loading={idx > 0 ? "lazy" : "eager"} />
      </picture>
      <div className="mm-fs-overlay" style={{ background: `rgba(0,0,0,${overlay})` }} />
      <div className={`mm-fs-content mm-fs-${align}`} style={{ color }}>
        <h2 className="mm-fs-title">{block.title}</h2>
        {block.subtitle && <p className="mm-fs-sub">{block.subtitle}</p>}
        {block.link_url && block.link_label && (
          <a href={block.link_url} className="mm-fs-cta" style={{ color, borderColor: color }}>{block.link_label}</a>
        )}
      </div>
      {total > 1 && (
        <div className="mm-counter" style={{ color }}>{idx + 1}<span>/{total}</span></div>
      )}
      {idx === 0 && (
        <div className="mm-scroll-hint" style={{ color }}>Scroll to explore<span className="mm-scroll-line"/></div>
      )}
    </section>
  );
}

function ProductScroller({ block, themeSlug }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const slug = block.settings?.category_slug;
        const limit = block.settings?.limit || 12;
        // Try category endpoint, fall back to generic products
        let r;
        if (slug) {
          try { r = await axios.get(`${API}/products`, { params: { category: slug, limit } }); }
          catch { r = await axios.get(`${API}/products`, { params: { limit } }); }
        } else {
          r = await axios.get(`${API}/products`, { params: { limit } });
        }
        const raw = Array.isArray(r.data) ? r.data : (r.data.items || r.data.products || []);
        if (!cancel) setItems(raw.slice(0, limit));
      } catch { if (!cancel) setError(true); }
    })();
    return () => { cancel = true; };
  }, [block.settings?.category_slug, block.settings?.limit]);

  // Fallback placeholder products if API empty/error
  const display = items.length > 0 ? items : (error || items.length === 0 ? PLACEHOLDER_PRODUCTS : []);

  return (
    <section className="mm-scroller" data-testid={`block-product-scroller-${block.id}`}>
      <div className="mm-scroller-head">
        <h2>{block.title}</h2>
        {block.link_url && block.link_label && <a href={block.link_url} className="mm-scroller-cta">{block.link_label}</a>}
      </div>
      <div className="mm-scroller-track">
        {display.map((p, i) => (
          <a key={p.id || p.slug || i} href={p.slug ? `/tema/${themeSlug}/urun/${p.slug}` : "#"} className="mm-product-card">
            <div className="mm-product-img">
              <img src={p.image || p.images?.[0] || p.thumbnail || PLACEHOLDER_IMG} alt={p.name || p.title || ""} loading="lazy" />
            </div>
            <div className="mm-product-name">{p.name || p.title || "Untitled"}</div>
          </a>
        ))}
      </div>
    </section>
  );
}

function Newsletter({ block }) {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const submit = (e) => { e.preventDefault(); if (email) setDone(true); };
  return (
    <section className="mm-newsletter" style={{ background: block.settings?.bg || "#000", color: block.settings?.color || "#fff" }} data-testid="block-newsletter">
      <h2>{block.title}</h2>
      {block.subtitle && <p>{block.subtitle}</p>}
      {done ? (
        <div className="mm-newsletter-done">Thanks for subscribing.</div>
      ) : (
        <form onSubmit={submit} className="mm-newsletter-form">
          <input type="email" required placeholder="Email address" value={email} onChange={e => setEmail(e.target.value)} aria-label="Email" data-testid="newsletter-email"/>
          <button type="submit" data-testid="newsletter-submit">{block.link_label || "Subscribe"}</button>
        </form>
      )}
    </section>
  );
}

/* ---------- Footer ---------- */
function Footer({ theme }) {
  return (
    <footer className="mm-footer" data-testid="storefront-footer">
      <div className="mm-footer-grid">
        <div>
          <h5>Customer Care</h5>
          <ul>
            <li><a href="/iletisim">Contact us</a></li>
            <li><a href="/sayfa/sss">FAQs</a></li>
            <li><a href="/siparis-takip">Track order</a></li>
            <li><a href="/sayfa/iade">Returns &amp; refunds</a></li>
          </ul>
        </div>
        <div>
          <h5>Company</h5>
          <ul>
            <li><a href="/sayfa/hakkimizda">About us</a></li>
            <li><a href="/sayfa/magazalar">Stores</a></li>
            <li><a href="/sayfa/kariyer">Careers</a></li>
            <li><a href="/sayfa/surdurulebilirlik">Sustainability</a></li>
          </ul>
        </div>
        <div>
          <h5>Legal</h5>
          <ul>
            <li><a href="/sayfa/kvkk">Privacy policy</a></li>
            <li><a href="/sayfa/cerez">Cookie policy</a></li>
            <li><a href="/sayfa/satis-sartlari">Terms of sale</a></li>
          </ul>
        </div>
        <div>
          <h5>Follow {theme.settings?.brand_name || "us"}</h5>
          <ul>
            <li><a href="#">Instagram</a></li>
            <li><a href="#">YouTube</a></li>
            <li><a href="#">TikTok</a></li>
            <li><a href="#">Pinterest</a></li>
          </ul>
        </div>
      </div>
      <div className="mm-footer-bot">
        <span>© {new Date().getFullYear()} {theme.settings?.brand_name || "Storefront"}. All rights reserved.</span>
        <span>Türkiye · TR</span>
      </div>
    </footer>
  );
}

const PLACEHOLDER_IMG = "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?auto=format&fit=crop&w=600&q=70";
const PLACEHOLDER_PRODUCTS = [
  { id: "p1", name: "Leather shoulder bag", image: "https://images.unsplash.com/photo-1584917865442-de89df76afd3?auto=format&fit=crop&w=600&q=70" },
  { id: "p2", name: "Poplin shirt", image: "https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=600&q=70" },
  { id: "p3", name: "Mini skirt", image: "https://images.unsplash.com/photo-1539109136881-3be0616acf4b?auto=format&fit=crop&w=600&q=70" },
  { id: "p4", name: "Sandals", image: "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=600&q=70" },
  { id: "p5", name: "Raffia hat", image: "https://images.unsplash.com/photo-1601925268684-09b1bf2c3e25?auto=format&fit=crop&w=600&q=70" },
  { id: "p6", name: "Cat-eye sunglasses", image: "https://images.unsplash.com/photo-1572635196237-14b3f281503f?auto=format&fit=crop&w=600&q=70" },
  { id: "p7", name: "Leather wallet", image: "https://images.unsplash.com/photo-1601924994987-69e26d50dc26?auto=format&fit=crop&w=600&q=70" },
  { id: "p8", name: "Tote bag", image: "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?auto=format&fit=crop&w=600&q=70" },
  { id: "p9", name: "Pleated dress", image: "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?auto=format&fit=crop&w=600&q=70" },
  { id: "p10", name: "Knit cardigan", image: "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=600&q=70" },
];
