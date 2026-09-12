from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_machines_stock,
    get_total_stock,
    get_warehouse_stock,
)
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
from sales import services as sale_services
from sales.models import Sale
from sales.services import (
    accept_sale_conflict,
    create_manual_sale,
    receive_sale,
    reject_sale_conflict,
    resolve_pending_sale,
    void_sale,
)


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

    def create_stock(
        self,
        product,
        purchased_quantity=10,
        replenished_quantity=6,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor A",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=product,
            quantity=purchased_quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=replenished_quantity,
        )

    def test_receive_sale_resolves_machine_and_product(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
        self.create_stock(self.product_a, replenished_quantity=10)

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
        self.create_stock(
            self.product_a,
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
        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

    def test_free_sale_without_amount_received_uses_zero(self):
        self.create_stock(
            self.product_a,
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
        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

    def test_paid_sale_can_have_unknown_amount_received(self):
        self.create_stock(
            self.product_a,
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

    def test_quantity_greater_than_one_is_accepted(self):
        self.create_stock(
            self.product_a,
            replenished_quantity=5,
        )

        payload = self.make_payload(
            event_id="evt-multiple-quantity",
            quantity=3,
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.quantity,
            3,
        )

    def test_decimal_quantity_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-decimal-quantity",
            quantity=1.9,
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-decimal-quantity",
            ).exists()
        )

    def test_boolean_quantity_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-boolean-quantity",
            quantity=True,
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-boolean-quantity",
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

    def test_resolved_paid_sale_reduces_total_and_machine_stock(self):
        self.create_stock(
            self.product_a,
        )

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

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

        payload = self.make_payload(
            event_id="evt-stock-paid",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

        self.assertEqual(
            get_machines_stock(self.product_a),
            4,
        )

    def test_resolved_free_sale_also_reduces_inventory(self):
        self.create_stock(
            self.product_a,
        )

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
            event_id="evt-stock-free",
            occurred_at=sale_time.isoformat(),
            quantity=1,
            dispense_type="free",
            amount_received=None,
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            sale.amount_received,
            Decimal("0.00"),
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

    def test_pending_sale_does_not_reduce_inventory(self):
        self.create_stock(
            self.product_a,
        )

        payload = self.make_payload(
            event_id="evt-stock-pending",
        )

        sale, created = receive_sale(payload)

        self.assertTrue(created)

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

    def test_repeated_event_does_not_reduce_inventory_twice(self):
        self.create_stock(
            self.product_a,
        )

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
            event_id="evt-stock-idempotent",
            occurred_at=sale_time.isoformat(),
            quantity=2,
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
                event_id="evt-stock-idempotent",
            ).count(),
            1,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

    def test_same_event_with_different_payload_creates_conflict(self):
        self.create_stock(self.product_a, replenished_quantity=10)
        self.create_stock(self.product_b, replenished_quantity=10)

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
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

        first_payload = self.make_payload(
            event_id="evt-conflict",
            occurred_at=first_sale_time.isoformat(),
            unit_price="1.50",
            amount_received="1.50",
        )

        first_sale, first_created = receive_sale(first_payload)

        second_payload = self.make_payload(
            event_id="evt-conflict",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        conflict_sale, conflict_created = receive_sale(second_payload)

        self.assertTrue(first_created)

        self.assertTrue(conflict_created)

        self.assertEqual(
            first_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            first_sale.product,
            self.product_a,
        )

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            conflict_sale.product,
            self.product_b,
        )

        self.assertEqual(
            conflict_sale.conflicts_with,
            first_sale,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-conflict",
            ).count(),
            2,
        )

    def test_conflict_sale_does_not_reduce_inventory(self):
        self.create_stock(
            self.product_a,
        )

        self.create_stock(
            self.product_b,
        )

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
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

        first_payload = self.make_payload(
            event_id="evt-conflict-stock",
            occurred_at=first_sale_time.isoformat(),
        )

        first_sale, _ = receive_sale(first_payload)

        conflict_payload = self.make_payload(
            event_id="evt-conflict-stock",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        conflict_sale, _ = receive_sale(conflict_payload)

        self.assertEqual(
            first_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_b,
                self.machine,
            ),
            6,
        )

    def test_repeated_conflicting_payload_is_idempotent(self):
        self.create_stock(self.product_a, replenished_quantity=10)
        self.create_stock(self.product_b, replenished_quantity=10)

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
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

        first_payload = self.make_payload(
            event_id="evt-repeat-conflict",
            occurred_at=first_sale_time.isoformat(),
        )

        receive_sale(first_payload)

        conflict_payload = self.make_payload(
            event_id="evt-repeat-conflict",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        first_conflict, first_created = receive_sale(conflict_payload)

        repeated_conflict, repeated_created = receive_sale(conflict_payload)

        self.assertTrue(first_created)

        self.assertFalse(repeated_created)

        self.assertEqual(
            first_conflict.pk,
            repeated_conflict.pk,
        )

        self.assertEqual(
            first_conflict.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-repeat-conflict",
            ).count(),
            2,
        )

    def test_multiple_different_conflicts_are_preserved(self):
        self.create_stock(self.product_a, replenished_quantity=10)
        self.create_stock(self.product_b, replenished_quantity=10)

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
            0,
        )

        third_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
            5,
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

        original_payload = self.make_payload(
            event_id="evt-multiple-conflicts",
            occurred_at=first_sale_time.isoformat(),
        )

        original_sale, _ = receive_sale(original_payload)

        second_payload = self.make_payload(
            event_id="evt-multiple-conflicts",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        second_sale, _ = receive_sale(second_payload)

        third_payload = self.make_payload(
            event_id="evt-multiple-conflicts",
            occurred_at=third_sale_time.isoformat(),
            quantity=2,
            unit_price="1.60",
            amount_received="3.20",
        )

        third_sale, _ = receive_sale(third_payload)

        self.assertEqual(
            original_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            second_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            third_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            second_sale.conflicts_with,
            original_sale,
        )

        self.assertEqual(
            third_sale.conflicts_with,
            original_sale,
        )

        self.assertNotEqual(
            second_sale.payload_hash,
            third_sale.payload_hash,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-multiple-conflicts",
            ).count(),
            3,
        )

    def test_payload_key_order_does_not_create_conflict(self):
        payload = self.make_payload(
            event_id="evt-key-order",
        )

        first_sale, first_created = receive_sale(payload)

        reordered_payload = dict(reversed(list(payload.items())))

        second_sale, second_created = receive_sale(reordered_payload)

        self.assertTrue(first_created)

        self.assertFalse(second_created)

        self.assertEqual(
            first_sale.pk,
            second_sale.pk,
        )

        self.assertEqual(
            first_sale.payload_hash,
            second_sale.payload_hash,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-key-order",
            ).count(),
            1,
        )

    def test_void_resolved_sale_restores_inventory(self):
        self.create_stock(
            self.product_a,
        )

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
            event_id="evt-void",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

        void_time = self.make_datetime(
            2026,
            9,
            3,
            10,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=void_time,
        ):
            voided_sale = void_sale(
                sale,
                "Dispensación registrada por error.",
            )

        self.assertEqual(
            voided_sale.status,
            Sale.Status.VOIDED,
        )

        self.assertEqual(
            voided_sale.void_reason,
            "Dispensación registrada por error.",
        )

        self.assertEqual(
            voided_sale.voided_at,
            void_time,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_void_sale_requires_reason(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-void-no-reason",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            void_sale(
                sale,
                "",
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

    def test_voided_sale_cannot_be_voided_again(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-double-void",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        void_sale(
            sale,
            "Primera anulación.",
        )

        with self.assertRaises(ValidationError):
            void_sale(
                sale,
                "Segunda anulación.",
            )

    def test_reject_conflict_keeps_original_sale_effective(self):
        self.create_stock(
            self.product_a,
        )

        self.create_stock(
            self.product_b,
        )

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
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

        original_payload = self.make_payload(
            event_id="evt-reject-conflict",
            occurred_at=first_sale_time.isoformat(),
        )

        original_sale, _ = receive_sale(original_payload)

        conflict_payload = self.make_payload(
            event_id="evt-reject-conflict",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        conflict_sale, _ = receive_sale(conflict_payload)

        rejected_sale = reject_sale_conflict(conflict_sale)

        original_sale.refresh_from_db()

        self.assertEqual(
            original_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            rejected_sale.status,
            Sale.Status.REJECTED,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            10,
        )

    def test_accept_conflict_switches_effective_inventory_sale(self):
        self.create_stock(
            self.product_a,
        )

        self.create_stock(
            self.product_b,
        )

        first_activation = self.make_datetime(
            2026,
            9,
            2,
            9,
            0,
        )

        second_activation = self.make_datetime(
            2026,
            9,
            2,
            12,
            0,
        )

        first_sale_time = self.make_datetime(
            2026,
            9,
            2,
            10,
            30,
        )

        second_sale_time = self.make_datetime(
            2026,
            9,
            2,
            13,
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

        original_payload = self.make_payload(
            event_id="evt-accept-conflict",
            occurred_at=first_sale_time.isoformat(),
            unit_price="1.50",
            amount_received="1.50",
        )

        original_sale, _ = receive_sale(original_payload)

        conflict_payload = self.make_payload(
            event_id="evt-accept-conflict",
            occurred_at=second_sale_time.isoformat(),
            unit_price="1.60",
            amount_received="1.60",
        )

        conflict_sale, _ = receive_sale(conflict_payload)

        self.assertEqual(
            original_sale.product,
            self.product_a,
        )

        self.assertEqual(
            conflict_sale.product,
            self.product_b,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_b,
                self.machine,
            ),
            6,
        )

        review_time = self.make_datetime(
            2026,
            9,
            3,
            10,
            30,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=review_time,
        ):
            accepted_sale, voided_sale = accept_sale_conflict(conflict_sale)

        self.assertEqual(
            accepted_sale.pk,
            conflict_sale.pk,
        )

        self.assertEqual(
            accepted_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            accepted_sale.product,
            self.product_b,
        )

        self.assertEqual(
            voided_sale.pk,
            original_sale.pk,
        )

        self.assertEqual(
            voided_sale.status,
            Sale.Status.VOIDED,
        )

        self.assertEqual(
            voided_sale.voided_at,
            review_time,
        )

        self.assertTrue(voided_sale.void_reason)

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            9,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_b,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_b),
            4,
        )

    def test_conflict_without_product_cannot_be_accepted(self):
        first_payload = self.make_payload(
            event_id="evt-unresolved-conflict",
            selection="Z9",
        )

        original_sale, _ = receive_sale(first_payload)

        second_payload = self.make_payload(
            event_id="evt-unresolved-conflict",
            selection="Z8",
        )

        conflict_sale, _ = receive_sale(second_payload)

        self.assertEqual(
            original_sale.status,
            Sale.Status.PENDING,
        )

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertIsNone(
            conflict_sale.product,
        )

        with self.assertRaises(ValidationError):
            accept_sale_conflict(conflict_sale)

        conflict_sale.refresh_from_db()

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

    def test_unresolved_conflict_can_resolve_machine_and_product(self):
        self.create_stock(
            self.product_a,
            replenished_quantity=10,
        )

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

        original_sale, _ = receive_sale(
            self.make_payload(
                event_id="evt-conflict-resolution",
                occurred_at=sale_time.isoformat(),
            )
        )

        conflict_sale, _ = receive_sale(
            self.make_payload(
                event_id="evt-conflict-resolution",
                machine_identifier="VM-UNKNOWN",
                occurred_at=sale_time.isoformat(),
            )
        )

        self.assertEqual(
            original_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertIsNone(
            conflict_sale.machine,
        )

        self.assertIsNone(
            conflict_sale.product,
        )

        resolved_conflict = resolve_pending_sale(
            conflict_sale,
            self.machine,
            self.product_a,
        )

        self.assertEqual(
            resolved_conflict.status,
            Sale.Status.CONFLICT,
        )

        self.assertEqual(
            resolved_conflict.machine,
            self.machine,
        )

        self.assertEqual(
            resolved_conflict.product,
            self.product_a,
        )

    def test_resolved_conflict_can_be_accepted(self):
        self.create_stock(
            self.product_a,
            replenished_quantity=10,
        )

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

        original_sale, _ = receive_sale(
            self.make_payload(
                event_id="evt-conflict-resolution-accept",
                occurred_at=sale_time.isoformat(),
            )
        )

        conflict_sale, _ = receive_sale(
            self.make_payload(
                event_id="evt-conflict-resolution-accept",
                machine_identifier="VM-UNKNOWN",
                occurred_at=sale_time.isoformat(),
            )
        )

        resolve_pending_sale(
            conflict_sale,
            self.machine,
            self.product_a,
        )

        accepted_sale, voided_sale = accept_sale_conflict(conflict_sale)

        self.assertEqual(
            accepted_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            voided_sale.pk,
            original_sale.pk,
        )

        self.assertEqual(
            voided_sale.status,
            Sale.Status.VOIDED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            9,
        )

    def test_unresolved_conflict_cannot_be_resolved_without_enough_stock(
        self,
    ):
        self.create_stock(
            self.product_a,
            purchased_quantity=1,
            replenished_quantity=1,
        )

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

        receive_sale(
            self.make_payload(
                event_id="evt-conflict-no-stock",
                occurred_at=sale_time.isoformat(),
                quantity=1,
            )
        )

        conflict_sale, _ = receive_sale(
            self.make_payload(
                event_id="evt-conflict-no-stock",
                machine_identifier="VM-UNKNOWN",
                occurred_at=sale_time.isoformat(),
                quantity=2,
                amount_received="3.00",
            )
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Stock insuficiente",
        ):
            resolve_pending_sale(
                conflict_sale,
                self.machine,
                self.product_a,
            )

        conflict_sale.refresh_from_db()

        self.assertEqual(
            conflict_sale.status,
            Sale.Status.CONFLICT,
        )

        self.assertIsNone(
            conflict_sale.machine,
        )

        self.assertIsNone(
            conflict_sale.product,
        )

    def test_resolved_sale_cannot_be_rejected_as_conflict(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-not-conflict",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            reject_sale_conflict(sale)

    def test_resolved_sale_cannot_be_accepted_as_conflict(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-not-acceptable-conflict",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            accept_sale_conflict(sale)

    def test_pending_sale_can_be_resolved_manually(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-manual-resolution",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="A1",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

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

        resolved_sale = resolve_pending_sale(
            sale,
            self.machine,
            self.product_a,
        )

        self.assertEqual(
            resolved_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            resolved_sale.machine,
            self.machine,
        )

        self.assertEqual(
            resolved_sale.product,
            self.product_a,
        )

    def test_resolving_pending_sale_preserves_telemetry_data(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-preserve-resolution",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="A1",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        sale, _ = receive_sale(payload)

        original_raw_payload = sale.raw_payload.copy()

        resolve_pending_sale(
            sale,
            self.machine,
            self.product_a,
        )

        sale.refresh_from_db()

        self.assertEqual(
            sale.machine_identifier,
            "VM-EXTERNAL-ERROR",
        )
        self.assertEqual(
            sale.selection,
            "A1",
        )

        self.assertEqual(
            sale.quantity,
            2,
        )

        self.assertEqual(
            sale.raw_payload,
            original_raw_payload,
        )

        self.assertEqual(
            sale.event_id,
            "evt-preserve-resolution",
        )

    def test_resolving_pending_sale_makes_it_affect_inventory(self):
        self.create_stock(
            self.product_a,
        )
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
            event_id="evt-pending-inventory",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="A1",
            occurred_at=sale_time.isoformat(),
            quantity=2,
        )

        sale, _ = receive_sale(payload)

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

        resolved_sale = resolve_pending_sale(
            sale,
            self.machine,
            self.product_a,
        )

        self.assertEqual(
            resolved_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_pending_sale_cannot_be_resolved_without_machine(self):
        payload = self.make_payload(
            event_id="evt-resolution-no-machine",
            machine_identifier="VM-UNKNOWN",
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                None,
                self.product_a,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_pending_sale_cannot_be_resolved_without_product(self):
        payload = self.make_payload(
            event_id="evt-resolution-no-product",
            machine_identifier="VM-UNKNOWN",
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                self.machine,
                None,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_resolved_sale_cannot_be_resolved_manually(self):
        self.create_stock(self.product_a, replenished_quantity=10)

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
            event_id="evt-already-resolved",
            occurred_at=sale_time.isoformat(),
        )

        sale, _ = receive_sale(payload)

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                self.machine,
                self.product_b,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.product,
            self.product_a,
        )

    def test_pending_sale_cannot_resolve_with_product_outside_layout(self):
        product_outside_layout = Product.objects.create(
            name="VimaExtra Sale",
            category=self.category,
            format_unit="500 ml",
            default_sale_price=Decimal("2.00"),
            vat_rate=Decimal("21.00"),
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
                self.layout_a,
            )

        payload = self.make_payload(
            event_id="evt-product-outside-layout",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="Z9",
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                self.machine,
                product_outside_layout,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

        self.assertIsNone(
            sale.product,
        )

    def test_pending_sale_cannot_override_product_resolved_by_selection(self):
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
            event_id="evt-selection-product",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="A1",
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                self.machine,
                self.product_b,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_pending_sale_cannot_resolve_without_historical_layout(self):
        payload = self.make_payload(
            event_id="evt-no-historical-layout-resolution",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="A1",
        )

        sale, _ = receive_sale(payload)

        with self.assertRaises(ValidationError):
            resolve_pending_sale(
                sale,
                self.machine,
                self.product_a,
            )

        sale.refresh_from_db()

        self.assertEqual(
            sale.status,
            Sale.Status.PENDING,
        )

    def test_manual_sale_can_be_created_without_event_id(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
        )

        self.assertEqual(
            sale.source,
            Sale.Source.MANUAL,
        )

        self.assertIsNone(
            sale.event_id,
        )

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
            sale.machine_identifier,
            self.machine.identifier,
        )

        self.assertIsNone(
            sale.raw_payload,
        )

    def assert_paid_manual_sale_rejects_missing_field(self, field_name):
        self.create_stock(self.product_a, replenished_quantity=10)

        sale_data = {
            "machine": self.machine,
            "product": self.product_a,
            "occurred_at": self.make_datetime(2026, 9, 3, 18, 0),
            "quantity": 1,
            "dispense_type": Sale.DispenseType.PAID,
            "unit_price": Decimal("1.50"),
            "amount_received": Decimal("1.50"),
            "payment_method": "cash",
        }
        sale_data[field_name] = None

        with self.assertRaises(ValidationError) as context:
            create_manual_sale(**sale_data)

        self.assertIn(field_name, context.exception.message_dict)
        self.assertFalse(Sale.objects.filter(source=Sale.Source.MANUAL).exists())

    def test_manual_paid_sale_requires_unit_price(self):
        self.assert_paid_manual_sale_rejects_missing_field("unit_price")

    def test_manual_paid_sale_requires_amount_received(self):
        self.assert_paid_manual_sale_rejects_missing_field("amount_received")

    def test_manual_paid_sale_requires_payment_method(self):
        self.assert_paid_manual_sale_rejects_missing_field("payment_method")

    def test_manual_paid_sale_accepts_unknown_payment_method(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=self.make_datetime(2026, 9, 3, 18, 0),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="unknown",
        )

        self.assertEqual(sale.payment_method, "unknown")

    def test_manual_sale_allows_product_outside_active_historical_layout(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        activation_time = self.make_datetime(2026, 9, 3, 12, 0)

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(self.layout_b)

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=self.make_datetime(2026, 9, 3, 18, 0),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="unknown",
        )

        self.assertEqual(sale.product, self.product_a)
        self.assertIsNone(sale.resolution_layout)

    def test_manual_sale_can_store_external_event_id(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            event_id="evt-manual-known",
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
        )

        self.assertEqual(
            sale.source,
            Sale.Source.MANUAL,
        )

        self.assertEqual(
            sale.event_id,
            "evt-manual-known",
        )

    def test_manual_sale_cannot_use_existing_event_id(self):
        payload = self.make_payload(
            event_id="evt-already-received",
            machine_identifier="VM-NO-EXISTE",
        )

        existing_sale, _ = receive_sale(payload)

        self.assertEqual(
            existing_sale.status,
            Sale.Status.PENDING,
        )

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        with self.assertRaises(ValidationError):
            create_manual_sale(
                event_id="evt-already-received",
                machine=self.machine,
                product=self.product_a,
                occurred_at=occurred_at,
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                unit_price=Decimal("1.50"),
                amount_received=Decimal("1.50"),
                payment_method="cash",
            )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-already-received",
            ).count(),
            1,
        )

    def test_manual_free_sale_uses_zero_amount_received(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.FREE,
            amount_received=None,
        )

        self.assertEqual(
            sale.dispense_type,
            Sale.DispenseType.FREE,
        )

        self.assertEqual(
            sale.amount_received,
            Decimal("0.00"),
        )

        self.assertIsNone(sale.unit_price)
        self.assertEqual(sale.payment_method, "")

    def test_manual_sale_affects_inventory(self):
        self.create_stock(
            self.product_a,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            6,
        )

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=2,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("3.00"),
            payment_method="cash",
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_manual_sale_can_be_created_without_selection(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            selection="",
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
        )

        self.assertEqual(
            sale.selection,
            "",
        )

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

    def test_resolved_manual_sale_cannot_be_modified(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
        )

        sale.quantity = 5

        with self.assertRaises(ValidationError):
            sale.save()

        sale.refresh_from_db()

        self.assertEqual(
            sale.quantity,
            1,
        )

    def test_resolved_manual_sale_can_be_voided(self):
        self.create_stock(self.product_a, replenished_quantity=10)

        occurred_at = self.make_datetime(
            2026,
            9,
            3,
            18,
            0,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product_a,
            occurred_at=occurred_at,
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
        )

        voided_sale = void_sale(
            sale,
            "Registro manual incorrecto.",
        )

        self.assertEqual(
            voided_sale.status,
            Sale.Status.VOIDED,
        )

        self.assertEqual(
            voided_sale.void_reason,
            "Registro manual incorrecto.",
        )

    def test_multiple_distinct_sales_accumulate_inventory_effect(
        self,
    ):
        self.create_stock(
            self.product_a,
        )

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

        for index in range(3):
            sale, created = receive_sale(
                self.make_payload(
                    event_id=(f"evt-multiple-{index}"),
                    occurred_at=(sale_time.isoformat()),
                )
            )

            self.assertTrue(created)

            self.assertEqual(
                sale.status,
                Sale.Status.RESOLVED,
            )

        self.assertEqual(
            get_total_stock(self.product_a),
            7,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            3,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_sale_only_affects_its_product_and_machine(
        self,
    ):
        other_machine = Machine.objects.create(
            identifier="VM-SALE-002",
            name="Máquina ventas 2",
            serial_number="SN-SALE-002",
            rows=4,
            columns=4,
        )

        purchase_a = Purchase.objects.create(
            supplier="Proveedor A",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase_a,
            product=self.product_a,
            quantity=20,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment_a = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment_a,
            product=self.product_a,
            quantity=6,
        )

        other_replenishment = Replenishment.objects.create(
            machine=other_machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=other_replenishment,
            product=self.product_a,
            quantity=5,
        )

        purchase_b = Purchase.objects.create(
            supplier="Proveedor B",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase_b,
            product=self.product_b,
            quantity=10,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment_b = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment_b,
            product=self.product_b,
            quantity=4,
        )

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

        receive_sale(
            self.make_payload(
                event_id="evt-isolation",
                occurred_at=sale_time.isoformat(),
            )
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                other_machine,
            ),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_b,
                self.machine,
            ),
            4,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            10,
        )

    def test_received_sale_is_rejected_when_stock_would_become_negative(
        self,
    ):
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

        with self.assertRaisesMessage(ValidationError, "Stock insuficiente"):
            receive_sale(
                self.make_payload(
                    event_id="evt-negative-integration",
                    occurred_at=sale_time.isoformat(),
                    quantity=2,
                )
            )

        self.assertFalse(
            Sale.objects.filter(event_id="evt-negative-integration").exists()
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            0,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            0,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            0,
        )

    def test_non_finite_unit_price_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-nan-unit-price",
            unit_price="NaN",
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-nan-unit-price",
            ).exists()
        )

    def test_non_finite_amount_received_is_rejected(self):
        payload = self.make_payload(
            event_id="evt-infinite-amount",
            amount_received="Infinity",
        )

        with self.assertRaises(ValidationError):
            receive_sale(payload)

        self.assertFalse(
            Sale.objects.filter(
                event_id="evt-infinite-amount",
            ).exists()
        )


class SaleConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-CONCURRENCY-001",
            name="Máquina concurrencia",
            serial_number="SN-CONCURRENCY-001",
            rows=4,
            columns=4,
        )

        self.category = Category.objects.create(
            name="Bebidas concurrencia",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaCola Concurrency",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición concurrencia",
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

        activation_time = timezone.make_aware(
            datetime(
                2026,
                9,
                2,
                9,
                0,
            )
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(self.layout)

    def create_stock(self, quantity=1):
        purchase = Purchase.objects.create(
            supplier="Proveedor concurrencia",
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

    def make_payload(
        self,
        event_id,
        amount_received="1.50",
    ):
        return {
            "event_id": event_id,
            "machine_identifier": self.machine.identifier,
            "selection": "A1",
            "occurred_at": "2026-09-02T10:30:00+02:00",
            "quantity": 1,
            "dispense_type": "paid",
            "unit_price": "1.50",
            "amount_received": amount_received,
            "payment_method": "cash",
        }

    def receive_concurrently(self, *payloads):
        barrier = Barrier(len(payloads))

        original_lock = sale_services._lock_sale_event

        def synchronized_lock(event_id):
            barrier.wait(timeout=5)
            return original_lock(event_id)

        def worker(payload):
            close_old_connections()

            try:
                sale, created = receive_sale(payload)

                return sale.pk, created

            finally:
                close_old_connections()

        with patch(
            "sales.services._lock_sale_event",
            side_effect=synchronized_lock,
        ):
            with ThreadPoolExecutor(
                max_workers=len(payloads),
            ) as executor:
                futures = [
                    executor.submit(
                        worker,
                        payload,
                    )
                    for payload in payloads
                ]

                return [future.result(timeout=10) for future in futures]

    def test_same_event_concurrent_requests_are_idempotent(self):
        self.create_stock(quantity=1)

        payload = self.make_payload(
            event_id="evt-concurrent-idempotent",
        )

        results = self.receive_concurrently(
            payload,
            payload.copy(),
        )

        created_values = [created for _, created in results]

        sale_ids = {sale_id for sale_id, _ in results}

        self.assertEqual(
            sorted(created_values),
            [
                False,
                True,
            ],
        )

        self.assertEqual(
            len(sale_ids),
            1,
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-concurrent-idempotent",
            ).count(),
            1,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

    def test_same_event_different_concurrent_payloads_create_conflict(
        self,
    ):
        self.create_stock(quantity=1)

        first_payload = self.make_payload(
            event_id="evt-concurrent-conflict",
            amount_received="1.50",
        )

        second_payload = self.make_payload(
            event_id="evt-concurrent-conflict",
            amount_received="2.00",
        )

        results = self.receive_concurrently(
            first_payload,
            second_payload,
        )

        self.assertTrue(all(created for _, created in results))

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-concurrent-conflict",
            ).count(),
            2,
        )

        resolved_sale = Sale.objects.get(
            event_id="evt-concurrent-conflict",
            status=Sale.Status.RESOLVED,
        )

        conflict_sale = Sale.objects.get(
            event_id="evt-concurrent-conflict",
            status=Sale.Status.CONFLICT,
        )

        self.assertEqual(
            conflict_sale.conflicts_with_id,
            resolved_sale.pk,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )
