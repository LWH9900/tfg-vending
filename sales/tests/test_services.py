from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
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
from sales.models import Sale
from sales.services import (
    accept_sale_conflict,
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

    def test_resolved_sale_cannot_be_rejected_as_conflict(self):
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
        payload = self.make_payload(
            event_id="evt-manual-resolution",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="Z9",
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
        payload = self.make_payload(
            event_id="evt-preserve-resolution",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="Z9",
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
            "Z9",
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

        payload = self.make_payload(
            event_id="evt-pending-inventory",
            machine_identifier="VM-EXTERNAL-ERROR",
            selection="Z9",
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
