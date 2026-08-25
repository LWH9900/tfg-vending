from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ReplenishmentFilterForm,
    ReplenishmentForm,
    ReplenishmentLineFormSet,
)
from .models import Replenishment


def replenishment_list(request):
    replenishments = (
        Replenishment.objects.select_related("machine")
        .prefetch_related("lines")
        .order_by("-replenished_at", "-pk")
    )

    filter_form = ReplenishmentFilterForm(request.GET)

    if filter_form.is_valid():
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")
        machine = filter_form.cleaned_data.get("machine")
        product = filter_form.cleaned_data.get("product")

        if date_from:
            replenishments = replenishments.filter(replenished_at__date__gte=date_from)

        if date_to:
            replenishments = replenishments.filter(replenished_at__date__lte=date_to)

        if machine:
            replenishments = replenishments.filter(machine=machine)

        if product:
            replenishments = replenishments.filter(lines__product=product)

    replenishments = replenishments.distinct()

    return render(
        request,
        "replenishments/replenishment_list.html",
        {
            "replenishments": replenishments,
            "filter_form": filter_form,
        },
    )


def replenishment_detail(request, pk):
    replenishment = get_object_or_404(
        Replenishment.objects.select_related("machine").prefetch_related(
            "lines__product",
            "lines__product__category",
        ),
        pk=pk,
    )

    return render(
        request,
        "replenishments/replenishment_detail.html",
        {
            "replenishment": replenishment,
        },
    )


def replenishment_create(request):
    replenishment = Replenishment()

    if request.method == "POST":
        form = ReplenishmentForm(
            request.POST,
            instance=replenishment,
        )

        formset = ReplenishmentLineFormSet(
            request.POST,
            instance=replenishment,
        )

        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()

        if form_is_valid and formset_is_valid:
            with transaction.atomic():
                replenishment = form.save()

                formset.instance = replenishment
                formset.save()

            return redirect(
                "replenishments:replenishment_detail",
                pk=replenishment.pk,
            )

    else:
        form = ReplenishmentForm(
            instance=replenishment,
        )

        formset = ReplenishmentLineFormSet(
            instance=replenishment,
        )

    return render(
        request,
        "replenishments/replenishment_form.html",
        {
            "form": form,
            "formset": formset,
        },
    )
