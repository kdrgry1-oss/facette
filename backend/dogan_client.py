"""
Doğan e-Dönüşüm Client - e-Fatura, e-Arşiv, e-İrsaliye
SOAP API integration with zeep
"""
import logging
import os
from zeep import Client, Settings as ZeepSettings
from zeep.transports import Transport
from requests import Session
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Doğan'ın kabul ettiği XSLT (Doğan örnek faturasından çıkarıldı, base64).
# UBL içinde AdditionalDocumentReference olarak gömülmeli, aksi halde
# Doğan "Gönderilen istek geçersizdir. Belge içerisinde şablon bulanamamıştır." (10013) hatası verir.
_XSLT_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "dogan_xslt_template.txt")
try:
    with open(_XSLT_TEMPLATE_PATH, "r", encoding="utf-8") as _f:
        DOGAN_XSLT_B64 = _f.read().strip()
except Exception as _e:  # noqa
    logger.warning(f"Doğan XSLT template not loaded: {_e}")
    DOGAN_XSLT_B64 = ""


class DoganClient:
    def __init__(self, username: str, password: str, is_test: bool = True):
        self.username = username
        self.password = password
        self.is_test = is_test
        self.session_id = None

        if is_test:
            self.auth_wsdl = "https://efaturatest.doganedonusum.com/AuthenticationWS?wsdl"
            self.efatura_wsdl = "https://efaturatest.doganedonusum.com/EFaturaOIB?wsdl"
            self.earsiv_wsdl = "https://efaturatest.doganedonusum.com:443/EIArchiveWS/EFaturaArchive?wsdl"
            self.eirsaliye_wsdl = "https://efaturatest.doganedonusum.com/EIrsaliyeWS/EIrsaliye?wsdl"
        else:
            # CANLI endpoint = connector.doganedonusum.com (Doğan müşteri yöneticisi tarafından sağlanan resmi URL'ler)
            self.auth_wsdl = "https://connector.doganedonusum.com/AuthenticationWS?wsdl"
            self.efatura_wsdl = "https://connector.doganedonusum.com/EFaturaOIB?wsdl"
            self.earsiv_wsdl = "https://connector.doganedonusum.com/EIArchiveWS/EFaturaArchive?wsdl"
            self.eirsaliye_wsdl = "https://connector.doganedonusum.com/EIrsaliyeWS/EIrsaliye?wsdl"

        session = Session()
        session.verify = True
        self.transport = Transport(session=session, timeout=30)
        self.zeep_settings = ZeepSettings(strict=False, xml_huge_tree=True)

    def login(self) -> str:
        """Authenticate and get session ID. Raises on failure."""
        try:
            client = Client(self.auth_wsdl, transport=self.transport, settings=self.zeep_settings)
            header = {"SESSION_ID": "", "APPLICATION_NAME": "FACETTE"}
            result = client.service.Login(
                REQUEST_HEADER=header,
                USER_NAME=self.username,
                PASSWORD=self.password
            )
            # Response: LoginResponse{SESSION_ID, ERROR_TYPE}
            err = None
            sid = None
            if hasattr(result, "__values__"):
                vals = dict(result.__values__)
                sid = vals.get("SESSION_ID")
                err = vals.get("ERROR_TYPE")
            else:
                sid = str(result) if result else None

            if err:
                err_dict = dict(err.__values__) if hasattr(err, "__values__") else {"ERROR_SHORT_DES": str(err)}
                code = err_dict.get("ERROR_CODE")
                msg = err_dict.get("ERROR_SHORT_DES") or err_dict.get("ERROR_LONG_DES") or "Login hatası"
                raise Exception(f"Doğan login {code}: {msg}")

            if not sid:
                raise Exception("SESSION_ID alınamadı")

            self.session_id = str(sid)
            logger.info(f"Doğan e-Dönüşüm login successful, session: {self.session_id[:20]}...")
            return self.session_id
        except Exception as e:
            logger.error(f"Doğan e-Dönüşüm login failed: {e}")
            raise

    def logout(self):
        """Close session"""
        if not self.session_id:
            return
        try:
            client = Client(self.auth_wsdl, transport=self.transport, settings=self.zeep_settings)
            header = {"SESSION_ID": self.session_id, "APPLICATION_NAME": "FACETTE"}
            client.service.Logout(REQUEST_HEADER=header)
            self.session_id = None
        except Exception as e:
            logger.warning(f"Doğan logout error: {e}")

    def _get_efatura_client(self):
        if not self.session_id:
            self.login()
        return Client(self.efatura_wsdl, transport=self.transport, settings=self.zeep_settings)

    def _get_earsiv_client(self):
        if not self.session_id:
            self.login()
        return Client(self.earsiv_wsdl, transport=self.transport, settings=self.zeep_settings)

    def _make_header(self, compressed="N"):
        return {
            "SESSION_ID": self.session_id,
            "APPLICATION_NAME": "FACETTE",
            "COMPRESSED": compressed,
        }

    def get_invoice_status(self, uuid: str) -> dict:
        """Get status of an invoice by UUID"""
        try:
            client = self._get_efatura_client()
            result = client.service.GetInvoiceStatus(
                REQUEST_HEADER=self._make_header(),
                INVOICE_SEARCH_KEY={"UUID": uuid}
            )
            return {"success": True, "status": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_user(self, vkn: str) -> dict:
        """Check if a VKN is registered for e-Fatura. Returns the user list with
        their PK aliases. is_efatura=True if INVOICE document_type alias exists.
        """
        try:
            from zeep.helpers import serialize_object
            client = self._get_efatura_client()
            result = client.service.CheckUser(
                REQUEST_HEADER=self._make_header(),
                USER={"IDENTIFIER": vkn}
            )
            ser = serialize_object(result) or {}
            # Response shape: {USER: [...], ERROR_TYPE: ...}
            user_list = ser.get("USER") or []
            users = []
            for u in user_list:
                if not u or not isinstance(u, dict):
                    continue
                users.append({
                    "identifier": str(u.get("IDENTIFIER") or ""),
                    "alias": str(u.get("ALIAS") or ""),
                    "title": str(u.get("TITLE") or ""),
                    "type": str(u.get("TYPE") or ""),
                    "unit": str(u.get("UNIT") or ""),
                    "document_type": str(u.get("DOCUMENT_TYPE") or ""),
                })
            # e-Fatura mükellefi sayılır: en az 1 INVOICE document_type'a sahip alias varsa
            invoice_users = [u for u in users if u.get("document_type") == "INVOICE" and u.get("alias")]
            return {
                "success": True,
                "users": users,
                "is_efatura": len(invoice_users) > 0,
                "invoice_alias": invoice_users[0]["alias"] if invoice_users else "",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "is_efatura": False}

    def test_connection(self) -> dict:
        """Test connection to Doğan e-Dönüşüm"""
        try:
            session_id = self.login()
            self.logout()
            return {"success": True, "message": "Bağlantı başarılı", "session_id": session_id[:20] + "..."}
        except Exception as e:
            return {"success": False, "message": f"Bağlantı hatası: {str(e)}"}

    # ═════════════════ UBL-TR e-Arşiv Fatura Üretimi ═════════════════════
    @staticmethod
    def build_earsiv_ubl_xml(*,
                              invoice_uuid: str,
                              invoice_number: str,
                              issue_date: str,            # YYYY-MM-DD
                              issue_time: str,            # HH:MM:SS
                              supplier_vkn: str,
                              supplier_name: str,
                              supplier_district: str = "",
                              supplier_city: str = "",
                              supplier_street: str = "",
                              supplier_country: str = "Türkiye",
                              supplier_tax_office: str = "",
                              supplier_phone: str = "",
                              supplier_email: str = "",
                              supplier_website: str = "",
                              customer_vkn_or_tckn: str,  # 11 haneli TCKN veya 10 haneli VKN
                              customer_name: str,
                              customer_district: str = "",
                              customer_city: str = "",
                              customer_street: str = "",
                              customer_country: str = "Türkiye",
                              customer_phone: str = "",
                              customer_email: str = "",
                              customer_tax_office: str = "",
                              currency: str = "TRY",
                              kdv_rate: float = 20.0,
                              line_items: list = None,    # [{name, qty, unit_price, kdv_rate, sku, note, barcode}]
                              shipping_cost: float = 0.0,
                              discount: float = 0.0,
                              note: str = "",
                              order_number: str = "",
                              payment_method: str = "",
                              carrier_vkn: str = "6080712084",
                              carrier_name: str = "MNG KARGO YURTİÇİ VE YURTDIŞI TAŞIMACILIK A.Ş.",
                              carrier_city: str = "İstanbul",
                              ) -> str:
        """UBL-TR 1.2 e-Arşiv Fatura XML üretici (Doğan e-Dönüşüm CANLI uyumlu).

        Bireysel müşteri (TCKN 11 hane) ve kurumsal (VKN 10 hane) destekler.
        FCT2026000011227.xml örnek dosyasına birebir şema uyumudur:
          • Tam namespace seti (ubltr, ds, xades, qdt, ccts, udt)
          • cac:Signature bloğu (UBL-TR'de zorunlu)
          • cac:AdditionalDocumentReference > SendingType=ELEKTRONIK
          • InvoicedQuantity unitCode="C62" (UBL-TR adet kodu)
          • cac:PaymentMeans, cac:Delivery (opsiyonel ama Doğan örneğinde mevcut)
          • SellersItemIdentification her satırda
        Tüm tutarlar KDV hariç. Satır toplamı + KDV + kargo - indirim = genel toplam.
        """
        from html import escape

        line_items = line_items or []
        is_individual = len(customer_vkn_or_tckn) == 11
        party_id_scheme = "TCKN" if is_individual else "VKN"

        # null/None safety — UBL'de "None" string'i şema hatası verir
        def _s(v):
            if v is None or str(v).lower() == "none":
                return ""
            return str(v).strip()

        supplier_phone = _s(supplier_phone)
        supplier_email = _s(supplier_email)
        supplier_website = _s(supplier_website)
        supplier_street = _s(supplier_street)
        supplier_district = _s(supplier_district)
        supplier_city = _s(supplier_city) or "İstanbul"
        supplier_tax_office = _s(supplier_tax_office) or "HALKALI VERGİ DAİRESİ BAŞKANLIĞI"
        customer_phone = _s(customer_phone)
        customer_email = _s(customer_email)
        customer_street = _s(customer_street)
        customer_district = _s(customer_district)
        customer_city = _s(customer_city) or "İstanbul"
        customer_name = _s(customer_name) or "Bireysel Müşteri"
        customer_tax_office = _s(customer_tax_office)
        note = _s(note)
        order_number = _s(order_number)
        payment_method = _s(payment_method) or "DIGER"

        # ─── InvoiceLine'lar — UBL-TR unitCode "C62" (Adet) ──────────────
        invoice_lines_xml = []
        line_subtotal = 0.0
        kdv_total = 0.0
        # KDV oranı bazlı gruplandırma (TaxTotal'da multi-subtotal için)
        kdv_groups = {}  # rate → {"taxable": x, "tax": y}

        for idx, it in enumerate(line_items, start=1):
            qty = float(it.get("qty") or 1)
            unit_price = float(it.get("unit_price") or 0)
            line_amount = round(qty * unit_price, 2)
            li_kdv_rate = float(it.get("kdv_rate") if it.get("kdv_rate") is not None else kdv_rate)
            line_kdv = round(line_amount * li_kdv_rate / 100.0, 2)
            line_subtotal += line_amount
            kdv_total += line_kdv
            grp = kdv_groups.setdefault(li_kdv_rate, {"taxable": 0.0, "tax": 0.0})
            grp["taxable"] += line_amount
            grp["tax"] += line_kdv

            name = escape((it.get("name") or "Ürün"))[:255]
            sku = escape(_s(it.get("sku") or it.get("product_code") or f"URN{idx:04d}"))
            li_note = escape(_s(it.get("note") or it.get("barcode") or ""))
            note_xml = f"<cbc:Note>{li_note}</cbc:Note>" if li_note else ""

            invoice_lines_xml.append(f"""<cac:InvoiceLine>
    <cbc:ID>{idx}</cbc:ID>
    {note_xml}
    <cbc:InvoicedQuantity unitCode="C62">{qty:g}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{line_amount:.2f}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{line_amount:.2f}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
        <cbc:Percent>{li_kdv_rate:g}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>{name}</cbc:Name>
      <cac:SellersItemIdentification>
        <cbc:ID>{sku}</cbc:ID>
      </cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{unit_price:.4f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>""")

        # Kargo bedeli — ayrı InvoiceLine olarak eklenir (sample böyle yapıyor)
        if shipping_cost > 0:
            sh_kdv_rate = 20.0
            sh_kdv = round(shipping_cost * sh_kdv_rate / 100.0, 2)
            sh_taxable = round(shipping_cost - sh_kdv, 2)
            kdv_total += sh_kdv
            line_subtotal += sh_taxable
            grp = kdv_groups.setdefault(sh_kdv_rate, {"taxable": 0.0, "tax": 0.0})
            grp["taxable"] += sh_taxable
            grp["tax"] += sh_kdv
            next_idx = len(line_items) + 1
            invoice_lines_xml.append(f"""<cac:InvoiceLine>
    <cbc:ID>{next_idx}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{sh_taxable:.2f}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{sh_kdv:.2f}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{sh_taxable:.2f}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{sh_kdv:.2f}</cbc:TaxAmount>
        <cbc:Percent>{sh_kdv_rate:g}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>KARGO</cbc:Name>
      <cac:SellersItemIdentification><cbc:ID>KARGO</cbc:ID></cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{sh_taxable:.4f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>""")

        # İndirim — AllowanceCharge bloğu (root seviyesinde, TaxTotal öncesinde)
        allowance_charges_xml = []
        if discount > 0:
            line_subtotal -= discount
            allowance_charges_xml.append(f"""<cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>İndirim</cbc:AllowanceChargeReason>
    <cbc:Amount currencyID="{currency}">{discount:.2f}</cbc:Amount>
  </cac:AllowanceCharge>""")

        tax_inclusive_total = round(line_subtotal + kdv_total, 2)
        payable_amount = tax_inclusive_total

        # KDV TaxSubtotal blokları (multi-rate destekler)
        tax_subtotals_xml = []
        for rate, grp in sorted(kdv_groups.items()):
            tax_subtotals_xml.append(f"""<cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{grp['taxable']:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{grp['tax']:.2f}</cbc:TaxAmount>
      <cbc:Percent>{rate:g}</cbc:Percent>
      <cac:TaxCategory>
        <cac:TaxScheme>
          <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
          <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
        </cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>""")

        # ─── AccountingCustomerParty ─────────────────────────────────────
        if is_individual:
            parts = (customer_name or "").strip().split(" ", 1)
            first_name = escape(parts[0])
            last_name = escape(parts[1] if len(parts) > 1 else parts[0])
            customer_name_block = f"""<cac:Person>
        <cbc:FirstName>{first_name}</cbc:FirstName>
        <cbc:FamilyName>{last_name}</cbc:FamilyName>
      </cac:Person>"""
            customer_legal_block = ""
            customer_tax_scheme_block = ""
        else:
            customer_name_block = ""
            customer_legal_block = f"""<cac:PartyName>
        <cbc:Name>{escape(customer_name)}</cbc:Name>
      </cac:PartyName>"""
            customer_tax_scheme_block = f"""<cac:PartyTaxScheme>
        <cac:TaxScheme>
          <cbc:Name>{escape(customer_tax_office or '-')}</cbc:Name>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>"""

        customer_contact_xml = ""
        if customer_phone or customer_email:
            tel_xml = f"<cbc:Telephone>{escape(customer_phone)}</cbc:Telephone>" if customer_phone else ""
            mail_xml = f"<cbc:ElectronicMail>{escape(customer_email)}</cbc:ElectronicMail>" if customer_email else ""
            customer_contact_xml = f"<cac:Contact>{tel_xml}{mail_xml}</cac:Contact>"
        else:
            customer_contact_xml = "<cac:Contact/>"

        # ─── Notlar (sample birden fazla Note kullanıyor) ────────────────
        notes_xml = []
        if order_number:
            notes_xml.append(f"<cbc:Note>{escape(order_number)}</cbc:Note>")
            notes_xml.append(f"<cbc:Note>Sipariş No: {escape(order_number)}</cbc:Note>")
        if customer_street:
            notes_xml.append(f"<cbc:Note>Taraf : Alıcı; {escape(customer_street)}</cbc:Note>")
            notes_xml.append(f"<cbc:Note>Delivery; {escape(customer_street)}</cbc:Note>")
        if note:
            notes_xml.append(f"<cbc:Note>{escape(note)}</cbc:Note>")
        notes_xml.append("<cbc:Note>Bu Satış Internet Üzerinden Yapılmıştır.</cbc:Note>")

        # ─── XML İskeleti ────────────────────────────────────────────────
        supplier_website_xml = (f"<cbc:WebsiteURI>{escape(supplier_website)}</cbc:WebsiteURI>"
                                if supplier_website else "")
        supplier_contact_xml = "<cac:Contact/>"
        if supplier_phone or supplier_email:
            tel_xml = f"<cbc:Telephone>{escape(supplier_phone)}</cbc:Telephone>" if supplier_phone else ""
            mail_xml = f"<cbc:ElectronicMail>{escape(supplier_email)}</cbc:ElectronicMail>" if supplier_email else ""
            supplier_contact_xml = f"<cac:Contact>{tel_xml}{mail_xml}</cac:Contact>"

        import uuid as _uuid
        xslt_ref_id = str(_uuid.uuid4())
        sending_ref_id = str(_uuid.uuid4())

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:qdt="urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2" xmlns:ccts="urn:un:unece:uncefact:documentation:2" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:ubltr="urn:oasis:names:specification:ubl:schema:xsd:TurkishCustomizationExtensionComponents" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:udt="urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 UBL-Invoice-2.1.xsd">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>EARSIVFATURA</cbc:ProfileID>
  <cbc:ID>{escape(invoice_number)}</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>{escape(invoice_uuid)}</cbc:UUID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:IssueTime>{issue_time}</cbc:IssueTime>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  {''.join(notes_xml)}
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(invoice_lines_xml)}</cbc:LineCountNumeric>
  <cac:AdditionalDocumentReference>
    <cbc:ID>{xslt_ref_id}</cbc:ID>
    <cbc:IssueDate>{issue_date}</cbc:IssueDate>
    <cbc:DocumentType>XSLT</cbc:DocumentType>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject characterSetCode="UTF-8" encodingCode="Base64" filename="{escape(invoice_number)}.xslt" mimeCode="application/CSTAdata+xml">{DOGAN_XSLT_B64}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
  <cac:AdditionalDocumentReference>
    <cbc:ID>{sending_ref_id}</cbc:ID>
    <cbc:IssueDate>{issue_date}</cbc:IssueDate>
    <cbc:DocumentTypeCode>SendingType</cbc:DocumentTypeCode>
    <cbc:DocumentType>ELEKTRONIK</cbc:DocumentType>
  </cac:AdditionalDocumentReference>
  <cac:Signature>
    <cbc:ID schemeID="VKN_TCKN">{escape(supplier_vkn)}</cbc:ID>
    <cac:SignatoryParty>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(supplier_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
        <cbc:CitySubdivisionName>{escape(supplier_district or 'Küçükçekmece')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(supplier_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>{escape(supplier_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cac:TaxScheme>
          <cbc:Name>{escape(supplier_tax_office)}</cbc:Name>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:Contact/>
    </cac:SignatoryParty>
    <cac:DigitalSignatureAttachment>
      <cac:ExternalReference>
        <cbc:URI>#Signature_{escape(invoice_number)}</cbc:URI>
      </cac:ExternalReference>
    </cac:DigitalSignatureAttachment>
  </cac:Signature>
  <cac:AccountingSupplierParty>
    <cac:Party>
      {supplier_website_xml}
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(supplier_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
        <cbc:CitySubdivisionName>{escape(supplier_district or 'Küçükçekmece')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(supplier_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>{escape(supplier_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cac:TaxScheme>
          <cbc:Name>{escape(supplier_tax_office)}</cbc:Name>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>
      {supplier_contact_xml}
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="{party_id_scheme}">{escape(customer_vkn_or_tckn)}</cbc:ID>
      </cac:PartyIdentification>
      {customer_legal_block}
      <cac:PostalAddress>
        <cbc:CitySubdivisionName>{escape(customer_district or '-')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(customer_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>{escape(customer_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      {customer_tax_scheme_block}
      {customer_contact_xml}
      {customer_name_block}
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:Delivery>
    <cac:CarrierParty>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(carrier_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(carrier_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:CitySubdivisionName/>
        <cbc:CityName>{escape(carrier_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>Türkiye</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
    </cac:CarrierParty>
    <cac:Despatch>
      <cbc:ActualDespatchDate>{issue_date}</cbc:ActualDespatchDate>
      <cbc:ActualDespatchTime>{issue_time}</cbc:ActualDespatchTime>
    </cac:Despatch>
  </cac:Delivery>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>1</cbc:PaymentMeansCode>
    <cbc:PaymentDueDate>{issue_date}</cbc:PaymentDueDate>
    <cbc:InstructionNote>Odeme Tipi : {escape(payment_method)} - Web Adresi : {escape(supplier_website or 'facette.com.tr')}</cbc:InstructionNote>
  </cac:PaymentMeans>
  {''.join(allowance_charges_xml)}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{kdv_total:.2f}</cbc:TaxAmount>
    {''.join(tax_subtotals_xml)}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{currency}">{line_subtotal:.2f}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{line_subtotal:.2f}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{currency}">{tax_inclusive_total:.2f}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{currency}">{payable_amount:.2f}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  {''.join(invoice_lines_xml)}
</Invoice>"""
        return xml

    # ═════════════════ UBL-TR e-Fatura (TEMELFATURA) Üretimi ════════════
    @staticmethod
    def build_efatura_ubl_xml(*,
                                invoice_uuid: str,
                                invoice_number: str,
                                issue_date: str,
                                issue_time: str,
                                supplier_vkn: str,
                                supplier_name: str,
                                supplier_district: str = "KÜÇÜKÇEKMECE",
                                supplier_city: str = "İstanbul",
                                supplier_country: str = "Türkiye",
                                supplier_tax_office: str = "HALKALI VERGİ DAİRESİ BAŞKANLIĞI",
                                supplier_website: str = "facette.com.tr",
                                customer_vkn: str,
                                customer_name: str,
                                customer_street: str = "",
                                customer_district: str = "",
                                customer_city: str = "İstanbul",
                                customer_postal_zone: str = "",
                                customer_country: str = "Türkiye",
                                customer_email: str = "",
                                currency: str = "TRY",
                                kdv_rate: float = 20.0,
                                line_items: list = None,
                                shipping_cost: float = 0.0,
                                discount: float = 0.0,
                                order_number: str = "",
                                order_date: str = "",
                                profile_id: str = "TEMELFATURA",
                                ) -> str:
        """UBL-TR 1.2 e-Fatura (TEMELFATURA) — kurumsal alıcılar için.

        Örnek EFC2026000000049.xml referansı:
          • ProfileID=TEMELFATURA
          • cac:OrderReference (sipariş no + tarih)
          • cac:BuyerCustomerParty (alıcı ayrı blok)
          • cac:Delivery>DeliveryAddress (CarrierParty yok)
          • cac:PaymentMeans yok
          • InvoiceLine: BuyersItemIdentification + SellersItemIdentification
          • Customer kesinlikle 10 haneli VKN olmalı
        """
        from html import escape
        import uuid as _uuid

        line_items = line_items or []
        if len(customer_vkn) != 10:
            raise ValueError(f"e-Fatura için 10 haneli VKN gerekli, alındı: {customer_vkn} ({len(customer_vkn)} hane)")

        def _s(v):
            if v is None or str(v).lower() == "none":
                return ""
            return str(v).strip()

        supplier_website = _s(supplier_website)
        customer_street = _s(customer_street)
        customer_district = _s(customer_district)
        customer_city = _s(customer_city) or "İstanbul"
        customer_postal_zone = _s(customer_postal_zone) or "34000"
        customer_email = _s(customer_email)
        customer_name = _s(customer_name) or "Müşteri"
        order_number = _s(order_number)
        order_date = _s(order_date) or issue_date

        # InvoiceLine'lar — C62 unitCode
        invoice_lines_xml = []
        line_subtotal = 0.0
        kdv_total = 0.0
        kdv_groups = {}
        for idx, it in enumerate(line_items, start=1):
            qty = float(it.get("qty") or 1)
            unit_price = float(it.get("unit_price") or 0)
            line_amount = round(qty * unit_price, 2)
            li_kdv_rate = float(it.get("kdv_rate") if it.get("kdv_rate") is not None else kdv_rate)
            line_kdv = round(line_amount * li_kdv_rate / 100.0, 2)
            line_subtotal += line_amount
            kdv_total += line_kdv
            grp = kdv_groups.setdefault(li_kdv_rate, {"taxable": 0.0, "tax": 0.0})
            grp["taxable"] += line_amount
            grp["tax"] += line_kdv

            name = escape((it.get("name") or "Ürün"))[:255]
            sku = escape(_s(it.get("sku") or it.get("product_code") or f"URN{idx:04d}"))
            buyer_sku = escape(_s(it.get("buyer_sku") or it.get("sku") or sku))
            li_note = escape(_s(it.get("note") or it.get("barcode") or ""))
            note_xml = f"<cbc:Note>{li_note}</cbc:Note>" if li_note else ""

            invoice_lines_xml.append(f"""<cac:InvoiceLine>
    <cbc:ID>{idx}</cbc:ID>
    {note_xml}
    <cbc:InvoicedQuantity unitCode="C62">{qty:g}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{line_amount:.2f}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{line_amount:.2f}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
        <cbc:Percent>{li_kdv_rate:g}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>{name}</cbc:Name>
      <cac:BuyersItemIdentification>
        <cbc:ID>{buyer_sku}</cbc:ID>
      </cac:BuyersItemIdentification>
      <cac:SellersItemIdentification>
        <cbc:ID>{sku}</cbc:ID>
      </cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{unit_price:.4f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>""")

        # Kargo ayrı satır olarak (e-Fatura'da da)
        if shipping_cost > 0:
            sh_kdv_rate = 20.0
            sh_kdv = round(shipping_cost * sh_kdv_rate / 100.0, 2)
            sh_taxable = round(shipping_cost - sh_kdv, 2)
            kdv_total += sh_kdv
            line_subtotal += sh_taxable
            grp = kdv_groups.setdefault(sh_kdv_rate, {"taxable": 0.0, "tax": 0.0})
            grp["taxable"] += sh_taxable
            grp["tax"] += sh_kdv
            invoice_lines_xml.append(f"""<cac:InvoiceLine>
    <cbc:ID>{len(line_items) + 1}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{currency}">{sh_taxable:.2f}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{currency}">{sh_kdv:.2f}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{currency}">{sh_taxable:.2f}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{currency}">{sh_kdv:.2f}</cbc:TaxAmount>
        <cbc:Percent>{sh_kdv_rate:g}</cbc:Percent>
        <cac:TaxCategory>
          <cac:TaxScheme>
            <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
            <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
          </cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Name>KARGO</cbc:Name>
      <cac:SellersItemIdentification><cbc:ID>KARGO</cbc:ID></cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{currency}">{sh_taxable:.4f}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>""")

        allowance_charges_xml = []
        if discount > 0:
            line_subtotal -= discount
            allowance_charges_xml.append(f"""<cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>İndirim</cbc:AllowanceChargeReason>
    <cbc:Amount currencyID="{currency}">{discount:.2f}</cbc:Amount>
  </cac:AllowanceCharge>""")

        tax_inclusive_total = round(line_subtotal + kdv_total, 2)

        tax_subtotals_xml = []
        for rate, grp in sorted(kdv_groups.items()):
            tax_subtotals_xml.append(f"""<cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{grp['taxable']:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{grp['tax']:.2f}</cbc:TaxAmount>
      <cbc:Percent>{rate:g}</cbc:Percent>
      <cac:TaxCategory>
        <cac:TaxScheme>
          <cbc:Name>GERÇEK USULDE KATMA DEĞER VERGİSİ</cbc:Name>
          <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
        </cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>""")

        notes_xml = []
        if order_number:
            notes_xml.append(f"<cbc:Note>{escape(order_number)}</cbc:Note>")
            notes_xml.append(f"<cbc:Note>Sipariş Numarası: {escape(order_number)}</cbc:Note>")
        notes_xml.append("<cbc:Note>Bu Satış İnternet Üzerinden Yapılmıştır</cbc:Note>")
        notes_xml.append(f"<cbc:Note>Web Adresi: {escape(supplier_website)}</cbc:Note>")
        if customer_street:
            notes_xml.append(f"<cbc:Note>Delivery; {escape(customer_street)}</cbc:Note>")

        xslt_ref_id = str(_uuid.uuid4())

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:qdt="urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2" xmlns:ccts="urn:un:unece:uncefact:documentation:2" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns:ubltr="urn:oasis:names:specification:ubl:schema:xsd:TurkishCustomizationExtensionComponents" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:udt="urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 UBL-Invoice-2.1.xsd">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>{escape(profile_id)}</cbc:ProfileID>
  <cbc:ID>{escape(invoice_number)}</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>{escape(invoice_uuid)}</cbc:UUID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:IssueTime>{issue_time}</cbc:IssueTime>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  {''.join(notes_xml)}
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(invoice_lines_xml)}</cbc:LineCountNumeric>
  <cac:OrderReference>
    <cbc:ID>{escape(order_number) or escape(invoice_number)}</cbc:ID>
    <cbc:IssueDate>{order_date}</cbc:IssueDate>
  </cac:OrderReference>
  <cac:AdditionalDocumentReference>
    <cbc:ID>{xslt_ref_id}</cbc:ID>
    <cbc:IssueDate>{issue_date}</cbc:IssueDate>
    <cbc:DocumentType>XSLT</cbc:DocumentType>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject characterSetCode="UTF-8" encodingCode="Base64" filename="{escape(invoice_number)}.xslt" mimeCode="application/CSTAdata+xml">{DOGAN_XSLT_B64}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
  <cac:Signature>
    <cbc:ID schemeID="VKN_TCKN">{escape(supplier_vkn)}</cbc:ID>
    <cac:SignatoryParty>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(supplier_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
        <cbc:CitySubdivisionName>{escape(supplier_district)}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(supplier_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>{escape(supplier_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cac:TaxScheme>
          <cbc:Name>{escape(supplier_tax_office)}</cbc:Name>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:Contact/>
    </cac:SignatoryParty>
    <cac:DigitalSignatureAttachment>
      <cac:ExternalReference>
        <cbc:URI>#Signature_{escape(invoice_number)}</cbc:URI>
      </cac:ExternalReference>
    </cac:DigitalSignatureAttachment>
  </cac:Signature>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(supplier_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID>
        <cbc:CitySubdivisionName>{escape(supplier_district)}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(supplier_city)}</cbc:CityName>
        <cac:Country>
          <cbc:Name>{escape(supplier_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cac:TaxScheme>
          <cbc:Name>{escape(supplier_tax_office)}</cbc:Name>
        </cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:Contact/>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(customer_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(customer_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>{escape(customer_street or '-')}</cbc:StreetName>
        <cbc:CitySubdivisionName>{escape(customer_district or '-')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(customer_city)}</cbc:CityName>
        <cbc:PostalZone>{escape(customer_postal_zone)}</cbc:PostalZone>
        <cac:Country>
          <cbc:Name>{escape(customer_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      {('<cac:Contact><cbc:ElectronicMail>' + escape(customer_email) + '</cbc:ElectronicMail></cac:Contact>') if customer_email else ''}
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:BuyerCustomerParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{escape(customer_vkn)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName>
        <cbc:Name>{escape(customer_name)}</cbc:Name>
      </cac:PartyName>
      <cac:PostalAddress>
        <cbc:ID schemeID="VKN">{escape(customer_vkn)}</cbc:ID>
        <cbc:StreetName>{escape(customer_street or '-')}</cbc:StreetName>
        <cbc:CitySubdivisionName>{escape(customer_district or '-')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(customer_city)}</cbc:CityName>
        <cbc:PostalZone>{escape(customer_postal_zone)}</cbc:PostalZone>
        <cac:Country>
          <cbc:Name>{escape(customer_country)}</cbc:Name>
        </cac:Country>
      </cac:PostalAddress>
      {('<cac:Contact><cbc:ElectronicMail>' + escape(customer_email) + '</cbc:ElectronicMail></cac:Contact>') if customer_email else ''}
    </cac:Party>
  </cac:BuyerCustomerParty>
  <cac:Delivery>
    <cac:DeliveryAddress>
      <cbc:CitySubdivisionName>{escape(customer_district or '-')}</cbc:CitySubdivisionName>
      <cbc:CityName>{escape(customer_city)}</cbc:CityName>
      <cbc:PostalZone>{escape(customer_postal_zone)}</cbc:PostalZone>
      <cac:Country>
        <cbc:Name>{escape(customer_country)}</cbc:Name>
      </cac:Country>
    </cac:DeliveryAddress>
  </cac:Delivery>
  {''.join(allowance_charges_xml)}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{kdv_total:.2f}</cbc:TaxAmount>
    {''.join(tax_subtotals_xml)}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{currency}">{line_subtotal:.2f}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{line_subtotal:.2f}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{currency}">{tax_inclusive_total:.2f}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{currency}">{tax_inclusive_total:.2f}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  {''.join(invoice_lines_xml)}
</Invoice>"""
        return xml

    def send_efatura_invoice(self, ubl_xml: str, invoice_uuid: str,
                              invoice_number: str,
                              receiver_vkn: str, receiver_alias: str,
                              sender_alias: str = "",
                              email_to: str = "") -> dict:
        """E-Faturayı Doğan EFaturaOIB.SendInvoice ile gönderir.

        Önemli: receiver_alias e-Fatura ataması (PK alias). check_user'dan dönen
        ilk user'ın alias'ı kullanılmalı (örn: "urn:mail:defaultpk@vkn.tr").
        sender_alias boşsa Doğan default'u kullanır.
        """
        try:
            client = self._get_efatura_client()
            xml_bytes = ubl_xml.encode("utf-8")
            mail_flag = "Y" if email_to else "N"
            mail_list = [email_to] if email_to else []

            invoice_obj = {
                "HEADER": {
                    "SENDER": self.username if not sender_alias else sender_alias,
                    "RECEIVER": receiver_alias,
                    "MAIL_FLAG": mail_flag,
                    "MAIL": mail_list,
                },
                "CONTENT": xml_bytes,
                "ID": invoice_number,
                "UUID": invoice_uuid,
            }

            result = client.service.SendInvoice(
                REQUEST_HEADER=self._make_header(compressed="N"),
                SENDER={"vkn": self.username, "alias": sender_alias or ""},
                RECEIVER={"vkn": receiver_vkn, "alias": receiver_alias},
                INVOICE=[invoice_obj],
            )
            from zeep.helpers import serialize_object
            ser = serialize_object(result) or {}

            err = ser.get("ERROR_TYPE") or {}
            err_code = err.get("ERROR_CODE") if err else None
            err_msg = err.get("ERROR_SHORT_DES") if err else None
            intl_txn_id = (err.get("INTL_TXN_ID") if err else None) or \
                          (ser.get("REQUEST_RETURN") or {}).get("INTL_TXN_ID")
            if err_code:
                return {
                    "success": False,
                    "code": str(err_code),
                    "message": str(err_msg or "Bilinmeyen hata"),
                    "intl_txn_id": str(intl_txn_id or ""),
                    "uuid": invoice_uuid,
                    "raw": str(ser)[:600],
                }

            invoice_id = ser.get("INVOICE_ID") or invoice_number
            return {
                "success": True,
                "code": "0",
                "message": "OK",
                "invoice_id": str(invoice_id),
                "intl_txn_id": str(intl_txn_id or ""),
                "uuid": invoice_uuid,
                "receiver_alias": receiver_alias,
                "raw": str(ser)[:300],
            }
        except Exception as e:
            logger.error(f"send_efatura_invoice error: {e}")
            return {"success": False, "code": "", "message": str(e), "raw": ""}

    def send_earsiv_invoice(self, ubl_xml: str, invoice_uuid: str = None,
                              email_to: str = "", archive_note: str = "") -> dict:
        """E-Arşiv faturayı Doğan WriteToArchiveExtended ile senkron olarak gönderir.

        WriteToArchiveExtended **senkron** çalışır ve INVOICE_ID/WEB_KEY'i ya da
        somut hata kodunu (ERROR_CODE/ERROR_SHORT_DES) anında döner. Bu sayede
        UBL parse / şema / şablon hatalarını anında görebiliriz.

        ubl_xml: UBL-TR 1.2 invoice XML (UTF-8 string, içinde XSLT gömülü olmalı).
        invoice_uuid: opsiyonel, sadece log için.
        email_to: dolu ise Doğan PDF'i bu adrese gönderir.
        Returns: {success, code, message, invoice_id, web_key, intl_txn_id, uuid}
        """
        try:
            client = self._get_earsiv_client()
            xml_bytes = ubl_xml.encode("utf-8")

            content_type = client.get_type("ns0:ArchiveInvoiceExtendedContent")
            earsiv_props = {
                "EARSIV_TYPE": "INTERNET",
                "EARSIV_EMAIL_FLAG": "Y" if email_to else "N",
                "EARCHIVE_TEST_FLAG": "Y" if self.is_test else "N",
                "VALIDATION_FLAG": "Y",
            }
            if email_to:
                earsiv_props["EARSIV_EMAIL"] = [email_to]

            content = content_type(INVOICE_PROPERTIES=[{
                "EARSIV_FLAG": "Y",
                "EARSIV_PROPERTIES": earsiv_props,
                "PDF_PROPERTIES": {
                    "EARSIV_PDF_FLAG": "Y",  # PDF üret
                    "PDF_SIGNATURE_FLAG": "Y",
                },
                "ARCHIVE_NOTE": (archive_note or "")[:200],
                "INVOICE_CONTENT": xml_bytes,
            }])

            result = client.service.WriteToArchiveExtended(
                REQUEST_HEADER=self._make_header(compressed="N"),
                ArchiveInvoiceExtendedContent=content,
            )
            from zeep.helpers import serialize_object
            ser = serialize_object(result) or {}

            err = ser.get("ERROR_TYPE") or {}
            err_code = err.get("ERROR_CODE") if err else None
            err_msg = err.get("ERROR_SHORT_DES") if err else None
            intl_txn_id = (err.get("INTL_TXN_ID") if err else None) or \
                          (ser.get("REQUEST_RETURN") or {}).get("INTL_TXN_ID")
            if err_code:
                return {
                    "success": False,
                    "code": str(err_code),
                    "message": str(err_msg or "Bilinmeyen hata"),
                    "intl_txn_id": str(intl_txn_id or ""),
                    "uuid": invoice_uuid or "",
                    "raw": str(ser)[:600],
                }

            invoice_id = ser.get("INVOICE_ID") or ""
            web_key = ser.get("WEB_KEY") or ""
            return {
                "success": True,
                "code": "0",
                "message": "OK",
                "invoice_id": str(invoice_id),
                "web_key": str(web_key),
                "intl_txn_id": str(intl_txn_id or ""),
                "uuid": invoice_uuid or "",
                "raw": str(ser)[:300],
            }
        except Exception as e:
            logger.error(f"send_earsiv_invoice error: {e}")
            return {"success": False, "code": "", "message": str(e), "raw": ""}
