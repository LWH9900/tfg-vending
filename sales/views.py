import json

from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sales.forms import SaleFilterForm
from sales.models import Sale
from sales.services import receive_sale


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
