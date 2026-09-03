import json
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import Machine
from sales.models import Sale
from sales.services import (
    reject_sale_conflict,
    void_sale,
)


class SaleHistoryViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas histórico",
            default_vat_rate=Decimal("21.00"),
        )

        self.product_a = Product.objects.create(
            name="VimaCola Histórico",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            name="VimaTea Histórico",
            category=self.category,
            format_unit="250 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.machine_a = Machine.objects.create(
            identifier="VM-HIST-001",
            name="Máquina histórico A",
            serial_number="SN-HIST-001",
            rows=4,
            columns=4,
        )

        self.machine_b = Machine.objects.create(
            identifier="VM-HIST-002",
            name="Máquina histórico B",
            serial_number="SN-HIST-002",
            rows=4,
            columns=4,
        )

        self.sale_resolved = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-history-001",
            payload_hash="a" * 64,
            machine_identifier="VM-HIST-001",
            machine=self.machine_a,
            selection="A1",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                9,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("1.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload={
                "event_id": "evt-history-001",
                "machine_identifier": "VM-HIST-001",
                "selection": "A1",
                "quantity": 1,
            },
        )

        self.sale_pending = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-special-pending",
            payload_hash="b" * 64,
            machine_identifier="VM-NO-RESUELTA",
            machine=None,
            selection="Z9",
            product=None,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                11,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.70"),
            amount_received=Decimal("1.70"),
            payment_method="card",
            status=Sale.Status.PENDING,
            raw_payload={
                "event_id": "evt-special-pending",
                "machine_identifier": "VM-NO-RESUELTA",
                "selection": "Z9",
                "quantity": 1,
            },
        )

        self.sale_voided = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-history-voided",
            payload_hash="c" * 64,
            machine_identifier="VM-HIST-002",
            machine=self.machine_b,
            selection="B1",
            product=self.product_b,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                13,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.60"),
            amount_received=Decimal("1.60"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload={
                "event_id": "evt-history-voided",
                "machine_identifier": "VM-HIST-002",
                "selection": "B1",
                "quantity": 1,
            },
        )

        self.sale_voided = void_sale(
            self.sale_voided,
            "Venta anulada para prueba del histórico.",
        )

        self.sale_conflict = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-history-001",
            payload_hash="d" * 64,
            machine_identifier="VM-HIST-001",
            machine=self.machine_a,
            selection="A2",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                9,
                5,
            ),
            quantity=2,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("3.00"),
            payment_method="cash",
            status=Sale.Status.CONFLICT,
            conflicts_with=self.sale_resolved,
            raw_payload={
                "event_id": "evt-history-001",
                "machine_identifier": "VM-HIST-001",
                "selection": "A2",
                "quantity": 2,
            },
        )

        rejected_conflict = Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-history-001",
            payload_hash="e" * 64,
            machine_identifier="VM-HIST-001",
            machine=self.machine_a,
            selection="A3",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                9,
                10,
            ),
            quantity=3,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("4.50"),
            payment_method="cash",
            status=Sale.Status.CONFLICT,
            conflicts_with=self.sale_resolved,
            raw_payload={
                "event_id": "evt-history-001",
                "machine_identifier": "VM-HIST-001",
                "selection": "A3",
                "quantity": 3,
            },
        )

        self.sale_rejected = reject_sale_conflict(rejected_conflict)

        self.sale_manual = Sale.objects.create(
            source=Sale.Source.MANUAL,
            event_id=None,
            machine_identifier="VM-HIST-001",
            machine=self.machine_a,
            selection="",
            product=self.product_a,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                15,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.FREE,
            unit_price=None,
            amount_received=Decimal("0.00"),
            payment_method="",
            status=Sale.Status.RESOLVED,
            raw_payload=None,
        )

        self.list_url = reverse("sales:sale_list")

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

    def test_sale_list_returns_all_sales(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_list.html",
        )

        self.assertEqual(
            len(response.context["sales"]),
            6,
        )

    def test_sale_list_displays_all_statuses(self):
        response = self.client.get(self.list_url)

        self.assertContains(
            response,
            "Resuelta",
        )

        self.assertContains(
            response,
            "Pendiente",
        )

        self.assertContains(
            response,
            "En conflicto",
        )

        self.assertContains(
            response,
            "Descartada",
        )

        self.assertContains(
            response,
            "Anulada",
        )

    def test_pending_sale_shows_external_machine_identifier(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "VM-NO-RESUELTA",
        )

        self.assertIn(
            self.sale_pending,
            response.context["sales"],
        )

    def test_filter_by_machine(self):
        response = self.client.get(
            self.list_url,
            {
                "machine": self.machine_b.pk,
            },
        )

        sales = response.context["sales"]

        self.assertIn(
            self.sale_voided,
            sales,
        )

        self.assertNotIn(
            self.sale_resolved,
            sales,
        )

        self.assertNotIn(
            self.sale_pending,
            sales,
        )

    def test_filter_by_product(self):
        response = self.client.get(
            self.list_url,
            {
                "product": self.product_b.pk,
            },
        )

        sales = response.context["sales"]

        self.assertIn(
            self.sale_voided,
            sales,
        )

        self.assertNotIn(
            self.sale_resolved,
            sales,
        )

    def test_filter_by_status(self):
        response = self.client.get(
            self.list_url,
            {
                "status": Sale.Status.CONFLICT,
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_conflict,
            ],
        )

    def test_filter_by_event_id(self):
        response = self.client.get(
            self.list_url,
            {
                "event_id": ("special-pending"),
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_pending,
            ],
        )

    def test_filter_by_datetime_range(self):
        response = self.client.get(
            self.list_url,
            {
                "date_from": ("2026-09-03T10:00"),
                "date_to": ("2026-09-03T12:00"),
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_pending,
            ],
        )

    def test_invalid_datetime_range_shows_form_error(self):
        response = self.client.get(
            self.list_url,
            {
                "date_from": ("2026-09-03T15:00"),
                "date_to": ("2026-09-03T10:00"),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            ("La fecha inicial no puede ser posterior a la fecha final."),
        )

    def test_filter_by_manual_source(self):
        response = self.client.get(
            self.list_url,
            {
                "source": (Sale.Source.MANUAL),
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_manual,
            ],
        )

    def test_filter_by_dispense_type(self):
        response = self.client.get(
            self.list_url,
            {
                "dispense_type": (Sale.DispenseType.FREE),
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_manual,
            ],
        )

    def test_filters_can_be_combined(self):
        response = self.client.get(
            self.list_url,
            {
                "machine": (self.machine_a.pk),
                "product": (self.product_a.pk),
                "status": (Sale.Status.RESOLVED),
                "source": (Sale.Source.TELEMETRY),
            },
        )

        sales = list(response.context["sales"])

        self.assertEqual(
            sales,
            [
                self.sale_resolved,
            ],
        )

    def test_sale_detail_returns_sale(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.sale_resolved.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_detail.html",
        )

        self.assertEqual(
            response.context["sale"],
            self.sale_resolved,
        )

        self.assertContains(
            response,
            "evt-history-001",
        )

        self.assertContains(
            response,
            "VimaCola Histórico",
        )

        self.assertContains(
            response,
            "VM-HIST-001",
        )

    def test_sale_detail_displays_pretty_payload(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.sale_resolved.pk,
            ],
        )

        response = self.client.get(url)

        pretty_payload = response.context["pretty_payload"]

        self.assertIsNotNone(pretty_payload)

        self.assertIn(
            "\n",
            pretty_payload,
        )

        self.assertIn(
            '"event_id": "evt-history-001"',
            pretty_payload,
        )

    def test_conflict_detail_shows_reference_sale(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.sale_conflict.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (f"Venta #{self.sale_resolved.pk}"),
        )

        self.assertEqual(
            response.context["sale"].conflicts_with,
            self.sale_resolved,
        )

    def test_original_sale_detail_lists_related_conflicts(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.sale_resolved.pk,
            ],
        )

        response = self.client.get(url)

        conflicting_sales = list(response.context["conflicting_sales"])

        self.assertIn(
            self.sale_conflict,
            conflicting_sales,
        )

        self.assertIn(
            self.sale_rejected,
            conflicting_sales,
        )

    def test_voided_sale_detail_shows_void_information(self):
        url = reverse(
            "sales:sale_detail",
            args=[
                self.sale_voided.pk,
            ],
        )

        response = self.client.get(url)

        self.assertContains(
            response,
            "Anulada",
        )

        self.assertContains(
            response,
            ("Venta anulada para prueba del histórico."),
        )

        self.assertIsNotNone(self.sale_voided.voided_at)

    def test_payload_download_returns_json_attachment(self):
        url = reverse(
            "sales:sale_payload_download",
            args=[
                self.sale_resolved.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(response["Content-Type"].startswith("application/json"))

        self.assertIn(
            "attachment;",
            response["Content-Disposition"],
        )

        self.assertIn(
            (f"sale-{self.sale_resolved.pk}-payload.json"),
            response["Content-Disposition"],
        )

        downloaded_payload = json.loads(response.content)

        self.assertEqual(
            downloaded_payload,
            self.sale_resolved.raw_payload,
        )

    def test_sale_without_payload_returns_404_on_download(self):
        url = reverse(
            "sales:sale_payload_download",
            args=[
                self.sale_manual.pk,
            ],
        )

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            404,
        )
