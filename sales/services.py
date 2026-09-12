import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, time
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from inventory.models import Product
from inventory.services import get_machine_stock, get_total_stock, get_warehouse_stock
from machines.models import Machine, MachineLayoutActivation, MachinePosition
from machines.services.layouts import (
    get_machine_layout_at,
    get_product_for_selection,
)
from sales.models import Sale


def _validate_sale_stock(machine, product, quantity, replaced_sale=None):
    Machine.objects.select_for_update().get(pk=machine.pk)
    Product.objects.select_for_update().get(pk=product.pk)

    machine_stock = get_machine_stock(product, machine)

    if (
        replaced_sale is not None
        and replaced_sale.status == Sale.Status.RESOLVED
        and replaced_sale.machine_id == machine.pk
        and replaced_sale.product_id == product.pk
    ):
        machine_stock += replaced_sale.quantity

    if machine_stock < quantity:
        raise ValidationError(
            {
                "quantity": ValidationError(
                    (
                        "Stock insuficiente para registrar la venta. "
                        f"La máquina dispone de {machine_stock} unidades "
                        f"y se han solicitado {quantity}."
                    ),
                    code="insufficient_stock",
                )
            }
        )


def _calculate_estimated_consumption(historical_sales, history_days, forecast_days):
    daily_average = Decimal(historical_sales) / Decimal(history_days)

    estimated_consumption = int(
        (daily_average * Decimal(forecast_days)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )

    return daily_average, estimated_consumption


def _get_projection_history_bounds(history_start, history_end):
    current_timezone = timezone.get_current_timezone()

    history_from = timezone.make_aware(
        datetime.combine(history_start, time.min),
        current_timezone,
    )
    history_until = timezone.make_aware(
        datetime.combine(history_end, time.max),
        current_timezone,
    )

    return history_from, history_until


def _get_historical_sales_by_machine_product(history_from, history_until):
    return {
        (row["machine_id"], row["product_id"]): row["total"]
        for row in (
            Sale.objects.filter(
                status=Sale.Status.RESOLVED,
                machine__isnull=False,
                product__isnull=False,
                occurred_at__gte=history_from,
                occurred_at__lte=history_until,
            )
            .values("machine_id", "product_id")
            .annotate(total=Sum("quantity"))
        )
    }


def _get_active_machine_product_pairs():
    now = timezone.now()

    return set(
        MachinePosition.objects.filter(
            product__isnull=False,
            layout__activations__effective_from__lte=now,
            layout__activations__effective_to__isnull=True,
        ).values_list(
            "layout__machine_id",
            "product_id",
        )
    )


def get_sales_projection(
    history_start,
    history_end,
    forecast_start,
    forecast_end,
):
    if history_start > history_end or forecast_start > forecast_end:
        raise ValueError("Las fechas finales no pueden preceder a las iniciales.")

    history_days = (history_end - history_start).days + 1
    forecast_days = (forecast_end - forecast_start).days + 1

    history_from, history_until = _get_projection_history_bounds(
        history_start,
        history_end,
    )

    historical_sales_by_pair = _get_historical_sales_by_machine_product(
        history_from,
        history_until,
    )

    active_pairs = _get_active_machine_product_pairs()
    all_pairs = active_pairs | set(historical_sales_by_pair)

    machine_ids = {machine_id for machine_id, _product_id in all_pairs}

    machines = {
        machine.pk: machine
        for machine in Machine.objects.filter(pk__in=machine_ids).order_by("identifier")
    }

    products = list(
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("name", "pk")
    )

    products_by_id = {product.pk: product for product in products}

    details_by_product = {}

    for machine_id, product_id in all_pairs:
        product = products_by_id.get(product_id)

        if product is None:
            continue

        machine = machines[machine_id]

        historical_sales = historical_sales_by_pair.get(
            (machine_id, product_id),
            0,
        )

        daily_average, estimated_consumption = _calculate_estimated_consumption(
            historical_sales,
            history_days,
            forecast_days,
        )

        machine_stock = get_machine_stock(product, machine)
        usable_machine_stock = max(machine_stock, 0)

        is_in_active_layout = (
            machine_id,
            product_id,
        ) in active_pairs

        if is_in_active_layout:
            machine_need = max(
                estimated_consumption - usable_machine_stock,
                0,
            )
        else:
            machine_need = 0

        details_by_product.setdefault(
            product_id,
            [],
        ).append(
            {
                "machine": machine,
                "historical_sales": historical_sales,
                "daily_average": daily_average,
                "estimated_consumption": estimated_consumption,
                "machine_stock": machine_stock,
                "usable_machine_stock": usable_machine_stock,
                "has_stock_incident": machine_stock < 0,
                "machine_need": machine_need,
                "is_in_active_layout": is_in_active_layout,
            }
        )

    projections = []

    for product in products:
        machine_details = sorted(
            details_by_product.get(product.pk, []),
            key=lambda item: item["machine"].identifier,
        )

        historical_sales = sum(item["historical_sales"] for item in machine_details)

        daily_average = Decimal(historical_sales) / Decimal(history_days)

        estimated_consumption = sum(
            item["estimated_consumption"]
            for item in machine_details
            if item["is_in_active_layout"]
        )

        total_stock = get_total_stock(product)
        warehouse_stock = get_warehouse_stock(product)
        usable_warehouse_stock = max(warehouse_stock, 0)

        total_machine_need = sum(item["machine_need"] for item in machine_details)

        suggested_purchase = max(
            total_machine_need - usable_warehouse_stock,
            0,
        )

        projections.append(
            {
                "product": product,
                "historical_sales": historical_sales,
                "daily_average": daily_average,
                "total_stock": total_stock,
                "has_total_stock_incident": total_stock < 0,
                "warehouse_stock": warehouse_stock,
                "usable_warehouse_stock": usable_warehouse_stock,
                "has_warehouse_stock_incident": warehouse_stock < 0,
                "estimated_consumption": estimated_consumption,
                "total_machine_need": total_machine_need,
                "suggested_purchase": suggested_purchase,
                "warehouse_shortage": (usable_warehouse_stock < total_machine_need),
                "machine_details": machine_details,
            }
        )

    return projections


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


def _lock_sale_event(event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [event_id],
        )


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

    elif isinstance(value, str):
        valid_format = re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            value,
        )
        occurred_at = parse_datetime(value) if valid_format else None

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
    if isinstance(value, bool):
        raise ValidationError(
            {field: (f"El campo '{field}' debe ser un número entero.")}
        )

    if isinstance(value, int):
        parsed_value = value

    elif isinstance(value, str):
        stripped_value = value.strip()

        if not stripped_value.isdigit():
            raise ValidationError(
                {field: (f"El campo '{field}' debe ser un número entero.")}
            )

        parsed_value = int(stripped_value)

    else:
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
        if not parsed_value.is_finite():
            raise ValidationError(
                {field: (f"El campo '{field}' debe contener un importe válido.")}
            )

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

    _lock_sale_event(event_id)

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

    if status == Sale.Status.RESOLVED:
        _validate_sale_stock(machine, product, quantity)

    elif status == Sale.Status.CONFLICT and machine is not None and product is not None:
        _validate_sale_stock(
            machine,
            product,
            quantity,
            replaced_sale=reference_sale,
        )

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

    _validate_sale_stock(
        locked_sale.machine,
        locked_sale.product,
        locked_sale.quantity,
    )

    locked_sale.status = Sale.Status.RESOLVED

    locked_sale.save()

    return (
        locked_sale,
        current_sale,
    )


