from django.test import TestCase
from django.urls import reverse

from machines.models import Machine


class MachineViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            location="Biblioteca - Planta baja",
        )

    def test_machine_list_access(self):
        response = self.client.get(reverse("machines:machine_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "machines/machine_list.html",
        )
        self.assertContains(response, "VM-001")
        self.assertContains(response, "Máquina Biblioteca")

    def test_machine_detail_access(self):
        response = self.client.get(
            reverse(
                "machines:machine_detail",
                args=[self.machine.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "machines/machine_detail.html",
        )
        self.assertContains(response, "VM-001")
        self.assertContains(response, "SN-001")

    def test_machine_create_access(self):
        response = self.client.get(reverse("machines:machine_create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "machines/machine_form.html",
        )

    def test_create_machine(self):
        response = self.client.post(
            reverse("machines:machine_create"),
            {
                "identifier": "VM-002",
                "name": "Máquina Cafetería",
                "serial_number": "SN-002",
                "location": "Cafetería",
            },
        )

        machine = Machine.objects.get(identifier="VM-002")

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_detail",
                args=[machine.pk],
            ),
        )

        self.assertEqual(machine.name, "Máquina Cafetería")
        self.assertEqual(machine.serial_number, "SN-002")
        self.assertEqual(machine.location, "Cafetería")

    def test_create_machine_with_duplicate_identifier_is_invalid(self):
        response = self.client.post(
            reverse("machines:machine_create"),
            {
                "identifier": "VM-001",
                "name": "Máquina duplicada",
                "serial_number": "SN-002",
                "location": "Edificio A",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            Machine.objects.filter(identifier="VM-001").count(),
            1,
        )

        self.assertContains(
            response,
            "Ya existe una máquina con este identificador.",
        )

    def test_update_machine(self):
        response = self.client.post(
            reverse(
                "machines:machine_update",
                args=[self.machine.pk],
            ),
            {
                "identifier": "VM-001",
                "name": "Máquina Biblioteca Actualizada",
                "serial_number": "SN-001",
                "location": "Biblioteca - Primera planta",
            },
        )

        self.machine.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_detail",
                args=[self.machine.pk],
            ),
        )

        self.assertEqual(
            self.machine.name,
            "Máquina Biblioteca Actualizada",
        )
        self.assertEqual(
            self.machine.location,
            "Biblioteca - Primera planta",
        )


def test_update_machine_with_duplicate_identifier_is_invalid(self):
    second_machine = Machine.objects.create(
        identifier="VM-002",
        name="Máquina Cafetería",
        serial_number="SN-002",
        location="Cafetería",
    )

    response = self.client.post(
        reverse(
            "machines:machine_update",
            args=[second_machine.pk],
        ),
        {
            "identifier": "VM-001",
            "name": second_machine.name,
            "serial_number": second_machine.serial_number,
            "location": second_machine.location,
        },
    )

    second_machine.refresh_from_db()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(
        second_machine.identifier,
        "VM-002",
    )

    self.assertContains(
        response,
        "Ya existe una máquina con este identificador.",
    )


class EmptyMachineListTests(TestCase):
    def test_empty_machine_list_shows_message(self):
        response = self.client.get(reverse("machines:machine_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No hay máquinas registradas.",
        )
