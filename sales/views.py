import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sales.models import Sale
from sales.services import receive_sale


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
