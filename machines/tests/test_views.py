from django.test import TestCase
from django.urls import reverse

from machines.models import Machine, MachineLayout, MachinePosition


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


class MachineLayoutDeleteViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-DELETE-001",
            name="Máquina eliminación",
            serial_number="SN-DELETE-001",
            rows=4,
            columns=5,
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición borrador",
            status=MachineLayout.Status.DRAFT,
        )

        self.position_a1 = MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
        )

        self.position_a2 = MachinePosition.objects.create(
            layout=self.layout,
            identifier="A2",
            row=1,
            column=2,
        )

        self.url = reverse(
            "machines:machine_layout_delete",
            args=[self.layout.pk],
        )

    def test_delete_requires_post(self):
        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        self.assertTrue(
            MachineLayout.objects.filter(
                pk=self.layout.pk,
            ).exists()
        )

    def test_draft_layout_can_be_deleted(self):
        layout_pk = self.layout.pk

        response = self.client.post(
            self.url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            ),
        )

        self.assertFalse(
            MachineLayout.objects.filter(
                pk=layout_pk,
            ).exists()
        )

    def test_deleting_draft_layout_deletes_its_positions(self):
        layout_pk = self.layout.pk

        position_a1_pk = self.position_a1.pk

        position_a2_pk = self.position_a2.pk

        self.client.post(
            self.url,
        )

        self.assertFalse(
            MachineLayout.objects.filter(
                pk=layout_pk,
            ).exists()
        )

        self.assertFalse(
            MachinePosition.objects.filter(
                pk=position_a1_pk,
            ).exists()
        )

        self.assertFalse(
            MachinePosition.objects.filter(
                pk=position_a2_pk,
            ).exists()
        )

    def test_registered_layout_cannot_be_deleted(self):
        self.layout.status = MachineLayout.Status.REGISTERED

        self.layout.save()

        response = self.client.post(
            self.url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            ),
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.status,
            MachineLayout.Status.REGISTERED,
        )

        self.assertTrue(
            MachineLayout.objects.filter(
                pk=self.layout.pk,
            ).exists()
        )

    def test_rejected_registered_layout_delete_keeps_positions(self):
        self.layout.status = MachineLayout.Status.REGISTERED

        self.layout.save()

        self.client.post(
            self.url,
        )

        self.assertTrue(
            MachinePosition.objects.filter(
                pk=self.position_a1.pk,
            ).exists()
        )

        self.assertTrue(
            MachinePosition.objects.filter(
                pk=self.position_a2.pk,
            ).exists()
        )
