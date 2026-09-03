import hashlib
import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from machines.models import Machine
from machines.services.layouts import (
    get_product_for_selection,
)
from sales.models import Sale


def _get_payload_hash(payload):
    try:
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError("El contenido de la venta debe ser JSON válido.")

    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _get_reference_sale(
    event_id,
):
    resolved_sale = (
        Sale.objects.filter(
            event_id=event_id,
            status=Sale.Status.RESOLVED,
        )
        .order_by(
            "received_at",
            "pk",
        )
        .first()
    )

    if resolved_sale is not None:
        return resolved_sale

    return (
        Sale.objects.filter(
            event_id=event_id,
        )
        .order_by(
            "received_at",
            "pk",
        )
        .first()
    )


def _get_required_value(
    payload,
    field,
):
    value = payload.get(field)

    if value in (
        None,
        "",
    ):
        raise ValidationError({field: (f"El campo '{field}' es obligatorio.")})

    return value


def _parse_occurred_at(value):
    if isinstance(
        value,
        datetime,
    ):
        occurred_at = value

    elif isinstance(
        value,
        str,
    ):
        occurred_at = parse_datetime(value)

    else:
        occurred_at = None

    if occurred_at is None:
        raise ValidationError(
            {"occurred_at": ("La fecha y hora de la venta no es válida.")}
        )

    if timezone.is_naive(occurred_at):
        raise ValidationError(
            {
                "occurred_at": (
                    "La fecha y hora de la venta debe incluir "
                    "información de zona horaria."
                )
            }
        )

    return occurred_at


def _parse_positive_integer(
    value,
    field,
):
    try:
        parsed_value = int(value)

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            {field: (f"El campo '{field}' debe ser un número entero.")}
        )

    if parsed_value < 1:
        raise ValidationError({field: (f"El campo '{field}' debe ser mayor que cero.")})

    return parsed_value


def _parse_optional_decimal(
    value,
    field,
):
    if value in (
        None,
        "",
    ):
        return None

    try:
        parsed_value = Decimal(str(value))

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            {field: (f"El campo '{field}' debe contener un importe válido.")}
        )

    if parsed_value < 0:
        raise ValidationError({field: (f"El campo '{field}' no puede ser negativo.")})

    return parsed_value


@transaction.atomic
def receive_sale(
    payload,
):
    if not isinstance(
        payload,
        dict,
    ):
        raise ValidationError("El contenido de la venta debe ser un objeto JSON.")

    event_id = str(
        _get_required_value(
            payload,
            "event_id",
        )
    ).strip()

    payload_hash = _get_payload_hash(payload)

    exact_sale = Sale.objects.filter(
        source=Sale.Source.TELEMETRY,
        event_id=event_id,
        payload_hash=payload_hash,
    ).first()

    if exact_sale is not None:
        return exact_sale, False

    machine_identifier = str(
        _get_required_value(
            payload,
            "machine_identifier",
        )
    ).strip()

    selection = str(
        _get_required_value(
            payload,
            "selection",
        )
    ).strip()

    occurred_at = _parse_occurred_at(
        _get_required_value(
            payload,
            "occurred_at",
        )
    )

    quantity = _parse_positive_integer(
        _get_required_value(
            payload,
            "quantity",
        ),
        "quantity",
    )

    dispense_type = (
        str(
            _get_required_value(
                payload,
                "dispense_type",
            )
        )
        .strip()
        .lower()
    )

    if dispense_type not in (
        Sale.DispenseType.PAID,
        Sale.DispenseType.FREE,
    ):
        raise ValidationError(
            {"dispense_type": ("El tipo de dispensación debe ser 'paid' o 'free'.")}
        )

    unit_price = _parse_optional_decimal(
        payload.get("unit_price"),
        "unit_price",
    )

    amount_received = _parse_optional_decimal(
        payload.get("amount_received"),
        "amount_received",
    )

    if dispense_type == Sale.DispenseType.FREE and amount_received is None:
        amount_received = Decimal("0.00")

    payment_method = payload.get("payment_method") or ""

    payment_method = str(payment_method).strip()

    machine = Machine.objects.filter(
        identifier=machine_identifier,
    ).first()

    product = None

    if machine is not None:
        product = get_product_for_selection(
            machine,
            selection,
            occurred_at,
        )

    reference_sale = _get_reference_sale(event_id)

    if reference_sale is not None:
        status = Sale.Status.CONFLICT

    elif machine is not None and product is not None:
        status = Sale.Status.RESOLVED

    else:
        status = Sale.Status.PENDING

    sale_data = {
        "source": Sale.Source.TELEMETRY,
        "event_id": event_id,
        "payload_hash": payload_hash,
        "machine_identifier": machine_identifier,
        "machine": machine,
        "selection": selection,
        "product": product,
        "occurred_at": occurred_at,
        "quantity": quantity,
        "dispense_type": dispense_type,
        "unit_price": unit_price,
        "amount_received": amount_received,
        "payment_method": payment_method,
        "status": status,
        "raw_payload": deepcopy(payload),
    }

    if status == Sale.Status.CONFLICT:
        sale_data["conflicts_with"] = reference_sale

    try:
        with transaction.atomic():
            sale = Sale.objects.create(**sale_data)

    except IntegrityError:
        exact_sale = Sale.objects.filter(
            source=Sale.Source.TELEMETRY,
            event_id=event_id,
            payload_hash=payload_hash,
        ).first()

        if exact_sale is not None:
            return exact_sale, False

        reference_sale = _get_reference_sale(event_id)

        if reference_sale is None:
            raise

        sale_data["status"] = Sale.Status.CONFLICT

        sale_data["conflicts_with"] = reference_sale

        with transaction.atomic():
            sale = Sale.objects.create(**sale_data)

    return sale, True


