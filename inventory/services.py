from decimal import Decimal

from django.db.models import (
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from inventory.models import Product
from machines.models import Machine
from machines.services.pricing import (
    calculate_price_with_vat,
    get_product_price_excl_vat_for_machine,
    get_product_price_for_machine,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale


def _has_stock_inconsistency(product):
    if get_warehouse_stock(product) < 0:
        return True

    return (
        get_product_machine_stocks(product)
        .filter(
            product_stock__lt=0,
        )
        .exists()
    )


def _get_purchased_quantity(product):
    return (
        PurchaseLine.objects.filter(
            product=product,
            purchase__status=Purchase.Status.REGISTERED,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )


def _get_sold_quantity(
    product,
    machine=None,
):
    sales = Sale.objects.filter(
        product=product,
        status=Sale.Status.RESOLVED,
    )

    if machine is not None:
        sales = sales.filter(
            machine=machine,
        )

    return sales.aggregate(total=Sum("quantity"))["total"] or 0


def get_total_stock(product):
    purchased_quantity = _get_purchased_quantity(product)

    sold_quantity = _get_sold_quantity(product)

    return purchased_quantity - sold_quantity


def get_warehouse_stock(product):
    purchased_quantity = _get_purchased_quantity(product)

    replenished_quantity = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__status=(Replenishment.Status.REGISTERED),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    return purchased_quantity - replenished_quantity


def get_products_with_warehouse_stock(queryset=None):
    if queryset is None:
        queryset = Product.objects.all()

    purchased_quantity_subquery = (
        PurchaseLine.objects.filter(
            product_id=OuterRef("pk"),
            purchase__status=Purchase.Status.REGISTERED,
        )
        .values("product_id")
        .annotate(
            total=Sum("quantity"),
        )
        .values("total")
    )

    replenished_quantity_subquery = (
        ReplenishmentLine.objects.filter(
            product_id=OuterRef("pk"),
            replenishment__status=Replenishment.Status.REGISTERED,
        )
        .values("product_id")
        .annotate(
            total=Sum("quantity"),
        )
        .values("total")
    )

    return queryset.annotate(
        purchased_quantity=Coalesce(
            Subquery(
                purchased_quantity_subquery,
                output_field=IntegerField(),
            ),
            Value(0),
            output_field=IntegerField(),
        ),
        replenished_quantity=Coalesce(
            Subquery(
                replenished_quantity_subquery,
                output_field=IntegerField(),
            ),
            Value(0),
            output_field=IntegerField(),
        ),
    ).annotate(
        warehouse_stock=(F("purchased_quantity") - F("replenished_quantity")),
    )


def get_machine_stock(
    product,
    machine,
):
    replenished_quantity = (
        ReplenishmentLine.objects.filter(
            product=product,
            replenishment__machine=machine,
            replenishment__status=(Replenishment.Status.REGISTERED),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    sold_quantity = _get_sold_quantity(
        product,
        machine,
    )

    return replenished_quantity - sold_quantity


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
            replenishment__status=(Replenishment.Status.REGISTERED),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )

    sold_quantity = _get_sold_quantity(product)

    return replenished_quantity - sold_quantity


def get_product_machine_stocks(
    product,
):
    sold_quantity_subquery = (
        Sale.objects.filter(
            machine_id=OuterRef("pk"),
            product=product,
            status=Sale.Status.RESOLVED,
        )
        .values("machine_id")
        .annotate(total=Sum("quantity"))
        .values("total")
    )

    return (
        Machine.objects.annotate(
            replenished_quantity=Coalesce(
                Sum(
                    "replenishments__lines__quantity",
                    filter=Q(
                        replenishments__status=(Replenishment.Status.REGISTERED),
                        replenishments__lines__product=product,
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
            sold_quantity=Coalesce(
                Subquery(
                    sold_quantity_subquery,
                    output_field=IntegerField(),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
        )
        .annotate(product_stock=(F("replenished_quantity") - F("sold_quantity")))
        .exclude(
            product_stock=0,
        )
        .order_by("identifier")
    )


def get_machine_product_stocks(
    machine,
):
    sold_quantity_subquery = (
        Sale.objects.filter(
            machine=machine,
            product_id=OuterRef("pk"),
            status=Sale.Status.RESOLVED,
        )
        .values("product_id")
        .annotate(total=Sum("quantity"))
        .values("total")
    )

    return (
        Product.objects.select_related("category")
        .annotate(
            replenished_quantity=Coalesce(
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
            ),
            sold_quantity=Coalesce(
                Subquery(
                    sold_quantity_subquery,
                    output_field=IntegerField(),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
        )
        .annotate(machine_stock=(F("replenished_quantity") - F("sold_quantity")))
        .exclude(
            machine_stock=0,
        )
        .order_by("name")
    )


def get_potential_sale_value(
    product,
):
    warehouse_stock = get_warehouse_stock(product)

    warehouse_sale_price = calculate_price_with_vat(
        product.default_sale_price,
        product.vat_rate,
    )

    value = (
        Decimal(
            max(
                warehouse_stock,
                0,
            )
        )
        * warehouse_sale_price
    )

    machine_stocks = get_product_machine_stocks(product)

    for machine in machine_stocks:
        final_price = get_product_price_for_machine(
            machine,
            product,
        )

        value += (
            Decimal(
                max(
                    machine.product_stock,
                    0,
                )
            )
            * final_price
        )

    return value.quantize(Decimal("0.01"))


def get_potential_sale_value_excl_vat(product):
    warehouse_stock = get_warehouse_stock(product)

    value = Decimal(max(warehouse_stock, 0)) * product.default_sale_price

    machine_stocks = get_product_machine_stocks(product)

    for machine in machine_stocks:
        price_excl_vat = get_product_price_excl_vat_for_machine(
            machine,
            product,
        )

        value += Decimal(max(machine.product_stock, 0)) * price_excl_vat

    return value.quantize(Decimal("0.01"))


def get_potential_profit_margin(product):
    if product.average_purchase_cost is None:
        return None

    if _has_stock_inconsistency(product):
        return None

    if get_total_stock(product) <= 0:
        return None

    potential_sale_value_excl_vat = get_potential_sale_value_excl_vat(product)

    if potential_sale_value_excl_vat <= 0:
        return None

    inventory_cost_value = get_inventory_cost_value(product)

    profit = potential_sale_value_excl_vat - inventory_cost_value

    return (profit / potential_sale_value_excl_vat * Decimal("100")).quantize(
        Decimal("0.01")
    )
