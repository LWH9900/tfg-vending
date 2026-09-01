import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.services import get_machine_product_stocks
from machines.forms import (
    MachineLayoutActivationForm,
    MachineLayoutForm,
    MachinePositionForm,
    MachinePositionFormSet,
)
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
    MachinePriceOverride,
    PricingProfile,
)
from machines.services.layouts import activate_machine_layout, get_machine_layout_at

from .forms import (
    MachineForm,
    MachinePriceOverrideForm,
    MachinePriceOverrideUpdateForm,
    MachinePricingProfileForm,
    PricingProfileForm,
)
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


def machine_layout_create(
    request,
    machine_pk,
):
    machine = get_object_or_404(
        Machine,
        pk=machine_pk,
    )

    grid_configured = machine.rows is not None and machine.columns is not None

    existing_layouts = machine.layouts.prefetch_related("positions__product").order_by(
        "name"
    )

    layout_templates = {}

    for existing_layout in existing_layouts:
        layout_templates[str(existing_layout.pk)] = [
            {
                "identifier": position.identifier,
                "product_id": (position.product_id if position.product_id else None),
                "row": position.row,
                "column": position.column,
                "width": position.width,
                "height": position.height,
            }
            for position in existing_layout.positions.all()
        ]

    grid_cells = []

    if grid_configured:
        grid_cells = [
            {
                "row": row,
                "column": column,
            }
            for row in range(1, machine.rows + 1)
            for column in range(1, machine.columns + 1)
        ]

    positions_json = "[]"

    selected_source_layout_id = None

    if request.method == "POST":
        form = MachineLayoutForm(
            request.POST,
            machine=machine,
        )
        source_layout_value = request.POST.get(
            "source_layout",
            "",
        )

        if source_layout_value.isdigit():
            selected_source_layout_id = int(source_layout_value)

        position_form = MachinePositionForm()

        positions_json = request.POST.get(
            "positions",
            "[]",
        )

        if not grid_configured:
            form.add_error(
                None,
                "La máquina debe tener una cuadrícula configurada.",
            )

        try:
            positions_data = json.loads(positions_json)
        except json.JSONDecodeError:
            positions_data = None

            form.add_error(
                None,
                "No se ha podido interpretar la configuración de posiciones.",
            )

        if form.is_valid() and positions_data is not None:
            try:
                with transaction.atomic():
                    layout = form.save(
                        commit=False,
                    )

                    layout.machine = machine
                    layout.status = MachineLayout.Status.DRAFT

                    layout.save()

                    for position_data in positions_data:
                        position = MachinePosition(
                            layout=layout,
                            identifier=position_data.get(
                                "identifier",
                                "",
                            ),
                            row=position_data.get("row"),
                            column=position_data.get("column"),
                            width=position_data.get(
                                "width",
                                1,
                            ),
                            height=position_data.get(
                                "height",
                                1,
                            ),
                            product_id=(position_data.get("product_id") or None),
                        )

                        position.save()

                return redirect(
                    "machines:machine_layout_detail",
                    pk=layout.pk,
                )

            except (
                ValidationError,
                TypeError,
                ValueError,
            ) as error:
                if isinstance(error, ValidationError):
                    message = " ".join(error.messages)
                else:
                    message = str(error)

                form.add_error(
                    None,
                    message,
                )

    else:
        form = MachineLayoutForm(
            machine=machine,
        )

        position_form = MachinePositionForm()

    return render(
        request,
        "machines/machine_layout_form.html",
        {
            "form": form,
            "position_form": position_form,
            "machine": machine,
            "grid_configured": grid_configured,
            "grid_cells": grid_cells,
            "existing_layouts": existing_layouts,
            "layout_templates": layout_templates,
            "positions_json": positions_json,
            "selected_source_layout_id": selected_source_layout_id,
            "is_editing": False,
        },
    )


def machine_layout_edit(request, pk):
    layout = get_object_or_404(
        MachineLayout.objects.select_related("machine"),
        pk=pk,
    )

    if layout.has_been_activated:
        raise PermissionDenied(
            "Una disposición que ya ha sido activada no puede modificarse."
        )

    if request.method == "POST":
        form = MachineLayoutForm(
            request.POST,
            instance=layout,
        )

        formset = MachinePositionFormSet(
            request.POST,
            instance=layout,
        )

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            messages.success(
                request,
                "La disposición se ha actualizado correctamente.",
            )

            return redirect(
                "machines:machine_detail",
                pk=layout.machine.pk,
            )
    else:
        form = MachineLayoutForm(
            instance=layout,
        )

        formset = MachinePositionFormSet(
            instance=layout,
        )

    return render(
        request,
        "machines/machine_layout_form.html",
        {
            "machine": layout.machine,
            "layout": layout,
            "form": form,
            "formset": formset,
            "is_edit": True,
        },
    )


def machine_layout_activate(request, pk):
    layout = get_object_or_404(
        MachineLayout.objects.select_related("machine"),
        pk=pk,
    )

    if request.method == "POST":
        form = MachineLayoutActivationForm(
            request.POST,
        )

        if form.is_valid():
            try:
                activate_machine_layout(
                    layout=layout,
                    effective_from=form.cleaned_data["effective_from"],
                )
            except ValidationError as exc:
                form.add_error(
                    None,
                    exc,
                )
            else:
                messages.success(
                    request,
                    "La disposición se ha activado correctamente.",
                )

                return redirect(
                    "machines:machine_detail",
                    pk=layout.machine.pk,
                )
    else:
        form = MachineLayoutActivationForm()

    return render(
        request,
        "machines/machine_layout_activate.html",
        {
            "machine": layout.machine,
            "layout": layout,
            "form": form,
        },
    )


