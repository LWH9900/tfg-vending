from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import Machine, MachineLayout
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

    def test_telemetry_sale_requires_event_id(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.TELEMETRY,
                event_id=None,
                machine_identifier="VM-SALE-001",
                selection="A1",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                raw_payload=self.payload,
            )

        self.assertIn(
            "event_id",
            context.exception.message_dict,
        )

    def test_telemetry_sale_requires_raw_payload(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.TELEMETRY,
                event_id="evt-no-payload",
                machine_identifier="VM-SALE-001",
                selection="A1",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                raw_payload=None,
            )

        self.assertIn(
            "raw_payload",
            context.exception.message_dict,
        )

    def test_telemetry_sale_requires_selection(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.TELEMETRY,
                event_id="evt-no-selection",
                machine_identifier="VM-SALE-001",
                selection="",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                raw_payload=self.payload,
            )

        self.assertIn(
            "selection",
            context.exception.message_dict,
        )

    def test_voided_sale_requires_reason(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                machine_identifier="VM-SALE-001",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.VOIDED,
                void_reason="",
                voided_at=timezone.now(),
            )

        self.assertIn(
            "void_reason",
            context.exception.message_dict,
        )

    def test_voided_sale_requires_voided_at(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                machine_identifier="VM-SALE-001",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.VOIDED,
                void_reason="Motivo de prueba.",
                voided_at=None,
            )

        self.assertIn(
            "voided_at",
            context.exception.message_dict,
        )

    def test_conflict_sale_requires_reference_sale(self):
        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                event_id="evt-conflict-without-reference",
                machine_identifier="VM-SALE-001",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.CONFLICT,
            )

        self.assertIn(
            "conflicts_with",
            context.exception.message_dict,
        )

    def test_sale_cannot_conflict_with_itself(self):
        sale = Sale.objects.create(
            source=Sale.Source.MANUAL,
            event_id="evt-self-conflict",
            machine_identifier="VM-SALE-001",
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            status=Sale.Status.PENDING,
        )

        sale.status = Sale.Status.CONFLICT
        sale.conflicts_with = sale

        with self.assertRaises(ValidationError) as context:
            sale.save()

        self.assertIn(
            "conflicts_with",
            context.exception.message_dict,
        )

    def test_conflicting_sales_must_share_event_id(self):
        reference_sale = Sale.objects.create(
            source=Sale.Source.MANUAL,
            event_id="evt-original",
            machine_identifier="VM-SALE-001",
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            status=Sale.Status.PENDING,
        )

        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                event_id="evt-different",
                machine_identifier="VM-SALE-001",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.CONFLICT,
                conflicts_with=reference_sale,
            )

        self.assertIn(
            "conflicts_with",
            context.exception.message_dict,
        )

    def test_resolution_layout_requires_machine(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición resolución",
        )

        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                machine_identifier="VM-SALE-001",
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.PENDING,
                resolution_layout=layout,
            )

        self.assertIn(
            "resolution_layout",
            context.exception.message_dict,
        )

    def test_resolution_layout_must_belong_to_sale_machine(self):
        other_machine = Machine.objects.create(
            identifier="VM-SALE-002",
            name="Máquina ventas 2",
            serial_number="SN-SALE-002",
            rows=4,
            columns=4,
        )

        other_layout = MachineLayout.objects.create(
            machine=other_machine,
            name="Disposición otra máquina",
        )

        with self.assertRaises(ValidationError) as context:
            Sale.objects.create(
                source=Sale.Source.MANUAL,
                machine_identifier=self.machine.identifier,
                machine=self.machine,
                occurred_at=timezone.now(),
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                status=Sale.Status.PENDING,
                resolution_layout=other_layout,
            )

        self.assertIn(
            "resolution_layout",
            context.exception.message_dict,
        )

    def test_resolved_manual_sale_cannot_modify_data_when_voided(self):
        sale = Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            product=self.product,
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
        )

        sale.status = Sale.Status.VOIDED
        sale.void_reason = "Anulación de prueba."
        sale.voided_at = timezone.now()
        sale.quantity = 2

        with self.assertRaisesMessage(
            ValidationError,
            "Los datos de una venta resuelta no pueden modificarse.",
        ):
            sale.save()

    def test_rejected_sale_cannot_be_modified(self):
        sale = Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=self.machine.identifier,
            occurred_at=timezone.now(),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            status=Sale.Status.REJECTED,
        )

        sale.payment_method = "cash"

        with self.assertRaisesMessage(
            ValidationError,
            "Una venta finalizada no puede modificarse.",
        ):
            sale.save()

    def test_string_representation_for_new_manual_sale(self):
        sale = Sale(
            source=Sale.Source.MANUAL,
            machine_identifier="VM-MANUAL-001",
            selection="",
        )

        self.assertEqual(
            str(sale),
            "Manual #nueva - VM-MANUAL-001 - sin selección",
        )
