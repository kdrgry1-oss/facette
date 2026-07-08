import { useState } from "react";
import { Copy, Check, Building2 } from "lucide-react";
import { toast } from "sonner";

/**
 * BankTransferInfo — Havale/EFT ile ödenecek siparişlerde müşteriye gösterilen
 * KOPYALANABİLİR banka hesap bilgileri kartı.
 *
 * Her satırın yanında kopyala butonu var; ayrıca "Tümünü Kopyala" ile IBAN + alıcı +
 * sipariş numarası (açıklama) tek seferde panoya alınır. Sipariş numarası havale
 * açıklamasına yazılması için vurgulanır.
 *
 * Props: orderNumber (string), amount (number|string)
 */

// Facette resmî hesap bilgileri
const BANK = {
  holder: "FACETTE DIŞ TİCARET A.Ş.",
  bank: "Türkiye İş Bankası",
  currency: "TRY",
  branch: "ESENYURT",
  branchCode: "1454",
  iban: "TR86 0006 4000 0011 4540 1414 67",
  ibanRaw: "TR860006400000114540141467",
};

function CopyRow({ label, value, mono = false, strong = false }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(`${label} kopyalandı`);
      setTimeout(() => setCopied(false), 1600);
    } catch (_) {
      toast.error("Kopyalanamadı");
    }
  };
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-gray-100 last:border-0">
      <div className="min-w-0">
        <p className="text-[10px] tracking-[0.15em] text-gray-500 uppercase">{label}</p>
        <p className={`text-black break-all ${mono ? "font-mono" : ""} ${strong ? "text-base font-medium tracking-wide" : "text-sm"}`}>
          {value}
        </p>
      </div>
      <button
        type="button"
        onClick={copy}
        aria-label={`${label} kopyala`}
        className="flex-shrink-0 w-9 h-9 border border-gray-300 flex items-center justify-center hover:bg-black hover:text-white hover:border-black transition-colors"
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
      </button>
    </div>
  );
}

export default function BankTransferInfo({ orderNumber, amount }) {
  const [copiedAll, setCopiedAll] = useState(false);

  const amountText =
    amount != null && amount !== "" ? `${Number(amount).toFixed(2)} TL` : "";

  const copyAll = async () => {
    const lines = [
      `Alıcı: ${BANK.holder}`,
      `Banka: ${BANK.bank} (${BANK.currency})`,
      `Şube: ${BANK.branch} - Şube Kodu: ${BANK.branchCode}`,
      `IBAN: ${BANK.ibanRaw}`,
      orderNumber ? `Açıklama: ${orderNumber}` : "",
      amountText ? `Tutar: ${amountText}` : "",
    ].filter(Boolean);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopiedAll(true);
      toast.success("Tüm bilgiler kopyalandı");
      setTimeout(() => setCopiedAll(false), 1800);
    } catch (_) {
      toast.error("Kopyalanamadı");
    }
  };

  return (
    <div className="border border-black/80 mb-12" data-testid="bank-transfer-info">
      <div className="bg-black text-white px-5 sm:px-8 py-4 flex items-center gap-2.5">
        <Building2 size={18} strokeWidth={1.6} />
        <div>
          <p className="text-sm font-medium tracking-wide">Havale / EFT ile Ödeme</p>
          <p className="text-[11px] text-white/70">
            Ödemenizi aşağıdaki hesaba yapın; havale onaylanınca siparişiniz hazırlanır.
          </p>
        </div>
      </div>

      <div className="px-5 sm:px-8 py-4">
        <CopyRow label="Alıcı" value={BANK.holder} />
        <CopyRow label="Banka" value={`${BANK.bank} · ${BANK.currency} · ${BANK.branch} Şube (${BANK.branchCode})`} />
        <CopyRow label="IBAN" value={BANK.iban} mono strong />
        {orderNumber && (
          <CopyRow label="Açıklama (sipariş no)" value={orderNumber} mono />
        )}
        {amountText && <CopyRow label="Tutar" value={amountText} strong />}

        <button
          type="button"
          onClick={copyAll}
          className="mt-4 w-full h-11 bg-black text-white text-xs tracking-[0.2em] uppercase flex items-center justify-center gap-2 hover:opacity-90 transition-opacity"
        >
          {copiedAll ? <Check size={15} /> : <Copy size={15} />}
          {copiedAll ? "Kopyalandı" : "Tüm Bilgileri Kopyala"}
        </button>

        <p className="mt-3 text-[11px] text-gray-500 leading-relaxed">
          <strong className="text-gray-700">Önemli:</strong> Havale/EFT açıklamasına
          mutlaka <strong className="text-black">sipariş numaranızı</strong> yazın
          {orderNumber ? ` (${orderNumber})` : ""}. Ödemeniz onaylandığında sipariş
          durumunuz güncellenir ve size bilgi verilir.
        </p>
      </div>
    </div>
  );
}
