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

    existing_sale = Sale.objects.filter(
        event_id=event_id,
    ).first()

    if existing_sale is not None:
        return existing_sale, False

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

    if machine is not None and product is not None:
        status = Sale.Status.RESOLVED

    else:
        status = Sale.Status.PENDING

    try:
        sale = Sale.objects.create(
            event_id=event_id,
            machine_identifier=machine_identifier,
            machine=machine,
            selection=selection,
            product=product,
            occurred_at=occurred_at,
            quantity=quantity,
            dispense_type=dispense_type,
            unit_price=unit_price,
            amount_received=amount_received,
            payment_method=payment_method,
            status=status,
            raw_payload=deepcopy(payload),
        )

    except IntegrityError:
        sale = Sale.objects.get(
            event_id=event_id,
        )

        return sale, False

    return sale, True
