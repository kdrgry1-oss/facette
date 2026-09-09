import { priceView, fmtTL } from '../lib/price';
import './fullLook.css';

export default function FullLookSections({ looks = [], interactive = true }) {
  return <div className="full-look-flow" data-testid="full-look-flow">
    {looks.map((look, index) => <section className="full-look-section" key={look.id} aria-label={look.title || `Kombin ${index + 1}`}>
      <div className="full-look-hero">
        {look.image ? <img src={look.image} alt={look.title || `Kombin ${index + 1}`} loading={index ? 'lazy' : 'eager'} />
          : <div className="full-look-placeholder">Soldaki kombin fotoğrafını seçin</div>}
        <span className="full-look-number">{String(index + 1).padStart(2, '0')}</span>
      </div>
      <div className="full-look-selection">
        <div className="full-look-caption"><span>GÖRÜNÜMÜ TAMAMLA</span>{look.title && <h2>{look.title}</h2>}</div>
        <div className="full-look-products">
          {(look.products || []).map(product => {
            const price = priceView(product);
            const content = <><div className="full-look-product-image">
              {product.images?.[0] ? <img src={product.images[0]} alt={product.name} loading="lazy" /> : <span>Görsel yok</span>}
            </div><h3>{product.name}</h3><p className="full-look-price">
              {price.hasDiscount && <del>{fmtTL(price.list)}</del>}<span>{fmtTL(price.display)}</span>
            </p></>;
            return interactive ? <a className="full-look-product" key={product.id} href={`/urun/${encodeURIComponent(product.slug || product.id)}`}>{content}</a>
              : <div className="full-look-product" key={product.id}>{content}</div>;
          })}
        </div>
        {!look.products?.length && <p className="full-look-empty-products">Bu görseldeki ürünleri sağ tarafa ekleyin.</p>}
      </div>
    </section>)}
  </div>;
}
