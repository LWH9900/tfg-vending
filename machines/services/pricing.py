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


def calculate_adjusted_price(
    base_price,
    percentage_adjustment,
):
    multiplier = Decimal("1") + (percentage_adjustment / Decimal("100"))

    return (base_price * multiplier).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def calculate_price_with_vat(
    price_excl_vat,
    vat_rate,
):
    multiplier = Decimal("1") + (vat_rate / Decimal("100"))

    return (price_excl_vat * multiplier).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def build_product_price_details(
    machine,
    product,
    override,
):
    base_price = product.default_sale_price

    if override is not None:
        percentage_adjustment = override.percentage_adjustment

        source = "override"

        description = (
            "Excepción específica para esta máquina: "
            f"{percentage_adjustment:+.2f} % "
            "sobre el precio base sin IVA."
        )

    elif machine.pricing_profile is not None:
        percentage_adjustment = machine.pricing_profile.percentage_adjustment

        source = "profile"

        description = (
            f'Tarifa "{machine.pricing_profile.name}": '
            f"{percentage_adjustment:+.2f} % "
            "sobre el precio base sin IVA."
        )

    else:
        percentage_adjustment = Decimal("0.00")

        source = "base"
        description = ""

    price_excl_vat = calculate_adjusted_price(
        base_price,
        percentage_adjustment,
    )

    adjustment_amount = price_excl_vat - base_price

    final_price = calculate_price_with_vat(
        price_excl_vat,
        product.vat_rate,
    )

    vat_amount = final_price - price_excl_vat

    return {
        "base_price": base_price,
        "adjustment_amount": (adjustment_amount),
        "adjustment_percentage": (percentage_adjustment),
        "price_excl_vat": (price_excl_vat),
        "vat_rate": product.vat_rate,
        "vat_amount": vat_amount,
        "final_price": final_price,
        "price_source": source,
        "adjustment_description": (description),
    }


def get_product_price_for_machine(
    machine,
    product,
):
    override = MachinePriceOverride.objects.filter(
        machine=machine,
        product=product,
    ).first()

    price_details = build_product_price_details(
        machine,
        product,
        override,
    )

    return price_details["final_price"]


def get_product_price_excl_vat_for_machine(
    machine,
    product,
):
    override = MachinePriceOverride.objects.filter(
        machine=machine,
        product=product,
    ).first()

    price_details = build_product_price_details(
        machine,
        product,
        override,
    )

    return price_details["price_excl_vat"]
