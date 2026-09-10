import json
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from inventory.models import Product
from inventory.services import get_machine_stock
from machines.models import Machine
from machines.services.layouts import (
    get_machine_layout_at,
    get_machine_layout_resolution_candidates,
)
from machines.services.pricing import (
    get_product_price_for_machine,
)
from sales.forms import (
    PROJECTION_MODE_DATES,
    PROJECTION_MODE_DAYS,
    ManualSaleForm,
    ResolvePendingMachineForm,
    ResolvePendingSaleForm,
    SaleFilterForm,
    SalesProjectionForm,
    VoidSaleForm,
)
from sales.models import Sale
from sales.services import (
    accept_sale_conflict,
    create_manual_sale,
    get_sales_projection,
    receive_sale,
    reject_sale_conflict,
    resolve_pending_sale,
    void_sale,
)


def _get_projection_data(request):
    initial_data = {
        "mode": PROJECTION_MODE_DAYS,
        "history_days": 30,
        "forecast_days": 7,
    }

    form = SalesProjectionForm(request.GET or initial_data)
    projections = []
    periods = {}

    if not form.is_valid():
        return form, projections, periods

    if form.cleaned_data["mode"] == PROJECTION_MODE_DATES:
        history_start = form.cleaned_data["history_start"]
        history_end = form.cleaned_data["history_end"]
        forecast_start = form.cleaned_data["forecast_start"]
        forecast_end = form.cleaned_data["forecast_end"]
    else:
        today = timezone.localdate()

        history_end = today
        history_start = today - timedelta(days=form.cleaned_data["history_days"] - 1)

        forecast_start = today + timedelta(days=1)
        forecast_end = forecast_start + timedelta(
            days=form.cleaned_data["forecast_days"] - 1
        )

    periods = {
        "history_start": history_start,
        "history_end": history_end,
        "forecast_start": forecast_start,
        "forecast_end": forecast_end,
        "history_days": (history_end - history_start).days + 1,
        "forecast_days": (forecast_end - forecast_start).days + 1,
    }

    projections = get_sales_projection(
        history_start,
        history_end,
        forecast_start,
        forecast_end,
    )

    return form, projections, periods


def sales_projection(request):
    form, projections, periods = _get_projection_data(request)

    context = {
        "form": form,
        "projections": projections,
        "periods": periods,
        "query_string": request.GET.urlencode(),
    }

    return render(
        request,
        "sales/sales_projection.html",
        context,
    )


def sales_projection_detail(request, pk):
    product = get_object_or_404(
        Product,
        pk=pk,
        is_active=True,
    )

    form, projections, periods = _get_projection_data(request)

    projection = next(
        (item for item in projections if item["product"].pk == product.pk),
        None,
    )

    sales_history_query = ""

    if periods:
        sales_history_query = urlencode(
            {
                "product": product.pk,
                "date_from": (f"{periods['history_start'].isoformat()}T00:00"),
                "date_to": (f"{periods['history_end'].isoformat()}T23:59"),
            }
        )

    context = {
        "form": form,
        "product": product,
        "projection": projection,
        "periods": periods,
        "query_string": request.GET.urlencode(),
        "sales_history_query": sales_history_query,
    }

    return render(
        request,
        "sales/sales_projection_detail.html",
        context,
    )


