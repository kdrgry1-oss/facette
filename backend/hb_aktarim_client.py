#!/usr/bin/env python3
"""
hb_aktarim_client.py — "Özel HB Aktarım" modülünün KENDİ Hepsiburada istemcisi.

Bu istemci tamamen Hepsiburada resmi API dökümantasyonundan (developers.hepsiburada.com)
türetilmiştir; sistemin diğer entegrasyon kodlarından bağımsız, kendi kendine yeten bir
ada olarak tasarlanmıştır. Modülün tek bağımlılığı budur.

KAPSAM (HB resmi uçlarına birebir):
  • Katalog (MPOP)    : kategori listesi, kategori özellikleri, özellik (enum) değerleri
  • Ürün (MPOP)       : ürün gönderme (import / multipart), import takip/statü, statü sorgu
  • Listing           : fiyat / stok / birleşik (inventory) güncelleme + durum sorgu, listing çek,
                        satışa aç/kapat, sil
  • Sipariş/İade (OMS): sipariş listesi/detay, paket, fatura, etiket, kalem iptali, talepler

AUTH (HB dökümanı):
  • Authorization: Basic base64("<merchant_id>:<secret_key>")
  • User-Agent:    <developer_username>          (HB User-Agent'ı zorunlu kılar)
  • OMS için ayrı bir Basic kimlik gerekebilir (oms_username/oms_password verilirse o denenir).

ORTAM:
  test=True  -> *-sit.hepsiburada.com (sandbox)
  test=False -> canlı host
"""
from __future__ import annotations

import base64
import json
import uuid
import urllib.request
import urllib.parse
import urllib.error


class HBAktarimError(Exception):
    """HB Aktarım istemci hatası (HTTP / bağlantı / parse)."""
    pass


def _decode_body(raw, headers=None) -> str:
    """HB gövdesini güvenle metne çevirir. WAF/CDN 403 sayfaları gzip/deflate ya da
    binary gelebildiği için açılır; HTML ise kabaca sadeleştirilir."""
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        enc = ""
        if headers:
            try:
                enc = (headers.get("Content-Encoding") or headers.get("content-encoding") or "").lower()
            except Exception:
                enc = ""
        if raw[:2] == b"\x1f\x8b" or "gzip" in enc:
            import gzip
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            import zlib
            try:
                raw = zlib.decompress(raw)
            except Exception:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    except Exception:
        pass
    txt = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    low = txt.lower()
    if "<html" in low or "<!doctype" in low:
        import re as _re
        txt = _re.sub(r"<[^>]+>", " ", txt)
    return " ".join(txt.split())


