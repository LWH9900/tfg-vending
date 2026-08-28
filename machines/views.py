from django.shortcuts import get_object_or_404, redirect, render

from inventory.services import get_machine_product_stocks

from .forms import (
    MachineForm,
    MachinePriceOverrideForm,
    MachinePriceOverrideUpdateForm,
    MachinePricingProfileForm,
    PricingProfileForm,
)
from .models import Machine, MachinePriceOverride, PricingProfile
from .services.pricing import (
    build_product_price_details,
    calculate_adjusted_price,
    change_machine_pricing_profile,
    get_redundant_price_overrides,
)


def build_machine_inventory_items(machine):
    machine_product_stocks = get_machine_product_stocks(machine)

    overrides = {
        override.product_id: override for override in machine.price_overrides.all()
    }

    items = []

    for product in machine_product_stocks:
        override = overrides.get(product.pk)

        price_details = build_product_price_details(
            machine,
            product,
            override,
        )

        items.append(
            {
                "product": product,
                "machine_stock": product.machine_stock,
                "potential_sale_value": (
                    product.machine_stock * price_details["final_price"]
                ),
                **price_details,
            }
        )

    return items


def machine_list(request):
    machines = Machine.objects.all().order_by("identifier")

    return render(
        request,
        "machines/machine_list.html",
        {"machines": machines},
    )


def machine_create(request):
    if request.method == "POST":
        form = MachineForm(request.POST)

        if form.is_valid():
            machine = form.save()

            return redirect(
                "machines:machine_detail",
                pk=machine.pk,
            )
    else:
        form = MachineForm()

    return render(
        request,
        "machines/machine_form.html",
        {
            "form": form,
            "is_editing": False,
        },
    )


def machine_update(request, pk):
    machine = get_object_or_404(Machine, pk=pk)

    if request.method == "POST":
        form = MachineForm(
            request.POST,
            instance=machine,
        )

        if form.is_valid():
            machine = form.save()

            return redirect(
                "machines:machine_detail",
                pk=machine.pk,
            )
    else:
        form = MachineForm(
            instance=machine,
        )

    return render(
        request,
        "machines/machine_form.html",
        {
            "form": form,
            "machine": machine,
            "is_editing": True,
        },
    )


def machine_detail(request, pk):
    machine = get_object_or_404(
        Machine.objects.select_related("pricing_profile"),
        pk=pk,
    )

    machine_inventory_items = build_machine_inventory_items(machine)

    overrides = list(
        machine.price_overrides.select_related(
            "product",
            "product__category",
        ).order_by("product__name")
    )

    price_overrides = [
        {
            "override": override,
            "effective_price": calculate_adjusted_price(
                override.product.default_sale_price,
                override.percentage_adjustment,
            ),
        }
        for override in overrides
    ]

    override_form = MachinePriceOverrideForm(
        machine=machine,
    )

    product_prices = {
        str(product.pk): str(product.default_sale_price)
        for product in override_form.fields["product"].queryset
    }

    pricing_profile_form = MachinePricingProfileForm(
        initial={
            "pricing_profile": machine.pricing_profile,
        }
    )

    return render(
        request,
        "machines/machine_detail.html",
        {
            "machine": machine,
            "price_overrides": price_overrides,
            "override_form": override_form,
            "pricing_profile_form": pricing_profile_form,
            "product_prices": product_prices,
            "machine_inventory_items": (machine_inventory_items),
        },
    )


def machine_price_override_create(request, pk):
    machine = get_object_or_404(
        Machine.objects.select_related("pricing_profile"),
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "machines:machine_detail",
            pk=machine.pk,
        )

    form = MachinePriceOverrideForm(
        request.POST,
        machine=machine,
    )

    if form.is_valid():
        form.save()

        return redirect(
            "machines:machine_detail",
            pk=machine.pk,
        )

    overrides = machine.price_overrides.select_related(
        "product",
        "product__category",
    ).order_by("product__name")

    price_overrides = [
        {
            "override": override,
            "effective_price": calculate_adjusted_price(
                override.product.default_sale_price,
                override.percentage_adjustment,
            ),
        }
        for override in overrides
    ]

    pricing_profile_form = MachinePricingProfileForm(
        initial={
            "pricing_profile": machine.pricing_profile,
        }
    )

    product_prices = {
        str(product.pk): str(product.default_sale_price)
        for product in form.fields["product"].queryset
    }
    machine_inventory_items = build_machine_inventory_items(machine)
    return render(
        request,
        "machines/machine_detail.html",
        {
            "machine": machine,
            "price_overrides": price_overrides,
            "override_form": form,
            "pricing_profile_form": pricing_profile_form,
            "product_prices": product_prices,
            "machine_inventory_items": (machine_inventory_items),
            "open_override_modal": True,
        },
    )


