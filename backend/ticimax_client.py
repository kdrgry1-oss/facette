"""
Ticimax SOAP Web Service Client  –  facette.com.tr
API Key : HANXFWINXLDBY0WH47WMB6QKTE20T5

Gerçek WSDL imzaları (doğrulanmış):
  SelectKategori  : UyeKodu, kategoriID=0, dil='tr', parentID
    → parentID=0 → kök kategoriler, parentID=X → X'in alt kategorileri
    → Dönen alanlar: ID, PID, Tanim, Aktif, AltKategoriSayisi, Sira, Url,
                     Icerik, Kod, KategoriMenuGoster, SeoAnahtarKelime,
                     SeoSayfaAciklama, SeoSayfaBaslik, PaylasimAyar
  SelectUrun      : UyeKodu, f:UrunFiltre (Aktif=1|None,KategoriID,...), s:UrunSayfalama (BaslangicIndex, KayitSayisi, KayitSayisinaGoreGetir)
  SelectUrunCount : UyeKodu, f:UrunFiltre
  SelectVaryasyon : UyeKodu, f:VaryasyonFiltre (UrunKartiID), s:UrunSayfalama, varyasyonAyar:SelectVaryasyonAyar
  SelectUrunResim : UyeKodu, request:UrunResimListeleRequest (UrunKartiId)
  SelectAsortiMiktar: UyeKodu, asortiMiktarId
  SelectSiparis   : UyeKodu, f:WebSiparisFiltre, s:WebSiparisSayfalama (BaslangicIndex, KayitSayisi, SiralamaDegeri, SiralamaYonu)
  SelectSiparisUrun: UyeKodu, siparisId, iptalEdilmisUrunler
"""
import logging, warnings, time
from typing import List, Dict, Optional, Any

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

TICIMAX_DOMAIN  = "www.facette.com.tr"
TICIMAX_API_KEY = "HANXFWINXLDBY0WH47WMB6QKTE20T5"
RATE_LIMIT_SLEEP = 13   # Ticimax rate limit: 12 sn, biz 13 sn bekliyoruz

URUN_WSDL    = f"https://{TICIMAX_DOMAIN}/Servis/UrunServis.svc?wsdl"
SIPARIS_WSDL = f"https://{TICIMAX_DOMAIN}/Servis/SiparisServis.svc?wsdl"

_urun_client_cache = None
_siparis_client_cache = None


def _urun_client():
    global _urun_client_cache
    if _urun_client_cache is None:
        from zeep import Client, Settings
        from zeep.transports import Transport
        _urun_client_cache = Client(
            URUN_WSDL,
            settings=Settings(strict=False, xml_huge_tree=True),
            transport=Transport(timeout=90, operation_timeout=180),
        )
    return _urun_client_cache


def _siparis_client():
    global _siparis_client_cache
    if _siparis_client_cache is None:
        from zeep import Client, Settings
        from zeep.transports import Transport
        _siparis_client_cache = Client(
            SIPARIS_WSDL,
            settings=Settings(strict=False, xml_huge_tree=True),
            transport=Transport(timeout=90, operation_timeout=180),
        )
    return _siparis_client_cache


