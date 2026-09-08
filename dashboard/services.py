from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from inventory.models import Product
from inventory.services import (
    get_inventory_cost_value,
    get_machines_stock,
    get_potential_sale_value,
    get_total_stock,
    get_warehouse_stock,
)
from sales.models import Sale


def _date_range(end_date, days):
    return end_date - timedelta(days=days - 1), end_date


def _daily_sales(start_date, end_date):
    sales = Sale.objects.filter(
        status=Sale.Status.RESOLVED,
        occurred_at__date__gte=start_date,
        occurred_at__date__lte=end_date,
    )

    grouped_sales = {
        row["day"]: row
        for row in sales.annotate(day=TruncDate("occurred_at"))
        .values("day")
        .annotate(
            units=Sum("quantity"),
            revenue=Sum("amount_received"),
        )
    }

    result = []
    current_day = start_date
    while current_day <= end_date:
        row = grouped_sales.get(current_day, {})
        result.append(
            {
                "date": current_day,
                "units": row.get("units") or 0,
                "revenue": row.get("revenue") or Decimal("0.00"),
            }
        )
        current_day += timedelta(days=1)

    return result


def _percentage_change(current, previous):
    if previous == 0:
        return None

    return ((Decimal(current - previous) / Decimal(previous)) * 100).quantize(
        Decimal("0.1")
    )


def _inventory_summary():
    products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("name", "pk")
    )

    total_units = 0
    warehouse_units = 0
    machine_units = 0
    inventory_value = Decimal("0.00")
    potential_sale_value = Decimal("0.00")

    for product in products:
        total_units += get_total_stock(product)
        warehouse_units += get_warehouse_stock(product)
        machine_units += get_machines_stock(product)
        inventory_value += get_inventory_cost_value(product)
        potential_sale_value += get_potential_sale_value(product)

    return {
        "total_units": total_units,
        "warehouse_units": warehouse_units,
        "machine_units": machine_units,
        "inventory_value": inventory_value,
        "potential_sale_value": potential_sale_value,
    }


def _top_products(start_date, end_date):
    return list(
        Sale.objects.filter(
            status=Sale.Status.RESOLVED,
            product__isnull=False,
            occurred_at__date__gte=start_date,
            occurred_at__date__lte=end_date,
        )
        .values(
            "product_id",
            "product__name",
            "product__category__name",
            "product__format_unit",
        )
        .annotate(units=Sum("quantity"))
        .order_by("-units", "product__name", "product_id")[:5]
    )


def _top_machines(start_date, end_date):
    return list(
        Sale.objects.filter(
            status=Sale.Status.RESOLVED,
            machine__isnull=False,
            occurred_at__date__gte=start_date,
            occurred_at__date__lte=end_date,
        )
        .values("machine_id", "machine__identifier")
        .annotate(units=Sum("quantity"))
        .order_by("-units", "machine__identifier", "machine_id")[:5]
    )


def get_dashboard_data(today=None):
    today = today or timezone.localdate()
    sales_start, sales_end = _date_range(today, 7)
    previous_start = sales_start - timedelta(days=7)
    previous_end = sales_start - timedelta(days=1)
    top_start, top_end = _date_range(today, 30)

    daily_sales = _daily_sales(sales_start, sales_end)
    previous_sales = _daily_sales(previous_start, previous_end)
    current_units = sum(day["units"] for day in daily_sales)
    previous_units = sum(day["units"] for day in previous_sales)
    current_revenue = sum((day["revenue"] for day in daily_sales), Decimal("0.00"))

    max_units = max((day["units"] for day in daily_sales), default=0)
    max_revenue = max((day["revenue"] for day in daily_sales), default=Decimal("0.00"))

    for day in daily_sales:
        day["units_percent"] = (day["units"] / max_units * 100) if max_units else 0
        day["revenue_percent"] = (
            (day["revenue"] / max_revenue * 100) if max_revenue else 0
        )

    inventory = _inventory_summary()
    pending_sales = Sale.objects.filter(status=Sale.Status.PENDING).count()
    conflict_sales = Sale.objects.filter(status=Sale.Status.CONFLICT).count()

    return {
        "today_units": next(
            (day["units"] for day in daily_sales if day["date"] == today),
            0,
        ),
        "week_units": current_units,
        "week_revenue": current_revenue,
        "week_start": sales_start,
        "week_end": sales_end,
        "week_units_change": _percentage_change(current_units, previous_units),
        "daily_sales": daily_sales,
        "top_products": _top_products(top_start, top_end),
        "top_machines": _top_machines(top_start, top_end),
        "inventory": inventory,
        "pending_sales": pending_sales,
        "conflict_sales": conflict_sales,
        "active_incidents": pending_sales + conflict_sales,
        "inventory_value": inventory["inventory_value"],
        "potential_sale_value": inventory["potential_sale_value"],
        "stock_total": inventory["total_units"],
        "max_revenue": max_revenue,
    }
