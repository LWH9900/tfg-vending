from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    PurchaseFilterForm,
    PurchaseForm,
    PurchaseLineFormSet,
)
from .models import Purchase
from .services import (
    get_purchase_cancellation_stock_errors,
    get_purchase_profitability_warning,
)


def purchase_list(request):
    purchases = Purchase.objects.prefetch_related("lines").order_by(
        "-purchased_at", "-pk"
    )

    filter_form = PurchaseFilterForm(request.GET)

    if filter_form.is_valid():
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")
        product = filter_form.cleaned_data.get("product")
        supplier = filter_form.cleaned_data.get("supplier")
        status = filter_form.cleaned_data.get("status")

        if date_from:
            purchases = purchases.filter(
                purchased_at__date__gte=date_from,
            )

        if date_to:
            purchases = purchases.filter(
                purchased_at__date__lte=date_to,
            )

        if product:
            purchases = purchases.filter(
                lines__product=product,
            )

        if supplier:
            purchases = purchases.filter(
                supplier__icontains=supplier,
            )

        if status:
            purchases = purchases.filter(
                status=status,
            )

    purchases = purchases.distinct()

    return render(
        request,
        "purchases/purchase_list.html",
        {
            "purchases": purchases,
            "filter_form": filter_form,
        },
    )


def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.prefetch_related(
            "lines__product",
            "lines__product__category",
        ),
        pk=pk,
    )
    profitability_warning = None

    if purchase.status != Purchase.Status.CANCELLED:
        profitability_warning = get_purchase_profitability_warning(purchase)

    return render(
        request,
        "purchases/purchase_detail.html",
        {
            "purchase": purchase,
            "is_edit": False,
            "profitability_warning": (profitability_warning),
        },
    )


def purchase_create(request):
    purchase = Purchase()

    if request.method == "POST":
        form = PurchaseForm(
            request.POST,
            instance=purchase,
        )
        formset = PurchaseLineFormSet(
            request.POST,
            instance=purchase,
        )

        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()

        if form_is_valid and formset_is_valid:
            with transaction.atomic():
                purchase = form.save()

                formset.instance = purchase
                formset.save()

            return redirect(
                "purchases:purchase_detail",
                pk=purchase.pk,
            )

    else:
        form = PurchaseForm(
            instance=purchase,
        )
        formset = PurchaseLineFormSet(
            instance=purchase,
        )

    return render(
        request,
        "purchases/purchase_form.html",
        {
            "form": form,
            "formset": formset,
        },
    )


def purchase_edit(request, pk):
    purchase = get_object_or_404(
        Purchase,
        pk=pk,
    )
    if purchase.status != Purchase.Status.DRAFT:
        raise PermissionDenied("Solo se pueden editar compras en borrador.")

    if request.method == "POST":
        form = PurchaseForm(
            request.POST,
            instance=purchase,
        )
        formset = PurchaseLineFormSet(
            request.POST,
            instance=purchase,
        )

        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()

        if form_is_valid and formset_is_valid:
            with transaction.atomic():
                form.save()
                formset.save()

            return redirect(
                "purchases:purchase_detail",
                pk=purchase.pk,
            )

    else:
        form = PurchaseForm(instance=purchase)
        formset = PurchaseLineFormSet(instance=purchase)

    return render(
        request,
        "purchases/purchase_detail.html",
        {
            "purchase": purchase,
            "form": form,
            "formset": formset,
            "is_edit": True,
        },
    )


@require_POST
def purchase_register(request, pk):
    purchase = get_object_or_404(
        Purchase,
        pk=pk,
    )

    if purchase.status != Purchase.Status.DRAFT:
        raise PermissionDenied("Solo se pueden registrar compras en borrador.")

    if not purchase.lines.exists():
        raise PermissionDenied("No se puede registrar una compra sin productos.")

    purchase.status = Purchase.Status.REGISTERED
    purchase.save(update_fields=["status"])

    return redirect(
        "purchases:purchase_detail",
        pk=purchase.pk,
    )


@require_POST
def purchase_delete(request, pk):
    purchase = get_object_or_404(
        Purchase,
        pk=pk,
    )

    if purchase.status != Purchase.Status.DRAFT:
        raise PermissionDenied("Solo se pueden eliminar compras en borrador.")

    purchase.delete()

    return redirect("purchases:purchase_list")


@require_POST
def purchase_cancel(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.prefetch_related("lines__product"),
        pk=pk,
    )

    if purchase.status != Purchase.Status.REGISTERED:
        raise PermissionDenied("Solo se pueden anular compras registradas.")

    stock_errors = get_purchase_cancellation_stock_errors(purchase)

    if stock_errors:
        details = "; ".join(
            (
                f"{error['product'].name}: "
                f"{error['current_stock']} uds. disponibles, "
                f"la compra aporta "
                f"{error['purchase_quantity']} uds."
            )
            for error in stock_errors
        )

        messages.error(
            request,
            (
                "No se puede anular la compra porque "
                "el stock de almacén quedaría negativo. "
                f"{details}"
            ),
        )

        return redirect(
            "purchases:purchase_detail",
            pk=purchase.pk,
        )

    with transaction.atomic():
        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status"])

    return redirect(
        "purchases:purchase_detail",
        pk=purchase.pk,
    )
