from decimal import Decimal

from django.db.models import IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce

from inventory.models import Product
from machines.models import Machine
from machines.services.pricing import (
    get_product_price_for_machine,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine


def get_total_stock(product):
    purchased_quantity = (
        PurchaseLine.objects.filter(
            product=product,
            purchase__status=Purchase.Status.REGISTERED,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return purchased_quantity


def get_warehouse_stock(product):
    purchased_quantity = get_total_stock(product)

    replenished_quantity = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__status=Replenishment.Status.REGISTERED,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return purchased_quantity - replenished_quantity


def get_machine_stock(product, machine):
    replenished_quantity = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__machine=machine,
            replenishment__status=Replenishment.Status.REGISTERED,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return replenished_quantity


def get_inventory_cost_value(product):
    stock = get_total_stock(product)
    average_cost = product.average_purchase_cost

    if average_cost is None:
        return Decimal("0.00")

    return stock * average_cost


def get_warehouse_stock_value(product):
    stock = get_warehouse_stock(product)
    average_cost = product.average_purchase_cost

    if average_cost is None:
        return Decimal("0.00")

    return stock * average_cost


def get_machine_stock_value(product, machine):
    stock = get_machine_stock(product, machine)
    average_cost = product.average_purchase_cost

    if average_cost is None:
        return Decimal("0.00")

    return stock * average_cost


def get_machines_stock(product):
    replenished_quantity = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__status=Replenishment.Status.REGISTERED,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return replenished_quantity


def get_product_machine_stocks(product):
    return (
        Machine.objects.annotate(
            product_stock=Coalesce(
                Sum(
                    "replenishments__lines__quantity",
                    filter=Q(
                        replenishments__status=Replenishment.Status.REGISTERED,
                        replenishments__lines__product=product,
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .filter(product_stock__gt=0)
        .order_by("identifier")
    )


def get_machine_product_stocks(machine):
    return (
        Product.objects.select_related("category")
        .annotate(
            machine_stock=Coalesce(
                Sum(
                    "replenishment_lines__quantity",
                    filter=Q(
                        replenishment_lines__replenishment__machine=machine,
                        replenishment_lines__replenishment__status=(
                            Replenishment.Status.REGISTERED
                        ),
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .filter(machine_stock__gt=0)
        .order_by("name")
    )


def get_potential_sale_value(product):
    warehouse_stock = get_warehouse_stock(product)

    value = Decimal(warehouse_stock) * product.default_sale_price

    machine_stocks = get_product_machine_stocks(product)

    for machine in machine_stocks:
        final_price = get_product_price_for_machine(
            machine,
            product,
        )

        value += Decimal(machine.product_stock) * final_price

    return value.quantize(Decimal("0.01"))
