from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
    MachinePosition,
)


class MachineModelTests(TestCase):
    def test_create_valid_machine(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            location="Biblioteca - Planta baja",
            rows=4,
            columns=6,
        )

        machine.full_clean()
        machine.save()

        self.assertEqual(Machine.objects.count(), 1)
        self.assertEqual(machine.identifier, "VM-001")
        self.assertEqual(machine.rows, 4)
        self.assertEqual(machine.columns, 6)

    def test_duplicate_identifier_is_invalid(self):
        Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            location="Biblioteca",
        )

        duplicate = Machine(
            identifier="VM-001",
            name="Otra máquina",
            serial_number="SN-002",
            location="Edificio A",
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_required_fields_are_validated(self):
        required_fields = [
            "identifier",
            "name",
            "serial_number",
        ]

        for field in required_fields:
            with self.subTest(field=field):
                data = {
                    "identifier": "VM-001",
                    "name": "Máquina Biblioteca",
                    "serial_number": "SN-001",
                    "location": "Biblioteca",
                }

                data[field] = ""

                machine = Machine(**data)

                with self.assertRaises(ValidationError):
                    machine.full_clean()

    def test_location_is_optional(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            location="",
        )

        machine.full_clean()
        machine.save()

        self.assertEqual(machine.location, "")

    def test_duplicate_serial_number_is_invalid(self):
        Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            location="Biblioteca",
        )

        duplicate = Machine(
            identifier="VM-002",
            name="Máquina Cafetería",
            serial_number="SN-001",
            location="Cafetería",
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_grid_can_be_unconfigured(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
        )

        machine.full_clean()

        self.assertIsNone(machine.rows)
        self.assertIsNone(machine.columns)

    def test_rows_and_columns_must_be_configured_together(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=4,
            columns=None,
        )

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_columns_and_rows_must_be_configured_together(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=None,
            columns=6,
        )

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_grid_can_be_configured_for_first_time(self):
        machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
        )

        machine.rows = 4
        machine.columns = 6

        machine.full_clean()
        machine.save()

        machine.refresh_from_db()

        self.assertEqual(machine.rows, 4)
        self.assertEqual(machine.columns, 6)

    def test_rows_cannot_change_once_grid_is_configured(self):
        machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=4,
            columns=6,
        )

        machine.rows = 5

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_columns_cannot_change_once_grid_is_configured(self):
        machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=4,
            columns=6,
        )

        machine.columns = 7

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_grid_cannot_be_removed_once_configured(self):
        machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=4,
            columns=6,
        )

        machine.rows = None
        machine.columns = None

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_rows_cannot_exceed_maximum(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=21,
            columns=6,
        )

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_columns_cannot_exceed_maximum(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=4,
            columns=21,
        )

        with self.assertRaises(ValidationError):
            machine.full_clean()

    def test_grid_dimensions_must_be_positive(self):
        machine = Machine(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=0,
            columns=6,
        )

        with self.assertRaises(ValidationError):
            machine.full_clean()


class MachineLayoutModelTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina 1",
            serial_number="SN-001",
            rows=4,
            columns=6,
        )

        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="Cola",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

    def test_machine_can_have_multiple_layouts(self):
        MachineLayout.objects.create(
            machine=self.machine,
            name="Verano",
        )

        MachineLayout.objects.create(
            machine=self.machine,
            name="Invierno",
        )

        self.assertEqual(
            self.machine.layouts.count(),
            2,
        )

    def test_new_layout_is_draft_by_default(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        self.assertEqual(
            layout.status,
            MachineLayout.Status.DRAFT,
        )

    def test_draft_layout_can_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        layout.name = "Principal modificada"
        layout.save()

        layout.refresh_from_db()

        self.assertEqual(
            layout.name,
            "Principal modificada",
        )

    def test_registered_layout_cannot_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        layout.name = "Modificada"

        with self.assertRaises(ValidationError):
            layout.save()

    def test_position_maps_selection_to_product(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A3",
            row=1,
            column=3,
            width=1,
            height=1,
            product=self.product,
        )

        self.assertEqual(
            position.product,
            self.product,
        )
        self.assertEqual(
            position.identifier,
            "A3",
        )
        self.assertEqual(position.row, 1)
        self.assertEqual(position.column, 3)
        self.assertEqual(position.width, 1)
        self.assertEqual(position.height, 1)

    def test_position_can_have_no_product(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=None,
        )

        self.assertIsNone(position.product)

    def test_position_cannot_be_created_without_machine_grid(self):
        machine = Machine.objects.create(
            identifier="VM-002",
            name="Máquina sin cuadrícula",
            serial_number="SN-002",
        )

        layout = MachineLayout.objects.create(
            machine=machine,
            name="Principal",
        )

        position = MachinePosition(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        with self.assertRaises(ValidationError):
            position.full_clean()

    def test_position_cannot_exceed_machine_rows(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition(
            layout=layout,
            identifier="A1",
            row=4,
            column=1,
            width=1,
            height=2,
            product=self.product,
        )

        with self.assertRaises(ValidationError):
            position.full_clean()

    def test_position_cannot_exceed_machine_columns(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition(
            layout=layout,
            identifier="A1",
            row=1,
            column=6,
            width=2,
            height=1,
            product=self.product,
        )

        with self.assertRaises(ValidationError):
            position.full_clean()

    def test_position_can_occupy_multiple_cells(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            width=2,
            height=2,
            product=self.product,
        )

        self.assertEqual(position.width, 2)
        self.assertEqual(position.height, 2)

    def test_positions_cannot_overlap(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            width=2,
            height=1,
            product=self.product,
        )

        overlapping_position = MachinePosition(
            layout=layout,
            identifier="A2",
            row=1,
            column=2,
            width=1,
            height=1,
            product=self.product,
        )

        with self.assertRaises(ValidationError):
            overlapping_position.full_clean()

    def test_positions_can_be_adjacent_without_overlapping(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            width=1,
            height=1,
            product=self.product,
        )

        position = MachinePosition(
            layout=layout,
            identifier="A2",
            row=1,
            column=2,
            width=1,
            height=1,
            product=self.product,
        )

        position.full_clean()

    def test_position_in_draft_layout_can_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        position.identifier = "A2"
        position.save()

        position.refresh_from_db()

        self.assertEqual(
            position.identifier,
            "A2",
        )

    def test_position_in_registered_layout_cannot_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        position.identifier = "A2"

        with self.assertRaises(ValidationError):
            position.save()

    def test_position_cannot_be_added_to_registered_layout(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        with self.assertRaises(ValidationError):
            MachinePosition.objects.create(
                layout=layout,
                identifier="A1",
                row=1,
                column=1,
                product=self.product,
            )

    def test_position_in_registered_layout_cannot_be_deleted(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        with self.assertRaises(ValidationError):
            position.delete()

    def test_only_registered_layout_can_be_activated(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        activation = MachineLayoutActivation(
            layout=layout,
            effective_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            activation.full_clean()

    def test_layout_can_be_activated_multiple_times(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Verano",
            status=MachineLayout.Status.REGISTERED,
        )

        first_activation = MachineLayoutActivation(
            layout=layout,
            effective_from=timezone.now(),
        )
        first_activation.full_clean()
        first_activation.save()

        second_activation = MachineLayoutActivation(
            layout=layout,
            effective_from=timezone.now() + timedelta(days=30),
        )
        second_activation.full_clean()
        second_activation.save()

        self.assertEqual(
            layout.activations.count(),
            2,
        )