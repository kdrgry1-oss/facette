#!/usr/bin/env python3
"""
hepsiburada_client.py — Hepsiburada Marketplace (MPOP) API istemcisi.
Kategori agaci, kategori ozellikleri, ozellik (enum) degerleri.

Auth : HTTP Basic (merchant_id:secret_key) + User-Agent (developer username).
Ortam: test=True  -> https://mpop-sit.hepsiburada.com (sandbox)
       test=False -> https://mpop.hepsiburada.com     (canli)

Kütüphane:
  hb = HepsiburadaClient(merchant_id, secret_key, dev_username, test=True)
  cats  = hb.get_categories(leaf=True, active=True, available=True)
  attrs = hb.get_category_attributes(category_id)   # {'baseAttributes':[], 'attributes':[]}
  vals  = hb.iter_attribute_values(category_id, attribute_id)  # sadece type=='enum'

Self-test:
  python3 hepsiburada_client.py
"""
import base64
import json
import urllib.request
import urllib.parse
import urllib.error


class HepsiburadaError(Exception):
    pass


class HepsiburadaClient:
    SANDBOX = "https://mpop-sit.hepsiburada.com"
    PROD = "https://mpop.hepsiburada.com"

    def __init__(self, merchant_id, secret_key, dev_username, test=True, timeout=30,
                 oms_username=None, oms_password=None):
        if not (merchant_id and secret_key and dev_username):
            raise ValueError("merchant_id, secret_key ve dev_username zorunlu.")
        self.merchant_id = str(merchant_id).strip()
        self.secret_key = str(secret_key).strip()
        self.dev_username = str(dev_username).strip()
        self.oms_username = (str(oms_username).strip() if oms_username else "")
        self.oms_password = (str(oms_password).strip() if oms_password else "")
        self.base = self.SANDBOX if test else self.PROD
        self.timeout = timeout
        token = base64.b64encode(f"{self.merchant_id}:{self.secret_key}".encode()).decode()
        self._auth = f"Basic {token}"

    def _get(self, path, params=None, return_headers=False):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": self._auth,
            "User-Agent": self.dev_username,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read().decode("utf-8", "replace")
                data = json.loads(body) if body else {}
                return (data, dict(r.headers)) if return_headers else data
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise HepsiburadaError(f"HTTP {e.code} {path} -> {detail}")
        except urllib.error.URLError as e:
            raise HepsiburadaError(f"Baglanti hatasi {path}: {e}")

    # ---------- Kategoriler ----------
    def get_categories(self, leaf=None, active=None, available=None, page=0, size=2000):
        params = {"page": page, "size": size}
        if leaf is not None:
            params["leaf"] = str(leaf).lower()
        if available is not None:
            params["available"] = str(available).lower()
        if active is not None:
            params["status"] = "ACTIVE" if active else "INACTIVE"
        return self._get("/product/api/categories/get-all-categories", params)

    def iter_all_categories(self, leaf=None, active=None, available=None, size=2000):
        page, out = 0, []
        while True:
            d = self.get_categories(leaf=leaf, active=active, available=available, page=page, size=size)
            rows = d.get("data", []) or []
            out.extend(rows)
            if d.get("last") or not rows:
                break
            page += 1
        return out

    # ---------- Ozellikler ----------
    def get_category_attributes(self, category_id):
        """Sadece leaf+available kategorilerde dolu gelir.
        Doner: {'baseAttributes':[...], 'attributes':[...]}
        Her ozellik: {name, id, mandatory, type, multiValue}"""
        d = self._get(f"/product/api/categories/{category_id}/attributes")
        return d.get("data", {}) or {}

    # ---------- Ozellik (enum) degerleri ----------
    def get_attribute_values(self, category_id, attribute_id, page=0, limit=1000):
        """type=='enum' ozellikler icin gecerli degerler (paginasyonlu).
        Path 'attribute' TEKIL. Toplam adet header'da (Total-Count)."""
        aid = urllib.parse.quote(str(attribute_id), safe="")
        path = f"/product/api/categories/{category_id}/attribute/{aid}/values"
        data, headers = self._get(path, {"page": page, "limit": limit}, return_headers=True)
        rows = data.get("data", data) if isinstance(data, dict) else data
        total = (headers.get("Total-Count") or headers.get("total-count")
                 or headers.get("X-Total-Count"))
        return {"data": rows or [],
                "total": int(total) if total and str(total).isdigit() else None,
                "page": page, "limit": limit}

    def iter_attribute_values(self, category_id, attribute_id, limit=1000):
        page, out = 0, []
        while True:
            res = self.get_attribute_values(category_id, attribute_id, page=page, limit=limit)
            chunk = res["data"] or []
            out.extend(chunk)
            total = res.get("total")
            if total is not None:
                if len(out) >= total or not chunk:
                    break
            elif not chunk or len(chunk) < limit:
                break
            page += 1
        return out

    # ---------- Siparişler (OMS — Order Management System) ----------
    # NOT: Siparişler MPOP'tan DEĞİL, ayrı OMS host'undan gelir. OMS Basic auth genelde
    # MPOP'tan FARKLI kimlik ister (merchant_id:secret_key 401 verir). Bu yüzden olası
    # kombinasyonları sırayla deneriz; 401 olmayan ilk yanıtı kullanırız.
    OMS_SANDBOX = "https://oms-external-sit.hepsiburada.com"
    OMS_PROD = "https://oms-external.hepsiburada.com"

    def _oms_base(self):
        return self.OMS_SANDBOX if self.base == self.SANDBOX else self.OMS_PROD

    def _oms_auth_candidates(self):
        """OMS için denenecek Basic auth (kullanıcı:şifre) kombinasyonları — en olasıdan başlayarak."""
        def b(u, p):
            return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()
        cands = []
        if self.oms_username and self.oms_password:
            cands.append(("oms_username:oms_password", b(self.oms_username, self.oms_password)))
        cands += [
            ("dev_username:secret_key", b(self.dev_username, self.secret_key)),
            ("merchant_id:secret_key", b(self.merchant_id, self.secret_key)),
            ("dev_username:merchant_id", b(self.dev_username, self.merchant_id)),
        ]
        return cands

    def _oms_get(self, path, params=None):
        url = self._oms_base() + path
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        tried = []
        for label, auth in self._oms_auth_candidates():
            req = urllib.request.Request(url, headers={
                "Authorization": auth,
                "User-Agent": self.dev_username,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=min(self.timeout, 15)) as r:
                    body = r.read().decode("utf-8", "replace")
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code == 401:
                    tried.append(label)
                    continue  # bu kimlik reddedildi, sıradakini dene
                raise HepsiburadaError(f"OMS HTTP {e.code} {path} -> {detail}")
            except urllib.error.URLError as e:
                raise HepsiburadaError(f"OMS baglanti hatasi {path}: {e}")
        raise HepsiburadaError(
            f"OMS 401 — denenen kimlik kombinasyonlarinin hepsi reddedildi ({', '.join(tried)}). "
            f"Hepsiburada OMS icin AYRI Entegrasyon Kullanici Adi/Sifre gerekiyor olabilir "
            f"(Merchant panel > Entegrasyon Bilgileri)."
        )

    def get_orders(self, begin_date=None, end_date=None, offset=0, limit=100):
        """Geçmiş sipariş kalemlerini tarih aralığına göre listeler.
        beginDate/endDate ISO-8601 (ör. 2026-06-01T00:00:00). OMS line-item bazlı döner."""
        params = {"offset": offset, "limit": limit, "beginDate": begin_date, "endDate": end_date}
        return self._oms_get(f"/orders/merchantid/{self.merchant_id}", params)

    def get_order_by_number(self, order_number):
        """Tek bir siparişi numarasına göre getirir."""
        on = urllib.parse.quote(str(order_number), safe="")
        return self._oms_get(f"/orders/merchantid/{self.merchant_id}/ordernumber/{on}")



