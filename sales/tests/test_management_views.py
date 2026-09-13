from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_total_stock,
    get_warehouse_stock,
)
from machines.models import Machine, MachineLayout, MachinePosition
from machines.services.layouts import activate_machine_layout
from purchases.models import Purchase, PurchaseLine
from replenishments.models import (
    Replenishment,
    ReplenishmentLine,
)
from sales.models import Sale


class SaleManagementViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas gestión",
            default_vat_rate=Decimal("21.00"),
        )

        self.product_a = Product.objects.create(
            name="VimaCola Gestión",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            name="VimaTea Gestión",
            category=self.category,
            format_unit="250 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.machine = Machine.objects.create(
            identifier="VM-MANAGEMENT-001",
            name="Máquina gestión",
            serial_number="SN-MANAGEMENT-001",
            rows=4,
            columns=4,
        )

        self.pending_sale = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-management-pending",
            payload_hash="a" * 64,
            machine_identifier="VM-EXTERNAL-ERROR",
            machine=None,
            selection="Z9",
            product=None,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                10,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.PENDING,
            raw_payload={
                "event_id": "evt-management-pending",
                "machine_identifier": "VM-EXTERNAL-ERROR",
                "selection": "Z9",
                "quantity": 1,
            },
        )

        self.resolved_sale = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-management-resolved",
            payload_hash="b" * 64,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            selection="A1",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                11,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload={
                "event_id": "evt-management-resolved",
                "machine_identifier": self.machine.identifier,
                "selection": "A1",
                "quantity": 1,
            },
        )

        self.conflict_reference = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-management-conflict",
            payload_hash="c" * 64,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            selection="A1",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                12,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload={
                "event_id": "evt-management-conflict",
                "machine_identifier": self.machine.identifier,
                "selection": "A1",
                "quantity": 1,
            },
        )

        self.conflict_sale = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-management-conflict",
            payload_hash="d" * 64,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            selection="A2",
            product=self.product_b,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                12,
                5,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.60"),
            amount_received=Decimal("1.60"),
            payment_method="cash",
            status=Sale.Status.CONFLICT,
            conflicts_with=self.conflict_reference,
            raw_payload={
                "event_id": "evt-management-conflict",
                "machine_identifier": self.machine.identifier,
                "selection": "A2",
                "quantity": 1,
            },
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición gestión",
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product_a,
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A2",
            row=1,
            column=2,
            product=self.product_b,
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="Z9",
            row=1,
            column=3,
            product=None,
        )

        self.layout.status = MachineLayout.Status.REGISTERED
        self.layout.save()

        activation_time = self.make_datetime(
            2026,
            9,
            3,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout,
            )

    def make_datetime(
        self,
        year,
        month,
        day,
        hour,
        minute,
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

    def create_stock(
        self,
        product,
        purchased_quantity=10,
        replenished_quantity=6,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor gestión",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=product,
            quantity=purchased_quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=replenished_quantity,
        )

    def test_pending_sale_resolve_view_returns_form(self):
        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_resolve.html",
        )

        self.assertContains(
            response,
            "Resolver venta pendiente",
        )

        self.assertContains(
            response,
            "VM-EXTERNAL-ERROR",
        )

        self.assertContains(
            response,
            "Z9",
        )
        self.assertContains(
            response,
            "Identificar máquina",
        )

    def test_resolved_sale_cannot_open_pending_resolution(self):
        url = reverse(
            "sales:sale_resolve",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.resolved_sale.pk,
                ],
            ),
        )

    def test_pending_sale_can_be_resolved_from_view(self):
        self.create_stock(self.product_a)

        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.post(
            url,
            {
                "machine": self.machine.pk,
                "product": self.product_a.pk,
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.pending_sale.pk,
                ],
            ),
        )

        self.pending_sale.refresh_from_db()

        self.assertEqual(
            self.pending_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            self.pending_sale.machine,
            self.machine,
        )

        self.assertEqual(
            self.pending_sale.product,
            self.product_a,
        )

    def test_resolving_pending_sale_from_view_preserves_original_data(self):
        self.create_stock(self.product_a)

        original_payload = self.pending_sale.raw_payload.copy()

        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        self.client.post(
            url,
            {
                "machine": self.machine.pk,
                "product": self.product_a.pk,
            },
        )

        self.pending_sale.refresh_from_db()

        self.assertEqual(
            self.pending_sale.machine_identifier,
            "VM-EXTERNAL-ERROR",
        )

        self.assertEqual(
            self.pending_sale.selection,
            "Z9",
        )

        self.assertEqual(
            self.pending_sale.raw_payload,
            original_payload,
        )

    def test_resolving_pending_sale_from_view_affects_inventory(self):
        self.create_stock(
            self.product_a,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )
        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        self.client.post(
            url,
            {
                "machine": self.machine.pk,
                "product": self.product_a.pk,
            },
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            7,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            3,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_pending_resolution_requires_product(self):
        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.post(
            url,
            {
                "machine": self.machine.pk,
                "product": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.pending_sale.refresh_from_db()

        self.assertEqual(
            self.pending_sale.status,
            Sale.Status.PENDING,
        )

    def test_resolved_sale_void_view_returns_form(self):
        url = reverse(
            "sales:sale_void",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_void.html",
        )

        self.assertContains(
            response,
            "Anular venta",
        )

        self.assertContains(
            response,
            self.product_a.name,
        )

        self.assertContains(
            response,
            self.category.name,
        )

        self.assertContains(
            response,
            self.product_a.format_unit,
        )

    def test_pending_sale_cannot_open_void_view(self):
        url = reverse(
            "sales:sale_void",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.pending_sale.pk,
                ],
            ),
        )

    def test_resolved_sale_can_be_voided_from_view(self):
        url = reverse(
            "sales:sale_void",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.post(
            url,
            {
                "reason": ("Venta anulada desde la interfaz de prueba."),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.resolved_sale.pk,
                ],
            ),
        )

        self.resolved_sale.refresh_from_db()

        self.assertEqual(
            self.resolved_sale.status,
            Sale.Status.VOIDED,
        )

        self.assertEqual(
            self.resolved_sale.void_reason,
            ("Venta anulada desde la interfaz de prueba."),
        )

        self.assertIsNotNone(
            self.resolved_sale.voided_at,
        )

    def test_void_sale_view_requires_reason(self):
        url = reverse(
            "sales:sale_void",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.post(
            url,
            {
                "reason": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.resolved_sale.refresh_from_db()

        self.assertEqual(
            self.resolved_sale.status,
            Sale.Status.RESOLVED,
        )

    def test_voiding_sale_from_view_restores_inventory(self):
        self.create_stock(
            self.product_a,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            4,
        )

        url = reverse(
            "sales:sale_void",
            args=[
                self.resolved_sale.pk,
            ],
        )

        self.client.post(
            url,
            {
                "reason": "Anulación por prueba.",
            },
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_machine_stock(
                self.product_a,
                self.machine,
            ),
            5,
        )

        self.assertEqual(
            get_warehouse_stock(self.product_a),
            4,
        )

    def test_conflict_review_displays_both_sales(self):
        url = reverse(
            "sales:sale_conflict_review",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_conflict_review.html",
        )

        self.assertContains(
            response,
            "Venta efectiva actual",
        )

        self.assertContains(
            response,
            "Recepción conflictiva",
        )

        self.assertContains(
            response,
            self.product_a.name,
        )

        self.assertContains(
            response,
            self.product_b.name,
        )

        self.assertContains(
            response,
            self.product_a.format_unit,
        )

        self.assertContains(
            response,
            self.product_b.format_unit,
        )

    def test_non_conflict_cannot_open_conflict_review(self):
        url = reverse(
            "sales:sale_conflict_review",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.resolved_sale.pk,
                ],
            ),
        )

    def test_conflict_can_be_rejected_from_view(self):
        url = reverse(
            "sales:sale_conflict_reject",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.conflict_sale.pk,
                ],
            ),
        )

        self.conflict_sale.refresh_from_db()
        self.conflict_reference.refresh_from_db()

        self.assertEqual(
            self.conflict_sale.status,
            Sale.Status.REJECTED,
        )

        self.assertEqual(
            self.conflict_reference.status,
            Sale.Status.RESOLVED,
        )

    def test_conflict_reject_requires_post(self):
        url = reverse(
            "sales:sale_conflict_reject",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            405,
        )

        self.conflict_sale.refresh_from_db()

        self.assertEqual(
            self.conflict_sale.status,
            Sale.Status.CONFLICT,
        )

    def test_conflict_can_be_accepted_from_view(self):
        self.create_stock(self.product_b)

        url = reverse(
            "sales:sale_conflict_accept",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    self.conflict_sale.pk,
                ],
            ),
        )

        self.conflict_sale.refresh_from_db()
        self.conflict_reference.refresh_from_db()

        self.assertEqual(
            self.conflict_sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertEqual(
            self.conflict_reference.status,
            Sale.Status.VOIDED,
        )

        self.assertIsNotNone(
            self.conflict_reference.voided_at,
        )

        self.assertTrue(
            self.conflict_reference.void_reason,
        )

    def test_conflict_accept_requires_post(self):
        url = reverse(
            "sales:sale_conflict_accept",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_accepting_conflict_from_view_switches_inventory(self):
        self.create_stock(
            self.product_a,
        )

        self.create_stock(
            self.product_b,
        )

        self.assertEqual(
            get_total_stock(self.product_a),
            8,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            10,
        )

        url = reverse(
            "sales:sale_conflict_accept",
            args=[
                self.conflict_sale.pk,
            ],
        )

        self.client.post(url)

        self.assertEqual(
            get_total_stock(self.product_a),
            9,
        )

        self.assertEqual(
            get_total_stock(self.product_b),
            9,
        )

    def test_pending_detail_shows_resolve_action(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertContains(
            response,
            "Resolver venta",
        )

        self.assertNotContains(
            response,
            "Anular venta",
        )

    def test_resolved_detail_shows_void_action(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.resolved_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertContains(
            response,
            "Anular venta",
        )

        self.assertNotContains(
            response,
            "Resolver venta",
        )

    def test_conflict_detail_shows_review_action(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.conflict_sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertContains(
            response,
            "Revisar conflicto",
        )

    def test_pending_resolution_shows_historical_layout_candidates(self):
        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.get(
            url,
            {
                "machine": self.machine.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.context["selected_machine"],
            self.machine,
        )

        self.assertEqual(
            response.context["layout"],
            self.layout,
        )

        self.assertContains(
            response,
            "Disposición gestión",
        )

        self.assertContains(
            response,
            self.product_a.name,
        )

        self.assertContains(
            response,
            self.product_b.name,
        )

        self.assertContains(
            response,
            self.category.name,
        )

    def test_pending_resolution_product_choices_are_limited_to_layout(self):
        outside_product = Product.objects.create(
            name="VimaOutside Gestión",
            category=self.category,
            format_unit="500 ml",
            default_sale_price=Decimal("2.00"),
            vat_rate=Decimal("21.00"),
        )

        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.get(
            url,
            {
                "machine": self.machine.pk,
            },
        )

        form = response.context["form"]

        products = list(form.fields["product"].queryset)

        self.assertIn(
            self.product_a,
            products,
        )

        self.assertIn(
            self.product_b,
            products,
        )

        self.assertNotIn(
            outside_product,
            products,
        )

    def test_pending_resolution_rejects_product_outside_layout(self):
        outside_product = Product.objects.create(
            name="VimaOutside POST",
            category=self.category,
            format_unit="500 ml",
            default_sale_price=Decimal("2.00"),
            vat_rate=Decimal("21.00"),
        )

        url = reverse(
            "sales:sale_resolve",
            args=[
                self.pending_sale.pk,
            ],
        )

        response = self.client.post(
            url,
            {
                "machine": self.machine.pk,
                "product": outside_product.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.pending_sale.refresh_from_db()

        self.assertEqual(
            self.pending_sale.status,
            Sale.Status.PENDING,
        )

        self.assertIsNone(
            self.pending_sale.product,
        )

    def test_pending_sale_with_known_machine_does_not_ask_machine_again(self):
        sale = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-known-machine",
            payload_hash="f" * 64,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            selection="000000",
            product=None,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                10,
                30,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.60"),
            amount_received=Decimal("1.60"),
            payment_method="cash",
            status=Sale.Status.PENDING,
            raw_payload={
                "event_id": "evt-known-machine",
                "machine_identifier": (self.machine.identifier),
                "selection": "000000",
            },
        )

        url = reverse(
            "sales:sale_resolve",
            args=[
                sale.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.context["selected_machine"],
            self.machine,
        )

        self.assertIsNone(
            response.context["machine_form"],
        )

        self.assertEqual(
            response.context["layout"],
            self.layout,
        )

        self.assertContains(
            response,
            "000000",
        )
        self.assertNotContains(
            response,
            "Identificar máquina",
        )

        self.assertContains(
            response,
            "La selección",
        )

        self.assertContains(
            response,
            "no existe en",
        )

        self.assertContains(
            response,
            self.product_a.name,
        )
