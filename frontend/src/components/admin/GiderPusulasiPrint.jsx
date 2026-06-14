// Paylaşılan Gider Pusulası A4 yazdırma bileşeni.
// Returns.jsx (Trendyol) tarafındaki kanıtlanmış 4-kopya matbu yazdırma mantığının
// birebir kopyasıdır; site iadeleri (SiteReturns.jsx) de aynı çıktıyı/numara serisini kullanır.
import { createPortal } from "react-dom";

// Gider pusulası takip numarası: 6 haneli, başında sıfırla (085490)
export function pad6(n) {
  const v = parseInt(String(n).replace(/\D/g, ""), 10);
  return isNaN(v) ? "" : String(v).padStart(6, "0");
}

// Tutarı sadece tamsayı kısmını TR yazıya çevirir (kuruşsuz): 1862 -> "Binsekizyüzaltmışiki"
export function sayiToWords(num) {
  num = Math.abs(Math.floor(Number(num) || 0));
  if (num === 0) return "Sıfır";
  const birler = ["", "Bir", "İki", "Üç", "Dört", "Beş", "Altı", "Yedi", "Sekiz", "Dokuz"];
  const onlar = ["", "On", "Yirmi", "Otuz", "Kırk", "Elli", "Altmış", "Yetmiş", "Seksen", "Doksan"];
  const basamak = ["", "Bin", "Milyon", "Milyar", "Trilyon"];
  const uclu = (n) => {
    let s = "";
    const y = Math.floor(n / 100), o = Math.floor((n % 100) / 10), b = n % 10;
    if (y > 0) s += (y === 1 ? "" : birler[y]) + "Yüz";
    if (o > 0) s += onlar[o];
    if (b > 0) s += birler[b];
    return s;
  };
  const parts = [];
  let i = 0;
  while (num > 0) {
    const grp = num % 1000;
    if (grp > 0) {
      let g = uclu(grp);
      if (i === 1 && grp === 1) g = ""; // "Bin", "BirBin" değil
      parts.unshift(g + basamak[i]);
    }
    num = Math.floor(num / 1000);
    i++;
  }
  const joined = parts.join("");
  return joined.charAt(0) + joined.slice(1).toLocaleLowerCase("tr-TR");
}

export function fmt2(v) {
  return new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v || 0);
}

// A4 yatay: sayfada aynı pusula 4 kopya (4 sütun), her sütun 74.25mm
export const GP_COPIES = 4;            // bir A4 yatay sayfada aynı pusula 4 kopya (4 sütun)
export const GP_SLIP_W_MM = 74.25;     // sütun genişliği (297mm / 4)
export const GP_SLIP_H_MM = 210;       // sütun yüksekliği (A4 yatay)
export const GP_PAGE_W_MM = 297;       // A4 yatay genişlik
export const GP_PAGE_H_MM = 210;       // A4 yatay yükseklik