def machine_pricing_profile_update(request, pk):
    machine = get_object_or_404(
        Machine.objects.select_related("pricing_profile"),
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "machines:machine_detail",
            pk=machine.pk,
        )

    form = MachinePricingProfileForm(request.POST)

    if form.is_valid():
        pricing_profile = form.cleaned_data["pricing_profile"]

        redundant_overrides = get_redundant_price_overrides(
            machine,
            pricing_profile,
        )

        confirmed = request.POST.get("confirm_redundant_overrides") == "1"

        if redundant_overrides.exists() and not confirmed:
            overrides = machine.price_overrides.select_related(
                "product",
                "product__category",
            ).order_by("product__name")

            price_overrides = [
                {
                    "override": override,
                    "effective_price": calculate_adjusted_price(
                        override.product.default_sale_price,
                        override.percentage_adjustment,
                    ),
                }
                for override in overrides
            ]

            override_form = MachinePriceOverrideForm(
                machine=machine,
            )

            product_prices = {
                str(product.pk): str(product.default_sale_price)
                for product in override_form.fields["product"].queryset
            }
            machine_inventory_items = build_machine_inventory_items(machine)
            return render(
                request,
                "machines/machine_detail.html",
                {
                    "machine": machine,
                    "price_overrides": price_overrides,
                    "override_form": override_form,
                    "pricing_profile_form": form,
                    "product_prices": product_prices,
                    "machine_inventory_items": (machine_inventory_items),
                    "redundant_overrides": redundant_overrides,
                    "open_pricing_modal": True,
                },
            )

        change_machine_pricing_profile(
            machine,
            pricing_profile,
            remove_redundant_overrides=confirmed,
        )

    return redirect(
        "machines:machine_detail",
        pk=machine.pk,
    )


def machine_price_override_update(
    request,
    machine_pk,
    override_pk,
):
    machine = get_object_or_404(
        Machine.objects.select_related("pricing_profile"),
        pk=machine_pk,
    )

    override = get_object_or_404(
        MachinePriceOverride.objects.select_related(
            "product",
            "product__category",
        ),
        pk=override_pk,
        machine=machine,
    )

    if request.method != "POST":
        return redirect(
            "machines:machine_detail",
            pk=machine.pk,
        )

    form = MachinePriceOverrideUpdateForm(
        request.POST,
        instance=override,
    )

    if form.is_valid():
        form.save()

        return redirect(
            "machines:machine_detail",
            pk=machine.pk,
        )

    overrides = machine.price_overrides.select_related(
        "product",
        "product__category",
    ).order_by("product__name")

    price_overrides = [
        {
            "override": item,
            "effective_price": calculate_adjusted_price(
                item.product.default_sale_price,
                item.percentage_adjustment,
            ),
        }
        for item in overrides
    ]

    override_form = MachinePriceOverrideForm(
        machine=machine,
    )

    pricing_profile_form = MachinePricingProfileForm(
        initial={
            "pricing_profile": machine.pricing_profile,
        }
    )

    product_prices = {
        str(product.pk): str(product.default_sale_price)
        for product in override_form.fields["product"].queryset
    }
    machine_inventory_items = build_machine_inventory_items(machine)
    return render(
        request,
        "machines/machine_detail.html",
        {
            "machine": machine,
            "price_overrides": price_overrides,
            "override_form": override_form,
            "pricing_profile_form": pricing_profile_form,
            "product_prices": product_prices,
            "machine_inventory_items": (machine_inventory_items),
            "edit_override_form": form,
            "edit_override": override,
            "open_edit_override_modal": True,
        },
    )


def machine_price_override_delete(
    request,
    machine_pk,
    override_pk,
):
    machine = get_object_or_404(
        Machine,
        pk=machine_pk,
    )

    override = get_object_or_404(
        MachinePriceOverride,
        pk=override_pk,
        machine=machine,
    )

    if request.method == "POST":
        override.delete()

    return redirect(
        "machines:machine_detail",
        pk=machine.pk,
    )


def pricing_profile_list(request):
    pricing_profiles = PricingProfile.objects.prefetch_related("machines").order_by(
        "name"
    )

    pricing_profile_form = PricingProfileForm()

    return render(
        request,
        "machines/pricing_profile_list.html",
        {
            "pricing_profiles": pricing_profiles,
            "pricing_profile_form": pricing_profile_form,
        },
    )


def pricing_profile_create(request):
    if request.method != "POST":
        return redirect("machines:pricing_profile_list")

    form = PricingProfileForm(request.POST)

    if form.is_valid():
        form.save()

        return redirect("machines:pricing_profile_list")

    pricing_profiles = PricingProfile.objects.prefetch_related("machines").order_by(
        "name"
    )

    return render(
        request,
        "machines/pricing_profile_list.html",
        {
            "pricing_profiles": pricing_profiles,
            "pricing_profile_form": form,
            "open_pricing_profile_create_modal": True,
        },
    )


def pricing_profile_delete(request, pk):
    pricing_profile = get_object_or_404(
        PricingProfile,
        pk=pk,
    )

    if request.method != "POST":
        return redirect("machines:pricing_profile_list")

    if pricing_profile.machines.exists():
        return redirect("machines:pricing_profile_list")

    pricing_profile.delete()

    return redirect("machines:pricing_profile_list")