@transaction.atomic
def void_sale(
    sale,
    reason,
):
    if sale.pk is None:
        raise ValidationError("La venta debe estar guardada antes de poder anularla.")

    reason = str(reason or "").strip()

    if not reason:
        raise ValidationError(
            {"void_reason": ("Debe indicarse el motivo de la anulación.")}
        )

    locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if locked_sale.status != Sale.Status.RESOLVED:
        raise ValidationError("Solo se puede anular una venta resuelta.")

    locked_sale.status = Sale.Status.VOIDED

    locked_sale.void_reason = reason

    locked_sale.voided_at = timezone.now()

    locked_sale.save()

    return locked_sale


@transaction.atomic
def reject_sale_conflict(
    sale,
):
    if sale.pk is None:
        raise ValidationError("La venta debe estar guardada antes de poder revisarla.")

    locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if locked_sale.status != Sale.Status.CONFLICT:
        raise ValidationError("Solo se puede descartar una venta en conflicto.")

    locked_sale.status = Sale.Status.REJECTED

    locked_sale.save()

    return locked_sale


@transaction.atomic
def accept_sale_conflict(
    sale,
):
    if sale.pk is None:
        raise ValidationError("La venta debe estar guardada antes de poder revisarla.")

    if not sale.event_id:
        raise ValidationError(
            "Una venta en conflicto debe tener un identificador de evento."
        )

    event_sales = list(
        Sale.objects.select_for_update()
        .filter(
            event_id=sale.event_id,
        )
        .order_by("pk")
    )

    locked_sale = next(
        (event_sale for event_sale in event_sales if event_sale.pk == sale.pk),
        None,
    )

    if locked_sale is None:
        raise ValidationError("La venta en conflicto no existe.")

    if locked_sale.status != Sale.Status.CONFLICT:
        raise ValidationError("Solo se puede aceptar una venta en conflicto.")

    if locked_sale.machine_id is None:
        raise ValidationError(
            {
                "machine": (
                    "No se puede aceptar el conflicto sin haber resuelto la máquina."
                )
            }
        )

    if locked_sale.product_id is None:
        raise ValidationError(
            {
                "product": (
                    "No se puede aceptar el conflicto sin haber resuelto el producto."
                )
            }
        )

    current_sale = next(
        (
            event_sale
            for event_sale in event_sales
            if (
                event_sale.status == Sale.Status.RESOLVED
                and event_sale.pk != locked_sale.pk
            )
        ),
        None,
    )

    if current_sale is not None:
        current_sale.status = Sale.Status.VOIDED

        current_sale.void_reason = (
            f"Anulada al aceptar la venta en conflicto #{locked_sale.pk}."
        )

        current_sale.voided_at = timezone.now()

        current_sale.save()

    locked_sale.status = Sale.Status.RESOLVED

    locked_sale.save()

    return (
        locked_sale,
        current_sale,
    )
