import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Play, ArrowRight, Instagram } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { optimizeImg, aspectFromDims } from "../lib/img";
import { trackSelectPromotion } from "../lib/dataLayer";
import { dedupeColorGroups } from "../lib/colorGroups";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Default/Fallback content
const DEFAULT_HERO_BANNERS = [
  { id: 1, image: "https://cdn.facette.com.tr/pagedesign/en-yeniler-dc2e-1920.webp", link: "/en-yeniler" },
  { id: 2, image: "https://cdn.facette.com.tr/pagedesign/ae79c961-ba0b-49e3-b274-2c6cc78ab700-1920.webp", link: "/sale" }
];

const DEFAULT_INSTASHOP = [
  { id: 1, image: "https://cdn.facette.com.tr/pagedesign/orj-ce09fd5d-c580-40eb-87f2-e4637265bad9-1920.webp", link: "/basic-atki" },
  { id: 2, image: "https://cdn.facette.com.tr/pagedesign/orj-114d3d37-9c7f-495c-8bc2-28d32781818d-1920.webp", link: "/ceket" },
  { id: 3, image: "https://cdn.facette.com.tr/pagedesign/orj-e18eff06-8597-4f10-92cb-64b11151a74d-1920.webp", link: "/kaban" },
  { id: 4, image: "https://cdn.facette.com.tr/pagedesign/orj-fa071a71-bcaf-452b-90d5-e8cb0c352fe0-1920.webp", link: "/pantolon" },
  { id: 5, image: "https://cdn.facette.com.tr/pagedesign/orj-87d15ba0-0081-4b65-acc5-b12328de368b-1920.webp", link: "/elbise" }
];

// Bir slayt görsel mi video mu — uzantıdan belirlenir (aynı images[] dizisi ikisini de taşır).
const isVideoUrl = (u) => typeof u === "string" && /\.(mp4|webm|mov|m4v|ogg)(\?|$)/i.test(u);

// Block Components
function HeroSlider({ block }) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const images = block?.images?.length > 0 ? block.images : DEFAULT_HERO_BANNERS.map(b => b.image);
  const links = block?.links || DEFAULT_HERO_BANNERS.map(b => b.link);
  const videoRefs = useRef({});

  useEffect(() => {
    if (images.length > 1) {
      const interval = setInterval(() => {
        setCurrentSlide((prev) => (prev + 1) % images.length);
      }, 6000);
      return () => clearInterval(interval);
    }
  }, [images.length]);

  // PERFORMANS: yalnızca AKTİF slaytın videosu oynatılır; diğerleri duraklatılır.
  // Böylece birden çok video aynı anda decode edilip sistemi/anasayfayı yormaz.
  useEffect(() => {
    Object.entries(videoRefs.current).forEach(([i, v]) => {
      if (!v) return;
      if (Number(i) === currentSlide) { const p = v.play?.(); if (p?.catch) p.catch(() => {}); }
      else { try { v.pause?.(); } catch (_) { /* noop */ } }
    });
  }, [currentSlide, images.length]);

  const nextSlide = () => setCurrentSlide((prev) => (prev + 1) % images.length);
  const prevSlide = () => setCurrentSlide((prev) => (prev - 1 + images.length) % images.length);

  // Görselin gerçek en-boy oranı: admin panelinde kaydedilmiş img_dims varsa onu
  // kullan; yoksa tarayıcıda <img> yüklenince gerçek pikseli oku (loadedDims) —
  // hangi ölçüde görsel yüklendiyse container o orana göre şekillenir, kırpma olmaz.
  const [loadedDims, setLoadedDims] = useState({}); // { [index]: [w, h] }
  const handleImgLoad = (index) => (e) => {
    const { naturalWidth: w, naturalHeight: h } = e.target;
    if (w && h) {
      setLoadedDims((prev) => (prev[index] ? prev : { ...prev, [index]: [w, h] }));
    }
  };

  const savedDims = block?.settings?.img_dims;
  const dimsFor = (index) => (savedDims && savedDims[index]) || loadedDims[index] || null;
  const fallbackDims = (block?.settings?.img_width ? [block.settings.img_width, block.settings.img_height] : null);
  const activeDims = dimsFor(currentSlide) || fallbackDims;
  const aspect = aspectFromDims(activeDims, "16 / 9");

  return (
    <section className="relative" data-testid="hero-slider">
      <div className="relative overflow-hidden w-full bg-stone-100 transition-[aspect-ratio] duration-300" style={{ aspectRatio: aspect }}>
        {images.map((img, index) => (
          <Link
            key={index}
            to={links[index] || "/"}
            onClick={() => {
              try {
                trackSelectPromotion({
                  promotionId: `hero_${index + 1}`,
                  promotionName: block?.title || links[index] || `Hero ${index + 1}`,
                });
              } catch (_) { /* silent */ }
            }}
            className={`absolute inset-0 block transition-opacity duration-700 ${index === currentSlide ? "opacity-100 z-10" : "opacity-0"}`}
          >
            {isVideoUrl(img) ? (
              <video
                ref={(el) => { videoRefs.current[index] = el; }}
                src={img}
                className="w-full h-full object-cover block"
                muted
                loop
                playsInline
                autoPlay={index === 0}
                // İlk slayt hazır olsun; diğer videolar yalnızca sıraları gelince yüklenir (bant genişliği + hız).
                preload={index === 0 ? "auto" : "none"}
                width={dimsFor(index)?.[0]}
                height={dimsFor(index)?.[1]}
                onLoadedMetadata={(e) => {
                  const w = e.target.videoWidth, h = e.target.videoHeight;
                  if (w && h) setLoadedDims((prev) => (prev[index] ? prev : { ...prev, [index]: [w, h] }));
                }}
              />
            ) : (
              <img
                src={optimizeImg(img, 1920, 78)}
                alt={block?.title || ""}
                className="w-full h-full object-cover block"
                fetchPriority={index === 0 ? "high" : "auto"}
                loading={index === 0 ? "eager" : "lazy"}
                decoding="async"
                width={dimsFor(index)?.[0]}
                height={dimsFor(index)?.[1]}
                onLoad={handleImgLoad(index)}
              />
            )}
          </Link>
        ))}
      </div>
      {images.length > 1 && (
        <>
          <button onClick={prevSlide} className="absolute left-4 top-1/2 -translate-y-1/2 z-20 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronLeft size={20} />
          </button>
          <button onClick={nextSlide} className="absolute right-4 top-1/2 -translate-y-1/2 z-20 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronRight size={20} />
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex gap-2">
            {images.map((_, i) => (
              <button key={i} onClick={() => setCurrentSlide(i)} className={`w-2 h-2 rounded-full ${i === currentSlide ? 'bg-black' : 'bg-white/70'}`} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

// Dikey Editorial Akış (Zara/OYSHO mobil stili) — her slayt TAM EKRAN (100svh), NORMAL akışta
// alt alta. OTOMATİK KAYMA YOK: parmakla/scroll ile bir sonraki slayta geçilir; son slayttan
// sonra sayfa (ürünler) doğal olarak devam eder. Video slaytlar yalnızca EKRANDAYKEN oynar
// (IntersectionObserver, performans). İlk slaytta ince "aşağı kaydır" ipucu.
// Tek slaytın medyası + yazısı (hem tekli hem sticky slider için ortak).
function HeroSlide({ img, cap, title, vidRef, eager }) {
  return (
    <>
      {isVideoUrl(img) ? (
        <video
          ref={vidRef}
          src={img}
          className="absolute inset-0 w-full h-full object-cover"
          muted loop playsInline
          preload={eager ? "auto" : "none"}
        />
      ) : (
        <img
          src={optimizeImg(img, 1920, 80)}
          alt={cap.title || title || ""}
          className="absolute inset-0 w-full h-full object-cover"
          loading={eager ? "eager" : "lazy"}
          fetchPriority={eager ? "high" : "auto"}
          decoding="async"
        />
      )}
      {/* Yazılar YALNIZCA admin girmişse çıkar (görselde zaten yazı varsa çift olmaz). */}
      {(cap.eyebrow || cap.title || cap.cta) && (
        <>
          <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(0,0,0,.42), rgba(0,0,0,0) 45%)" }} />
          <div className="absolute left-5 md:left-10 bottom-16 md:bottom-24 z-10 text-white max-w-[82%]">
            {cap.eyebrow ? <div className="text-[11px] tracking-[0.32em] uppercase opacity-90 mb-2">{cap.eyebrow}</div> : null}
            {cap.title ? <div className="text-3xl md:text-5xl font-light tracking-wide leading-tight">{cap.title}</div> : null}
            {cap.cta ? <div className="mt-3 text-[11px] tracking-[0.24em] uppercase inline-block border-b border-white/70 pb-1">{cap.cta}</div> : null}
          </div>
        </>
      )}
    </>
  );
}

/**
 * HeroEditorial — Zara Home tarzı DİKEY TAM-EKRAN slider (fullpage / jest tabanlı).
 * Yalnızca 1. slayt görünür; 2/3/4 ekran DIŞINDA gizli. TEK bir kaydırma/swipe = TEK slayt
 * (parmağı takip etmez, uzun kaydırma beklemez). Slaytlar arasında SAYFA KAYMAZ → scrollY 0'da
 * kalır → header tüm slider boyunca ŞEFFAF/BEYAZ (logo+ikonlar slider üzerine biner). Son slayttan
 * sonra bir kaydırma daha yapınca hero serbest kalır ve sayfa normal aşağı iner.
 */
function HeroEditorial({ block, isFirst = false }) {
  const images = block?.images?.length > 0 ? block.images : DEFAULT_HERO_BANNERS.map(b => b.image);
  const links = block?.links || DEFAULT_HERO_BANNERS.map(b => b.link);
  const captions = block?.settings?.captions || [];
  const n = images.length;
  const vids = useRef({});
  const sectionRef = useRef(null);
  const [active, setActive] = useState(0);
  const activeRef = useRef(0);
  const lockRef = useRef(false);
  const touchStart = useRef(null);
  const safeActive = Math.min(active, Math.max(0, n - 1));
  useEffect(() => { activeRef.current = safeActive; }, [safeActive]);

  // Header overlay: hero ekranı kapladığı sürece "1" (şeffaf/beyaz header). Slaytlar arası sayfa
  // kaymadığından bu, tüm slider boyunca açık kalır; hero yukarı kayıp çıkınca "0" olur.
  useEffect(() => {
    if (!isFirst) return;
    const compute = () => {
      const el = sectionRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      // Sticky header/duyuru barı hero'yu birkaç px aşağı itebilir → r.top tam 0 olmayabilir.
      // "Hero ekranın çoğunu kaplıyor mu" diye bak (üst ofsete toleranslı).
      const covering = r.top < vh * 0.5 && r.bottom > vh * 0.5;
      document.documentElement.setAttribute("data-hero-overlay", covering ? "1" : "0");
    };
    compute();
    window.addEventListener("scroll", compute, { passive: true });
    window.addEventListener("resize", compute);
    return () => {
      window.removeEventListener("scroll", compute);
      window.removeEventListener("resize", compute);
      document.documentElement.removeAttribute("data-hero-overlay");
    };
  }, [isFirst, n]);

  // Jest yakalama: hero ekranı tam kapladığında ve sınır slaytta değilken tek kaydırma = tek slayt.
  useEffect(() => {
    if (n <= 1) return;
    const el = sectionRef.current;
    if (!el) return;

    const covering = () => {
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      // Header/duyuru barı ofsetine toleranslı: hero ekranın çoğunu kaplıyorsa jest aktif.
      return r.top < vh * 0.4 && r.bottom > vh * 0.5;
    };
    // dir +1 = sonraki slayt (yukarı kaydır), -1 = önceki (aşağı kaydır)
    const canHijack = (dir) => {
      if (!covering()) return false;
      const a = activeRef.current;
      if (dir > 0 && a >= n - 1) return false; // son slayttan sonra → sayfa aksın
      if (dir < 0 && a <= 0) return false;      // ilk slayttan önce → sayfa aksın
      return true;
    };
    const go = (dir) => {
      if (lockRef.current) return;
      if (!canHijack(dir)) return;
      lockRef.current = true;
      setActive((cur) => Math.min(n - 1, Math.max(0, cur + dir)));
      setTimeout(() => { lockRef.current = false; }, 620);
    };

    const onWheel = (e) => {
      const dir = e.deltaY > 0 ? 1 : -1;
      if (!canHijack(dir)) return;   // sınırda → tarayıcı normal kaydırsın
      e.preventDefault();            // hero içindeyken sayfayı kaydırma, slayt değiştir
      go(dir);
    };
    const onTouchStart = (e) => { touchStart.current = e.touches[0].clientY; };
    const onTouchMove = (e) => {
      if (touchStart.current == null) return;
      const dy = touchStart.current - e.touches[0].clientY; // + yukarı
      const dir = dy > 0 ? 1 : -1;
      if (Math.abs(dy) > 6 && canHijack(dir)) e.preventDefault(); // sayfa kaymasın
    };
    const onTouchEnd = (e) => {
      if (touchStart.current == null) return;
      const endY = (e.changedTouches && e.changedTouches[0] ? e.changedTouches[0].clientY : touchStart.current);
      const dy = touchStart.current - endY;
      touchStart.current = null;
      if (Math.abs(dy) < 30) return;          // küçük dokunuş → yok say
      go(dy > 0 ? 1 : -1);                     // tek swipe = tek slayt
    };

    window.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [n]);

  // Video: yalnızca aktif slayt oynar
  useEffect(() => {
    Object.entries(vids.current).forEach(([i, v]) => {
      if (!v) return;
      if (Number(i) === safeActive) { const p = v.play?.(); if (p?.catch) p.catch(() => {}); }
      else { try { v.pause?.(); } catch (_) { /* noop */ } }
    });
  }, [safeActive, n]);

  return (
    <section
      ref={sectionRef}
      data-testid="hero-editorial"
      className="relative w-full overflow-hidden bg-stone-100"
      // İlk hero: üstteki siyah duyuru barıyla arasında beyaz boşluk/çizgi kalmasın diye yukarı çek.
      style={{ height: "100vh", marginTop: isFirst ? "-2px" : 0 }}
    >
      {images.map((img, i) => {
        const cap = captions[i] || {};
        const offset = (i - safeActive) * 100;                 // dikey kayma: aktif 0, diğerleri ekran dışı
        const isActive = i === safeActive;
        return (
          <div
            key={i}
            className="absolute inset-0 will-change-transform"
            style={{
              transform: `translateY(${offset}%)`,
              transition: "transform .62s cubic-bezier(0.22,1,0.36,1)",
              zIndex: isActive ? 2 : 1,
            }}
            aria-hidden={!isActive}
          >
            <Link
              to={links[i] || "/"}
              onClick={() => { try { trackSelectPromotion({ promotionId: `hero_${i + 1}`, promotionName: cap.title || links[i] || `Hero ${i + 1}` }); } catch (_) { /* silent */ } }}
              className="block w-full h-full"
              tabIndex={isActive ? 0 : -1}
            >
              <HeroSlide img={img} cap={cap} title={block?.title} vidRef={(el) => { vids.current[i] = el; }} eager={i === 0} />
            </Link>
          </div>
        );
      })}

      {/* Sağ dikey ilerleme göstergesi (tıklanabilir) */}
      {n > 1 && (
        <div className="absolute right-4 md:right-6 top-1/2 -translate-y-1/2 z-20 flex flex-col gap-2">
          {images.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Slayt ${i + 1}`}
              onClick={() => { if (!lockRef.current) { lockRef.current = true; setActive(i); setTimeout(() => { lockRef.current = false; }, 620); } }}
              className={`w-[3px] rounded-full transition-all duration-300 ${i === safeActive ? "h-7 bg-white" : "h-2 bg-white/45 hover:bg-white/70"}`}
            />
          ))}
        </div>
      )}
    </section>
  );
}

// Görseli YÜKLENDİĞİ en-boy oranında, KIRPMADAN gösterir. Container oranı = görsel oranı
// olduğundan object-cover kırpmaz (tam oturur). Kayıtlı boyut (dims) varsa onu kullanır;
// yoksa görsel yüklenince gerçek pikselinden okur → hangi boyutta yüklersen o oranda görünür.
function NaturalImg({ src, dims, alt = "", w = 1920, fallback = "16 / 9", imgClass = "" }) {
  const [d, setD] = useState(dims && dims.length === 2 ? dims : null);
  const aspect = aspectFromDims(d, fallback);
  return (
    <div className="w-full bg-stone-100" style={{ aspectRatio: aspect }}>
      <img
        src={optimizeImg(src, w)}
        alt={alt}
        className={`w-full h-full object-cover block ${imgClass}`}
        loading="lazy"
        decoding="async"
        onLoad={(e) => {
          const nw = e.target.naturalWidth, nh = e.target.naturalHeight;
          if (!d && nw && nh) setD([nw, nh]);
        }}
      />
    </div>
  );
}

function FullBanner({ block }) {
  if (!block?.images?.[0]) return null;
  return (
    <Link to={block.links?.[0] || "/"} className="block w-full" data-testid="full-banner">
      <NaturalImg src={block.images[0]} dims={block?.settings?.img_dims?.[0]} alt={block.title || ""} w={1920} fallback="16 / 6" />
    </Link>
  );
}

function HalfBanners({ block }) {
  if (!block?.images || block.images.length < 2) return null;
  // Her görsel KENDİ yüklendiği oranda, kırpılmadan gösterilir. Farklı oranlar olabileceğinden
  // sütunlar üstten hizalanır (items-start). Admin block.settings.aspect verirse o zorlanır.
  const forced = block?.settings?.aspect || null;
  return (
    <div className="grid grid-cols-2 items-start" data-testid="half-banners">
      {block.images.slice(0, 2).map((img, index) => (
        <Link key={index} to={block.links?.[index] || "/"} className="block overflow-hidden">
          {forced ? (
            <div className="w-full bg-stone-100" style={{ aspectRatio: forced }}>
              <img src={optimizeImg(img, 1000)} alt="" className="w-full h-full object-cover block" loading="lazy" decoding="async" />
            </div>
          ) : (
            <NaturalImg src={img} dims={block?.settings?.img_dims?.[index]} w={1000} fallback="4 / 5" />
          )}
        </Link>
      ))}
    </div>
  );
}

function ProductSlider({ block, products }) {
  const selectedIds = block?.settings?.product_ids;
  const source = block?.settings?.source || (selectedIds?.length > 0 ? "manual" : "newest");
  const limit = block?.settings?.limit || 8;
  const [feed, setFeed] = useState(null); // kaynak bazlı çekilen ürünler

  // Favoriler / indirim / kategori kaynakları ana sayfa listesinde olmayabilir —
  // backend slider-feed ucundan kendi verisini çeker. manual/newest eski davranış.
  useEffect(() => {
    if (source === "manual" || source === "newest") { setFeed(null); return; }
    let alive = true;
    const cids = (block?.settings?.category_ids || []).join(",");
    axios
      .get(`${API}/products/slider-feed?source=${source}&limit=${limit}${cids ? `&category_ids=${encodeURIComponent(cids)}` : ""}`)
      .then((r) => { if (alive) setFeed(r.data?.products || []); })
      .catch(() => { if (alive) setFeed([]); });
    return () => { alive = false; };
  }, [source, limit, JSON.stringify(block?.settings?.category_ids || [])]);

  // TÜM hook'lar erken return'den ÖNCE çağrılmalı (React kuralı — #310).
  const scrollRef = useRef(null);

  let displayProducts;
  if (source !== "manual" && source !== "newest") {
    displayProducts = feed || [];
  } else if (selectedIds && selectedIds.length > 0) {
    // Show only the selected products in the configured order
    displayProducts = selectedIds
      .map(id => products?.find(p => p._id === id || p.id === id))
      .filter(Boolean);
  } else {
    displayProducts = dedupeColorGroups(products?.slice(0, limit * 2) || [])
      .slice(0, limit);
  }

  if (displayProducts.length === 0) return null;

  const defaultCtaLink = source === "discounted" ? "/sale" : "/en-yeniler";
  const title = block?.title;
  const subtitle = block?.settings?.subtitle;
  const ctaLabel = block?.settings?.cta_label || "Tümünü Gör";
  const ctaHref = block?.settings?.cta_link || defaultCtaLink;
  // Kaç satır alt alta (yatay kayan slider içinde 1–3)
  const rows = Math.max(1, Math.min(Number(block?.settings?.rows) || 1, 3));
  const serif = { fontFamily: 'Georgia, "Times New Roman", "Playfair Display", serif' };
  const scrollByDir = (dir) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * Math.round(el.clientWidth * 0.85), behavior: "smooth" });
  };

  return (
    <section className="w-full py-10 md:py-14" data-testid="product-slider">
      {/* Başlık bloğu — girildiyse: sol büyük serif başlık + alt yazı, sağda "Tümünü Gör →"
          (2. görsel tarzı). Standalone alt "Tümünü Gör" butonu kaldırıldı. */}
      {(title || subtitle) && (
        <div className="max-w-screen-2xl mx-auto px-4 md:px-6 mb-6 md:mb-9 flex items-end justify-between gap-4">
          <div className="min-w-0">
            {title && <h2 className="text-3xl md:text-5xl font-light tracking-tight text-black leading-none" style={serif}>{title}</h2>}
            {subtitle && <p className="mt-3 text-sm md:text-[15px] text-gray-500 font-light max-w-md leading-relaxed">{subtitle}</p>}
          </div>
          <Link to={ctaHref} className="shrink-0 inline-flex items-center gap-1.5 md:gap-2 text-[10px] md:text-[11px] tracking-[0.18em] md:tracking-[0.24em] uppercase text-gray-600 hover:text-black border-b border-gray-300 hover:border-black pb-1 md:pb-1.5 transition-colors whitespace-nowrap">
            {ctaLabel} <ArrowRight size={13} />
          </Link>
        </div>
      )}

      {/* Yatay kayan ürün slider'ı — N satır. Kartlar yan yana, kaydırılır (mobilde peek).
          Masaüstünde sol/sağ oklarla da kaydırılır (ana slider gibi). */}
      <div className="relative">
        <div ref={scrollRef} className="overflow-x-auto scrollbar-hide snap-x px-4 md:px-6 scroll-smooth">
          <div
            className="grid grid-flow-col auto-cols-[46%] sm:auto-cols-[31%] md:auto-cols-[23%] lg:auto-cols-[19%] gap-x-2 gap-y-6"
            style={{ gridTemplateRows: `repeat(${rows}, auto)` }}
          >
            {displayProducts.map((product) => (
              <div key={product.id} className="snap-start">
                <ProductCard product={product} />
              </div>
            ))}
          </div>
        </div>

        {/* Oklar — yalnızca masaüstü (mobilde parmakla kaydırma yeterli). */}
        {displayProducts.length > 1 && (
          <>
            <button
              type="button"
              onClick={() => scrollByDir(-1)}
              aria-label="Önceki ürünler"
              className="hidden md:flex absolute left-2 top-1/2 -translate-y-1/2 z-20 w-11 h-11 rounded-full bg-white/95 shadow-md ring-1 ring-black/5 items-center justify-center text-black hover:bg-black hover:text-white transition-colors"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              type="button"
              onClick={() => scrollByDir(1)}
              aria-label="Sonraki ürünler"
              className="hidden md:flex absolute right-2 top-1/2 -translate-y-1/2 z-20 w-11 h-11 rounded-full bg-white/95 shadow-md ring-1 ring-black/5 items-center justify-center text-black hover:bg-black hover:text-white transition-colors"
            >
              <ChevronRight size={20} />
            </button>
          </>
        )}
      </div>

    </section>
  );
}

function InstaShop({ block }) {
  // Gerçek @facette akışı: backend /instagram/feed (token'la çekilen ya da elle eklenen
  // gönderiler). Boşsa bloktaki elle görsellere / varsayılana düşer.
  const [feed, setFeed] = useState(null);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/instagram/feed?limit=12`)
      .then((r) => { if (alive) setFeed(r.data?.posts || []); })
      .catch(() => { if (alive) setFeed([]); });
    return () => { alive = false; };
  }, []);

  const blockImages = block?.images?.length > 0 ? block.images : DEFAULT_INSTASHOP.map(i => i.image);
  const blockLinks = block?.links?.length > 0 ? block.links : DEFAULT_INSTASHOP.map(i => i.link);

  // feed doluysa gerçek gönderiler; değilse blok görselleri.
  const usingFeed = Array.isArray(feed) && feed.length > 0;
  const items = usingFeed
    ? feed.slice(0, 6).map((p) => ({
        img: p.image,
        href: p.product_link || p.permalink || "#",
        external: !p.product_link && !!p.permalink,
      }))
    : blockImages.slice(0, 6).map((img, i) => ({ img, href: blockLinks[i] || "/", external: false }));

  if (!usingFeed && (feed === null)) {
    // İlk yükleme — flash olmasın diye başlığı gösterip grid'i boş bırakmak yerine blok
    // görselleriyle devam eder (feed null iken items zaten blockImages'e düşüyor).
  }

  return (
    <section className="py-14 md:py-20 bg-gray-50" data-testid="instashop">
      <div className="max-w-screen-2xl mx-auto px-4">
        {/* #FACETTE × YOU — premium imza başlığı */}
        <div className="text-center mb-8 md:mb-10">
          <p className="text-[10px] md:text-[11px] tracking-[0.42em] uppercase text-gray-400 mb-3">Stilini Paylaş</p>
          <h2 className="text-2xl md:text-[2.4rem] leading-none font-extralight tracking-[0.22em] text-black">
            #FACETTE <span className="text-gray-300 mx-1">×</span> YOU
          </h2>
          <p className="mt-3.5 text-xs md:text-sm font-light text-gray-500 max-w-md mx-auto leading-relaxed">
            Tarzını <a href="https://instagram.com/facette" target="_blank" rel="noopener noreferrer" className="text-black hover:underline">@facette</a> etiketiyle paylaş, koleksiyonun bir parçası ol.
          </p>
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-1">
          {items.map((it, index) => {
            const inner = (
              <>
                <img src={optimizeImg(it.img, 600)} alt="" className="w-full aspect-square object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy" decoding="async" />
                <span className="absolute inset-0 bg-black/0 group-hover:bg-black/15 transition-colors flex items-center justify-center">
                  <Instagram size={22} className="text-white opacity-0 group-hover:opacity-100 transition-opacity" strokeWidth={1.5} />
                </span>
              </>
            );
            return it.external ? (
              <a key={index} href={it.href} target="_blank" rel="noopener noreferrer" className="relative block overflow-hidden group">
                {inner}
              </a>
            ) : (
              <Link key={index} to={it.href} className="relative block overflow-hidden group">
                {inner}
              </Link>
            );
          })}
        </div>
        <div className="text-center mt-8">
          <a href="https://instagram.com/facette" target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-[11px] tracking-[0.24em] uppercase text-gray-600 hover:text-black border-b border-gray-300 hover:border-black pb-1.5 transition-colors">
            <Instagram size={14} /> @facette
          </a>
        </div>
      </div>
    </section>
  );
}

function TextBlock({ block }) {
  const img = block?.images?.[0];
  if (!block?.title && !block?.settings?.text && !img) return null;

  return (
    <section className="py-16 text-center" data-testid="text-block">
      <div className="max-w-2xl mx-auto px-4">
        {img && (
          block.links?.[0] ? (
            <Link to={block.links[0]} className="block mb-8">
              <img src={optimizeImg(img, 1200)} alt={block.title || ""} className="w-full object-cover" loading="lazy" decoding="async" />
            </Link>
          ) : (
            <img src={optimizeImg(img, 1200)} alt={block.title || ""} className="w-full object-cover mb-8" loading="lazy" decoding="async" />
          )
        )}
        {block.title && (
          <h2 className="text-2xl md:text-3xl font-light tracking-wide mb-4">{block.title}</h2>
        )}
        {block.settings?.text && (
          <p className="text-gray-600">{block.settings.text}</p>
        )}
        {block.links?.[0] && (
          <Link to={block.links[0]} className="inline-block mt-6 border border-black px-8 py-2 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
            Keşfet
          </Link>
        )}
      </div>
    </section>
  );
}

function VideoBanner({ block }) {
  const [playing, setPlaying] = useState(false);
  
  if (!block?.settings?.video_url && !block?.images?.[0]) return null;

  return (
    <section className="relative" data-testid="video-banner">
      {block.settings?.video_url ? (
        <div className="relative aspect-video bg-black">
          {playing ? (
            <video 
              src={block.settings.video_url} 
              autoPlay 
              loop 
              muted 
              playsInline
              className="w-full h-full object-cover"
            />
          ) : (
            <>
              <img 
                src={block.images?.[0] || ""} 
                alt={block.title || ""} 
                className="w-full h-full object-cover"
              />
              <button 
                onClick={() => setPlaying(true)}
                className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/30 transition-colors"
              >
                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                  <Play size={24} className="ml-1" />
                </div>
              </button>
            </>
          )}
        </div>
      ) : (
        <Link to={block.links?.[0] || "/"} className="block">
          <img src={optimizeImg(block.images[0], 1920)} alt={block.title || ""} className="w-full h-auto" loading="lazy" decoding="async" />
        </Link>
      )}
    </section>
  );
}

function RotatingText({ block }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const texts = (block?.settings?.texts || ["500 TL Üzeri Ücretsiz Kargo"]).filter((t) => (t || "").trim());

  useEffect(() => {
    if (texts.length < 2) return;
    const sec = Math.max(2, Number(block?.settings?.interval) || 4);
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % texts.length);
    }, sec * 1000);
    return () => clearInterval(interval);
  }, [texts.length, block]);

  if (texts.length === 0) return null;
  const bg = block?.settings?.bg_color || "#ffffff";
  const fg = block?.settings?.text_color || "#374151";

  return (
    <div
      className="text-center py-1"
      style={{ backgroundColor: bg }}
      data-testid="rotating-text"
    >
      <span
        key={currentIndex}
        className="text-[9px] md:text-[10px] tracking-[0.3em] uppercase font-light"
        style={{ color: fg }}
      >
        {texts[currentIndex % texts.length]}
      </span>
    </div>
  );
}

// İlk yükleme skeleton'u — page-blocks fetch tamamlanana kadar gösterilir.
// Böylece hardcoded DEFAULT_HERO_BANNERS (eski görseller) bir an flash etmez.
function HomeSkeleton() {
  return (
    <div data-testid="home-skeleton">
      <div className="w-full aspect-[16/7] bg-stone-100 animate-pulse" />
      <section className="w-full px-2 md:px-4 py-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-[2px] gap-y-3 md:gap-y-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="aspect-[2/3] bg-stone-100 mb-3" />
              <div className="h-3 bg-stone-100 w-3/4 mb-2" />
              <div className="h-3 bg-stone-100 w-1/3" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// Block Renderer
function BlockRenderer({ block, products, index }) {
  let component = null;
  switch (block.type) {
    case "hero_slider": {
      // İlk hero bloğu, AKSİ (klasik) belirtilmedikçe otomatik fullpage/editorial olur —
      // böylece "Dikey Editorial" seçilmese de mobilde tek-swipe slider + şeffaf header çalışır.
      const _style = block?.settings?.hero_style;
      const _useEditorial = _style === "dikey" || (index === 0 && _style !== "klasik");
      component = _useEditorial
        ? <HeroEditorial block={block} isFirst={index === 0} />
        : <HeroSlider block={block} />;
      break;
    }
    case "full_banner":   component = <FullBanner block={block} />; break;
    case "half_banners":  component = <HalfBanners block={block} />; break;
    case "product_slider":component = <ProductSlider block={block} products={products} />; break;
    case "instashop":     component = <InstaShop block={block} />; break;
    case "text_block":    component = <TextBlock block={block} />; break;
    case "video_banner":  component = <VideoBanner block={block} />; break;
    case "rotating_text": component = <RotatingText block={block} />; break;
    case "countdown_bar": return null; // Header'da render ediliyor — burada gösterme
    default: return null;
  }
  // Cihaz görünürlüğü — show_desktop / show_mobile false ise tailwind ile gizle
  const showDesktop = block.show_desktop !== false;
  const showMobile  = block.show_mobile  !== false;
  if (!showDesktop && !showMobile) return null;
  let visClass = "";
  if (!showDesktop) visClass = "md:hidden";       // sadece mobil
  else if (!showMobile) visClass = "hidden md:block"; // sadece masaüstü
  return visClass ? <div className={visClass}>{component}</div> : component;
}

export default function Home() {
  const [products, setProducts] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [productsRes, blocksRes] = await Promise.all([
          axios.get(`${API}/products?limit=100&sort=created_at&order=desc`),
          axios.get(`${API}/page-blocks?page=home`).catch(() => ({ data: [] }))
        ]);
        if (!active) return;
        setProducts(productsRes.data?.products || []);

        const isPreview = new URLSearchParams(window.location.search).get('preview') === 'true';
        // Sort blocks by sort_order and filter active ones (non-mutating)
        const activeBlocks = (blocksRes.data || [])
          .filter(b => isPreview || b.is_active)
          .toSorted((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
        setBlocks(activeBlocks);
      } catch (err) {
        console.error(err);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  // Check if we have CMS blocks to render
  const hasCMSBlocks = blocks.length > 0;
  
  // Check if specific block types exist
  const hasHeroSlider = blocks.some(b => b.type === "hero_slider");
  const hasProductSlider = blocks.some(b => b.type === "product_slider");
  const hasInstaShop = blocks.some(b => b.type === "instashop");

  // Üst duyuru barı (rotating_text) — orijinaldeki gibi en üstte (header üstü) gösterilir,
  // blok akışında tekrar render edilmemesi için ayrılır.
  const rotatingBlock = blocks.find(b => b.type === "rotating_text");
  const flowBlocks = blocks.filter(b => b.type !== "rotating_text");

  // İLK blok TAM EKRAN editorial hero mu? Öyleyse header şeffaf-overlay (beyaz logo/ikon) olur.
  // <html data-hero-overlay="1"> bayrağını Header okur; sayfadan ayrılınca temizlenir.
  const firstIsEditorialHero = flowBlocks[0]?.type === "hero_slider"
    && flowBlocks[0]?.settings?.hero_style !== "klasik"
    && (flowBlocks[0]?.show_mobile !== false || flowBlocks[0]?.show_desktop !== false);
  useEffect(() => {
    // Editorial hero VARSA bayrağı hemen "1" yap → header ANINDA fixed/şeffaf olur, akıştan çıkar,
    // hero en üste (y=0) oturur; böylece deadlock kırılır (sticky header hero'yu aşağı itmez).
    // Sonrasında değeri HeroEditorial kapsama alanına göre "1"/"0" günceller.
    if (firstIsEditorialHero) document.documentElement.setAttribute("data-hero-overlay", "1");
    else document.documentElement.removeAttribute("data-hero-overlay");
    return () => document.documentElement.removeAttribute("data-hero-overlay");
  }, [firstIsEditorialHero]);

  return (
    <div className="min-h-screen bg-white" data-testid="home-page">
      {rotatingBlock && <RotatingText block={rotatingBlock} />}
      <Header />
      
      {/* İlk yüklemede eski görsellerin (hardcoded default) flash etmemesi için
          page-blocks fetch tamamlanana kadar skeleton göster. */}
      {loading ? (
        <HomeSkeleton />
      ) : hasCMSBlocks ? (
        <>
          {flowBlocks.map((block, idx) => (
            <BlockRenderer key={block.id} block={block} products={products} index={idx} />
          ))}
          
          {/* Add default product grid if no product_slider block */}
          {!hasProductSlider && products.length > 0 && (
            <section className="w-full px-2 md:px-4 py-10">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-[2px] gap-y-3 md:gap-y-4">
                {dedupeColorGroups(products).slice(0, 8).map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
              <div className="text-center mt-12">
                <Link to="/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
                  Kategoriye Git
                </Link>
              </div>
            </section>
          )}
          
          {/* Add default InstaShop if no instashop block */}
          {!hasInstaShop && (
            <InstaShop block={{}} />
          )}
        </>
      ) : (
        /* Default Layout when no CMS blocks */
        <>
          {/* Hero Slider */}
          <HeroSlider block={{ images: DEFAULT_HERO_BANNERS.map(b => b.image), links: DEFAULT_HERO_BANNERS.map(b => b.link) }} />

          {/* Full Width Banner */}
          <Link to="/en-yeniler" className="block">
            <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-cb23757c-6-1920.webp", 1920)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
          </Link>

          {/* Two Half-Width Banners */}
          <div className="grid grid-cols-2">
            <Link to="/gomlek" className="block">
              <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-65777bd3-0-1920.webp", 1000)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
            </Link>
            <Link to="/aksesuar" className="block">
              <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-7b3e27f9-5-1920.webp", 1000)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
            </Link>
          </div>

          {/* Products Grid */}
          <section className="w-full px-2 md:px-4 py-10">
            {loading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 gap-y-8">
                {[...Array(8)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-[2/3] bg-gray-100 mb-3" />
                    <div className="h-4 bg-gray-100 w-3/4 mb-2" />
                    <div className="h-4 bg-gray-100 w-1/3" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-[2px] gap-y-3 md:gap-y-4">
                {dedupeColorGroups(products).map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            )}
            <div className="text-center mt-12">
              <Link to="/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
                Kategoriye Git
              </Link>
            </div>
          </section>

          {/* InstaShop */}
          <InstaShop block={{}} />
        </>
      )}

      <Footer />
    </div>
  );
}
