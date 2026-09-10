from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from inventory.models import Product
from machines.models import Machine
from machines.services.layouts import get_machine_layout_at

from .forms import (
    ReplenishmentFilterForm,
    ReplenishmentForm,
    ReplenishmentLineFormSet,
)
from .models import Replenishment
from .services import (
    get_replenishment_cancellation_stock_errors,
    get_replenishment_layout_errors,
    get_replenishment_stock_errors,
)


def _get_active_product_ids(machine, moment):
    if machine is None:
        return set()

    layout = get_machine_layout_at(
        machine,
        moment,
    )

    if layout is None:
        return set()

    return set(
        layout.positions.filter(
            product__isnull=False,
        ).values_list(
            "product_id",
            flat=True,
        )
    )


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
    paginator = Paginator(replenishments, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "replenishments/replenishment_list.html",
        {
            "replenishments": page_obj.object_list,
            "filter_form": filter_form,
            "page_obj": page_obj,
            "pagination_query": query_params.urlencode(),
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
    layout_warnings = []

    if replenishment.status == Replenishment.Status.DRAFT:
        stock_warnings = get_replenishment_stock_errors(replenishment)

        layout_warnings = get_replenishment_layout_errors(replenishment)

    stock_error = request.GET.get("stock_error") == "1"

    layout_error = request.GET.get("layout_error") == "1"

    return render(
        request,
        "replenishments/replenishment_detail.html",
        {
            "replenishment": replenishment,
            "stock_warnings": stock_warnings,
            "layout_warnings": layout_warnings,
            "stock_error": stock_error,
            "layout_error": layout_error,
        },
    )


def replenishment_create(request):
    replenishment = Replenishment()

    if request.method == "POST":
        moment = parse_datetime(request.POST.get("replenished_at", ""))

        if moment is None:
            moment = timezone.now()
        elif timezone.is_naive(moment):
            moment = timezone.make_aware(moment)

        selected_machine = Machine.objects.filter(
            pk=request.POST.get("machine"),
        ).first()

        active_product_ids = _get_active_product_ids(
            selected_machine,
            moment,
        )

        form = ReplenishmentForm(
            request.POST,
            instance=replenishment,
        )

        formset = ReplenishmentLineFormSet(
            request.POST,
            instance=replenishment,
            form_kwargs={
                "active_product_ids": active_product_ids,
            },
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
        initial_machine = None
        machine_id = request.GET.get("machine")

        if machine_id:
            initial_machine = Machine.objects.filter(
                pk=machine_id,
            ).first()

        moment = replenishment.replenished_at or timezone.now()

        active_product_ids = _get_active_product_ids(
            initial_machine,
            moment,
        )

        form = ReplenishmentForm(
            instance=replenishment,
            initial={
                "machine": initial_machine,
            },
        )

        formset = ReplenishmentLineFormSet(
            instance=replenishment,
            form_kwargs={
                "active_product_ids": active_product_ids,
            },
        )

    return render(
        request,
        "replenishments/replenishment_form.html",
        {
            "form": form,
            "formset": formset,
        },
    )


def active_products(request, machine_pk):
    machine = get_object_or_404(
        Machine,
        pk=machine_pk,
    )

    moment = parse_datetime(request.GET.get("moment", ""))

    if moment is None:
        moment = timezone.now()
    elif timezone.is_naive(moment):
        moment = timezone.make_aware(moment)

    product_ids = _get_active_product_ids(
        machine,
        moment,
    )

    return JsonResponse(
        {
            "product_ids": list(product_ids),
        }
    )


def replenishment_edit(request, pk):
    if request.method == "POST":
        with transaction.atomic():
            replenishment = get_object_or_404(
                Replenishment.objects.select_for_update().prefetch_related(
                    "lines__product",
                ),
                pk=pk,
            )

            if replenishment.status != Replenishment.Status.DRAFT:
                raise PermissionDenied(
                    "Solo se pueden editar reposiciones en borrador."
                )

            selected_machine = Machine.objects.filter(
                pk=request.POST.get("machine"),
            ).first()

            moment = parse_datetime(request.POST.get("replenished_at", ""))

            if moment is None:
                moment = timezone.now()
            elif timezone.is_naive(moment):
                moment = timezone.make_aware(moment)

            active_product_ids = _get_active_product_ids(
                selected_machine,
                moment,
            )

            form = ReplenishmentForm(
                request.POST,
                instance=replenishment,
            )

            formset = ReplenishmentLineFormSet(
                request.POST,
                instance=replenishment,
                form_kwargs={
                    "active_product_ids": active_product_ids,
                },
            )

            form_is_valid = form.is_valid()
            formset_is_valid = formset.is_valid()

            if form_is_valid and formset_is_valid:
                form.save()
                formset.save()

                return redirect(
                    "replenishments:replenishment_detail",
                    pk=replenishment.pk,
                )

    else:
        replenishment = get_object_or_404(
            Replenishment.objects.prefetch_related(
                "lines__product",
            ),
            pk=pk,
        )

        if replenishment.status != Replenishment.Status.DRAFT:
            raise PermissionDenied("Solo se pueden editar reposiciones en borrador.")

        active_product_ids = _get_active_product_ids(
            replenishment.machine,
            replenishment.replenished_at,
        )

        form = ReplenishmentForm(
            instance=replenishment,
        )

        formset = ReplenishmentLineFormSet(
            instance=replenishment,
            form_kwargs={
                "active_product_ids": active_product_ids,
            },
        )

    return render(
        request,
        "replenishments/replenishment_detail.html",
        {
            "replenishment": replenishment,
            "form": form,
            "formset": formset,
            "is_edit": True,
        },
    )


@require_POST
def replenishment_register(request, pk):
    with transaction.atomic():
        replenishment = get_object_or_404(
            Replenishment.objects.select_for_update(),
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

        product_ids = list(
            replenishment.lines.values_list(
                "product_id",
                flat=True,
            )
        )

        list(
            Product.objects.select_for_update()
            .filter(pk__in=product_ids)
            .order_by("pk")
        )

        stock_errors = get_replenishment_stock_errors(replenishment)

        layout_errors = get_replenishment_layout_errors(replenishment)

        error_params = []

        if stock_errors:
            error_params.append("stock_error=1")

        if layout_errors:
            error_params.append("layout_error=1")

        if error_params:
            detail_url = reverse(
                "replenishments:replenishment_detail",
                args=[replenishment.pk],
            )

            return redirect(f"{detail_url}?{'&'.join(error_params)}")

        replenishment.status = Replenishment.Status.REGISTERED
        replenishment.save(
            update_fields=["status"],
        )

    return redirect(
        "replenishments:replenishment_detail",
        pk=replenishment.pk,
    )


@require_POST
def replenishment_delete(request, pk):
    with transaction.atomic():
        replenishment = get_object_or_404(
            Replenishment.objects.select_for_update(),
            pk=pk,
        )

        if replenishment.status != Replenishment.Status.DRAFT:
            raise PermissionDenied("Solo se pueden eliminar reposiciones en borrador.")

        replenishment.delete()

    return redirect("replenishments:replenishment_list")


@require_POST
def replenishment_cancel(request, pk):
    with transaction.atomic():
        replenishment = get_object_or_404(
            Replenishment.objects.select_for_update().prefetch_related(
                "lines__product",
            ),
            pk=pk,
        )

        if replenishment.status != Replenishment.Status.REGISTERED:
            raise PermissionDenied("Solo se pueden anular reposiciones registradas.")

        product_ids = list(
            replenishment.lines.values_list(
                "product_id",
                flat=True,
            )
        )

        list(
            Product.objects.select_for_update()
            .filter(pk__in=product_ids)
            .order_by("pk")
        )

        stock_errors = get_replenishment_cancellation_stock_errors(replenishment)

        if stock_errors:
            details = "; ".join(
                (
                    f"{error['product'].name}: "
                    f"{error['current_stock']} uds. disponibles en la máquina, "
                    f"la reposición aporta "
                    f"{error['replenishment_quantity']} uds."
                )
                for error in stock_errors
            )

            messages.error(
                request,
                (
                    "No se puede anular la reposición porque "
                    "el stock de la máquina quedaría negativo. "
                    f"{details}"
                ),
            )

            return redirect(
                "replenishments:replenishment_detail",
                pk=replenishment.pk,
            )

        replenishment.status = Replenishment.Status.CANCELLED
        replenishment.save(
            update_fields=["status"],
        )

    return redirect(
        "replenishments:replenishment_detail",
        pk=replenishment.pk,
    )