@transaction.atomic
def resolve_pending_sale(
    sale,
    machine,
    product,
    reference_layout=None,
):
    if sale.pk is None:
        raise ValidationError("La venta debe estar guardada antes de poder resolverla.")

    if machine is None:
        raise ValidationError({"machine": ("Debe seleccionarse una máquina.")})

    if product is None:
        raise ValidationError({"product": ("Debe seleccionarse un producto.")})

    locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if locked_sale.status not in (
        Sale.Status.PENDING,
        Sale.Status.CONFLICT,
    ):
        raise ValidationError(
            "Solo se pueden resolver manualmente ventas pendientes o en conflicto."
        )

    is_conflict = locked_sale.status == Sale.Status.CONFLICT

    if locked_sale.machine_id is not None and locked_sale.machine_id != machine.pk:
        raise ValidationError(
            {
                "machine": (
                    "La máquina de esta venta "
                    "ya estaba resuelta y no "
                    "puede sustituirse."
                )
            }
        )

    historical_layout = get_machine_layout_at(
        machine,
        locked_sale.occurred_at,
    )

    if historical_layout is not None:
        if reference_layout is not None and reference_layout.pk != historical_layout.pk:
            raise ValidationError(
                (
                    "La venta ya tiene una disposición "
                    "histórica exacta. No puede utilizarse "
                    "otra disposición como referencia."
                )
            )

        layout = historical_layout
        resolution_layout = None

    else:
        if reference_layout is None:
            raise ValidationError(
                (
                    "No existe una disposición histórica "
                    "exacta para esta venta. Debe seleccionarse "
                    "una disposición de referencia."
                )
            )

        if reference_layout.machine_id != machine.pk:
            raise ValidationError(
                ("La disposición seleccionada no pertenece a la máquina de la venta.")
            )

        has_activation_history = MachineLayoutActivation.objects.filter(
            layout=reference_layout,
        ).exists()

        if not has_activation_history:
            raise ValidationError(
                (
                    "La disposición seleccionada nunca ha "
                    "estado activa en esta máquina y no puede "
                    "utilizarse como referencia."
                )
            )

        layout = reference_layout
        resolution_layout = reference_layout

    product_in_layout = layout.positions.filter(
        product=product,
    ).exists()

    if not product_in_layout:
        raise ValidationError(
            {
                "product": (
                    "El producto seleccionado no pertenece "
                    "a la disposición utilizada para resolver "
                    "la venta."
                )
            }
        )

    selection_position = (
        layout.positions.filter(
            identifier__iexact=locked_sale.selection,
        )
        .select_related("product")
        .first()
    )

    selection_product = (
        selection_position.product
        if (
            selection_position is not None and selection_position.product_id is not None
        )
        else None
    )

    if selection_product is not None and selection_product.pk != product.pk:
        raise ValidationError(
            {
                "product": (
                    "La selección recibida identifica "
                    "un producto concreto en la disposición "
                    "utilizada para resolver la venta y no "
                    "puede sustituirse por otro."
                )
            }
        )

    replaced_sale = None

    if is_conflict and locked_sale.conflicts_with_id is not None:
        replaced_sale = Sale.objects.select_for_update().get(
            pk=locked_sale.conflicts_with_id,
        )

    _validate_sale_stock(
        machine,
        product,
        locked_sale.quantity,
        replaced_sale=replaced_sale,
    )

    locked_sale.machine = machine
    locked_sale.product = product
    locked_sale.resolution_layout = resolution_layout

    if is_conflict:
        locked_sale.status = Sale.Status.CONFLICT
    else:
        locked_sale.status = Sale.Status.RESOLVED
    locked_sale.save()

    return locked_sale