def _to_dict(obj) -> Any:
    """Recursively convert zeep object → plain dict/list."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if hasattr(obj, "__values__"):
        return {k: _to_dict(v) for k, v in obj.__values__.items()}
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items()
                if not k.startswith("_")}
    return obj


def _unwrap_list(result) -> List[Dict]:
    """Pull a list out of whatever zeep returns."""
    data = _to_dict(result)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]
    return []


# ═══════════════ CATEGORIES ════════════════════════════════════

def get_categories(parent_id: int = 0, wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """
    SelectKategori(UyeKodu, kategoriID=0, dil='tr', parentID)
    parent_id=0 → kök kategoriler
    parent_id=X → X'in alt kategorileri
    Dönen alanlar: ID, PID, Tanim, Aktif, AltKategoriSayisi, Sira, Url,
                   Icerik, Kod, KategoriMenuGoster, SeoAnahtarKelime,
                   SeoSayfaAciklama, SeoSayfaBaslik, PaylasimAyar
    """
    c = _urun_client()
    result = c.service.SelectKategori(
        UyeKodu=wscode, kategoriID=0, dil="tr", parentID=parent_id)
    cats = _unwrap_list(result)
    logger.info(f"SelectKategori(parentID={parent_id}) → {len(cats)} categories")
    return cats


def get_all_categories(wscode: str = TICIMAX_API_KEY,
                       sleep_between: float = 1.5) -> List[Dict]:
    """
    Tüm kategori hiyerarşisini recursive olarak çeker.
    Kök kategorilerden başlar, AltKategoriSayisi > 0 olanların
    alt kategorilerini de çeker (2 seviye derinlik yeterli).
    sleep_between: rate limit için her API çağrısı arasında bekleme (sn)
    """
    import time
    all_cats: List[Dict] = []
    seen_ids = set()

    # Kök kategorileri çek
    roots = get_categories(parent_id=0, wscode=wscode)
    for cat in roots:
        cid = cat.get("ID")
        if cid and cid not in seen_ids:
            all_cats.append(cat)
            seen_ids.add(cid)

    # Alt kategorileri çek
    to_expand = [c for c in roots if (c.get("AltKategoriSayisi") or 0) > 0]
    for parent_cat in to_expand:
        time.sleep(sleep_between)
        try:
            subs = get_categories(parent_id=parent_cat["ID"], wscode=wscode)
            for sub in subs:
                sid = sub.get("ID")
                if sid and sid not in seen_ids:
                    all_cats.append(sub)
                    seen_ids.add(sid)
                # 3. seviye de varsa çek
                if (sub.get("AltKategoriSayisi") or 0) > 0:
                    time.sleep(sleep_between)
                    try:
                        subsubs = get_categories(parent_id=sid, wscode=wscode)
                        for ss in subsubs:
                            ssid = ss.get("ID")
                            if ssid and ssid not in seen_ids:
                                all_cats.append(ss)
                                seen_ids.add(ssid)
                    except Exception as e:
                        logger.error(f"SelectKategori(parentID={sid}): {e}")
        except Exception as e:
            logger.error(f"SelectKategori(parentID={parent_cat['ID']}): {e}")

    logger.info(f"get_all_categories → {len(all_cats)} total categories")
    return all_cats


# ═══════════════ PRODUCTS ══════════════════════════════════════

def get_product_count(aktif: Optional[int] = None,
                      wscode: str = TICIMAX_API_KEY) -> int:
    """
    SelectUrunCount(UyeKodu, f:UrunFiltre)
    aktif=1 → sadece aktif ürünler, aktif=0 → pasif, None → hepsi
    """
    c = _urun_client()
    ff = c.get_type("ns2:UrunFiltre")
    f_kwargs = {}
    if aktif is not None:
        f_kwargs["Aktif"] = aktif
    f = ff(**f_kwargs)
    try:
        result = c.service.SelectUrunCount(UyeKodu=wscode, f=f)
        return int(result or 0)
    except Exception as e:
        logger.error(f"SelectUrunCount: {e}")
        return 0


def get_products(page: int = 1, page_size: int = 50,
                 aktif: Optional[int] = 1,
                 kategori_id: Optional[int] = None,
                 wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """
    SelectUrun(UyeKodu, f:UrunFiltre, s:UrunSayfalama)
    aktif=1 → aktif ürünler (varsayılan), aktif=0 → pasif, None → hepsi
    kategori_id → belirli kategori filtresi
    UrunSayfalama: BaslangicIndex (0-based), KayitSayisi, KayitSayisinaGoreGetir
    """
    c = _urun_client()
    ff = c.get_type("ns2:UrunFiltre")
    sf = c.get_type("ns2:UrunSayfalama")

    f_kwargs = {}
    if aktif is not None:
        f_kwargs["Aktif"] = aktif
    if kategori_id is not None:
        f_kwargs["KategoriID"] = kategori_id
    f = ff(**f_kwargs)

    start = (page - 1) * page_size
    s = sf(BaslangicIndex=start, KayitSayisi=page_size, KayitSayisinaGoreGetir=True)

    result = c.service.SelectUrun(UyeKodu=wscode, f=f, s=s)
    prods = _unwrap_list(result)
    logger.info(f"SelectUrun page={page} aktif={aktif} → {len(prods)} products")
    return prods


# ═══════════════ VARIANTS ══════════════════════════════════════

def get_variants(urun_karti_id: int, wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """SelectVaryasyon(..., f.UrunKartiID=urun_karti_id)"""
    c = _urun_client()
    try:
        vf   = c.get_type("ns2:VaryasyonFiltre")
        sf   = c.get_type("ns2:UrunSayfalama")
        ayar = c.get_type("ns2:SelectVaryasyonAyar")

        f = vf(UrunKartiID=urun_karti_id)
        s = sf(BaslangicIndex=0, KayitSayisi=500, KayitSayisinaGoreGetir=True)
        a = ayar()

        result = c.service.SelectVaryasyon(
            UyeKodu=wscode, f=f, s=s, varyasyonAyar=a)
        return _unwrap_list(result)
    except Exception as e:
        logger.error(f"SelectVaryasyon({urun_karti_id}): {e}")
        return []


# ═══════════════ IMAGES ════════════════════════════════════════

def get_product_images(urun_karti_id: int, wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """SelectUrunResim(..., request.UrunKartiId=urun_karti_id)"""
    c = _urun_client()
    try:
        rt  = c.get_type("ns2:UrunResimListeleRequest")
        req = rt(UrunKartiId=urun_karti_id)
        result = c.service.SelectUrunResim(UyeKodu=wscode, request=req)
        return _unwrap_list(result)
    except Exception as e:
        logger.error(f"SelectUrunResim({urun_karti_id}): {e}")
        return []


# ═══════════════ ASORTI STOCK ══════════════════════════════════

def get_assorted_stock(asorti_grup_id: int, wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """SelectAsortiMiktar(UyeKodu, asortiMiktarId)"""
    c = _urun_client()
    try:
        result = c.service.SelectAsortiMiktar(
            UyeKodu=wscode, asortiMiktarId=asorti_grup_id)
        return _unwrap_list(result)
    except Exception as e:
        logger.error(f"SelectAsortiMiktar({asorti_grup_id}): {e}")
        return []


# ═══════════════ ORDERS ════════════════════════════════════════

def get_orders(page: int = 1, page_size: int = 50,
               wscode: str = TICIMAX_API_KEY,
               start_date: Optional[str] = None,
               end_date: Optional[str] = None) -> List[Dict]:
    """SelectSiparis(UyeKodu, f:WebSiparisFiltre, s:WebSiparisSayfalama)
    
    Doğru WSDL alan adları (doğrulandı):
      SiparisTarihiBas, SiparisTarihiSon  → dateTime formatı (YYYY-MM-DDTHH:MM:SS)
    """
    c = _siparis_client()
    try:
        ff = c.get_type("ns2:WebSiparisFiltre")
        sf = c.get_type("ns2:WebSiparisSayfalama")

        fkw = {}
        if start_date:
            # "DD.MM.YYYY" → "YYYY-MM-DDTHH:MM:SS" formatına çevir
            try:
                from datetime import datetime as _dt
                if "." in start_date:
                    d = _dt.strptime(start_date, "%d.%m.%Y")
                else:
                    d = _dt.strptime(start_date, "%Y-%m-%d")
                fkw["SiparisTarihiBas"] = d.strftime("%Y-%m-%dT00:00:00")
            except Exception:
                fkw["SiparisTarihiBas"] = start_date
        if end_date:
            try:
                from datetime import datetime as _dt
                if "." in end_date:
                    d = _dt.strptime(end_date, "%d.%m.%Y")
                else:
                    d = _dt.strptime(end_date, "%Y-%m-%d")
                fkw["SiparisTarihiSon"] = d.strftime("%Y-%m-%dT23:59:59")
            except Exception:
                fkw["SiparisTarihiSon"] = end_date

        f = ff(**fkw)
        s = sf(BaslangicIndex=(page-1)*page_size, KayitSayisi=page_size, SiralamaDegeri="SiparisTarih", SiralamaYonu="DESC")

        result = c.service.SelectSiparis(UyeKodu=wscode, f=f, s=s)
        orders = _unwrap_list(result)
        logger.info(f"SelectSiparis page={page} → {len(orders)} orders")
        return orders
    except Exception as e:
        logger.error(f"SelectSiparis: {e}")
        raise


def get_order_items(siparis_id: int, wscode: str = TICIMAX_API_KEY) -> List[Dict]:
    """SelectSiparisUrun(UyeKodu, siparisId, iptalEdilmisUrunler)"""
    c = _siparis_client()
    try:
        result = c.service.SelectSiparisUrun(
            UyeKodu=wscode, siparisId=siparis_id, iptalEdilmisUrunler=False)
        return _unwrap_list(result)
    except Exception as e:
        logger.error(f"SelectSiparisUrun({siparis_id}): {e}")
        return []
