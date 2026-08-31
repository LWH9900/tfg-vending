from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
    MachinePosition,
)


class MachineLayoutViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina Biblioteca",
            serial_number="SN-001",
            rows=5,
            columns=5,
        )

        self.other_machine = Machine.objects.create(
            identifier="VM-002",
            name="Máquina Cafetería",
            serial_number="SN-002",
            rows=4,
            columns=4,
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

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición principal",
        )

        self.position = MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
            width=1,
            height=1,
            product=self.product,
        )

    def test_layout_list_returns_200(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "machines/machine_layout_list.html",
        )

    def test_layout_list_shows_machine_layouts(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            )
        )

        self.assertContains(
            response,
            "Disposición principal",
        )

    def test_layout_list_does_not_show_other_machine_layouts(self):
        MachineLayout.objects.create(
            machine=self.other_machine,
            name="Disposición otra máquina",
        )

        response = self.client.get(
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            )
        )

        self.assertNotContains(
            response,
            "Disposición otra máquina",
        )

    def test_layout_list_shows_empty_message(self):
        self.layout.delete()

        response = self.client.get(
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            )
        )

        self.assertContains(
            response,
            "Esta máquina todavía no tiene disposiciones.",
        )

    def test_layout_list_contains_detail_link(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_list",
                args=[self.machine.pk],
            )
        )

        detail_url = reverse(
            "machines:machine_layout_detail",
            args=[self.layout.pk],
        )

        self.assertContains(
            response,
            detail_url,
        )

    def test_layout_detail_returns_200(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "machines/machine_layout_detail.html",
        )

    def test_layout_detail_uses_correct_layout_and_machine(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertEqual(
            response.context["layout"],
            self.layout,
        )
        self.assertEqual(
            response.context["machine"],
            self.machine,
        )

    def test_layout_detail_builds_complete_machine_grid(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        grid_cells = response.context["grid_cells"]

        self.assertEqual(
            len(grid_cells),
            25,
        )

    def test_layout_detail_grid_uses_machine_dimensions(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        grid_cells = response.context["grid_cells"]

        self.assertIn(
            {
                "row": 1,
                "column": 1,
            },
            grid_cells,
        )

        self.assertIn(
            {
                "row": 5,
                "column": 5,
            },
            grid_cells,
        )

    def test_layout_detail_contains_layout_positions(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertIn(
            self.position,
            response.context["positions"],
        )

    def test_layout_detail_shows_product_information(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertContains(response, "Cola")
        self.assertContains(response, "Bebidas")
        self.assertContains(response, "330 ml")

    def test_layout_detail_supports_position_without_product(self):
        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A2",
            row=1,
            column=2,
            product=None,
        )

        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin producto")

    def test_layout_detail_identifies_active_layout(self):
        self.layout.status = MachineLayout.Status.REGISTERED
        self.layout.save()

        MachineLayoutActivation.objects.create(
            layout=self.layout,
            effective_from=timezone.now(),
        )

        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertTrue(
            response.context["is_active"],
        )

    def test_layout_detail_identifies_non_active_layout(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout.pk],
            )
        )

        self.assertFalse(
            response.context["is_active"],
        )

    def test_layout_detail_returns_404_for_unknown_layout(self):
        response = self.client.get(
            reverse(
                "machines:machine_layout_detail",
                args=[999999],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )
