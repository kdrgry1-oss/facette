# FACETTE E-Commerce Platform PRD

## Original Problem Statement
Kullanıcı, facette.com.tr, zara.com, suudcollection.com ve fahhar.com'dan ilham alan kapsamlı bir e-ticaret platformu istemektedir. Platform, ticimax.com/e-ticaret-paketleri/ adresindeki özellikleri içermeli ve tam kapsamlı bir admin paneli ile yönetilebilir olmalıdır.

## Tech Stack
- **Frontend**: React 18, Tailwind CSS, Shadcn/UI, Lucide Icons, React Router v6
- **Backend**: FastAPI (Python 3.11), Motor (async MongoDB driver)
- **Database**: MongoDB
- **Authentication**: JWT-based auth

## Core Requirements

### P0 - MVP Features (COMPLETED)
- [x] Homepage with hero slider, category banners, product grids
- [x] Product listing with filters and search
- [x] Product detail page with size selection, gallery, add to cart
- [x] Shopping cart with drawer functionality
- [x] User authentication (login/register)
- [x] Admin panel with dashboard
- [x] Admin product management (CRUD, XML import)
- [x] Admin category, banner, campaign, pages management
- [x] 246 products imported from facette.com.tr XML

### P1 - Next Phase
- [ ] Advanced search with autocomplete
- [ ] Mega menu with images
- [ ] Checkout flow with address management
- [ ] Order management for customers
- [ ] "Complete the Look" product combinations
- [ ] Similar products recommendations
- [ ] Social proof notifications (recent purchases)

### P2 - Future Integrations
- [ ] Iyzico payment integration
- [ ] MNG/DHL shipping integration
- [ ] Netgsm SMS integration
- [ ] Trendyol API (product sync, reviews)
- [ ] GIB e-invoice integration
- [ ] Email notifications for orders

## API Endpoints

### Authentication
- POST /api/auth/register - User registration
- POST /api/auth/login - User login
- GET /api/auth/me - Get current user

### Products
- GET /api/products - List products with filters
- GET /api/products/{slug} - Get product by slug
- POST /api/products - Create product (admin)
- PUT /api/products/{id} - Update product (admin)
- DELETE /api/products/{id} - Delete product (admin)

### Categories
- GET /api/categories - List all categories
- POST /api/categories - Create category (admin)

### Orders
- GET /api/orders - List orders (admin: all, user: own)
- POST /api/orders - Create order
- PUT /api/orders/{id}/status - Update order status (admin)

### Banners
- GET /api/banners - List banners
- POST /api/banners - Create banner (admin)

### Reports
- GET /api/reports/dashboard - Admin dashboard stats

### Import
- POST /api/import/xml - Import products from XML URL (admin)

## Database Collections
- users
- products
- categories
- orders
- banners
- menu_items
- pages
- campaigns
- settings

## Test Credentials
- Admin: admin@facette.com / admin123

## Current Status
**MVP COMPLETE** - E-commerce platform is fully functional with:
- 246 products imported and displayed
- Working shopping cart
- Admin panel with full CRUD operations
- Hero slider with 3 banners
- Category navigation
- Search functionality

## Known Issues
1. Category banner images need to be uploaded (currently showing gray placeholders)
2. Search URL redirect: /ara should redirect to /arama

## Files Structure
```
/app/
├── backend/
│   ├── server.py - Main FastAPI application
│   ├── models.py - Pydantic models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js - Main React app with routing
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Category.jsx
│   │   │   ├── ProductDetail.jsx
│   │   │   ├── Cart.jsx
│   │   │   ├── Checkout.jsx
│   │   │   ├── Search.jsx
│   │   │   ├── Login.jsx
│   │   │   ├── Account.jsx
│   │   │   └── admin/
│   │   │       ├── AdminLayout.jsx
│   │   │       ├── Dashboard.jsx
│   │   │       ├── Products.jsx
│   │   │       ├── Orders.jsx
│   │   │       └── ...
│   │   ├── components/
│   │   │   ├── Header.jsx
│   │   │   ├── Footer.jsx
│   │   │   ├── ProductCard.jsx
│   │   │   └── CartDrawer.jsx
│   │   └── context/
│   │       ├── AuthContext.jsx
│   │       └── CartContext.jsx
│   └── package.json
└── memory/
    └── PRD.md
```

## Last Updated
2026-03-22
