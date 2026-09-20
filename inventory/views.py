from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from inventory.services import (
    get_inventory_cost_value,
    get_machines_stock,
    get_potential_profit_margin,
    get_potential_sale_value,
    get_product_machine_stocks,
    get_total_stock,
    get_warehouse_stock,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale

from .forms import CategoryForm, ProductForm
from .models import Category, Product


def category_list(request):
    categories = Category.objects.annotate(product_count=Count("products")).order_by(
        "name"
    )

    return render(
        request,
        "inventory/category_list.html",
        {"categories": categories},
    )


def category_create(request):
    form = CategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La categoría se ha creado correctamente.")
        return redirect("inventory:category_list")

    return render(
        request,
        "inventory/category_form.html",
        {"form": form, "is_editing": False},
    )


def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    previous_vat_rate = category.default_vat_rate
    form = CategoryForm(request.POST or None, instance=category)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            category = form.save()

            if category.default_vat_rate != previous_vat_rate:
                category.products.filter(uses_category_vat=True).update(
                    vat_rate=category.default_vat_rate
                )

        messages.success(request, "La categoría se ha actualizado correctamente.")
        return redirect("inventory:category_list")

    return render(
        request,
        "inventory/category_form.html",
        {
            "form": form,
            "category": category,
            "is_editing": True,
        },
    )


def category_delete(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    category = get_object_or_404(Category, pk=pk)

    try:
        category.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar la categoría porque tiene productos asociados.",
        )
    else:
        messages.success(request, "La categoría se ha eliminado correctamente.")

    return redirect("inventory:category_list")


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("name")
    paginator = Paginator(products, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "inventory/product_list.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": query_params.urlencode(),
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )

    total_stock = get_total_stock(product)
    warehouse_stock = get_warehouse_stock(product)
    machines_stock = get_machines_stock(product)

    inventory_value = get_inventory_cost_value(product)

    potential_sale_value = get_potential_sale_value(product)

    profit_margin = get_potential_profit_margin(product)

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "is_edit": False,
            "total_stock": total_stock,
            "warehouse_stock": warehouse_stock,
            "machines_stock": machines_stock,
            "inventory_value": inventory_value,
            "potential_sale_value": (potential_sale_value),
            "profit_margin": profit_margin,
        },
    )


def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)

        if form.is_valid():
            product = form.save()

            return redirect(
                "inventory:product_detail",
                pk=product.pk,
            )
    else:
        form = ProductForm()

    category_vat_rates = {
        str(category.pk): str(category.default_vat_rate)
        for category in Category.objects.all()
    }

    return render(
        request,
        "inventory/product_form.html",
        {
            "form": form,
            "category_vat_rates": category_vat_rates,
        },
    )


def product_update(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )
    total_stock = get_total_stock(product)
    warehouse_stock = get_warehouse_stock(product)
    machines_stock = get_machines_stock(product)
    inventory_value = get_inventory_cost_value(product)

    potential_sale_value = get_potential_sale_value(product)
    profit_margin = get_potential_profit_margin(product)

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )

        if form.is_valid():
            form.save()

            return redirect(
                "inventory:product_detail",
                pk=product.pk,
            )

    else:
        form = ProductForm(
            instance=product,
        )

    category_vat_rates = {
        str(category.pk): str(category.default_vat_rate)
        for category in Category.objects.all()
    }

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "form": form,
            "is_edit": True,
            "category_vat_rates": category_vat_rates,
            "total_stock": total_stock,
            "warehouse_stock": warehouse_stock,
            "machines_stock": machines_stock,
            "inventory_value": inventory_value,
            "potential_sale_value": potential_sale_value,
            "profit_margin": profit_margin,
        },
    )


def product_stock_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )

    purchase_lines = (
        PurchaseLine.objects.filter(
            product=product,
            purchase__status=Purchase.Status.REGISTERED,
        )
        .select_related("purchase")
        .order_by(
            "-purchase__purchased_at",
            "-pk",
        )
    )

    replenishment_lines = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__status=(Replenishment.Status.REGISTERED),
        )
        .select_related(
            "replenishment",
            "replenishment__machine",
        )
        .order_by(
            "-replenishment__replenished_at",
            "-pk",
        )
    )
    sale_lines = (
        Sale.objects.filter(
            product=product,
            status=Sale.Status.RESOLVED,
        )
        .select_related("machine")
        .order_by(
            "-occurred_at",
            "-pk",
        )
    )

    return render(
        request,
        "inventory/product_stock_detail.html",
        {
            "product": product,
            "total_stock": get_total_stock(product),
            "warehouse_stock": get_warehouse_stock(product),
            "machines_stock": get_machines_stock(product),
            "machine_stocks": (get_product_machine_stocks(product)),
            "inventory_value": (get_inventory_cost_value(product)),
            "potential_sale_value": (get_potential_sale_value(product)),
            "sale_lines": sale_lines,
            "profit_margin": get_potential_profit_margin(product),
            "purchase_lines": purchase_lines,
            "replenishment_lines": replenishment_lines,
        },
    )


def inventory_overview(request):
    products = Product.objects.select_related("category").order_by("name")

    inventory_items = []

    total_units = 0
    warehouse_units = 0
    machines_units = 0

    total_inventory_value = Decimal("0.00")
    total_potential_sale_value = Decimal("0.00")

    for product in products:
        total_stock = get_total_stock(product)
        warehouse_stock = get_warehouse_stock(product)
        machines_stock = get_machines_stock(product)

        inventory_value = get_inventory_cost_value(product)
        potential_sale_value = get_potential_sale_value(product)

        inventory_items.append(
            {
                "product": product,
                "total_stock": total_stock,
                "warehouse_stock": warehouse_stock,
                "machines_stock": machines_stock,
                "average_cost": product.average_purchase_cost,
                "latest_cost": product.latest_purchase_cost,
                "inventory_value": inventory_value,
                "potential_sale_value": potential_sale_value,
            }
        )

        total_units += total_stock
        warehouse_units += warehouse_stock
        machines_units += machines_stock

        total_inventory_value += inventory_value
        total_potential_sale_value += potential_sale_value

    return render(
        request,
        "inventory/inventory_overview.html",
        {
            "inventory_items": inventory_items,
            "total_units": total_units,
            "warehouse_units": warehouse_units,
            "machines_units": machines_units,
            "total_inventory_value": total_inventory_value,
            "total_potential_sale_value": total_potential_sale_value,
        },
    )
