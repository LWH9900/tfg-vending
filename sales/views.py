import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sales.forms import (
    ResolvePendingSaleForm,
    SaleFilterForm,
    VoidSaleForm,
)
from sales.models import Sale
from sales.services import (
    accept_sale_conflict,
    receive_sale,
    reject_sale_conflict,
    resolve_pending_sale,
    void_sale,
)


def sale_list(
    request,
):
    sales = Sale.objects.select_related(
        "machine",
        "product",
        "product__category",
        "conflicts_with",
    ).order_by(
        "-occurred_at",
        "-pk",
    )

    filter_form = SaleFilterForm(request.GET)

    if filter_form.is_valid():
        event_id = filter_form.cleaned_data.get("event_id")

        machine = filter_form.cleaned_data.get("machine")

        product = filter_form.cleaned_data.get("product")

        date_from = filter_form.cleaned_data.get("date_from")

        date_to = filter_form.cleaned_data.get("date_to")

        status = filter_form.cleaned_data.get("status")

        source = filter_form.cleaned_data.get("source")

        dispense_type = filter_form.cleaned_data.get("dispense_type")

        if event_id:
            sales = sales.filter(event_id__icontains=event_id)

        if machine:
            sales = sales.filter(machine=machine)

        if product:
            sales = sales.filter(product=product)

        if date_from:
            sales = sales.filter(occurred_at__gte=date_from)

        if date_to:
            sales = sales.filter(occurred_at__lte=date_to)

        if status:
            sales = sales.filter(status=status)

        if source:
            sales = sales.filter(source=source)

        if dispense_type:
            sales = sales.filter(dispense_type=dispense_type)

    return render(
        request,
        "sales/sale_list.html",
        {
            "sales": sales,
            "filter_form": filter_form,
        },
    )


