from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from machines.models import MachinePriceOverride


def get_redundant_price_overrides(machine, pricing_profile):
    if pricing_profile is None:
        return MachinePriceOverride.objects.none()

    return MachinePriceOverride.objects.filter(
        machine=machine,
        percentage_adjustment=pricing_profile.percentage_adjustment,
    ).select_related("product")


@transaction.atomic
def change_machine_pricing_profile(
    machine,
    pricing_profile,
    remove_redundant_overrides=False,
):
    redundant_overrides = get_redundant_price_overrides(
        machine,
        pricing_profile,
    )

    if redundant_overrides.exists() and not remove_redundant_overrides:
        return redundant_overrides

    if remove_redundant_overrides:
        redundant_overrides.delete()

    machine.pricing_profile = pricing_profile
    machine.save(update_fields=["pricing_profile"])

    return None


def calculate_adjusted_price(base_price, percentage_adjustment):
    multiplier = Decimal("1") + (percentage_adjustment / Decimal("100"))

    return (base_price * multiplier).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def get_product_price_for_machine(machine, product):
    override = MachinePriceOverride.objects.filter(
        machine=machine,
        product=product,
    ).first()

    if override:
        return calculate_adjusted_price(
            product.default_sale_price,
            override.percentage_adjustment,
        )

    if machine.pricing_profile:
        return calculate_adjusted_price(
            product.default_sale_price,
            machine.pricing_profile.percentage_adjustment,
        )

    return product.default_sale_price
