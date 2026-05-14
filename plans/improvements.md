# ShopStack — Improvements & Next Steps

## What's Already Built

| Area | Status |
|---|---|
| Multi-tenant core (middleware, thread-locals, ORM manager) | Done |
| Models: Tenant, Category, Product, ProductVariant, Cart, CartItem, Address, Order, OrderItem, Payment, TenantUser | Done |
| REST APIs: products, categories, cart, cart items, orders, payments | Done |
| JWT Auth: register, login, logout, refresh, change password, password reset, `/me` | Done |
| UI Pages: login, dashboard, profile (MaterializeCSS templates) | Done (static only) |

---

## High Priority — Core Gaps

### 1. Address CRUD API
- No `/api/addresses/` endpoint exists
- Users cannot manage delivery addresses via API
- Need: list, create, update, delete, set default

### 2. Order Status Update API
- No endpoint to transition order status
- Flow: `PENDING → CONFIRMED → SHIPPED → DELIVERED / CANCELLED`
- Should be restricted to staff/admin role

### 3. Payment Confirmation API
- Payments can only be created as `PENDING`
- No way to mark a payment as `PAID` or `FAILED`
- Need a `PATCH /api/payments/<id>/` endpoint to update status and set `paid_at`

### 4. Stock Deduction on Order Placement
- `stock_qty` field exists on `ProductVariant` but is never decremented
- Should be deducted atomically inside the order placement transaction
- Should also block orders when `stock_qty` is 0

### 5. Password Reset Email
- Reset token is generated in `auth_views.py:95` but the link is built and discarded — never sent
- Need to integrate an email backend (SMTP or Django's console backend for dev)
- Send the reset link to the user's email

---

## Medium Priority — Feature Completeness

### 6. Product Images
- No image field on `Product` or `ProductVariant`
- Add an `image` field (FileField or URLField) and expose it in serializers

### 7. Product Search & Filters
- Only category filter currently exists on `/api/products/`
- Add: name search (`?search=`), price range (`?min_price=`, `?max_price=`), in-stock only (`?in_stock=true`)

### 8. Tenant Registration / Onboarding API
- No way to create a new `Tenant` via API — must be done through Django admin
- Add a public onboarding endpoint: `POST /api/tenants/register/`

### 9. User Roles in TenantUser
- `TenantUser` model exists but has no role field
- Add a `role` field (e.g. `admin`, `staff`, `customer`)
- Use roles to restrict order status updates and payment confirmation

### 10. Rate Limiting
- `throttle_scope = 'auth'` is set on auth views but no throttle classes are configured in `settings.py`
- Configure `DEFAULT_THROTTLE_CLASSES` and `DEFAULT_THROTTLE_RATES` in DRF settings

---

## Frontend — UI Pages Are Static Shells

### 11. Product Listing Page
- No HTML page to browse products
- Should call `GET /api/products/` and render with category filter support

### 12. Product Detail + Add to Cart Page
- Display product info, variants, price
- Call `POST /api/cart/items/` on add-to-cart

### 13. Cart & Checkout Page
- Show active cart items with quantities
- Allow quantity update (`PATCH /api/cart/items/<id>/`) and removal (`DELETE`)
- Checkout flow: select address → place order (`POST /api/orders/`)

### 14. Order History & Order Detail Page
- List past orders with status badges
- Detail view showing items, address, payment status

### 15. Connect Existing Pages to API
- Login, dashboard, and profile pages exist as static HTML shells
- Need JavaScript to call auth APIs and populate data

---

## Nice to Have

### 16. Coupon / Discount System
- No model or logic exists
- Add a `Coupon` model with code, discount type (flat/percent), expiry, usage limits
- Apply at cart or order level

### 17. Order Cancellation Logic
- `CANCELLED` status exists but no business rules
- Define: who can cancel, at what stages, stock reversal on cancellation, payment refund trigger

### 18. Webhook / Notification System
- No order status change notifications to users
- Options: Django signals → email, or a webhook model for tenant-configured endpoints

### 19. Django Admin Customization
- `admin.py` has minimal setup
- Register all models with `list_display`, `list_filter`, `search_fields` for operational use
