from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from inventory.services import (
    get_machines_stock,
    get_product_machine_stocks,
    get_stock_value,
    get_total_stock,
    get_warehouse_stock,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine

from .forms import ProductForm
from .models import Category, Product


def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    queryset = Product.objects.select_related(
        "category",
    ).filter(
        is_active=True,
    )

    if self.instance.pk and self.instance.product_id:
        queryset = Product.objects.select_related(
            "category",
        ).filter(Q(is_active=True) | Q(pk=self.instance.product_id))

    self.fields["product"].queryset = queryset.order_by(
        "name",
        "category__name",
        "format_unit",
    )


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "inventory/product_list.html",
        {"products": products},
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )
    total_stock = get_total_stock(product)
    warehouse_stock = get_warehouse_stock(product)
    machines_stock = get_machines_stock(product)

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "is_edit": False,
            "total_stock": total_stock,
            "warehouse_stock": warehouse_stock,
            "machines_stock": machines_stock,
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
        },
    )


def product_stock_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )

    total_stock = get_total_stock(product)
    warehouse_stock = get_warehouse_stock(product)
    machines_stock = get_machines_stock(product)

    machine_stocks = get_product_machine_stocks(product)

    purchase_lines = (
        PurchaseLine.objects.filter(
            product=product,
            purchase__status=Purchase.Status.REGISTERED,
        )
        .select_related("purchase")
        .order_by("-purchase__purchased_at", "-pk")
    )

    replenishment_lines = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__status=Replenishment.Status.REGISTERED,
        )
        .select_related(
            "replenishment",
            "replenishment__machine",
        )
        .order_by("-replenishment__replenished_at", "-pk")
    )

    return render(
        request,
        "inventory/product_stock_detail.html",
        {
            "product": product,
            "total_stock": total_stock,
            "warehouse_stock": warehouse_stock,
            "machines_stock": machines_stock,
            "machine_stocks": machine_stocks,
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
    total_value = 0

    for product in products:
        total_stock = get_total_stock(product)
        warehouse_stock = get_warehouse_stock(product)
        machines_stock = get_machines_stock(product)
        stock_value = get_stock_value(product)

        inventory_items.append(
            {
                "product": product,
                "total_stock": total_stock,
                "warehouse_stock": warehouse_stock,
                "machines_stock": machines_stock,
                "average_cost": product.average_purchase_cost,
                "latest_cost": product.latest_purchase_cost,
                "stock_value": stock_value,
            }
        )

        total_units += total_stock
        warehouse_units += warehouse_stock
        machines_units += machines_stock
        total_value += stock_value

    return render(
        request,
        "inventory/inventory_overview.html",
        {
            "inventory_items": inventory_items,
            "total_units": total_units,
            "warehouse_units": warehouse_units,
            "machines_units": machines_units,
            "total_value": total_value,
        },
    )
