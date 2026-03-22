from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid

# Helper function
def generate_id():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

# User Models
class UserBase(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_admin: bool = False

class UserCreate(UserBase):
    password: str

class User(UserBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    password_hash: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    is_active: bool = True

# Category Models
class CategoryBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    created_at: datetime = Field(default_factory=utc_now)

# Product Variant
class ProductVariant(BaseModel):
    id: str = Field(default_factory=generate_id)
    size: Optional[str] = None
    color: Optional[str] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    stock: int = 0
    price_adjustment: float = 0

# Product Models
class ProductBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    price: float
    sale_price: Optional[float] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    brand: str = "FACETTE"
    images: List[str] = []
    variants: List[ProductVariant] = []
    is_active: bool = True
    is_featured: bool = False
    is_new: bool = False
    stock: int = 0
    sku: Optional[str] = None
    barcode: Optional[str] = None
    weight: float = 0
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    technical_details: Dict[str, str] = {}
    size_chart_images: List[str] = []
    combo_product_ids: List[str] = []
    similar_product_ids: List[str] = []

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    view_count: int = 0

# Cart Item
class CartItem(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = 1
    price: float
    name: str
    image: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None

# Order Models
class OrderAddress(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: str
    address: str
    city: str
    district: str
    postal_code: Optional[str] = None

class OrderBase(BaseModel):
    user_id: Optional[str] = None
    items: List[CartItem]
    shipping_address: OrderAddress
    billing_address: Optional[OrderAddress] = None
    subtotal: float
    shipping_cost: float = 0
    discount: float = 0
    total: float
    payment_method: str  # credit_card, bank_transfer, cash_on_delivery
    notes: Optional[str] = None

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    order_number: str = Field(default_factory=lambda: f"FC{int(datetime.now().timestamp())}")
    status: str = "pending"  # pending, confirmed, preparing, shipped, delivered, cancelled
    payment_status: str = "pending"  # pending, paid, failed, refunded
    cargo_tracking: Optional[str] = None
    cargo_company: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

# Banner/Slider Models
class BannerBase(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    image_url: str
    video_url: Optional[str] = None
    link_url: Optional[str] = None
    position: str  # hero_slider, single_banner, double_banner, instashop
    sort_order: int = 0
    is_active: bool = True
    device: str = "all"  # all, mobile, desktop

class BannerCreate(BannerBase):
    pass

class Banner(BannerBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    created_at: datetime = Field(default_factory=utc_now)

# Homepage Block
class HomepageBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    type: str  # rotating_text, slider, single_banner, double_banner, product_slider, instashop
    title: Optional[str] = None
    content: Dict[str, Any] = {}
    sort_order: int = 0
    is_active: bool = True
    device: str = "all"

# Menu Item
class MenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    name: str
    url: str
    parent_id: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

# Settings
class SiteSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "main"
    site_name: str = "FACETTE"
    logo_url: str = ""
    favicon_url: str = ""
    free_shipping_limit: float = 500
    rotating_texts: List[str] = ["Yeni Sezon Ürünleri Keşfet", "500 TL Üzeri Ücretsiz Kargo", "Güvenli Alışveriş"]
    contact_email: str = ""
    contact_phone: str = ""
    address: str = ""
    social_links: Dict[str, str] = {}
    payment_methods: Dict[str, bool] = {"credit_card": True, "bank_transfer": True, "cash_on_delivery": True}

# Campaign
class Campaign(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    name: str
    type: str  # percentage, fixed, free_shipping, gift
    value: float = 0
    min_order_amount: float = 0
    code: Optional[str] = None
    start_date: datetime
    end_date: datetime
    is_active: bool = True
    usage_limit: int = 0
    used_count: int = 0

# Static Page
class StaticPage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=generate_id)
    title: str
    slug: str
    content: str
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utc_now)