def machine_layout_list(request, machine_pk):
    machine = get_object_or_404(
        Machine,
        pk=machine_pk,
    )

    now = timezone.now()

    layouts = list(
        machine.layouts.annotate(
            positions_count=Count(
                "positions",
                distinct=True,
            ),
            last_activation=Max(
                "activations__effective_from",
                filter=Q(
                    activations__effective_from__lte=now,
                ),
            ),
        ).order_by("name")
    )

    current_layout = get_machine_layout_at(
        machine,
        now,
    )

    for layout in layouts:
        layout.is_active = current_layout is not None and current_layout.pk == layout.pk

    return render(
        request,
        "machines/machine_layout_list.html",
        {
            "machine": machine,
            "layouts": layouts,
        },
    )


def machine_layout_detail(request, pk):
    layout = get_object_or_404(
        MachineLayout.objects.select_related("machine").prefetch_related(
            "positions__product"
        ),
        pk=pk,
    )

    positions = list(
        layout.positions.select_related("product").order_by(
            "row",
            "column",
            "identifier",
        )
    )

    now = timezone.now()

    current_layout = get_machine_layout_at(
        layout.machine,
        now,
    )

    is_active = current_layout is not None and current_layout.pk == layout.pk

    last_activation = (
        layout.activations.filter(
            effective_from__lte=now,
        )
        .order_by("-effective_from")
        .first()
    )

    grid_cells = []

    if layout.machine.rows and layout.machine.columns:
        grid_cells = [
            {
                "row": row,
                "column": column,
            }
            for row in range(1, layout.machine.rows + 1)
            for column in range(1, layout.machine.columns + 1)
        ]

    return render(
        request,
        "machines/machine_layout_detail.html",
        {
            "machine": layout.machine,
            "layout": layout,
            "positions": positions,
            "grid_cells": grid_cells,
            "is_active": is_active,
            "last_activation": last_activation,
        },
    )


def machine_layout_update(
    request,
    pk,
):
    layout = get_object_or_404(
        MachineLayout.objects.select_related("machine"),
        pk=pk,
    )

    machine = layout.machine

    if layout.status != MachineLayout.Status.DRAFT:
        raise PermissionDenied("Las disposiciones registradas no pueden modificarse.")

    grid_configured = machine.rows is not None and machine.columns is not None

    grid_cells = []

    if grid_configured:
        grid_cells = [
            {
                "row": row,
                "column": column,
            }
            for row in range(
                1,
                machine.rows + 1,
            )
            for column in range(
                1,
                machine.columns + 1,
            )
        ]

    position_form = MachinePositionForm()

    if request.method == "POST":
        form = MachineLayoutForm(
            request.POST,
            instance=layout,
            machine=machine,
        )

        positions_json = request.POST.get(
            "positions",
            "[]",
        )

        try:
            positions_data = json.loads(positions_json)

            if not isinstance(
                positions_data,
                list,
            ):
                raise ValueError("La configuración de posiciones no es válida.")

        except (
            json.JSONDecodeError,
            ValueError,
        ):
            positions_data = None

            form.add_error(
                None,
                "No se ha podido interpretar la configuración de posiciones.",
            )

        if form.is_valid() and positions_data is not None:
            try:
                with transaction.atomic():
                    layout = form.save()

                    layout.positions.all().delete()

                    for position_data in positions_data:
                        if not isinstance(
                            position_data,
                            dict,
                        ):
                            raise ValidationError(
                                "La configuración de una posición no es válida."
                            )

                        position = MachinePosition(
                            layout=layout,
                            identifier=position_data.get(
                                "identifier",
                                "",
                            ),
                            row=position_data.get("row"),
                            column=position_data.get("column"),
                            width=position_data.get(
                                "width",
                                1,
                            ),
                            height=position_data.get(
                                "height",
                                1,
                            ),
                            product_id=(position_data.get("product_id") or None),
                        )

                        position.save()

                return redirect(
                    "machines:machine_layout_detail",
                    pk=layout.pk,
                )

            except (
                ValidationError,
                TypeError,
                ValueError,
            ) as error:
                if isinstance(
                    error,
                    ValidationError,
                ):
                    message = " ".join(error.messages)
                else:
                    message = str(error)

                form.add_error(
                    None,
                    message,
                )

    else:
        form = MachineLayoutForm(
            instance=layout,
            machine=machine,
        )

        positions_json = json.dumps(
            [
                {
                    "identifier": position.identifier,
                    "product_id": position.product_id,
                    "row": position.row,
                    "column": position.column,
                    "width": position.width,
                    "height": position.height,
                }
                for position in layout.positions.all()
            ]
        )

    return render(
        request,
        "machines/machine_layout_form.html",
        {
            "form": form,
            "position_form": position_form,
            "machine": machine,
            "layout": layout,
            "grid_configured": grid_configured,
            "grid_cells": grid_cells,
            "positions_json": positions_json,
            "existing_layouts": [],
            "layout_templates": {},
            "selected_source_layout_id": None,
            "is_editing": True,
        },
    )
