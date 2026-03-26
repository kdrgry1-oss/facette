# Facette E-Commerce PRD

## Problem Statement
Facette e-ticaret uygulaması - React + FastAPI + MongoDB tabanlı admin paneli ve mağaza yönetimi. Trendyol entegrasyonu, ürün yönetimi, stok takibi, sipariş yönetimi ve toplu işlem özellikleri.

## Core Requirements
1. Ürün yönetimi (CRUD, varyantlar, özellikler, fiyatlandırma)
2. Trendyol entegrasyonu (kategori/özellik eşleştirme, ürün aktarma)
3. Cariler (Tedarikçi/Üretici) yönetimi
4. Global ayarlar (KDV, kâr oranı)
5. Excel toplu import/export

## Architecture
- Frontend: React, Tailwind CSS, Shadcn/UI, Lucide icons
- Backend: FastAPI, Motor (Async MongoDB)
- DB: MongoDB (test_database)
- Routes: /api prefix, Turkish URL slugs (/admin/urunler)

## Key DB Collections
- products, categories, settings, trendyol_categories, attribute_library, vendors, variant_options

## Completed Features
- [2026-03-25] MongoDB data restore (290 products, 34 categories)
- [2026-03-25] Stock code visibility fix
- [2026-03-25] Global Markup & VAT rate reflection in product form
- [2026-03-25] Vendors (Cariler) module - full CRUD
- [2026-03-25] Trendyol category/attribute sync
- [2026-03-25] Required Trendyol attributes highlighted in red
- [2026-03-25] Auto-match button for category attribute mapping
- [2026-03-25] 4-digit attribute IDs
- [2026-03-25] Variant (Size/Color) dropdown UX improvements
- [2026-03-26] Excel Technical Details Import - Upload xlsx, match products by name, apply attributes (126/126 matched)

## Credentials
- Admin: admin@facette.com / admin123

## Backlog (P0-P2)
- P1: All search dropdowns UX consistency check
- P2: Trendyol product export end-to-end testing
- P2: Products.jsx refactoring (2000+ lines → modular components)
- P2: File/directory structure cleanup
