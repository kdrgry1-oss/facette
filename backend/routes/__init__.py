# Routes package
from .auth import router as auth_router
from .products import router as products_router
from .orders import router as orders_router
from .categories import router as categories_router
from .banners import router as banners_router
from .cms import router as cms_router
from .integrations import router as integrations_router
from .admin import router as admin_router
from .customer import router as customer_router

__all__ = [
    "auth_router",
    "products_router", 
    "orders_router",
    "categories_router",
    "banners_router",
    "cms_router",
    "integrations_router",
    "admin_router",
    "customer_router",
]
