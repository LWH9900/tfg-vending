from inventory.services import get_warehouse_stock


def get_purchase_cancellation_stock_errors(purchase):
    errors = []

    lines = purchase.lines.select_related("product")

    for line in lines:
        current_stock = get_warehouse_stock(line.product)

        resulting_stock = current_stock - line.quantity

        if resulting_stock < 0:
            errors.append(
                {
                    "product": line.product,
                    "current_stock": current_stock,
                    "purchase_quantity": line.quantity,
                    "resulting_stock": resulting_stock,
                }
            )

    return errors
