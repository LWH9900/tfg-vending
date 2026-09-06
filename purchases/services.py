from decimal import Decimal

from inventory.services import get_warehouse_stock
from machines.models import MachineLayoutActivation, MachinePriceOverride
from machines.services.pricing import build_product_price_details


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


def get_purchase_profitability_warning(
    purchase,
):
    losses = []
    product_summaries = []

    lines = purchase.lines.select_related(
        "product",
        "product__category",
    ).order_by("pk")

    for line in lines:
        active_activations = (
            MachineLayoutActivation.objects.filter(
                effective_to__isnull=True,
                layout__positions__product=(line.product),
            )
            .select_related(
                "layout",
                "layout__machine",
                "layout__machine__pricing_profile",
            )
            .distinct()
        )

        machines = [activation.layout.machine for activation in active_activations]

        if not machines:
            continue

        product_losses = []

        for machine in machines:
            override = MachinePriceOverride.objects.filter(
                machine=machine,
                product=line.product,
            ).first()

            price_details = build_product_price_details(
                machine,
                line.product,
                override,
            )

            sale_price_excl_vat = price_details["price_excl_vat"]

            purchase_price = line.unit_price_excl_vat

            if purchase_price <= sale_price_excl_vat:
                continue

            loss_per_unit = (purchase_price - sale_price_excl_vat).quantize(
                Decimal("0.01")
            )

            theoretical_line_loss = (loss_per_unit * line.quantity).quantize(
                Decimal("0.01")
            )

            loss = {
                "line": line,
                "product": line.product,
                "machine": machine,
                "quantity": line.quantity,
                "purchase_price_excl_vat": (purchase_price),
                "sale_price_excl_vat": (sale_price_excl_vat),
                "sale_price_incl_vat": (price_details["final_price"]),
                "loss_per_unit": (loss_per_unit),
                "theoretical_line_loss": (theoretical_line_loss),
            }

            product_losses.append(loss)

            losses.append(loss)

        if product_losses:
            product_summaries.append(
                {
                    "product": line.product,
                    "selling_machine_count": (len(machines)),
                    "loss_machine_count": (len(product_losses)),
                    "all_machines": (len(product_losses) == len(machines)),
                }
            )

    if not losses:
        return None

    affected_machine_ids = {loss["machine"].pk for loss in losses}

    all_machines_for_any_product = any(
        summary["all_machines"] for summary in product_summaries
    )

    show_modal = len(losses) > 3 or all_machines_for_any_product

    return {
        "losses": losses,
        "inline_losses": losses[:3],
        "product_summaries": (product_summaries),
        "loss_count": len(losses),
        "affected_machine_count": (len(affected_machine_ids)),
        "all_machines_for_any_product": (all_machines_for_any_product),
        "show_modal": show_modal,
    }