@transaction.atomic
def create_manual_sale(
    *,
    machine,
    product,
    occurred_at,
    quantity,
    dispense_type,
    selection="",
    event_id=None,
    unit_price=None,
    amount_received=None,
    payment_method="",
):
    if machine is None:
        raise ValidationError({"machine": ("Debe seleccionarse una máquina.")})

    if occurred_at is None:
        raise ValidationError(
            {"occurred_at": ("Debe indicarse la fecha y hora real de la venta.")}
        )

    selection = str(selection or "").strip()

    if product is None:
        if not selection:
            raise ValidationError(
                {
                    "product": (
                        "Selecciona un producto o indica la selección "
                        "de la máquina para identificarlo automáticamente."
                    )
                }
            )

        layout = get_machine_layout_at(
            machine,
            occurred_at,
        )

        if layout is None:
            raise ValidationError(
                {
                    "selection": (
                        "No había ninguna disposición activa para esta máquina "
                        "en la fecha indicada."
                    )
                }
            )

        product = get_product_for_selection(
            machine,
            selection,
            occurred_at,
        )

        if product is None:
            raise ValidationError(
                {
                    "selection": (
                        "La selección indicada no existe o no tiene un producto "
                        "asignado en la disposición activa de esa fecha."
                    )
                }
            )

    quantity = _parse_positive_integer(
        quantity,
        "quantity",
    )

    if dispense_type not in (
        Sale.DispenseType.PAID,
        Sale.DispenseType.FREE,
    ):
        raise ValidationError(
            {"dispense_type": ("El tipo de dispensación debe ser 'paid' o 'free'.")}
        )

    unit_price = _parse_optional_decimal(
        unit_price,
        "unit_price",
    )

    amount_received = _parse_optional_decimal(
        amount_received,
        "amount_received",
    )

    payment_method = str(payment_method or "").strip()

    if dispense_type == Sale.DispenseType.PAID:
        economic_errors = {}

        if unit_price is None:
            economic_errors["unit_price"] = (
                "Debe indicarse el precio unitario de una venta manual pagada."
            )

        if amount_received is None:
            economic_errors["amount_received"] = (
                "Debe indicarse el importe recibido de una venta manual pagada."
            )

        if not payment_method:
            economic_errors["payment_method"] = (
                "Debe indicarse el medio de pago de una venta manual pagada."
            )

        if economic_errors:
            raise ValidationError(economic_errors)

    else:
        unit_price = None
        amount_received = Decimal("0.00")
        payment_method = ""

    event_id = str(event_id).strip() if event_id else None

    if event_id:
        existing_sale = Sale.objects.filter(
            event_id=event_id,
        ).first()

        if existing_sale is not None:
            raise ValidationError(
                {
                    "event_id": (
                        "Ya existe una recepción con este "
                        "identificador de evento. Debe revisarse "
                        "la venta existente en lugar de crear "
                        "una nueva venta manual."
                    )
                }
            )

    _validate_sale_stock(machine, product, quantity)

    sale = Sale.objects.create(
        source=Sale.Source.MANUAL,
        event_id=event_id,
        payload_hash="",
        machine_identifier=(machine.identifier),
        machine=machine,
        selection=selection,
        product=product,
        occurred_at=occurred_at,
        quantity=quantity,
        dispense_type=dispense_type,
        unit_price=unit_price,
        amount_received=amount_received,
        payment_method=payment_method,
        status=Sale.Status.RESOLVED,
        raw_payload=None,
    )

    return sale
