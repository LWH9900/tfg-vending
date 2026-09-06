from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import Machine
from sales.models import Sale


class SaleModelTests(TestCase):
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

        self.product = Product.objects.create(
            name="VimaCola Sale",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.payload = {
            "event_id": "evt-001",
            "machine_identifier": "VM-SALE-001",
            "selection": "A1",
            "occurred_at": "2026-09-02T10:30:00Z",
            "quantity": 1,
            "dispense_type": "paid",
            "unit_price": "1.50",
            "amount_received": "1.50",
            "payment_method": "cash",
        }

    def test_pending_sale_can_be_created_without_resolved_product(self):
        sale = Sale.objects.create(
            event_id="evt-001",
            machine_identifier="VM-SALE-001",
            selection="A1",
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            raw_payload=self.payload,
        )

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

    def test_resolved_sale_requires_machine(self):
        with self.assertRaises(ValidationError):
            Sale.objects.create(
                event_id="evt-002",
                machine_identifier="VM-SALE-001",
                selection="A1",
                product=self.product,
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.RESOLVED,
                raw_payload=self.payload,
            )

    def test_resolved_sale_requires_product(self):
        with self.assertRaises(ValidationError):
            Sale.objects.create(
                event_id="evt-003",
                machine_identifier="VM-SALE-001",
                machine=self.machine,
                selection="A1",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.RESOLVED,
                raw_payload=self.payload,
            )

    def test_resolved_sale_can_be_created(self):
        sale = Sale.objects.create(
            event_id="evt-004",
            machine_identifier="VM-SALE-001",
            machine=self.machine,
            selection="A1",
            product=self.product,
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload=self.payload,
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

    def test_event_id_must_be_unique(self):
        Sale.objects.create(
            event_id="evt-duplicate",
            machine_identifier="VM-SALE-001",
            selection="A1",
            occurred_at=timezone.now(),
            dispense_type=Sale.DispenseType.PAID,
            raw_payload=self.payload,
        )

        with self.assertRaises(ValidationError):
            Sale.objects.create(
                event_id="evt-duplicate",
                machine_identifier="VM-SALE-001",
                selection="A2",
                occurred_at=timezone.now(),
                dispense_type=Sale.DispenseType.PAID,
                raw_payload=self.payload,
            )

    def test_quantity_must_be_at_least_one(self):
        with self.assertRaises(ValidationError):
            Sale.objects.create(
                event_id="evt-005",
                machine_identifier="VM-SALE-001",
                selection="A1",
                occurred_at=timezone.now(),
                quantity=0,
                dispense_type=Sale.DispenseType.PAID,
                raw_payload=self.payload,
            )

    def test_dispense_type_must_be_valid(self):
        with self.assertRaises(ValidationError):
            Sale.objects.create(
                event_id="evt-006",
                machine_identifier="VM-SALE-001",
                selection="A1",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type="invalid",
                raw_payload=self.payload,
            )

    def test_free_sale_can_have_zero_amount_received(self):
        sale = Sale.objects.create(
            event_id="evt-007",
            machine_identifier="VM-SALE-001",
            machine=self.machine,
            selection="A1",
            product=self.product,
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.FREE,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("0.00"),
            status=Sale.Status.RESOLVED,
            raw_payload=self.payload,
        )

        self.assertEqual(
            sale.amount_received,
            Decimal("0.00"),
        )

        self.assertEqual(
            sale.dispense_type,
            Sale.DispenseType.FREE,
        )

    def test_sale_preserves_raw_payload(self):
        sale = Sale.objects.create(
            event_id="evt-008",
            machine_identifier="VM-SALE-001",
            selection="A1",
            occurred_at=timezone.now(),
            dispense_type=Sale.DispenseType.PAID,
            raw_payload=self.payload,
        )

        self.assertEqual(
            sale.raw_payload,
            self.payload,
        )

    def test_pending_sale_can_be_resolved(self):
        sale = Sale.objects.create(
            event_id="evt-009",
            machine_identifier="VM-SALE-001",
            selection="A1",
            occurred_at=timezone.now(),
            dispense_type=Sale.DispenseType.PAID,
            raw_payload=self.payload,
        )

        sale.machine = self.machine
        sale.product = self.product
        sale.status = Sale.Status.RESOLVED

        sale.save()

        sale.refresh_from_db()

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
            self.product,
        )

    def test_resolved_sale_cannot_be_modified(self):
        sale = Sale.objects.create(
            event_id="evt-010",
            machine_identifier="VM-SALE-001",
            machine=self.machine,
            selection="A1",
            product=self.product,
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            status=Sale.Status.RESOLVED,
            raw_payload=self.payload,
        )

        sale.quantity = 2

        with self.assertRaises(ValidationError):
            sale.save()

    def test_sale_cannot_be_deleted(self):
        sale = Sale.objects.create(
            event_id="evt-011",
            machine_identifier="VM-SALE-001",
            selection="A1",
            occurred_at=timezone.now(),
            dispense_type=Sale.DispenseType.PAID,
            raw_payload=self.payload,
        )

        with self.assertRaises(ValidationError):
            sale.delete()
