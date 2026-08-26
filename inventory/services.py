from decimal import Decimal

from django.db.models import Sum

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


def get_stock_value(product):
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