class HBAktarimClient:
    # MPOP (katalog + ürün)
    MPOP_SANDBOX = "https://mpop-sit.hepsiburada.com"
    MPOP_PROD = "https://mpop.hepsiburada.com"
    # Listing (fiyat / stok / listeleme)
    LISTING_SANDBOX = "https://listing-external-sit.hepsiburada.com"
    LISTING_PROD = "https://listing-external.hepsiburada.com"
    # OMS (sipariş + talep)
    OMS_SANDBOX = "https://oms-external-sit.hepsiburada.com"
    OMS_PROD = "https://oms-external.hepsiburada.com"

    # HB'nin desteklediği kargo firması adları (Listing dökümanı — birebir yazım).
    CARGO_COMPANIES = [
        "Yurtiçi Kargo", "Aras Kargo", "PTT Kargo", "Borusan Lojistik",
        "Horoz Lojistik", "HepsiJet", "MNG Kargo", "Sürat Kargo",
        "Ceva Lojistik", "UPS", "Mağaza Hesabı",
    ]

    def __init__(self, merchant_id, secret_key, dev_username, test=True,
                 timeout=30, oms_username=None, oms_password=None):
        if not (merchant_id and secret_key and dev_username):
            raise ValueError("merchant_id, secret_key ve dev_username zorunlu.")
        self.merchant_id = str(merchant_id).strip()
        self.secret_key = str(secret_key).strip()
        self.dev_username = str(dev_username).strip()
        self.oms_username = (str(oms_username).strip() if oms_username else "")
        self.oms_password = (str(oms_password).strip() if oms_password else "")
        self.test = bool(test)
        self.timeout = timeout
        self.mpop_base = self.MPOP_SANDBOX if test else self.MPOP_PROD
        self.listing_base = self.LISTING_SANDBOX if test else self.LISTING_PROD
        self.oms_base = self.OMS_SANDBOX if test else self.OMS_PROD
        token = base64.b64encode(f"{self.merchant_id}:{self.secret_key}".encode()).decode()
        self._auth = f"Basic {token}"
        self._oms_auth_ok = None  # OMS'te tutan kimlik cache'i

    # ------------------------------------------------------------------ #
    #  Ortak HTTP (MPOP + Listing — standart Basic auth)
    # ------------------------------------------------------------------ #
    def _request(self, base, method, path, params=None, json_body=None,
                 raw_body=None, content_type=None, return_headers=False, auth=None,
                 read_timeout=None):
        url = base + path
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Authorization": auth or self._auth,
            "User-Agent": self.dev_username,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            data = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8")
            if content_type:
                headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=(read_timeout or self.timeout)) as r:
                body = r.read()
                text = _decode_body(body, r.headers)
                parsed = json.loads(text) if text.strip() else {}
                return (parsed, dict(r.headers)) if return_headers else parsed
        except urllib.error.HTTPError as e:
            try:
                detail = _decode_body(e.read(), e.headers)[:600]
            except Exception:
                detail = ""
            hint = ""
            if e.code in (401, 403):
                hint = (" | 401/403: kimlik (merchant/secret/dev) veya ortam (sandbox/canlı) "
                        "uyuşmazlığı olabilir. Sandbox kimliğiyle canlı host'a (ya da tersi) "
                        "gidilirse HB reddeder.")
            raise HBAktarimError(f"HTTP {e.code} {method} {path} -> {detail}{hint}")
        except urllib.error.URLError as e:
            raise HBAktarimError(f"Bağlantı hatası {method} {path}: {e}")

    def _mpop_get(self, path, params=None, return_headers=False):
        return self._request(self.mpop_base, "GET", path, params=params, return_headers=return_headers)

    # ================================================================== #
    #  KATEGORİLER (MPOP)
    # ================================================================== #
    def get_categories(self, leaf=True, active=True, available=True, page=0, size=2000):
        """Kategori sayfası çeker. Ürün YALNIZCA leaf+ACTIVE+available kategorilere açılır."""
        params = {"page": page, "size": size}
        if leaf is not None:
            params["leaf"] = str(bool(leaf)).lower()
        if available is not None:
            params["available"] = str(bool(available)).lower()
        if active is not None:
            params["status"] = "ACTIVE" if active else "INACTIVE"
        return self._mpop_get("/product/api/categories/get-all-categories", params)

    def iter_categories(self, leaf=True, active=True, available=True, size=2000, max_pages=200):
        """Tüm (leaf/active/available) kategorileri sayfalayarak toplar."""
        page, out = 0, []
        while page < max_pages:
            d = self.get_categories(leaf=leaf, active=active, available=available, page=page, size=size)
            rows = (d.get("data") if isinstance(d, dict) else d) or []
            out.extend(rows)
            last = bool(d.get("last")) if isinstance(d, dict) else False
            total_pages = d.get("totalPages") if isinstance(d, dict) else None
            if last or not rows:
                break
            if total_pages is not None and page + 1 >= int(total_pages):
                break
            page += 1
        return out

    def get_category_attributes(self, category_id):
        """Uç kategorinin özellik şeması. Döner: {'baseAttributes':[...], 'attributes':[...]}.
        Her özellik: {id, name, mandatory, type, multiValue, ...}. Sadece leaf+available'da dolu."""
        d = self._mpop_get(f"/product/api/categories/{category_id}/attributes")
        return (d.get("data") if isinstance(d, dict) else d) or {}

    def get_attribute_values(self, category_id, attribute_id, page=0, limit=1000):
        """enum tipli özelliğin geçerli değerleri (sayfalı). Döner: {data:[{id,name}], total, page, limit}."""
        aid = urllib.parse.quote(str(attribute_id), safe="")
        path = f"/product/api/categories/{category_id}/attribute/{aid}/values"
        data, headers = self._mpop_get(path, {"page": page, "limit": limit}, return_headers=True)
        rows = data.get("data", data) if isinstance(data, dict) else data
        total = (headers.get("Total-Count") or headers.get("total-count") or headers.get("X-Total-Count"))
        return {"data": rows or [],
                "total": int(total) if total and str(total).isdigit() else None,
                "page": page, "limit": limit}

    def iter_attribute_values(self, category_id, attribute_id, limit=1000, max_pages=100):
        """Bir özelliğin TÜM değerlerini çeker (HB sayfa boyutunu kısabildiğinden ilerleme bazlı durur)."""
        page, out, seen = 0, [], set()
        while page < max_pages:
            res = self.get_attribute_values(category_id, attribute_id, page=page, limit=limit)
            chunk = res.get("data") or []
            if not chunk:
                break
            new = 0
            for v in chunk:
                if isinstance(v, dict):
                    k = v.get("id")
                    if k is None:
                        k = v.get("value") or v.get("name")
                else:
                    k = v
                if k in seen:
                    continue
                seen.add(k)
                out.append(v)
                new += 1
            total = res.get("total")
            if total is not None and len(out) >= total:
                break
            if new == 0:
                break
            page += 1
        return out

    # ================================================================== #
    #  ÜRÜN GÖNDERME (MPOP)  —  /product/api/products/import (multipart)
    # ================================================================== #
    def import_products(self, items):
        """Ürünleri HB kataloğuna gönderir. items: [{categoryId, merchant, attributes:{...}}].
        İstek multipart/form-data; 'file' alanında integrator.json gider. Döner: {trackingId,...}."""
        if isinstance(items, dict):
            items = [items]
        payload = json.dumps(items, ensure_ascii=False).encode("utf-8")
        boundary = "----HBAktarim" + uuid.uuid4().hex
        body = b""
        body += ("--" + boundary + "\r\n").encode()
        body += b'Content-Disposition: form-data; name="file"; filename="integrator.json"\r\n'
        body += b"Content-Type: application/json\r\n\r\n"
        body += payload + b"\r\n"
        body += ("--" + boundary + "--\r\n").encode()
        return self._request(self.mpop_base, "POST", "/product/api/products/import",
                             raw_body=body,
                             content_type="multipart/form-data; boundary=" + boundary)

    def get_import_status(self, tracking_id):
        """Ürün gönderme (import) takip numarasının durumunu döner."""
        tid = urllib.parse.quote(str(tracking_id), safe="")
        return self._mpop_get(f"/product/api/products/status/{tid}")

    def check_product_status(self, merchant_sku_list):
        """merchantSku listesinin ürün/eşleşme statülerini sorgular."""
        skus = [str(s) for s in (merchant_sku_list or []) if s]
        body = [{"merchant": self.merchant_id, "merchantSkuList": skus}]
        return self._request(self.mpop_base, "POST", "/product/api/products/check-product-status",
                             json_body=body)

    def products_by_status(self, product_status="WAITING", task_status=False, page=0, size=100, version=1):
        params = {"merchantId": self.merchant_id, "productStatus": product_status,
                  "taskStatus": str(bool(task_status)).lower(), "page": page, "size": size,
                  "version": version}
        return self._mpop_get("/product/api/products/products-by-merchant-and-status", params)

    def all_products(self, page=0, size=1000):
        return self._mpop_get(f"/product/api/products/all-products-of-merchant/{self.merchant_id}",
                              {"page": page, "size": size})

    # ================================================================== #
    #  LISTING  —  fiyat / stok / birleşik
    # ================================================================== #
    def update_prices(self, items):
        """[{"merchantSku"|"hepsiburadaSku": ..., "price": <float>}] — Döner: {"id": <uploadId>}."""
        path = f"/listings/merchantid/{self.merchant_id}/price-uploads"
        return self._request(self.listing_base, "POST", path, json_body=list(items))

    def update_stocks(self, items):
        """[{"merchantSku"|"hepsiburadaSku": ..., "availableStock": <int>}] — Döner: {"id": <uploadId>}."""
        path = f"/listings/merchantid/{self.merchant_id}/stock-uploads"
        return self._request(self.listing_base, "POST", path, json_body=list(items))

    def update_inventory_xml(self, listings):
        """Birleşik listing (fiyat+stok+kargo+termin) — XML body.
        listings: [{HepsiburadaSku, MerchantSku, ProductName, Price, AvailableStock,
                    DispatchTime, MaximumPurchasableQuantity, CargoCompany1..3, ShippingProfileName}]."""
        def esc(v):
            s = "" if v is None else str(v)
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts = ['<?xml version="1.0" encoding="utf-8"?>',
                 '<listings xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                 'xmlns:xsd="http://www.w3.org/2001/XMLSchema">']
        for it in listings:
            parts.append("<listing>")
            for k, v in it.items():
                if v in (None, ""):
                    continue
                parts.append(f"<{k}>{esc(v)}</{k}>")
            parts.append("</listing>")
        parts.append("</listings>")
        xml = "".join(parts)
        path = f"/listings/merchantid/{self.merchant_id}/inventory-uploads"
        return self._request(self.listing_base, "POST", path, raw_body=xml,
                             content_type="application/xml")

    def get_upload_status(self, kind, upload_id):
        """kind: 'price' | 'stock' | 'inventory'."""
        k = {"price": "price-uploads", "stock": "stock-uploads",
             "inventory": "inventory-uploads"}.get(kind, "stock-uploads")
        uid = urllib.parse.quote(str(upload_id), safe="")
        path = f"/listings/merchantid/{self.merchant_id}/{k}/id/{uid}"
        return self._request(self.listing_base, "GET", path)

    def get_listings(self, offset=0, limit=100, merchant_sku_list=None, hepsiburada_sku_list=None):
        params = {"offset": offset, "limit": limit}
        if merchant_sku_list:
            params["merchantSkuList"] = ",".join(str(s) for s in merchant_sku_list)
        if hepsiburada_sku_list:
            params["hepsiburadaSkuList"] = ",".join(str(s) for s in hepsiburada_sku_list)
        return self._request(self.listing_base, "GET", f"/listings/merchantid/{self.merchant_id}",
                             params=params)

    def activate_listing(self, hepsiburada_sku):
        sku = urllib.parse.quote(str(hepsiburada_sku), safe="")
        return self._request(self.listing_base, "POST",
                             f"/listings/merchantid/{self.merchant_id}/sku/{sku}/activate")

    def deactivate_listing(self, hepsiburada_sku):
        sku = urllib.parse.quote(str(hepsiburada_sku), safe="")
        return self._request(self.listing_base, "POST",
                             f"/listings/merchantid/{self.merchant_id}/sku/{sku}/deactivate")

    def delete_listing(self, hepsiburada_sku, merchant_sku):
        hb = urllib.parse.quote(str(hepsiburada_sku), safe="")
        ms = urllib.parse.quote(str(merchant_sku), safe="")
        return self._request(self.listing_base, "DELETE",
                             f"/listings/merchantid/{self.merchant_id}/sku/{hb}/merchantsku/{ms}")

    # ================================================================== #
    #  OMS (sipariş + talep)  —  ayrı Basic kimlik denemeli
    # ================================================================== #
    def _oms_auth_candidates(self):
        def b(u, p):
            return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()
        cands = []
        if self.oms_username and self.oms_password:
            cands.append(b(self.oms_username, self.oms_password))
        cands += [
            b(self.merchant_id, self.secret_key),
            b(self.dev_username, self.secret_key),
            b(self.dev_username, self.merchant_id),
        ]
        return cands

    def _oms_request(self, method, path, params=None, json_body=None, read_timeout=None):
        cands = self._oms_auth_candidates()
        if self._oms_auth_ok:
            cands.sort(key=lambda a: 0 if a == self._oms_auth_ok else 1)
        last = ""
        for auth in cands:
            try:
                res = self._request(self.oms_base, method, path, params=params,
                                    json_body=json_body, auth=auth,
                                    read_timeout=(read_timeout or min(self.timeout, 20)))
                self._oms_auth_ok = auth
                return res
            except HBAktarimError as e:
                msg = str(e)
                if " 401 " in msg or " 403 " in msg:
                    last = msg
                    continue
                raise
        raise HBAktarimError(
            "OMS 401/403 — denenen kimliklerin tümü reddedildi. HB OMS için ayrı "
            f"Entegrasyon Kullanıcı Adı/Şifre gerekebilir. Son yanıt: {last[:160]}")

    def get_orders(self, begin_date=None, end_date=None, offset=0, limit=100, read_timeout=12):
        params = {"offset": offset, "limit": limit, "beginDate": begin_date, "endDate": end_date}
        return self._oms_request("GET", f"/orders/merchantid/{self.merchant_id}", params=params,
                                 read_timeout=read_timeout)

    def get_order(self, order_number):
        on = urllib.parse.quote(str(order_number), safe="")
        return self._oms_request("GET", f"/orders/merchantid/{self.merchant_id}/ordernumber/{on}")

    def get_packages(self, offset=0, limit=100, begin_date=None, end_date=None):
        params = {"offset": offset, "limit": limit, "beginDate": begin_date, "endDate": end_date}
        return self._oms_request("GET", f"/packages/merchantid/{self.merchant_id}", params=params)

    def get_claims(self, offset=0, limit=100, begin_date=None, end_date=None):
        params = {"offset": offset, "limit": limit, "beginDate": begin_date, "endDate": end_date}
        return self._oms_request("GET", f"/claims/merchantid/{self.merchant_id}", params=params)

    # ------------------------------------------------------------------ #
    def ping(self):
        """Kimlik/ortam doğrulaması: 1 kategori çekebiliyorsak auth tamam demektir."""
        d = self.get_categories(leaf=True, active=True, available=True, page=0, size=1)
        rows = (d.get("data") if isinstance(d, dict) else d) or []
        return {"ok": True, "sample_count": len(rows)}
