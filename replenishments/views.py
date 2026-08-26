from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    ReplenishmentFilterForm,
    ReplenishmentForm,
    ReplenishmentLineFormSet,
)
from .models import Replenishment
from .services import get_replenishment_stock_errors


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
        status = filter_form.cleaned_data.get("status")

        if date_from:
            replenishments = replenishments.filter(replenished_at__date__gte=date_from)

        if date_to:
            replenishments = replenishments.filter(replenished_at__date__lte=date_to)

        if machine:
            replenishments = replenishments.filter(machine=machine)

        if product:
            replenishments = replenishments.filter(lines__product=product)
        if status:
            replenishments = replenishments.filter(status=status)

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

    stock_warnings = []

    if replenishment.status == Replenishment.Status.DRAFT:
        stock_warnings = get_replenishment_stock_errors(replenishment)

    stock_error = request.GET.get("stock_error") == "1"

    return render(
        request,
        "replenishments/replenishment_detail.html",
        {
            "replenishment": replenishment,
            "stock_warnings": stock_warnings,
            "stock_error": stock_error,
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
        form = ReplenishmentForm(instance=replenishment)
        formset = ReplenishmentLineFormSet(instance=replenishment)

    return render(
        request,
        "replenishments/replenishment_form.html",
        {
            "form": form,
            "formset": formset,
        },
    )


def replenishment_edit(request, pk):
    replenishment = get_object_or_404(
        Replenishment,
        pk=pk,
    )

    if replenishment.status != Replenishment.Status.DRAFT:
        raise PermissionDenied("Solo se pueden editar reposiciones en borrador.")

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
                form.save()
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
            "replenishment": replenishment,
            "form": form,
            "formset": formset,
            "is_edit": True,
        },
    )


@require_POST
def replenishment_register(request, pk):
    replenishment = get_object_or_404(
        Replenishment,
        pk=pk,
    )

    if replenishment.status != Replenishment.Status.DRAFT:
        raise PermissionDenied("Solo se pueden registrar reposiciones en borrador.")

    if not replenishment.lines.exists():
        messages.error(
            request,
            "No se puede registrar una reposición sin productos.",
        )

        return redirect(
            "replenishments:replenishment_detail",
            pk=replenishment.pk,
        )

    stock_errors = get_replenishment_stock_errors(replenishment)

    if stock_errors:
        return redirect(
            f"{reverse('replenishments:replenishment_detail', args=[replenishment.pk])}"
            "?stock_error=1"
        )

        return redirect(
            "replenishments:replenishment_detail",
            pk=replenishment.pk,
        )

    replenishment.status = Replenishment.Status.REGISTERED
    replenishment.save(update_fields=["status"])

    return redirect(
        "replenishments:replenishment_detail",
        pk=replenishment.pk,
    )


@require_POST
def replenishment_delete(request, pk):
    replenishment = get_object_or_404(
        Replenishment,
        pk=pk,
    )

    if replenishment.status != Replenishment.Status.DRAFT:
        raise PermissionDenied("Solo se pueden eliminar reposiciones en borrador.")

    replenishment.delete()

    return redirect("replenishments:replenishment_list")


@require_POST
def replenishment_cancel(request, pk):
    replenishment = get_object_or_404(
        Replenishment,
        pk=pk,
    )

    if replenishment.status != Replenishment.Status.REGISTERED:
        raise PermissionDenied("Solo se pueden anular reposiciones registradas.")

    replenishment.status = Replenishment.Status.CANCELLED
    replenishment.save(update_fields=["status"])

    return redirect(
        "replenishments:replenishment_detail",
        pk=replenishment.pk,
    )