def sale_list(
    request,
):
    session_key = "sales_filter_query"

    if request.GET.get("clear_filters") == "1":
        request.session.pop(session_key, None)
        return redirect("sales:sale_list")

    if request.GET:
        filter_query = request.GET.copy()
        filter_query.pop("page", None)
        request.session[session_key] = filter_query.urlencode()
    else:
        saved_query = request.session.get(session_key)
        if saved_query:
            return redirect(f"{request.path}?{saved_query}")

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

    paginator = Paginator(sales, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        "sales/sale_list.html",
        {
            "sales": page_obj.object_list,
            "filter_form": filter_form,
            "page_obj": page_obj,
            "pagination_query": query_params.urlencode(),
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

    payload = None

    if sale.raw_payload is not None:
        payload = json.dumps(
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
            "payload": (payload),
        },
    )


def sale_resolve(
    request,
    pk,
):
    sale = get_object_or_404(
        Sale.objects.select_related(
            "machine",
            "product",
        ),
        pk=pk,
    )

    if sale.status not in (
        Sale.Status.PENDING,
        Sale.Status.CONFLICT,
    ):
        messages.error(
            request,
            "Solo se pueden resolver ventas pendientes o en conflicto.",
        )

        return redirect(
            "sales:sale_detail",
            pk=sale.pk,
        )
    is_conflict = sale.status == Sale.Status.CONFLICT
    formatted_payload = None

    if sale.raw_payload is not None:
        formatted_payload = json.dumps(
            sale.raw_payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    machine_form = None

    selected_machine = sale.machine

    if selected_machine is None:
        machine_form = ResolvePendingMachineForm(request.GET or None)

        if machine_form.is_valid():
            selected_machine = machine_form.cleaned_data["machine"]

        elif request.method == "POST":
            machine_id = request.POST.get("machine")

            if machine_id:
                selected_machine = Machine.objects.filter(
                    pk=machine_id,
                ).first()

    historical_layout = None
    layout = None

    layout_candidates = []
    selected_reference_layout = None
    reference_layout_error = False

    automatic_product = None

    candidate_products = Product.objects.none()

    candidate_positions = []

    if selected_machine is not None:
        historical_layout = get_machine_layout_at(
            selected_machine,
            sale.occurred_at,
        )

        if historical_layout is not None:
            layout = historical_layout

        else:
            layout_candidates = get_machine_layout_resolution_candidates(
                selected_machine,
                sale.occurred_at,
            )

            candidate_by_id = {
                str(candidate["layout"].pk): candidate
                for candidate in layout_candidates
            }

            if request.method == "POST":
                requested_layout_id = request.POST.get("reference_layout")

            else:
                requested_layout_id = request.GET.get("layout")

            if requested_layout_id:
                candidate = candidate_by_id.get(str(requested_layout_id))

                if candidate is not None:
                    selected_reference_layout = candidate["layout"]

                    layout = selected_reference_layout

                else:
                    reference_layout_error = True

    if layout is not None:
        selection_position = (
            layout.positions.filter(
                identifier__iexact=sale.selection,
                product__isnull=False,
            )
            .select_related(
                "product",
                "product__category",
            )
            .first()
        )

        if selection_position is not None:
            automatic_product = selection_position.product

        candidate_products = (
            Product.objects.filter(
                machine_positions__layout=layout,
            )
            .select_related("category")
            .distinct()
            .order_by(
                "name",
                "category__name",
                "format_unit",
            )
        )

        positions = (
            layout.positions.filter(
                product__isnull=False,
            )
            .select_related(
                "product",
                "product__category",
            )
            .order_by(
                "row",
                "column",
                "identifier",
            )
        )

        for position in positions:
            candidate_positions.append(
                {
                    "position": position,
                    "product": (position.product),
                    "current_price": (
                        get_product_price_for_machine(
                            selected_machine,
                            position.product,
                        )
                    ),
                    "machine_stock": (
                        get_machine_stock(
                            position.product,
                            selected_machine,
                        )
                    ),
                }
            )

    form = None

    if layout is not None:
        reference_layouts = []

        if historical_layout is None:
            reference_layouts = [candidate["layout"] for candidate in layout_candidates]

        form = ResolvePendingSaleForm(
            request.POST or None,
            machine=selected_machine,
            candidate_products=(candidate_products),
            automatic_product=(automatic_product),
            reference_layouts=(reference_layouts),
            selected_reference_layout=(selected_reference_layout),
        )

        if request.method == "POST" and form.is_valid():
            try:
                resolved_sale = resolve_pending_sale(
                    sale,
                    machine=(form.cleaned_data["machine"]),
                    product=(form.cleaned_data["product"]),
                    reference_layout=(form.cleaned_data["reference_layout"]),
                )

            except ValidationError as error:
                if hasattr(
                    error,
                    "message_dict",
                ):
                    for (
                        field,
                        error_messages,
                    ) in error.message_dict.items():
                        target_field = field if field in form.fields else None

                        for message in error_messages:
                            form.add_error(
                                target_field,
                                message,
                            )

                else:
                    form.add_error(
                        None,
                        error,
                    )

            else:
                if is_conflict:
                    messages.success(
                        request,
                        (
                            "Los datos de la recepción conflictiva se han resuelto. "
                            "Ahora puedes decidir si debe sustituir a la venta "
                            "efectiva."
                        ),
                    )

                    return redirect(
                        "sales:sale_conflict_review",
                        pk=resolved_sale.pk,
                    )

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
            "machine_form": machine_form,
            "selected_machine": (selected_machine),
            "historical_layout": (historical_layout),
            "layout": layout,
            "layout_candidates": (layout_candidates),
            "selected_reference_layout": (selected_reference_layout),
            "reference_layout_error": (reference_layout_error),
            "automatic_product": (automatic_product),
            "candidate_positions": (candidate_positions),
            "form": form,
            "formatted_payload": (formatted_payload),
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


def sale_manual_create(
    request,
):
    form = ManualSaleForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            sale = create_manual_sale(
                event_id=(form.cleaned_data["event_id"]),
                machine=(form.cleaned_data["machine"]),
                product=(form.cleaned_data["product"]),
                selection=(form.cleaned_data["selection"]),
                occurred_at=(form.cleaned_data["occurred_at"]),
                quantity=(form.cleaned_data["quantity"]),
                dispense_type=(form.cleaned_data["dispense_type"]),
                unit_price=(form.cleaned_data["unit_price"]),
                amount_received=(form.cleaned_data["amount_received"]),
                payment_method=(form.cleaned_data["payment_method"]),
            )

        except ValidationError as error:
            if hasattr(
                error,
                "message_dict",
            ):
                for field, messages_list in error.message_dict.items():
                    target_field = field if field in form.fields else None

                    for message in messages_list:
                        form.add_error(
                            target_field,
                            message,
                        )

            else:
                form.add_error(
                    None,
                    error,
                )

        else:
            messages.success(
                request,
                "La venta manual se ha registrado correctamente.",
            )

            return redirect(
                "sales:sale_detail",
                pk=sale.pk,
            )

    return render(
        request,
        "sales/sale_manual_create.html",
        {
            "form": form,
        },
    )
