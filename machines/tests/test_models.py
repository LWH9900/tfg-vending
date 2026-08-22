from django.core.exceptions import ValidationError
from django.test import TestCase

from machines.models import Machine


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
