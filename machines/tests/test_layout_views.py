import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

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
from machines.services.layouts import (
    activate_machine_layout,
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

        activate_machine_layout(
            self.layout,
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

    def test_positions_json_must_be_a_list_when_creating_layout(self):
        for positions in ({"row": 1}, ["not-a-position"]):
            with self.subTest(positions=positions):
                response = self.client.post(
                    self.url,
                    {
                        "name": "Disposición inválida",
                        "positions": json.dumps(positions),
                        "source_layout": "",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertFalse(
                    MachineLayout.objects.filter(
                        machine=self.machine,
                        name="Disposición inválida",
                    ).exists()
                )
                self.assertTrue(response.context["form"].non_field_errors())

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

    def test_create_position_without_product(self):

        positions = [
            {
                "identifier": "A1",
                "product_id": None,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Disposición con hueco vacío",
                "positions": json.dumps(positions),
                "source_layout": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        layout = MachineLayout.objects.get(
            machine=self.machine,
            name="Disposición con hueco vacío",
        )

        position = layout.positions.get(
            identifier="A1",
        )

        self.assertIsNone(position.product)


class MachineLayoutUpdateViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-UPDATE-001",
            name="Máquina actualización",
            serial_number="SN-UPDATE-001",
            rows=4,
            columns=5,
        )

        self.category = Category.objects.create(
            name="Bebidas actualización",
            default_vat_rate=Decimal("21.00"),
        )

        self.product_a = Product.objects.create(
            name="VimaCola Update",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            name="VimaTea Update",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
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
            width=1,
            height=1,
            product=self.product_a,
        )

        self.position_a2 = MachinePosition.objects.create(
            layout=self.layout,
            identifier="A2",
            row=1,
            column=2,
            width=1,
            height=1,
            product=self.product_b,
        )

        self.url = reverse(
            "machines:machine_layout_update",
            args=[self.layout.pk],
        )

    def create_registered_layout(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición registrada",
            status=MachineLayout.Status.REGISTERED,
        )

        return layout

    def test_update_view_returns_200_for_draft_layout(self):
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

        self.assertTrue(response.context["is_editing"])

        self.assertEqual(
            response.context["layout"],
            self.layout,
        )

    def test_update_view_preloads_existing_positions(self):
        response = self.client.get(
            self.url,
        )

        positions = json.loads(response.context["positions_json"])

        self.assertEqual(
            len(positions),
            2,
        )

        self.assertIn(
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            positions,
        )

        self.assertIn(
            {
                "identifier": "A2",
                "product_id": self.product_b.pk,
                "row": 1,
                "column": 2,
                "width": 1,
                "height": 1,
            },
            positions,
        )

    def test_update_changes_layout_name(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "A2",
                "product_id": self.product_b.pk,
                "row": 1,
                "column": 2,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Disposición modificada",
                "positions": json.dumps(positions),
            },
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
            self.layout.name,
            "Disposición modificada",
        )

        self.assertEqual(
            MachineLayout.objects.filter(
                machine=self.machine,
            ).count(),
            1,
        )

    def test_update_changes_existing_position_configuration(self):
        positions = [
            {
                "identifier": "B1",
                "product_id": self.product_b.pk,
                "row": 2,
                "column": 1,
                "width": 2,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": self.layout.name,
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.positions.count(),
            1,
        )

        position = self.layout.positions.get()

        self.assertEqual(
            position.identifier,
            "B1",
        )

        self.assertEqual(
            position.product,
            self.product_b,
        )

        self.assertEqual(
            position.row,
            2,
        )

        self.assertEqual(
            position.column,
            1,
        )

        self.assertEqual(
            position.width,
            2,
        )

        self.assertEqual(
            position.height,
            1,
        )

    def test_update_can_add_position(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "A2",
                "product_id": self.product_b.pk,
                "row": 1,
                "column": 2,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "B1",
                "product_id": self.product_a.pk,
                "row": 2,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": self.layout.name,
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.positions.count(),
            3,
        )

        self.assertTrue(
            self.layout.positions.filter(
                identifier="B1",
            ).exists()
        )

    def test_update_can_add_position_without_product(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "B1",
                "product_id": None,
                "row": 2,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": self.layout.name,
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        position = self.layout.positions.get(
            identifier="B1",
        )

        self.assertIsNone(
            position.product,
        )

    def test_update_can_remove_position(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": self.layout.name,
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.positions.count(),
            1,
        )

        self.assertTrue(
            self.layout.positions.filter(
                identifier="A1",
            ).exists()
        )

        self.assertFalse(
            self.layout.positions.filter(
                identifier="A2",
            ).exists()
        )

    def test_update_can_keep_same_layout_name(self):
        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Disposición borrador",
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_update_rejects_duplicate_layout_name_case_insensitive(self):
        MachineLayout.objects.create(
            machine=self.machine,
            name="Otra disposición",
            status=MachineLayout.Status.DRAFT,
        )

        positions = [
            {
                "identifier": "A1",
                "product_id": self.product_a.pk,
                "row": 1,
                "column": 1,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "otra disposición",
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFormError(
            response.context["form"],
            "name",
            ("Ya existe una disposición con este nombre para esta máquina."),
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.name,
            "Disposición borrador",
        )

    def test_invalid_position_rolls_back_entire_update(self):
        original_layout_name = self.layout.name

        positions = [
            {
                "identifier": "B1",
                "product_id": self.product_a.pk,
                "row": 2,
                "column": 1,
                "width": 1,
                "height": 1,
            },
            {
                "identifier": "Z1",
                "product_id": self.product_b.pk,
                "row": 20,
                "column": 20,
                "width": 1,
                "height": 1,
            },
        ]

        response = self.client.post(
            self.url,
            {
                "name": "Nombre que no debe guardarse",
                "positions": json.dumps(positions),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.name,
            original_layout_name,
        )

        self.assertEqual(
            self.layout.positions.count(),
            2,
        )

        self.assertTrue(
            self.layout.positions.filter(
                identifier="A1",
            ).exists()
        )

        self.assertTrue(
            self.layout.positions.filter(
                identifier="A2",
            ).exists()
        )

        self.assertFalse(
            self.layout.positions.filter(
                identifier="B1",
            ).exists()
        )

    def test_invalid_positions_json_does_not_modify_layout(self):
        response = self.client.post(
            self.url,
            {
                "name": "Nombre modificado",
                "positions": "{invalid-json",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.name,
            "Disposición borrador",
        )

        self.assertEqual(
            self.layout.positions.count(),
            2,
        )

    def test_registered_layout_cannot_access_update_view(self):
        layout = self.create_registered_layout()

        url = reverse(
            "machines:machine_layout_update",
            args=[layout.pk],
        )

        response = self.client.get(
            url,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_registered_layout_cannot_be_updated_by_post(self):
        layout = self.create_registered_layout()

        url = reverse(
            "machines:machine_layout_update",
            args=[layout.pk],
        )

        response = self.client.post(
            url,
            {
                "name": "Nombre modificado",
                "positions": "[]",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        layout.refresh_from_db()

        self.assertEqual(
            layout.name,
            "Disposición registrada",
        )

        self.assertEqual(
            layout.status,
            MachineLayout.Status.REGISTERED,
        )


class MachineLayoutActivationViewTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-ACT-001",
            name="Máquina activaciones",
            serial_number="SN-ACT-001",
            rows=4,
            columns=4,
        )

        self.layout_a = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición A",
            status=MachineLayout.Status.REGISTERED,
        )

        self.layout_b = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición B",
            status=MachineLayout.Status.REGISTERED,
        )

        self.draft_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición borrador",
            status=MachineLayout.Status.DRAFT,
        )

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

    def test_activate_registered_layout(self):
        url = reverse(
            "machines:machine_layout_activate",
            args=[self.layout_a.pk],
        )

        response = self.client.post(
            url,
            follow=True,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout_a.pk],
            ),
        )

        activation = MachineLayoutActivation.objects.get(
            layout=self.layout_a,
        )

        self.assertIsNone(
            activation.effective_to,
        )

        self.assertContains(
            response,
            "La disposición se ha activado correctamente.",
            count=1,
        )

    def test_layout_activation_message_is_shown_only_once(
        self,
    ):
        activate_url = reverse(
            "machines:machine_layout_activate",
            args=[self.layout_a.pk],
        )

        detail_url = reverse(
            "machines:machine_layout_detail",
            args=[self.layout_a.pk],
        )

        response = self.client.post(
            activate_url,
            follow=True,
        )

        self.assertContains(
            response,
            "La disposición se ha activado correctamente.",
            count=1,
        )

        response = self.client.get(
            detail_url,
        )

        self.assertNotContains(
            response,
            "La disposición se ha activado correctamente.",
        )

    def test_activate_layout_requires_post(self):
        url = reverse(
            "machines:machine_layout_activate",
            args=[self.layout_a.pk],
        )

        response = self.client.get(
            url,
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        self.assertFalse(MachineLayoutActivation.objects.exists())

    def test_draft_layout_cannot_be_activated(self):
        url = reverse(
            "machines:machine_layout_activate",
            args=[self.draft_layout.pk],
        )

        response = self.client.post(
            url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.draft_layout.pk],
            ),
        )

        self.assertFalse(
            MachineLayoutActivation.objects.filter(
                layout=self.draft_layout,
            ).exists()
        )

    def test_activating_layout_closes_previous_layout(self):
        activate_machine_layout(
            self.layout_a,
        )

        url = reverse(
            "machines:machine_layout_activate",
            args=[self.layout_b.pk],
        )

        response = self.client.post(
            url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout_b.pk],
            ),
        )

        activation_a = MachineLayoutActivation.objects.get(
            layout=self.layout_a,
        )

        activation_b = MachineLayoutActivation.objects.get(
            layout=self.layout_b,
        )

        self.assertIsNotNone(
            activation_a.effective_to,
        )

        self.assertIsNone(
            activation_b.effective_to,
        )

        self.assertEqual(
            activation_a.effective_to,
            activation_b.effective_from,
        )

    def test_deactivate_active_layout(self):
        activation = activate_machine_layout(
            self.layout_a,
        )

        url = reverse(
            "machines:machine_layout_deactivate",
            args=[self.layout_a.pk],
        )

        response = self.client.post(
            url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout_a.pk],
            ),
        )

        activation.refresh_from_db()

        self.assertIsNotNone(
            activation.effective_to,
        )

        self.assertFalse(
            MachineLayoutActivation.objects.filter(
                layout__machine=self.machine,
                effective_to__isnull=True,
            ).exists()
        )

    def test_deactivate_layout_requires_post(self):
        activation = activate_machine_layout(
            self.layout_a,
        )

        url = reverse(
            "machines:machine_layout_deactivate",
            args=[self.layout_a.pk],
        )

        response = self.client.get(
            url,
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        activation.refresh_from_db()

        self.assertIsNone(
            activation.effective_to,
        )

    def test_cannot_deactivate_layout_that_is_not_active(self):
        activation_a = activate_machine_layout(
            self.layout_a,
        )

        url = reverse(
            "machines:machine_layout_deactivate",
            args=[self.layout_b.pk],
        )

        response = self.client.post(
            url,
        )

        self.assertRedirects(
            response,
            reverse(
                "machines:machine_layout_detail",
                args=[self.layout_b.pk],
            ),
        )

        activation_a.refresh_from_db()

        self.assertIsNone(
            activation_a.effective_to,
        )

    def test_activation_history_returns_200(self):
        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "machines/machine_layout_activation_history.html",
        )

    def test_activation_history_shows_current_and_finished_activations(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        second_moment = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activation_a = activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activation_b = activate_machine_layout(
                self.layout_b,
            )

        activation_a.refresh_from_db()
        activation_b.refresh_from_db()

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(url)

        self.assertContains(
            response,
            "Disposición A",
        )

        self.assertContains(
            response,
            "Disposición B",
        )

        self.assertContains(
            response,
            "Finalizada",
        )

        self.assertContains(
            response,
            "Activa",
        )

        self.assertEqual(
            activation_a.effective_to,
            activation_b.effective_from,
        )

    def test_activation_history_can_filter_by_machine(self):
        with patch(
            "django.utils.timezone.now",
            return_value=self.make_datetime(
                2026,
                9,
                1,
                10,
                0,
            ),
        ):
            activate_machine_layout(
                self.layout_a,
            )

        other_machine = Machine.objects.create(
            identifier="VM-ACT-002",
            name="Otra máquina",
            serial_number="SN-ACT-002",
            rows=4,
            columns=4,
        )

        other_layout = MachineLayout.objects.create(
            machine=other_machine,
            name="Disposición otra máquina",
            status=MachineLayout.Status.REGISTERED,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=self.make_datetime(
                2026,
                9,
                1,
                11,
                0,
            ),
        ):
            activate_machine_layout(
                other_layout,
            )

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(
            url,
            {
                "machine": str(self.machine.pk),
            },
        )

        self.assertContains(
            response,
            "Disposición A",
        )

        self.assertNotContains(
            response,
            "Disposición otra máquina",
        )

    def test_activation_history_filters_from_datetime(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        second_moment = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(
            url,
            {
                "date_from": "2026-09-01T11:00",
            },
        )

        activations = list(response.context["activations"])

        self.assertEqual(
            len(activations),
            2,
        )

    def test_activation_history_excludes_period_finished_before_from_datetime(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            8,
            0,
        )

        second_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        third_moment = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(
            url,
            {
                "date_from": (third_moment.strftime("%Y-%m-%dT%H:%M")),
            },
        )

        activations = list(response.context["activations"])

        self.assertEqual(
            len(activations),
            1,
        )

        self.assertEqual(
            activations[0].layout,
            self.layout_b,
        )

    def test_activation_history_filters_to_datetime(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        second_moment = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(
            url,
            {
                "date_to": "2026-09-01T11:00",
            },
        )

        activations = list(response.context["activations"])

        self.assertEqual(
            len(activations),
            1,
        )

        self.assertEqual(
            activations[0].layout,
            self.layout_a,
        )

    def test_activation_history_filters_by_datetime_range(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            8,
            0,
        )

        second_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        url = reverse("machines:machine_layout_activation_history")

        response = self.client.get(
            url,
            {
                "date_from": "2026-09-01T09:00",
                "date_to": "2026-09-01T09:30",
            },
        )

        activations = list(response.context["activations"])

        self.assertEqual(
            len(activations),
            1,
        )

        self.assertEqual(
            activations[0].layout,
            self.layout_a,
        )
