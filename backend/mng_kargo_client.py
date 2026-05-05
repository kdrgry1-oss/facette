"""
MNG Kargo (DHL eCommerce) SOAP Client
WSDL: https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL

Verified WSDL operations:
  - Baglanti_Test()                    : connection ping
  - SiparisGirisiDetayliV3(...)        : create shipment + return barcode
  - KargoTakipByReferans(pKullanici, pSifre, pReferansId): track by reference (sipariş no)
  - TekBarkodGonderiIptali(...)        : cancel a single shipment by barcode
  - MNGGonderiBarkod(req)              : barcode print request

Default credentials (override via DB settings):
  CustomerCode: FACETTE DIŞ TİC.A.Ş.
  Username    : 490059279
  Password    : Face.0024E
  TaxNumber   : 6080712084
"""
import logging
import warnings
from typing import Dict, Optional

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

WSDL_URL = "https://service.mngkargo.com.tr/musterikargosiparis/musterikargosiparis.asmx?WSDL"

_client_cache = None


def _get_client():
    global _client_cache
    if _client_cache is None:
        from zeep import Client, Settings
        from zeep.transports import Transport
        _client_cache = Client(
            WSDL_URL,
            settings=Settings(strict=False, xml_huge_tree=True),
            transport=Transport(timeout=60, operation_timeout=120),
        )
    return _client_cache