// Tek matbu form (sütun): 74.25mm x 210mm. overlay=true -> yalnız işaretli alan verisi basılır
// (matbu için). overlay=false -> gri referans form + siyah veri (boş kağıt / hizalama testi).
export function GiderPusulasiSlip({ data, overlay, offX = 0, offY = 0, guides = false }) {
  if (!data) return null;
  const c = data.customer || {};
  const tot = data.totals || {};
  const items = data.items || [];
  const dt = data.date ? new Date(data.date) : null;
  const dateStr = dt ? dt.toLocaleDateString("tr-TR") : "";
  const timeStr = dt ? dt.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  const neg = (v) => -Math.abs(v || 0);
  const net = tot.net || 0;
  const matrah = tot.net_without_vat || 0;
  const kdv = tot.vat_amount || 0;
  const indirim = tot.discount || 0;
  const words = sayiToWords(Math.round(net));
  const cityLine = [c.district, c.city, c.country || "Türkiye"].filter(Boolean).join("/");

  const wrap = {
    position: "relative", width: GP_SLIP_W_MM + "mm", height: GP_SLIP_H_MM + "mm",
    boxSizing: "border-box", overflow: "hidden", fontFamily: "Arial, sans-serif",
    color: "#000", background: "#fff", borderRight: guides ? "0.3mm dashed #c084fc" : "none",
  };

  // --- GRİ REFERANS (yalnız overlay kapalıyken / önizlemede; KAĞIDA BASILMAZ) ---
  const G = "#9aa0a6";
  const Gt = (x, y, s, txt, extra = {}) => (
    <div style={{ position: "absolute", left: x + "mm", top: y + "mm", fontSize: s + "mm", color: G, whiteSpace: "nowrap", ...extra }}>{txt}</div>
  );
  const reference = !overlay && (
    <div style={{ position: "absolute", inset: 0 }}>
      {Gt(5, 4, 1.7, "No: 3  34307 Küçükçekmece/İST.")}
      {Gt(5, 7.5, 1.7, "Halkalı V.D.: 781 081 6779")}
      {Gt(5, 11, 1.7, "Ticaret Sicil No: 203113-5")}
      {Gt(5, 14.5, 1.7, "iletisim@facette.com.tr")}
      <div style={{ position: "absolute", left: "52mm", top: "4mm", width: "13mm", height: "13mm", border: "0.3mm solid " + G, borderRadius: "50%", textAlign: "center", fontSize: "1.4mm", color: G, lineHeight: "13mm" }}>T.C.</div>
      {Gt(48, 27, 1.9, "İL KODU: 34", { fontWeight: 700 })}
      {Gt(52, 34, 2.0, "SERİ A", { fontWeight: 700 })}
      {Gt(5, 188, 1.6, "Yalnız _______________________")}
      {Gt(5, 193, 1.5, "____ den yukarıda belirtilen Mal/İş")}
      {Gt(5, 196.5, 1.5, "bedelini aldım.")}
      {Gt(5, 202, 1.6, "Adı Soyadı ________________")}
      {Gt(5, 206, 1.6, "Adresi ___________   İMZA")}
      <div style={{ position: "absolute", left: "2.4mm", top: "150mm", transform: "rotate(-90deg)", transformOrigin: "left top", fontSize: "1.7mm", color: "#cc2222" }}>SIRA NO   No {data.assigned_no || ""}</div>
    </div>
  );

  // --- SİYAH VERİ: sıkışık akışkan blok (KAĞIDA BASILAN TEK ALAN) ---
  const row = (label, val, bold) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "2mm", fontWeight: bold ? 700 : 400 }}>
      <span>{label}</span><span>{val}</span>
    </div>
  );
  const black = (
    <div style={{ position: "absolute", left: "6mm", top: "41mm", width: "63mm", transform: `translate(${offX}mm, ${offY}mm)`, fontSize: "2.0mm", lineHeight: 1.12, color: "#000" }}>
      <div style={{ fontWeight: 700 }}>{c.name || ""}</div>
      <div style={{ height: "2.4mm" }} />
      {c.address ? <div>{c.address}</div> : null}
      <div>{cityLine}</div>
      <div style={{ height: "1.2mm" }} />
      <div>Sipariş: {data.order_number || ""}</div>
      <div>{dateStr}{timeStr ? "  " + timeStr : ""}</div>
      <div style={{ height: "0.8mm" }} />
      <div>Satış Fatura No: {data.sales_invoice_no || "-"}</div>
      <div>Kargo Firma: {data.cargo_company || "-"}</div>
      <div>Satış Sorumlusu: {data.sales_rep || "-"}</div>
      <div style={{ height: "1mm" }} />
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "1.9mm" }}>
        <thead>
          <tr style={{ borderBottom: "0.2mm solid #999" }}>
            <th style={{ textAlign: "left", fontWeight: 700, padding: "0.2mm 0" }}>Açıklama</th>
            <th style={{ textAlign: "right", fontWeight: 700, width: "8mm" }}>Ad.</th>
            <th style={{ textAlign: "right", fontWeight: 700, width: "17mm" }}>Tutar</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i}>
              <td style={{ padding: "0.3mm 0", wordBreak: "break-word" }}>{it.name || ""}{it.size ? ` — Beden: ${it.size}` : ""}</td>
              <td style={{ textAlign: "right" }}>{it.quantity}</td>
              <td style={{ textAlign: "right" }}>{fmt2(neg(it.net_price))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ height: "1.2mm" }} />
      {row("Tutar (V.D.)", fmt2(net), true)}
      {row("Toplam Satır İsk (VD)", fmt2(indirim))}
      {row("Toplam Dip İsk (/D)", fmt2(0))}
      {row("Vergi Matrahı", fmt2(matrah))}
      {row("Kdv", fmt2(kdv))}
      {row("Net Tutar", fmt2(net), true)}
      <div style={{ height: "0.8mm" }} />
      <div>Yalnız: {words} TL</div>
    </div>
  );

  return <div style={wrap}>{reference}{black}</div>;
}

// A4 YATAY: her iade = 1 sayfa, aynı pusula 4 kopya (4 sütun). Ekranda gizli, yazdırmada görünür.
export function GpPrintLayer({ slips, overlay, offX, offY, guides }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="gp-print">
      <style>{`
        .gp-print { display: none; }
        @media print {
          @page { size: A4 landscape; margin: 0; }
          html, body { margin: 0 !important; padding: 0 !important; background: #fff !important; }
          /* Yazdırmada SADECE gider pusulası katmanı; admin arayüzü/başlık/kenar çubuğu/modal gizlenir */
          body > *:not(.gp-print) { display: none !important; }
          .gp-print { display: block !important; background: #fff; }
          .gp-page { width: ${GP_PAGE_W_MM}mm; height: ${GP_PAGE_H_MM}mm; display: flex; flex-direction: row; page-break-after: always; overflow: hidden; background: #fff; }
          .gp-page:last-child { page-break-after: auto; }
          .gp-col { width: ${GP_SLIP_W_MM}mm; height: ${GP_SLIP_H_MM}mm; }
        }
      `}</style>
      {(slips || []).map((gp, pi) => (
        <div className="gp-page" key={pi}>
          {Array.from({ length: GP_COPIES }).map((_, ci) => (
            <div className="gp-col" key={ci}>
              <GiderPusulasiSlip data={gp} overlay={overlay} offX={offX} offY={offY} guides={guides} />
            </div>
          ))}
        </div>
      ))}
    </div>,
    document.body
  );
}
