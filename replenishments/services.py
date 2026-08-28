from inventory.services import get_warehouse_stock


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
