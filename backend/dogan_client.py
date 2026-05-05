"""
Doğan e-Dönüşüm Client - e-Fatura, e-Arşiv, e-İrsaliye
SOAP API integration with zeep
"""
import logging
from zeep import Client, Settings as ZeepSettings
from zeep.transports import Transport
from requests import Session
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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
        """Check if a VKN is registered for e-Fatura"""
        try:
            client = self._get_efatura_client()
            result = client.service.CheckUser(
                REQUEST_HEADER=self._make_header(),
                USER={"IDENTIFIER": vkn}
            )
            users = []
            if result:
                for u in result:
                    users.append({
                        "identifier": str(getattr(u, "IDENTIFIER", "")),
                        "alias": str(getattr(u, "ALIAS", "")),
                        "title": str(getattr(u, "TITLE", "")),
                        "type": str(getattr(u, "TYPE", "")),
                    })
            return {"success": True, "users": users, "is_efatura": len(users) > 0}
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
                              currency: str = "TRY",
                              kdv_rate: float = 20.0,
                              line_items: list = None,    # [{name, qty, unit_price, kdv_rate}]
                              shipping_cost: float = 0.0,
                              discount: float = 0.0,
                              note: str = "",
                              ) -> str:
        """Minimal UBL-TR 1.2 e-Arşiv Fatura XML üretici.
        
        Bireysel müşteri (TCKN 11 hane) ve kurumsal (VKN 10 hane) destekler.
        Tüm tutarlar KDV hariç. Satır toplamı + KDV + kargo - indirim = genel toplam.
        """
        from html import escape
        from datetime import datetime as _dt

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
        supplier_city = _s(supplier_city)
        supplier_tax_office = _s(supplier_tax_office)
        customer_phone = _s(customer_phone)
        customer_email = _s(customer_email)
        customer_street = _s(customer_street)
        customer_district = _s(customer_district)
        customer_city = _s(customer_city)
        customer_name = _s(customer_name)
        note = _s(note)

        # Satır kalemlerini hesapla — unitCode "NIU" (Number of International Units = Adet) UBL-TR standardı
        invoice_lines_xml = []
        line_subtotal = 0.0
        kdv_total = 0.0
        for idx, it in enumerate(line_items, start=1):
            qty = float(it.get("qty") or 1)
            unit_price = float(it.get("unit_price") or 0)
            line_amount = round(qty * unit_price, 2)
            li_kdv_rate = float(it.get("kdv_rate") if it.get("kdv_rate") is not None else kdv_rate)
            line_kdv = round(line_amount * li_kdv_rate / 100.0, 2)
            line_subtotal += line_amount
            kdv_total += line_kdv
            name = escape(it.get("name") or "Ürün")[:255]
            invoice_lines_xml.append(f"""<cac:InvoiceLine>
  <cbc:ID>{idx}</cbc:ID>
  <cbc:InvoicedQuantity unitCode="NIU">{qty:.4f}</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="{currency}">{line_amount:.2f}</cbc:LineExtensionAmount>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{line_amount:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{line_kdv:.2f}</cbc:TaxAmount>
      <cbc:Percent>{li_kdv_rate:.0f}</cbc:Percent>
      <cac:TaxCategory>
        <cac:TaxScheme><cbc:Name>KDV</cbc:Name><cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:Item><cbc:Name>{name}</cbc:Name></cac:Item>
  <cac:Price><cbc:PriceAmount currencyID="{currency}">{unit_price:.4f}</cbc:PriceAmount></cac:Price>
</cac:InvoiceLine>""")

        # Allowance / Charge: kargo ve indirim
        allowance_charges_xml = []
        if shipping_cost > 0:
            line_subtotal += shipping_cost
            allowance_charges_xml.append(f"""<cac:AllowanceCharge>
  <cbc:ChargeIndicator>true</cbc:ChargeIndicator>
  <cbc:AllowanceChargeReason>Kargo Bedeli</cbc:AllowanceChargeReason>
  <cbc:Amount currencyID="{currency}">{shipping_cost:.2f}</cbc:Amount>
</cac:AllowanceCharge>""")
        if discount > 0:
            line_subtotal -= discount
            allowance_charges_xml.append(f"""<cac:AllowanceCharge>
  <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
  <cbc:AllowanceChargeReason>İndirim</cbc:AllowanceChargeReason>
  <cbc:Amount currencyID="{currency}">{discount:.2f}</cbc:Amount>
</cac:AllowanceCharge>""")

        tax_inclusive_total = line_subtotal + kdv_total
        payable_amount = tax_inclusive_total

        # Customer party block
        customer_party_id_block = f'<cac:PartyIdentification><cbc:ID schemeID="{party_id_scheme}">{escape(customer_vkn_or_tckn)}</cbc:ID></cac:PartyIdentification>'
        if is_individual:
            # Bireysel: Person bloğu
            parts = (customer_name or "").strip().split(" ", 1)
            first_name = escape(parts[0])
            last_name = escape(parts[1] if len(parts) > 1 else "")
            customer_name_block = f'<cac:Person><cbc:FirstName>{first_name}</cbc:FirstName><cbc:FamilyName>{last_name}</cbc:FamilyName></cac:Person>'
            customer_legal_block = ""
        else:
            customer_name_block = ""
            customer_legal_block = f'<cac:PartyName><cbc:Name>{escape(customer_name)}</cbc:Name></cac:PartyName>'

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
  xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>EARSIVFATURA</cbc:ProfileID>
  <cbc:ID>{escape(invoice_number)}</cbc:ID>
  <cbc:CopyIndicator>false</cbc:CopyIndicator>
  <cbc:UUID>{escape(invoice_uuid)}</cbc:UUID>
  <cbc:IssueDate>{issue_date}</cbc:IssueDate>
  <cbc:IssueTime>{issue_time}</cbc:IssueTime>
  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
  <cbc:Note>{escape(note or 'e-Arşiv Fatura')}</cbc:Note>
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(line_items)}</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty>
    <cac:Party>
      {('<cbc:WebsiteURI>' + escape(supplier_website) + '</cbc:WebsiteURI>') if supplier_website else ''}
      <cac:PartyIdentification><cbc:ID schemeID="VKN">{escape(supplier_vkn)}</cbc:ID></cac:PartyIdentification>
      <cac:PartyName><cbc:Name>{escape(supplier_name)}</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>{escape(supplier_street or '-')}</cbc:StreetName>
        <cbc:CitySubdivisionName>{escape(supplier_district or '-')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(supplier_city or '-')}</cbc:CityName>
        <cac:Country><cbc:Name>{escape(supplier_country)}</cbc:Name></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>{escape(supplier_tax_office or '-')}</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>
      {('<cac:Contact>' + (('<cbc:Telephone>' + escape(supplier_phone) + '</cbc:Telephone>') if supplier_phone else '') + (('<cbc:ElectronicMail>' + escape(supplier_email) + '</cbc:ElectronicMail>') if supplier_email else '') + '</cac:Contact>') if (supplier_phone or supplier_email) else ''}
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      {customer_party_id_block}
      {customer_legal_block}
      <cac:PostalAddress>
        <cbc:StreetName>{escape(customer_street or '-')}</cbc:StreetName>
        <cbc:CitySubdivisionName>{escape(customer_district or '-')}</cbc:CitySubdivisionName>
        <cbc:CityName>{escape(customer_city or '-')}</cbc:CityName>
        <cac:Country><cbc:Name>{escape(customer_country)}</cbc:Name></cac:Country>
      </cac:PostalAddress>
      {customer_name_block}
      {('<cac:Contact>' + (('<cbc:Telephone>' + escape(customer_phone) + '</cbc:Telephone>') if customer_phone else '') + (('<cbc:ElectronicMail>' + escape(customer_email) + '</cbc:ElectronicMail>') if customer_email else '') + '</cac:Contact>') if (customer_phone or customer_email) else ''}
    </cac:Party>
  </cac:AccountingCustomerParty>
  {''.join(allowance_charges_xml)}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{kdv_total:.2f}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{currency}">{line_subtotal:.2f}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{currency}">{kdv_total:.2f}</cbc:TaxAmount>
      <cbc:Percent>{kdv_rate:.1f}</cbc:Percent>
      <cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name><cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal>
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

    def send_earsiv_invoice(self, ubl_xml: str, invoice_uuid: str = None) -> dict:
        """E-Arşiv faturayı Doğan e-Dönüşüm WriteToArchive ile gönderir.
        
        ⚠ Doğan canlı endpoint UBL'i ZIP içinde bekliyor (ElementType="ZIP").
        ZIP içinde tek bir XML dosyası: <invoice_uuid>.xml
        
        ⚠ Ayrıca Doğan asenkron işliyor — RETURN_CODE=0 sadece "request alındı"
        anlamında, UBL parse hatası varsa GetEArchiveInvoiceStatus ile öğrenilir.
        Bu fonksiyon 2 saniye bekledikten sonra status sorgusu yapar ve gerçek
        sonucu döner.
        
        ubl_xml: UTF-8 string UBL-TR 1.2 invoice XML.
        invoice_uuid: ZIP içindeki dosya adı (varsayılan random uuid).
        Returns: {success, code, message, status, status_desc, intl_txn_id, uuid}
        """
        try:
            import io, zipfile, uuid as _uuid, time
            client = self._get_earsiv_client()
            xml_bytes = ubl_xml.encode("utf-8")
            inv_uuid = invoice_uuid or str(_uuid.uuid4())

            # UBL'i ZIP'le
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{inv_uuid}.xml", xml_bytes)
            zip_bytes = zip_buf.getvalue()

            content_type = client.get_type("ns0:ArchiveInvoiceWriteContent")
            content = content_type(Elements=[{
                "ElementType": "ZIP",
                "ElementCount": 1,
                "ElementList": [zip_bytes],
            }])
            result = client.service.WriteToArchive(
                REQUEST_HEADER=self._make_header(compressed="N"),
                ArchiveInvoiceWriteContent=content,
            )
            from zeep.helpers import serialize_object
            ser = serialize_object(result) or {}

            # Önce ERROR_TYPE kontrol et
            err = ser.get("ERROR_TYPE") or {}
            err_code = err.get("ERROR_CODE") if err else None
            err_msg = err.get("ERROR_SHORT_DES") if err else None
            if err_code:
                return {
                    "success": False,
                    "code": str(err_code),
                    "message": str(err_msg or "Bilinmeyen hata"),
                    "raw": str(ser)[:1000],
                    "uuid": inv_uuid,
                }

            ret = ser.get("REQUEST_RETURN") or {}
            return_code = ret.get("RETURN_CODE")
            intl_txn_id = ret.get("INTL_TXN_ID")
            if str(return_code) != "0":
                return {
                    "success": False,
                    "code": str(return_code or ""),
                    "message": f"WriteToArchive RETURN_CODE={return_code}",
                    "intl_txn_id": str(intl_txn_id or ""),
                    "uuid": inv_uuid,
                    "raw": str(ser)[:500],
                }

            # ⚠ Doğan asenkron — status sorgusu ile gerçek sonucu öğren
            # İlk denemede genellikle "FATURA ID BULUNAMADI" döner; 5 sn aralıklarla 4 kez dene.
            status, status_desc, invoice_id = "", "", ""
            st_ser = {}
            for attempt in range(4):
                time.sleep(5 if attempt == 0 else 4)
                try:
                    st_result = client.service.GetEArchiveInvoiceStatus(
                        REQUEST_HEADER=self._make_header(compressed="N"),
                        UUID=[inv_uuid],
                    )
                    st_ser = serialize_object(st_result) or {}
                    invoices = st_ser.get("INVOICE") or []
                    if invoices:
                        hdr = (invoices[0] or {}).get("HEADER") or {}
                        status = str(hdr.get("STATUS") or "")
                        status_desc = str(hdr.get("STATUS_DESC") or "")
                        invoice_id = str(hdr.get("INVOICE_ID") or "")
                        # 200 = "FATURA ID BULUNAMADI" → henüz işlenmiyor → retry
                        # 300+ veya invoice_id dolu → final state
                        if invoice_id or (status and status != "200"):
                            break
                except Exception as se:
                    logger.warning(f"GetEArchiveInvoiceStatus attempt {attempt+1} error: {se}")

            # STATUS değerlendir:
            # - 200 + boş invoice_id → 4 deneme sonrası hala bulunamadı = UBL parse hatası
            # - invoice_id dolu veya status=300+/100 → başarı
            is_success = bool(invoice_id) or (status and status not in ("200", "1000"))
            return {
                "success": is_success,
                "code": status or "0",
                "message": status_desc or ("OK" if is_success else "Doğan kayıt bulunamadı (UBL parse hatası olabilir)"),
                "intl_txn_id": str(intl_txn_id or ""),
                "uuid": inv_uuid,
                "invoice_id": invoice_id,
                "status": status,
                "status_desc": status_desc,
                "raw": str(st_ser)[:500],
            }
        except Exception as e:
            logger.error(f"send_earsiv_invoice error: {e}")
            return {"success": False, "code": "", "message": str(e), "raw": ""}
