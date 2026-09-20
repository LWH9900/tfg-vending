import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import (
    Category,
    Product,
)
from inventory.services import get_machine_stock, get_total_stock, get_warehouse_stock
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
)
from machines.services.layouts import (
    activate_machine_layout,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale


class SaleReceiveViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-SALE-API-001",
            name="Máquina ventas API",
            serial_number="SN-SALE-API-001",
            rows=4,
            columns=4,
        )

        self.category = Category.objects.create(
            name="Bebidas API",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaCola API",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición API",
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        self.layout.status = MachineLayout.Status.REGISTERED
        self.layout.save()

        self.url = reverse("sales:sale_receive")

    def make_datetime(
        self,
        year,
        month,
        day,
        hour=0,
        minute=0,
    ):
        return timezone.make_aware(
            datetime(
                year,
                month,
                day,
                hour,
                minute,
            )
        )

    def make_payload(
        self,
        event_id="evt-api-001",
        machine_identifier="VM-SALE-API-001",
        selection="A1",
        occurred_at=None,
        quantity=1,
        dispense_type="paid",
    ):
        if occurred_at is None:
            occurred_at = self.make_datetime(
                2026,
                9,
                2,
                10,
                30,
            ).isoformat()

        return {
            "event_id": event_id,
            "machine_identifier": (machine_identifier),
            "selection": selection,
            "occurred_at": occurred_at,
            "quantity": quantity,
            "dispense_type": dispense_type,
            "unit_price": "1.50",
            "amount_received": "1.50",
            "payment_method": "cash",
        }

    def create_stock(self, quantity=1):
        purchase = Purchase.objects.create(
            supplier="Proveedor API",
            status=Purchase.Status.REGISTERED,
        )
        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )
        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=quantity,
        )

    def test_receive_sale_requires_post(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_receive_valid_sale_returns_201(self):
        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        purchase = Purchase.objects.create(
            supplier="Proveedor API",
            status=Purchase.Status.REGISTERED,
        )
        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=1,
            unit_price_excl_vat=Decimal("1.00"),
        )
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )
        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=1,
        )

        payload = self.make_payload()

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        data = response.json()

        self.assertTrue(data["created"])

        self.assertEqual(
            data["event_id"],
            "evt-api-001",
        )

        self.assertEqual(
            data["status"],
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            Sale.objects.count(),
            1,
        )

    def test_receive_sale_without_stock_returns_error_and_is_not_saved(self):
        activation_time = self.make_datetime(2026, 9, 2, 9, 0)

        with patch("django.utils.timezone.now", return_value=activation_time):
            activate_machine_layout(self.layout)

        response = self.client.post(
            self.url,
            data=json.dumps(self.make_payload(event_id="evt-without-stock")),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Stock insuficiente", response.json()["errors"]["quantity"][0])
        self.assertFalse(Sale.objects.filter(event_id="evt-without-stock").exists())

    def test_receive_valid_sale_resolves_product(self):
        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        self.create_stock()

        payload = self.make_payload(
            event_id="evt-api-product",
        )

        self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        sale = Sale.objects.get(
            event_id="evt-api-product",
        )

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertEqual(
            sale.product,
            self.product,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

    def test_known_machine_without_resolved_product_is_pending(self):
        payload = self.make_payload(
            event_id="evt-api-pending",
        )

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        data = response.json()

        self.assertEqual(data["status"], Sale.Status.PENDING)
        self.assertTrue(Sale.objects.filter(event_id="evt-api-pending").exists())

    def test_historically_unresolved_selection_remains_pending(self):
        activation_time = self.make_datetime(2026, 9, 2, 9, 0)

        with patch("django.utils.timezone.now", return_value=activation_time):
            activate_machine_layout(self.layout)

        response = self.client.post(
            self.url,
            data=json.dumps(
                self.make_payload(
                    event_id="evt-api-old-without-stock",
                    occurred_at=self.make_datetime(2026, 9, 1, 14, 16).isoformat(),
                )
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Sale.Status.PENDING)
        self.assertTrue(
            Sale.objects.filter(event_id="evt-api-old-without-stock").exists()
        )

    def test_incomplete_occurred_at_is_rejected(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                self.make_payload(
                    event_id="evt-api-invalid-date",
                    occurred_at="2026-09-09T14:16:+02:00",
                )
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("occurred_at", response.json()["errors"])
        self.assertFalse(Sale.objects.filter(event_id="evt-api-invalid-date").exists())

    def test_unknown_machine_is_saved_as_pending(self):
        response = self.client.post(
            self.url,
            data=json.dumps(
                self.make_payload(
                    event_id="evt-api-unknown-machine",
                    machine_identifier="VM-UNKNOWN",
                )
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Sale.Status.PENDING)
        self.assertTrue(
            Sale.objects.filter(event_id="evt-api-unknown-machine").exists()
        )

    def test_repeated_event_returns_existing_sale(self):
        self.create_stock(quantity=10)

        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        payload = self.make_payload(
            event_id="evt-api-duplicate",
        )

        first_response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        second_response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            first_response.status_code,
            201,
        )

        self.assertEqual(
            second_response.status_code,
            200,
        )
        self.assertEqual(
            second_response.json()["status"],
            Sale.Status.RESOLVED,
        )

        self.assertFalse(second_response.json()["created"])

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-api-duplicate",
            ).count(),
            1,
        )

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            self.url,
            data="{invalid-json",
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            Sale.objects.count(),
            0,
        )

    def test_missing_required_field_returns_400(self):
        payload = self.make_payload(
            event_id="evt-api-missing",
        )

        del payload["selection"]

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertEqual(
            Sale.objects.count(),
            0,
        )

    def test_non_json_content_type_returns_415(self):
        response = self.client.post(
            self.url,
            data="event_id=evt-001",
            content_type=("application/x-www-form-urlencoded"),
        )

        self.assertEqual(
            response.status_code,
            415,
        )

        self.assertEqual(
            Sale.objects.count(),
            0,
        )

    def test_receive_endpoint_does_not_require_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)

        payload = self.make_payload(
            event_id="evt-api-no-csrf",
        )

        response = client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertNotEqual(
            response.status_code,
            403,
        )

    def test_different_payload_for_same_event_returns_409(self):
        self.create_stock(quantity=10)

        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        first_payload = self.make_payload(
            event_id="evt-api-conflict",
            occurred_at=sale_time.isoformat(),
        )

        first_response = self.client.post(
            self.url,
            data=json.dumps(first_payload),
            content_type="application/json",
        )

        self.assertEqual(
            first_response.status_code,
            201,
        )

        conflicting_payload = self.make_payload(
            event_id="evt-api-conflict",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        conflict_response = self.client.post(
            self.url,
            data=json.dumps(conflicting_payload),
            content_type="application/json",
        )

        self.assertEqual(
            conflict_response.status_code,
            409,
        )

        data = conflict_response.json()

        self.assertTrue(data["created"])

        self.assertEqual(
            data["status"],
            Sale.Status.CONFLICT,
        )

        self.assertIn(
            "conflicts_with",
            data,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-api-conflict",
            ).count(),
            2,
        )

    def test_conflict_response_references_original_sale(self):
        self.create_stock(quantity=10)

        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        first_payload = self.make_payload(
            event_id="evt-api-reference",
            occurred_at=sale_time.isoformat(),
        )

        self.client.post(
            self.url,
            data=json.dumps(first_payload),
            content_type="application/json",
        )

        original_sale = Sale.objects.get(
            event_id="evt-api-reference",
            status=Sale.Status.RESOLVED,
        )

        conflicting_payload = self.make_payload(
            event_id="evt-api-reference",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        response = self.client.post(
            self.url,
            data=json.dumps(conflicting_payload),
            content_type="application/json",
        )

        data = response.json()

        conflict_sale = Sale.objects.get(
            event_id="evt-api-reference",
            status=Sale.Status.CONFLICT,
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            conflict_sale.conflicts_with,
            original_sale,
        )

        self.assertEqual(
            data["conflicts_with"],
            original_sale.pk,
        )

    def test_repeated_conflicting_payload_returns_same_conflict(self):
        self.create_stock(quantity=10)

        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        original_payload = self.make_payload(
            event_id="evt-api-repeat-conflict",
            occurred_at=sale_time.isoformat(),
        )

        self.client.post(
            self.url,
            data=json.dumps(original_payload),
            content_type="application/json",
        )

        conflicting_payload = self.make_payload(
            event_id="evt-api-repeat-conflict",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        first_conflict_response = self.client.post(
            self.url,
            data=json.dumps(conflicting_payload),
            content_type="application/json",
        )

        repeated_conflict_response = self.client.post(
            self.url,
            data=json.dumps(conflicting_payload),
            content_type="application/json",
        )

        self.assertEqual(
            first_conflict_response.status_code,
            409,
        )

        self.assertEqual(
            repeated_conflict_response.status_code,
            409,
        )

        first_data = first_conflict_response.json()

        repeated_data = repeated_conflict_response.json()

        self.assertTrue(first_data["created"])

        self.assertFalse(repeated_data["created"])

        self.assertEqual(
            first_data["id"],
            repeated_data["id"],
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-api-repeat-conflict",
            ).count(),
            2,
        )

    def test_received_sale_flows_to_inventory_and_history(
        self,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor integración",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=self.make_datetime(
                2026,
                9,
                2,
                9,
                30,
            ),
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=6,
        )

        activation_time = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        payload = self.make_payload(
            event_id="evt-complete-flow",
        )

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        sale = Sale.objects.get(
            event_id="evt-complete-flow",
        )

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            sale.unit_price,
            Decimal("1.50"),
        )

        self.assertEqual(
            get_total_stock(self.product),
            9,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            4,
        )

        history_response = self.client.get(
            reverse("sales:sale_list"),
            {
                "event_id": "evt-complete-flow",
                "machine": self.machine.pk,
                "product": self.product.pk,
                "status": Sale.Status.RESOLVED,
            },
        )

        self.assertEqual(
            history_response.status_code,
            200,
        )

        self.assertIn(
            sale,
            history_response.context["sales"],
        )


class SaleManagementViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-SALE-VIEW-001",
            name="Máquina vistas ventas",
            serial_number="SN-SALE-VIEW-001",
            rows=4,
            columns=4,
        )

        self.category = Category.objects.create(
            name="Bebidas vistas ventas",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaCola vistas",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición vistas",
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        self.layout.status = MachineLayout.Status.REGISTERED
        self.layout.save()

    def make_datetime(
        self,
        year,
        month,
        day,
        hour=0,
        minute=0,
    ):
        return timezone.make_aware(
            datetime(
                year,
                month,
                day,
                hour,
                minute,
            )
        )

    def create_sale(
        self,
        *,
        event_id,
        status=Sale.Status.PENDING,
        occurred_at=None,
        product=None,
    ):
        occurred_at = occurred_at or self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        return Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id=event_id,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            selection="A1",
            product=product,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=status,
            raw_payload={
                "event_id": event_id,
            },
        )

    def test_sales_projection_uses_default_day_periods(self):
        today = date(
            2026,
            9,
            8,
        )

        with (
            patch(
                "sales.views.timezone.localdate",
                return_value=today,
            ),
            patch(
                "sales.views.get_sales_projection",
                return_value=[],
            ) as mock_projection,
        ):
            response = self.client.get(
                reverse(
                    "sales:sales_projection",
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        periods = response.context["periods"]

        self.assertEqual(
            periods["history_start"],
            date(
                2026,
                8,
                10,
            ),
        )
        self.assertEqual(
            periods["history_end"],
            today,
        )
        self.assertEqual(
            periods["forecast_start"],
            date(
                2026,
                9,
                9,
            ),
        )
        self.assertEqual(
            periods["forecast_end"],
            date(
                2026,
                9,
                15,
            ),
        )
        self.assertEqual(
            periods["history_days"],
            30,
        )
        self.assertEqual(
            periods["forecast_days"],
            7,
        )

        mock_projection.assert_called_once_with(
            date(
                2026,
                8,
                10,
            ),
            today,
            date(
                2026,
                9,
                9,
            ),
            date(
                2026,
                9,
                15,
            ),
        )

    def test_sale_resolve_can_select_reference_layout_candidate(self):
        sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            0,
        )

        activation_time = self.make_datetime(
            2026,
            9,
            3,
            10,
            0,
        )

        sale = self.create_sale(
            event_id="evt-view-reference-layout",
            occurred_at=sale_time,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        response = self.client.get(
            reverse(
                "sales:sale_resolve",
                args=[sale.pk],
            ),
            {
                "layout": self.layout.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertIsNone(
            response.context["historical_layout"],
        )
        self.assertEqual(
            response.context["selected_reference_layout"],
            self.layout,
        )
        self.assertEqual(
            response.context["layout"],
            self.layout,
        )
        self.assertEqual(
            response.context["automatic_product"],
            self.product,
        )
        self.assertIsNotNone(
            response.context["form"],
        )
        self.assertEqual(
            len(response.context["candidate_positions"]),
            1,
        )

    def test_sale_resolve_rejects_unknown_reference_layout_candidate(self):
        sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            0,
        )

        activation_time = self.make_datetime(
            2026,
            9,
            3,
            10,
            0,
        )

        sale = self.create_sale(
            event_id="evt-view-invalid-reference",
            occurred_at=sale_time,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

        response = self.client.get(
            reverse(
                "sales:sale_resolve",
                args=[sale.pk],
            ),
            {
                "layout": 999999,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTrue(
            response.context["reference_layout_error"],
        )
        self.assertIsNone(
            response.context["selected_reference_layout"],
        )

    def test_sale_resolve_handles_malformed_machine_id(self):
        sale = self.create_sale(
            event_id="evt-view-malformed-machine",
        )
        sale.machine = None
        sale.save(update_fields=["machine"])

        response = self.client.post(
            reverse("sales:sale_resolve", args=[sale.pk]),
            {"machine": "not-a-number"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"])
        self.assertIn("machine", response.context["machine_form"].errors)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.PENDING)

    def test_sale_resolve_adds_service_field_errors_to_form(self):
        sale = self.create_sale(
            event_id="evt-view-resolution-field-error",
        )

        error = ValidationError(
            {
                "product": "Producto no válido.",
            }
        )

        with (
            patch(
                "sales.views.get_machine_layout_at",
                return_value=self.layout,
            ),
            patch(
                "sales.views.ResolvePendingSaleForm",
            ) as form_class,
            patch(
                "sales.views.resolve_pending_sale",
                side_effect=error,
            ),
            patch(
                "sales.views.render",
                return_value=HttpResponse("ok"),
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "machine": self.machine,
                "product": self.product,
                "reference_layout": None,
            }
            form.fields = {
                "machine": object(),
                "product": object(),
                "reference_layout": object(),
            }

            response = self.client.post(
                reverse(
                    "sales:sale_resolve",
                    args=[sale.pk],
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        form.add_error.assert_called_once_with(
            "product",
            "Producto no válido.",
        )

    def test_sale_resolve_adds_general_service_error_to_form(self):
        sale = self.create_sale(
            event_id="evt-view-resolution-general-error",
        )

        error = ValidationError("No se ha podido resolver la venta.")

        with (
            patch(
                "sales.views.get_machine_layout_at",
                return_value=self.layout,
            ),
            patch(
                "sales.views.ResolvePendingSaleForm",
            ) as form_class,
            patch(
                "sales.views.resolve_pending_sale",
                side_effect=error,
            ),
            patch(
                "sales.views.render",
                return_value=HttpResponse("ok"),
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "machine": self.machine,
                "product": self.product,
                "reference_layout": None,
            }

            response = self.client.post(
                reverse(
                    "sales:sale_resolve",
                    args=[sale.pk],
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        form.add_error.assert_called_once_with(
            None,
            error,
        )

    def test_resolved_conflict_redirects_to_conflict_review(self):
        sale = self.create_sale(
            event_id="evt-view-resolved-conflict",
        )

        Sale.objects.filter(
            pk=sale.pk,
        ).update(
            status=Sale.Status.CONFLICT,
        )
        sale.refresh_from_db()

        with (
            patch(
                "sales.views.get_machine_layout_at",
                return_value=self.layout,
            ),
            patch(
                "sales.views.ResolvePendingSaleForm",
            ) as form_class,
            patch(
                "sales.views.resolve_pending_sale",
                return_value=sale,
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "machine": self.machine,
                "product": self.product,
                "reference_layout": None,
            }

            response = self.client.post(
                reverse(
                    "sales:sale_resolve",
                    args=[sale.pk],
                ),
            )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse(
                "sales:sale_conflict_review",
                args=[sale.pk],
            ),
        )

    def test_sale_void_adds_service_error_to_form(self):
        sale = self.create_sale(
            event_id="evt-view-void-error",
            status=Sale.Status.RESOLVED,
            product=self.product,
        )

        error = ValidationError("No se ha podido anular la venta.")

        with (
            patch(
                "sales.views.VoidSaleForm",
            ) as form_class,
            patch(
                "sales.views.void_sale",
                side_effect=error,
            ),
            patch(
                "sales.views.render",
                return_value=HttpResponse("ok"),
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "reason": "Motivo de prueba.",
            }

            response = self.client.post(
                reverse(
                    "sales:sale_void",
                    args=[sale.pk],
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        form.add_error.assert_called_once_with(
            None,
            error,
        )

    def test_conflict_reject_handles_invalid_sale_status(self):
        sale = self.create_sale(
            event_id="evt-view-reject-invalid",
            status=Sale.Status.RESOLVED,
            product=self.product,
        )

        response = self.client.post(
            reverse(
                "sales:sale_conflict_reject",
                args=[sale.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse(
                "sales:sale_detail",
                args=[sale.pk],
            ),
        )

    def test_conflict_accept_handles_invalid_sale_status(self):
        sale = self.create_sale(
            event_id="evt-view-accept-invalid",
            status=Sale.Status.RESOLVED,
            product=self.product,
        )

        response = self.client.post(
            reverse(
                "sales:sale_conflict_accept",
                args=[sale.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse(
                "sales:sale_detail",
                args=[sale.pk],
            ),
        )

    def test_conflict_accept_handles_sale_without_previous_effective_sale(self):
        sale = self.create_sale(
            event_id="evt-view-accept-without-previous",
            product=self.product,
        )

        Sale.objects.filter(
            pk=sale.pk,
        ).update(
            status=Sale.Status.CONFLICT,
        )
        sale.refresh_from_db()

        with patch(
            "sales.views.accept_sale_conflict",
            return_value=(
                sale,
                None,
            ),
        ):
            response = self.client.post(
                reverse(
                    "sales:sale_conflict_accept",
                    args=[sale.pk],
                )
            )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse(
                "sales:sale_detail",
                args=[sale.pk],
            ),
        )

    def test_receive_sale_handles_general_validation_error(self):
        error = ValidationError("Error general de recepción.")

        with patch(
            "sales.views.receive_sale",
            side_effect=error,
        ):
            response = self.client.post(
                reverse(
                    "sales:sale_receive",
                ),
                data=json.dumps(
                    {
                        "event_id": "evt-view-general-error",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(
            response.status_code,
            400,
        )
        self.assertEqual(
            response.json()["errors"]["non_field_errors"],
            [
                "Error general de recepción.",
            ],
        )

    def test_manual_sale_product_status_accepts_naive_moment(self):
        response = self.client.get(
            reverse(
                "sales:manual_sale_product_status",
                args=[self.machine.pk],
            ),
            {
                "moment": "2026-09-02T10:30:00",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        products = response.json()["products"]

        self.assertEqual(
            len(products),
            1,
        )
        self.assertEqual(
            products[0]["id"],
            self.product.pk,
        )

    def test_manual_sale_create_adds_general_service_error(self):
        error = ValidationError("No se ha podido registrar la venta manual.")

        with (
            patch(
                "sales.views.ManualSaleForm",
            ) as form_class,
            patch(
                "sales.views.create_manual_sale",
                side_effect=error,
            ),
            patch(
                "sales.views.render",
                return_value=HttpResponse("ok"),
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "event_id": None,
                "machine": self.machine,
                "product": self.product,
                "selection": "",
                "occurred_at": self.make_datetime(
                    2026,
                    9,
                    3,
                    18,
                    0,
                ),
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": Decimal("1.50"),
                "amount_received": Decimal("1.50"),
                "payment_method": "cash",
            }

            response = self.client.post(
                reverse(
                    "sales:sale_manual_create",
                ),
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        form.add_error.assert_called_once_with(
            None,
            error,
        )
