from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
)
from machines.services.layouts import (
    activate_machine_layout,
)
from sales.models import Sale
from sales.services import receive_sale


class SaleServiceTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-SALE-001",
            name="Máquina ventas",
            serial_number="SN-SALE-001",
            rows=4,
            columns=4,
        )

        self.category = Category.objects.create(
            name="Bebidas ventas",
            default_vat_rate=Decimal("21.00"),
        )

        self.product_a = Product.objects.create(
            name="VimaCola Sale",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            name="VimaTea Sale",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.layout_a = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición A",
        )

        MachinePosition.objects.create(
            layout=self.layout_a,
            identifier="A1",
            row=1,
            column=1,
            product=self.product_a,
        )

        MachinePosition.objects.create(
            layout=self.layout_a,
            identifier="A2",
            row=1,
            column=2,
            product=None,
        )

        self.layout_a.status = MachineLayout.Status.REGISTERED
        self.layout_a.save()

        self.layout_b = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición B",
        )

        MachinePosition.objects.create(
            layout=self.layout_b,
            identifier="A1",
            row=1,
            column=1,
            product=self.product_b,
        )

        self.layout_b.status = MachineLayout.Status.REGISTERED
        self.layout_b.save()

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
        event_id="evt-001",
        machine_identifier="VM-SALE-001",
        selection="A1",
        occurred_at="2026-09-02T10:30:00+02:00",
        quantity=1,
        dispense_type="paid",
        unit_price="1.50",
        amount_received="1.50",
        payment_method="cash",
    ):
        return {
            "event_id": event_id,
            "machine_identifier": machine_identifier,
            "selection": selection,
            "occurred_at": occurred_at,
            "quantity": quantity,
            "dispense_type": dispense_type,
            "unit_price": unit_price,
            "amount_received": amount_received,
            "payment_method": payment_method,
        }

    def test_receive_sale_resolves_machine_and_product(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            occurred_at=sale_time.isoformat(),
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertEqual(
            sale.product,
            self.product_a,
        )

        self.assertEqual(
            sale.selection,
            "A1",
        )

    def test_receive_sale_uses_historical_layout(self):
        first_activation = self.make_datetime(
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

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_activation,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        payload = self.make_payload(
            event_id="evt-historical",
            occurred_at=sale_time.isoformat(),
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.product,
            self.product_a,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

    def test_unknown_machine_creates_pending_sale(self):
        payload = self.make_payload(
            event_id="evt-unknown-machine",
            machine_identifier="VM-NO-EXISTE",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

        self.assertIsNone(
            sale.machine,
        )

        self.assertIsNone(
            sale.product,
        )

        self.assertEqual(
            sale.machine_identifier,
            "VM-NO-EXISTE",
        )

    def test_sale_without_active_layout_is_pending(self):
        payload = self.make_payload(
            event_id="evt-no-layout",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertIsNone(
            sale.product,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_unknown_selection_creates_pending_sale(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-unknown-selection",
            selection="Z9",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertIsNone(
            sale.product,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_position_without_product_creates_pending_sale(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-empty-position",
            selection="A2",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertIsNone(
            sale.product,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_repeated_event_is_idempotent(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-idempotent",
        )

        first_sale, first_created = receive_sale(payload)

        second_sale, second_created = receive_sale(payload)

        self.assertTrue(first_created)

        self.assertFalse(second_created)

        self.assertEqual(
            first_sale.pk,
            second_sale.pk,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-idempotent",
            ).count(),
            1,
        )

    def test_free_sale_without_amount_received_uses_zero(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-free",
            dispense_type="free",
            amount_received=None,
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.dispense_type,
            Sale.DispenseType.FREE,
        )

        self.assertEqual(
            sale.amount_received,
            Decimal("0.00"),
        )

    def test_paid_sale_can_have_unknown_amount_received(self):
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-paid-no-amount",
            amount_received=None,
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.dispense_type,
            Sale.DispenseType.PAID,
        )

        self.assertIsNone(
            sale.amount_received,
        )

    def test_receive_sale_preserves_raw_payload(self):
        payload = self.make_payload(
            event_id="evt-raw",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.raw_payload,
            payload,
        )

    def test_invalid_dispense_type_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-invalid-type",
            dispense_type="unknown",
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-invalid-type",
            ).exists()
        )

    def test_zero_quantity_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-zero-quantity",
            quantity=0,
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-zero-quantity",
            ).exists()
        )

    def test_occurred_at_without_timezone_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-naive-date",
            occurred_at="2026-09-02T10:30:00",
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-naive-date",
            ).exists()
        )
