from django.shortcuts import get_object_or_404, redirect, render

from .forms import MachineForm
from .models import Machine
from .services.pricing import calculate_adjusted_price


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

    overrides = machine.price_overrides.select_related("product").order_by(
        "product__name"
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

    return render(
        request,
        "machines/machine_detail.html",
        {
            "machine": machine,
            "price_overrides": price_overrides,
        },
    )
