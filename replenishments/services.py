from inventory.services import get_machine_stock, get_warehouse_stock
from machines.services.layouts import get_machine_layout_at


def get_replenishment_stock_errors(replenishment):
    errors = []

    lines = replenishment.lines.select_related("product")

    for line in lines:
        available_stock = get_warehouse_stock(line.product)

        if line.quantity > available_stock:
            errors.append(
                {
                    "product": line.product,
                    "requested_quantity": line.quantity,
                    "available_stock": available_stock,
                }
            )

    return errors


def get_replenishment_layout_errors(
    replenishment,
):
    layout = get_machine_layout_at(
        replenishment.machine,
        replenishment.replenished_at,
    )

    if layout is None:
        return [
            {
                "code": "no_layout",
                "layout": None,
                "product": None,
            }
        ]

    layout_product_ids = set(
        layout.positions.filter(
            product__isnull=False,
        ).values_list(
            "product_id",
            flat=True,
        )
    )

    errors = []

    lines = replenishment.lines.select_related(
        "product",
        "product__category",
    )

    for line in lines:
        if line.product_id not in layout_product_ids:
            errors.append(
                {
                    "code": ("product_not_in_layout"),
                    "layout": layout,
                    "product": line.product,
                }
            )

    return errors


def get_replenishment_cancellation_stock_errors(replenishment):
    errors = []

    lines = replenishment.lines.select_related("product")

    for line in lines:
        current_stock = get_machine_stock(
            line.product,
            replenishment.machine,
        )

        resulting_stock = current_stock - line.quantity

        if resulting_stock < 0:
            errors.append(
                {
                    "product": line.product,
                    "current_stock": current_stock,
                    "replenishment_quantity": line.quantity,
                    "resulting_stock": resulting_stock,
                }
            )

    return errors
