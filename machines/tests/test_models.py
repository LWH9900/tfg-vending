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
        )

        machine.full_clean()
        machine.save()

        self.assertEqual(Machine.objects.count(), 1)
        self.assertEqual(machine.identifier, "VM-001")

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


class MachineLayoutModelTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina 1",
            serial_number="SN-001",
        )

        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate="21.00",
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

    def test_position_maps_selection_to_product(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A3",
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

    def test_layout_can_be_activated_multiple_times(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Verano",
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        self.assertEqual(
            layout.activations.count(),
            2,
        )