def baglanti_test() -> Dict:
    """Test SOAP service availability."""
    try:
        c = _get_client()
        r = c.service.Baglanti_Test()
        return {"ok": True, "result": str(r)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_mng_shipment_status(*, username: str, password: str, siparis_no: str) -> Dict:
    """FaturaSiparisListesi → siparis_no'dan TÜM kargo durumunu çek.
    
    Returns:
      {
        "mng_siparis_no": "1757391445",  # MNG iç referans
        "gonderi_no": "NZ197406",         # ASIL KARGO TAKİP KODU (MNG şubesi atadığında)
        "kargo_statu": "0",               # 0=İşlem Yok, 1+=işleniyor
        "kargo_statu_aciklama": "...",
        "kargo_takip_url": "...",
        "teslim_tarihi": "...",
        "alici_il": "...",
      }
    """
    c = _get_client()
    try:
        r = c.service.FaturaSiparisListesi(
            pSiparisNo=siparis_no, pKullaniciAdi=username, pSifre=password
        )
        if r is None:
            return {"ok": False, "error": "Sipariş bulunamadı"}
        from zeep.helpers import serialize_object
        ser = serialize_object(r)
        # Navigate: schema → _value_1 → list → FaturaSiparisListesi
        try:
            rows = ser.get("_value_1", {}).get("_value_1", [])
            if rows and isinstance(rows, list):
                row = rows[0].get("FaturaSiparisListesi", {})
            else:
                row = {}
        except Exception:
            row = {}
        return {
            "ok": True,
            "mng_siparis_no": str(row.get("MNG_SIPARIS_NO") or "").strip(),
            "gonderi_no": str(row.get("GONDERI_NO") or "").strip(),
            "kargo_statu": str(row.get("KARGO_STATU") or "0").strip(),
            "kargo_statu_aciklama": str(row.get("KARGO_STATU_ACIKLAMA") or "").strip(),
            "kargo_takip_url": str(row.get("KARGO_TAKIP_URL") or "").strip(),
            "teslim_tarihi": str(row.get("TESLIM_TARIHI") or "").strip(),
            "alici_il": str(row.get("ALICI_IL") or "").strip(),
            "cikis_subesi": str(row.get("CIKIS_SUBESI") or "").strip(),
            "teslim_subesi": str(row.get("TESLIM_SUBESI") or "").strip(),
            "raw": row,
        }
    except Exception as e:
        logger.error(f"MNG get_shipment_status({siparis_no}): {e}")
        return {"ok": False, "error": str(e)}


def get_mng_barcode_by_siparis_no(*, username: str, password: str, siparis_no: str) -> Optional[str]:
    """Geriye uyumluluk: MNG_SIPARIS_NO döndürür."""
    info = get_mng_shipment_status(username=username, password=password, siparis_no=siparis_no)
    return info.get("mng_siparis_no") if info.get("ok") else None


def create_shipment(
    *,
    username: str,
    password: str,
    siparis_no: str,
    irsaliye_no: str = "",
    kiymet: float = 0.0,
    icerik: str = "",
    hizmet_sekli: str = "TS",   # TS=Standart, KP=Kapıda Ödeme, EX=Ekspres
    teslim_sekli: int = 1,       # 1=Adrese Teslim
    al_sms: int = 0,
    gn_sms: int = 1,
    parca_list: str = "1;1;1",   # Adet;En;Boy (basitleştirilmiş)
    alici_mng_no: str = "",
    alici_bayi_no: str = "",
    alici_ad: str,
    odeme_sekli: str = "GO",     # GO=Gönderici Öder, AO=Alıcı Öder
    adres_farkli: str = "0",
    il: str,
    ilce: str,
    adres: str,
    semt: str = "",
    mahalle: str = "",
    meydan_bulvar: str = "",
    cadde: str = "",
    sokak: str = "",
    tel_ev: str = "",
    tel_cep: str,
    tel_is: str = "",
    fax: str = "",
    email: str = "",
    vergi_dairesi: str = "",
    vergi_no: str = "",
    kapida_odeme: int = 0,
    mal_bedeli_odeme: str = "",
    platform_adi: str = "FACETTE",
    platform_kodu: str = "",
) -> Dict:
    """
    SiparisGirisiDetayliV3 ile gönderi oluştur.
    Return: { ok: bool, barkod: str, hata: str, raw: dict }
    """
    c = _get_client()
    try:
        result = c.service.SiparisGirisiDetayliV3(
            pChIrsaliyeNo=irsaliye_no,
            pPrKiymet=str(kiymet),
            pChBarkod="",
            pChIcerik=icerik[:250],
            pGonderiHizmetSekli=hizmet_sekli,
            pTeslimSekli=teslim_sekli,
            pFlAlSms=al_sms,
            pFlGnSms=gn_sms,
            pKargoParcaList=parca_list,
            pAliciMusteriMngNo=alici_mng_no,
            pAliciMusteriBayiNo=alici_bayi_no,
            pAliciMusteriAdi=alici_ad[:100],
            pChSiparisNo=siparis_no,
            pLuOdemeSekli=odeme_sekli,
            pFlAdresFarkli=adres_farkli,
            pChIl=il,
            pChIlce=ilce,
            pChAdres=adres[:250],
            pChSemt=semt,
            pChMahalle=mahalle,
            pChMeydanBulvar=meydan_bulvar,
            pChCadde=cadde,
            pChSokak=sokak,
            pChTelEv=tel_ev,
            pChTelCep=tel_cep,
            pChTelIs=tel_is,
            pChFax=fax,
            pChEmail=email,
            pChVergiDairesi=vergi_dairesi,
            pChVergiNumarasi=vergi_no,
            pFlKapidaOdeme=kapida_odeme,
            pMalBedeliOdemeSekli=mal_bedeli_odeme,
            pPlatformKisaAdi=platform_adi,
            pPlatformSatisKodu=platform_kodu,
            pKullaniciAdi=username,
            pSifre=password,
        )
        # MNG response: "1" = success, "0" = error veya "0~mesaj" / "1~mesaj"
        result_str = str(result or "").strip()
        logger.info(f"MNG SiparisGirisiDetayliV3 response for {siparis_no}: {result_str[:200]}")
        # V3 sadece status code döner: "1" = success. Gerçek barkod FaturaSiparisListesi ile alınır.
        if result_str == "1":
            # Fetch real barcode (MNG_SIPARIS_NO)
            import time as _t
            barcode = None
            for attempt in range(3):
                _t.sleep(1)
                barcode = get_mng_barcode_by_siparis_no(
                    username=username, password=password, siparis_no=siparis_no
                )
                if barcode:
                    break
            if barcode:
                return {"ok": True, "barkod": barcode, "raw": result_str}
            # Fallback: kayıt başarılı ama barkod henüz hazır değil
            return {"ok": True, "barkod": "", "raw": result_str,
                    "note": "Sipariş MNG'ye kaydedildi ancak barkod birkaç dakika sonra FaturaSiparisListesi ile alınabilir."}
        if "~" in result_str:
            parts = result_str.split("~", 1)
            code = parts[0].strip()
            payload = parts[1].strip() if len(parts) > 1 else ""
            if code == "0":
                return {"ok": True, "barkod": payload, "raw": result_str}
            return {"ok": False, "barkod": "", "hata": payload, "raw": result_str}
        # 0 veya bilinmeyen → hata
        return {"ok": False, "barkod": "", "hata": result_str or "Boş cevap", "raw": result_str}
    except Exception as e:
        logger.error(f"MNG create_shipment error for {siparis_no}: {e}")
        return {"ok": False, "barkod": "", "hata": str(e), "raw": None}


def cancel_shipment(*, username: str, password: str, siparis_no: str, gonderi_no: str = "") -> Dict:
    """TekBarkodGonderiIptali"""
    c = _get_client()
    try:
        r = c.service.TekBarkodGonderiIptali(
            pKullaniciAdi=username, pSifre=password,
            pChSiparisNo=siparis_no, pNmGonderiNo=gonderi_no
        )
        result_str = str(r or "")
        if result_str.startswith("0"):
            return {"ok": True, "raw": result_str}
        return {"ok": False, "hata": result_str.split("~", 1)[-1] if "~" in result_str else result_str}
    except Exception as e:
        return {"ok": False, "hata": str(e)}


def track_by_reference(*, username: str, password: str, referans_id: str) -> Dict:
    """KargoTakipByReferans → siparis_no ile takip"""
    c = _get_client()
    try:
        r = c.service.KargoTakipByReferans(
            pKullanici=username, pSifre=password, pReferansId=referans_id
        )
        if r is None:
            return {"ok": False, "events": [], "hata": "Bulunamadı"}
        # Normalize to dict
        if hasattr(r, "__values__"):
            r = dict(r.__values__)
        return {"ok": True, "data": r}
    except Exception as e:
        return {"ok": False, "hata": str(e)}
