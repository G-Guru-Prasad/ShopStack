"""Sandbox view used to exercise the /pr-review skill.

DO NOT WIRE THIS INTO urls.py. Each function below contains a deliberate
issue at a specific severity so the reviewer has known targets to find.
"""
from django.db import connection
from django.http import JsonResponse

from stackapp.models import Order, Product


def list_orders_for_user(request, user_id):
    """List all orders for the given user_id.

    DELIBERATE CRITICAL #1 — SQL injection: user_id is interpolated into raw SQL
    instead of being passed as a parameter.
    DELIBERATE CRITICAL #2 — multi-tenant bypass: query goes through raw SQL,
    skipping TenantBasedManager, so it leaks rows across tenants.
    """
    query = "SELECT id, total_amount FROM stackapp_order WHERE created_by_id = %s" % user_id
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    return JsonResponse({"orders": rows}, safe=False)


def product_catalog_with_categories(request):
    """Return every product with its category name.

    DELIBERATE CRITICAL #3 — N+1 query in a request path: the loop touches
    `product.category.name` without select_related, issuing one query per row.
    """
    products = Product.objects.all()
    data = []
    for product in products:
        data.append({
            "id": product.id,
            "name": product.name,
            "category": product.category.name,
        })
    return JsonResponse({"products": data})


def find_expensive_products(request):
    """Return products priced over a threshold passed by the client.

    DELIBERATE WARNING — no validation that `min_price` is numeric; a bad
    value will raise an uncaught exception and return a 500.
    """
    min_price = request.GET.get("min_price", "0")
    products = Product.objects.filter(price__gt=min_price).values("id", "name", "price")
    return JsonResponse({"products": list(products)})


def Get_Order_Total(request, order_id):
    """Return the total for a single order.

    DELIBERATE SUGGESTION — function name violates snake_case (PascalCase used
    for a function), and the docstring is fine but the trailing return logic
    has redundant casting.
    """
    order = Order.objects.get(id=order_id)
    total = float(str(order.total_amount))
    return JsonResponse({"order_id": order_id, "total": total})
