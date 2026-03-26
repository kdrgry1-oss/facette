"""
Trendyol API Client for advanced integrations.
Includes Product Category, Attribute, and Brand fetching.
"""
import base64
import logging
from typing import List, Dict, Optional, Any
import httpx

logger = logging.getLogger(__name__)

class TrendyolClient:
    def __init__(self, supplier_id: str, api_key: str, api_secret: str, mode: str = "live"):
        self.supplier_id = supplier_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode
        
        # Determine base URL based on mode
        if self.mode == "live":
            self.base_url = "https://apigw.trendyol.com/integration"
        else:
            self.base_url = "https://stageapigw.trendyol.com/integration"
            
        # Ensure credentials are provided
        if not self.supplier_id or not self.api_key or not self.api_secret:
            logger.warning("TrendyolClient initialized with missing credentials.")

    def _get_headers(self) -> Dict[str, str]:
        """Provides the Basic Auth headers necessary for Trendyol API."""
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        return {
            "Authorization": f"Basic {encoded_credentials}",
            "User-Agent": f"{self.supplier_id} - FacetteIntegration",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _async_get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Trendyol Category endpoints do not strictly require Auth, but we send it anyway
                # Some endpoints (like brands) might fail if Auth is not sent.
                headers = self._get_headers() if self.api_key else {}
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Trendyol API HTTP error on {endpoint}: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Trendyol API connection error on {endpoint}: {str(e)}")
                raise

    # ------------------ CATEGORIES ------------------

    async def get_categories(self) -> List[Dict]:
        """
        Fetches the entire category tree from Trendyol.
        Endpoint: GET /product/product-categories
        """
        data = await self._async_get("/product/product-categories")
        return data.get("categories", [])

    async def get_category_attributes(self, category_id: int) -> List[Dict]:
        """
        Fetches the required and optional attributes for a specific category.
        This includes size, color, waist, length, season, etc.
        Endpoint: GET /product/product-categories/{categoryId}/attributes
        """
        data = await self._async_get(f"/product/product-categories/{category_id}/attributes")
        return data.get("categoryAttributes", [])

    # ------------------ BRANDS ------------------

    async def get_brands(self, size: int = 500, page: int = 0) -> Dict:
        """
        Fetches brands from Trendyol, paginated.
        Endpoint: GET /brands/by-name?size={size}&page={page}
        Wait, standard endpoint is /brands. Let's use /brands
        """
        data = await self._async_get("/brands", params={"size": size, "page": page})
        return data
        
    # ------------------ ATTRIBUTES METADATA ------------------
    # Additional helpers to be added for endpoints like Providers, ShipmentProviders if needed.

    # ------------------ PRODUCTS ------------------

    async def create_products(self, items: List[Dict]) -> Dict:
        """
        Sends a batch of products to Trendyol.
        Endpoint: POST /suppliers/{supplierId}/v2/products
        """
        url = f"{self.base_url}/suppliers/{self.supplier_id}/v2/products"
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = self._get_headers()
            try:
                response = await client.post(url, headers=headers, json={"items": items})
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Trendyol Product Create Error: {e.response.text}")
                try:
                    return e.response.json()
                except:
                    raise
            except Exception as e:
                logger.error(f"Trendyol Product API Error: {str(e)}")
                raise

    async def get_batch_request_result(self, batch_request_id: str) -> Dict:
        """
        Checks the status of a batch request (e.g. product creation, price/inventory updates).
        Endpoint: GET /suppliers/{supplierId}/products/batch-requests/{batchRequestId}
        """
        url = f"{self.base_url}/suppliers/{self.supplier_id}/products/batch-requests/{batch_request_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = self._get_headers()
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Trendyol Batch Request Error for {batch_request_id}: {str(e)}")
                raise

    async def update_price_and_inventory(self, items: List[Dict]) -> Dict:
        """
        Updates price and stock for products by barcode.
        items format: [{"barcode": "123", "quantity": 10, "salePrice": 100, "listPrice": 120}, ...]
        Endpoint: POST /suppliers/{supplierId}/products/price-and-inventory
        """
        url = f"{self.base_url}/suppliers/{self.supplier_id}/products/price-and-inventory"
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = self._get_headers()
            try:
                response = await client.post(url, headers=headers, json={"items": items})
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Trendyol Price/Inventory Update Error: {e.response.text}")
                try:
                    return e.response.json()
                except:
                    raise
            except Exception as e:
                logger.error(f"Trendyol Price/Inventory API Error: {str(e)}")
                raise

    # ------------------ ORDERS ------------------

    async def get_orders(self, start_date_ms: int = None, end_date_ms: int = None, status: str = None, order_number: str = None, size: int = 50, page: int = 0) -> Dict:
        """
        Fetches orders from Trendyol.
        Endpoint: GET /order/sellers/{supplierId}/orders
        """
        url = f"{self.base_url}/order/sellers/{self.supplier_id}/orders"
        params = {"size": size, "page": page}
        if start_date_ms:
            params["startDate"] = start_date_ms
        if end_date_ms:
            params["endDate"] = end_date_ms
        if status:
            params["status"] = status
        if order_number:
            params["orderNumber"] = order_number
        else:
            # Sadece order_number yoksa siralamayi ekle, spesifik sipariste siralama istenmez
            params["orderByField"] = "PackageLastModifiedDate"
            params["orderByDirection"] = "DESC"
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = self._get_headers()
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Trendyol Get Orders Error: {e.response.text}")
                raise Exception(f"Trendyol API Error: {e.response.text}")
            except Exception as e:
                logger.error(f"Trendyol Get Orders API Error: {str(e)}")
                raise

    # ------------------ CARGO / SHIPMENT ------------------

    async def get_cargo_label(self, cargo_tracking_number: str) -> bytes:
        """
        Fetches the cargo label in PDF format as bytes.
        Endpoint: GET /suppliers/{supplierId}/common-label/{cargoTrackingNumber}?format=pdf
        """
        url = f"{self.base_url}/suppliers/{self.supplier_id}/common-label/{cargo_tracking_number}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = self._get_headers()
            try:
                response = await client.get(url, headers=headers, params={"format": "pdf"})
                response.raise_for_status()
                return response.content
            except Exception as e:
                logger.error(f"Trendyol Cargo Label Error for {cargo_tracking_number}: {str(e)}")
                raise
