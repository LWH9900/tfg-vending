import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
)


class MachineLayoutCreateViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina 1",
            serial_number="SN-001",
            rows=4,
            columns=5,
        )

        self.machine_without_grid = Machine.objects.create(
            identifier="VM-002",
            name="Máquina 2",
            serial_number="SN-002",
        )

        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.cola = Product.objects.create(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.tea = Product.objects.create(
            name="VimaTea",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.url = reverse(
            "machines:machine_layout_create",
            args=[self.machine.pk],
        )

    def test_create_view_returns_200(self):
        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "machines/machine_layout_form.html",
        )

    def test_create_view_builds_complete_machine_grid(self):
        response = self.client.get(
            self.url,
        )

        self.assertTrue(response.context["grid_configured"])

        self.assertEqual(
            len(response.context["grid_cells"]),
            20,
        )

        self.assertIn(
            {
                "row": 1,
                "column": 1,
            },
            response.context["grid_cells"],
        )

        self.assertIn(
            {
                "row": 4,
                "column": 5,
            },
            response.context["grid_cells"],
        )

    def test_create_view_warns_when_machine_has_no_grid(self):
        url = reverse(
            "machines:machine_layout_create",
            args=[self.machine_without_grid.pk],
        )

        response = self.client.get(
            url,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(response.context["grid_configured"])

        self.assertContains(
            response,
            "Cuadrícula sin configurar",
        )

    def test_create_layout_with_positions(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.cola.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "A2",
                "product_id": self.tea.pk,
                "row": 1,
                "column": 2,
                "width": 2,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Disposición principal",
                "positions": json.dumps(positions),
                "source_layout": "",
            },
        )

        layout = MachineLayout.objects.get(
            machine=self.machine,
            name="Disposición principal",
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[layout.pk],
            ),
        )

        self.assertEqual(
            layout.status,
            MachineLayout.Status.DRAFT,
        )

        self.assertEqual(
            layout.positions.count(),
            2,
        )

        position_a1 = layout.positions.get(
            identifier="A1",
        )

        self.assertEqual(
            position_a1.product,
            self.cola,
        )

        self.assertEqual(
            position_a1.row,
            1,
        )

        self.assertEqual(
            position_a1.column,
            1,
        )

        position_a2 = layout.positions.get(
            identifier="A2",
        )

        self.assertEqual(
            position_a2.product,
            self.tea,
        )

        self.assertEqual(
            position_a2.width,
            2,
        )

        self.assertEqual(
            position_a2.height,
            1,
        )

    def test_created_layout_is_draft(self):
        response = self.client.post(
            self.url,
            {
                "name": "Nueva disposición",
                "positions": "[]",
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        layout = MachineLayout.objects.get(
            machine=self.machine,
            name="Nueva disposición",
        )

        self.assertEqual(
            layout.status,
            MachineLayout.Status.DRAFT,
        )

    def test_duplicate_layout_name_is_rejected_case_insensitive(self):
        MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        response = self.client.post(
            self.url,
            {
                "name": "principal",
                "positions": "[]",
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            MachineLayout.objects.filter(
                machine=self.machine,
            ).count(),
            1,
        )

        self.assertFormError(
            response.context["form"],
            "name",
            ("Ya existe una disposición con este nombre para esta máquina."),
        )

    def test_invalid_positions_json_does_not_create_layout(self):
        response = self.client.post(
            self.url,
            {
                "name": "Nueva disposición",
                "positions": "{invalid-json",
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MachineLayout.objects.filter(
                machine=self.machine,
                name="Nueva disposición",
            ).exists()
        )

    def test_invalid_position_rolls_back_entire_layout(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.cola.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "Z1",
                "product_id": self.tea.pk,
                "row": 20,
                "column": 20,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Disposición inválida",
                "positions": json.dumps(positions),
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MachineLayout.objects.filter(
                machine=self.machine,
                name="Disposición inválida",
            ).exists()
        )

        self.assertFalse(
            MachinePosition.objects.filter(
                identifier="A1",
            ).exists()
        )

    def test_machine_without_grid_cannot_create_layout(self):
        url = reverse(
            "machines:machine_layout_create",
            args=[self.machine_without_grid.pk],
        )

        response = self.client.post(
            url,
            {
                "name": "Nueva disposición",
                "positions": "[]",
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            MachineLayout.objects.filter(
                machine=self.machine_without_grid,
            ).exists()
        )

    def test_create_view_exposes_existing_layout_as_template(self):
        source_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición base",
        )

        MachinePosition.objects.create(
            layout=source_layout,
            identifier="A1",
            row=1,
            column=1,
            width=2,
            height=1,
            product=self.cola,
        )

        response = self.client.get(
            self.url,
        )

        templates = response.context["layout_templates"]

        self.assertIn(
            str(source_layout.pk),
            templates,
        )

        self.assertEqual(
            templates[str(source_layout.pk)],
            [
                {
                    "identifier": "A1",
                    "product_id": self.cola.pk,
                    "row": 1,
                    "column": 1,
                    "width": 2,
                    "height": 1,
                }
            ],
        )

    def test_new_layout_created_from_copied_positions_is_independent(self):
        source_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición original",
        )

        source_position = MachinePosition.objects.create(
            layout=source_layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.cola,
        )

        copied_positions = [
            {
                "identifier": "A1",
                "product_id": self.tea.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        self.client.post(
            self.url,
            {
                "name": "Nueva disposición",
                "positions": json.dumps(copied_positions),
                "source_layout": str(source_layout.pk),
            },
        )

        source_position.refresh_from_db()

        new_layout = MachineLayout.objects.get(
            machine=self.machine,
            name="Nueva disposición",
        )

        new_position = new_layout.positions.get(
            identifier="A1",
        )

        self.assertEqual(
            source_position.product,
            self.cola,
        )

        self.assertEqual(
            new_position.product,
            self.tea,
        )
