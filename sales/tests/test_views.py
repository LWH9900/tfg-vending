import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import (
    Category,
    Product,
)
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
)
from machines.services.layouts import (
    activate_machine_layout,
)
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

    def test_unresolved_sale_returns_201_as_pending(self):
        payload = self.make_payload(
            event_id="evt-api-pending",
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

        data = response.json()

        self.assertTrue(data["created"])

        self.assertEqual(
            data["status"],
            Sale.Status.PENDING,
        )

        sale = Sale.objects.get(
            event_id="evt-api-pending",
        )

        self.assertIsNone(
            sale.product,
        )

    def test_repeated_event_returns_existing_sale(self):
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