def sale_detail(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale.objects.select_related(
            "machine",
            "product",
            "product__category",
            "conflicts_with",
            "conflicts_with__machine",
            "conflicts_with__product",
        ),
        pk=pk,
    )

    conflicting_sales = sale.conflicting_sales.select_related(
        "machine",
        "product",
    ).order_by(
        "received_at",
        "pk",
    )

    pretty_payload = None

    if sale.raw_payload is not None:
        pretty_payload = json.dumps(
            sale.raw_payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    return render(
        request,
        "sales/sale_detail.html",
        {
            "sale": sale,
            "conflicting_sales": (conflicting_sales),
            "pretty_payload": (pretty_payload),
        },
    )


def sale_resolve(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale,
        pk=pk,
    )

    if sale.status != Sale.Status.PENDING:
        messages.error(
            request,
            "Solo se pueden resolver ventas pendientes.",
        )

        return redirect(
            "sales:sale_detail",
            pk=sale.pk,
        )

    form = ResolvePendingSaleForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            resolved_sale = resolve_pending_sale(
                sale,
                form.cleaned_data["machine"],
                form.cleaned_data["product"],
            )

        except ValidationError as error:
            form.add_error(
                None,
                error,
            )

        else:
            messages.success(
                request,
                "La venta se ha resuelto correctamente.",
            )

            return redirect(
                "sales:sale_detail",
                pk=resolved_sale.pk,
            )

    return render(
        request,
        "sales/sale_resolve.html",
        {
            "sale": sale,
            "form": form,
        },
    )


def sale_void(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale,
        pk=pk,
    )

    if sale.status != Sale.Status.RESOLVED:
        messages.error(
            request,
            "Solo se pueden anular ventas resueltas.",
        )

        return redirect(
            "sales:sale_detail",
            pk=sale.pk,
        )

    form = VoidSaleForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            voided_sale = void_sale(
                sale,
                form.cleaned_data["reason"],
            )

        except ValidationError as error:
            form.add_error(
                None,
                error,
            )

        else:
            messages.success(
                request,
                "La venta se ha anulado correctamente.",
            )

            return redirect(
                "sales:sale_detail",
                pk=voided_sale.pk,
            )

    return render(
        request,
        "sales/sale_void.html",
        {
            "sale": sale,
            "form": form,
        },
    )


def sale_conflict_review(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale.objects.select_related(
            "machine",
            "product",
            "conflicts_with",
            "conflicts_with__machine",
            "conflicts_with__product",
        ),
        pk=pk,
    )

    if sale.status != Sale.Status.CONFLICT:
        messages.error(
            request,
            "Esta venta no está pendiente de revisión por conflicto.",
        )

        return redirect(
            "sales:sale_detail",
            pk=sale.pk,
        )

    reference_sale = sale.conflicts_with

    sale_payload = None

    if sale.raw_payload is not None:
        sale_payload = json.dumps(
            sale.raw_payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    reference_payload = None

    if reference_sale is not None and reference_sale.raw_payload is not None:
        reference_payload = json.dumps(
            reference_sale.raw_payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    return render(
        request,
        "sales/sale_conflict_review.html",
        {
            "sale": sale,
            "reference_sale": reference_sale,
            "sale_payload": sale_payload,
            "reference_payload": reference_payload,
        },
    )


@require_POST
def sale_conflict_reject(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale,
        pk=pk,
    )

    try:
        rejected_sale = reject_sale_conflict(sale)

    except ValidationError as error:
        messages.error(
            request,
            " ".join(error.messages),
        )

    else:
        messages.success(
            request,
            ("La recepción conflictiva se ha descartado."),
        )

        return redirect(
            "sales:sale_detail",
            pk=rejected_sale.pk,
        )

    return redirect(
        "sales:sale_detail",
        pk=sale.pk,
    )


@require_POST
def sale_conflict_accept(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale,
        pk=pk,
    )

    try:
        accepted_sale, voided_sale = accept_sale_conflict(sale)

    except ValidationError as error:
        messages.error(
            request,
            " ".join(error.messages),
        )

        return redirect(
            "sales:sale_detail",
            pk=sale.pk,
        )

    if voided_sale is not None:
        messages.success(
            request,
            (
                "La recepción conflictiva se ha aceptado "
                "y la venta efectiva anterior ha sido anulada."
            ),
        )

    else:
        messages.success(
            request,
            "La recepción conflictiva se ha aceptado.",
        )

    return redirect(
        "sales:sale_detail",
        pk=accepted_sale.pk,
    )


def sale_payload_download(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale,
        pk=pk,
    )

    if sale.raw_payload is None:
        return JsonResponse(
            {"error": ("Esta venta no dispone de un payload de telemetría.")},
            status=404,
        )

    payload_content = json.dumps(
        sale.raw_payload,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )

    response = HttpResponse(
        payload_content,
        content_type=("application/json; charset=utf-8"),
    )

    response["Content-Disposition"] = (
        f'attachment; filename="sale-{sale.pk}-payload.json"'
    )

    return response


@csrf_exempt
@require_POST
def sale_receive(
    request,
):
    if request.content_type != "application/json":
        return JsonResponse(
            {"error": ("El contenido de la petición debe ser JSON.")},
            status=415,
        )

    try:
        payload = json.loads(request.body)

    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return JsonResponse(
            {"error": ("El contenido JSON no es válido.")},
            status=400,
        )

    try:
        sale, created = receive_sale(payload)

    except ValidationError as error:
        if hasattr(
            error,
            "message_dict",
        ):
            errors = error.message_dict

        else:
            errors = {"non_field_errors": (error.messages)}

        return JsonResponse(
            {
                "errors": errors,
            },
            status=400,
        )

    response_data = {
        "id": sale.pk,
        "event_id": sale.event_id,
        "status": sale.status,
        "created": created,
    }

    if sale.status == Sale.Status.CONFLICT:
        response_data["conflicts_with"] = sale.conflicts_with_id

        response_data["error"] = (
            "El identificador de evento ya existe "
            "con un contenido diferente. "
            "La recepción se ha conservado para "
            "revisión manual."
        )

        return JsonResponse(
            response_data,
            status=409,
        )

    if created:
        return JsonResponse(
            response_data,
            status=201,
        )

    return JsonResponse(
        response_data,
        status=200,
    )
