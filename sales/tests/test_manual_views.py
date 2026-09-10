from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_total_stock,
)
from machines.models import Machine
from purchases.models import Purchase, PurchaseLine
from replenishments.models import (
    Replenishment,
    ReplenishmentLine,
)
from sales.models import Sale


class ManualSaleViewTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas manuales",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaTea Manual",
            category=self.category,
            format_unit="250 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.machine = Machine.objects.create(
            identifier="VM-MANUAL-001",
            name="Máquina manual",
            serial_number="SN-MANUAL-001",
            rows=4,
            columns=4,
        )

        self.url = reverse("sales:sale_manual_create")

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
        purchased_quantity=10,
        replenished_quantity=6,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor manual",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=purchased_quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=replenished_quantity,
        )

    def test_manual_sale_create_view_returns_form(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "sales/sale_manual_create.html",
        )

        self.assertContains(
            response,
            "Registrar venta manual",
        )

        self.assertContains(
            response,
            self.product.name,
        )

        self.assertContains(
            response,
            self.category.name,
        )

        self.assertContains(
            response,
            self.product.format_unit,
        )

    def test_manual_sale_can_be_created_from_view(self):
        self.create_stock()

        response = self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": self.product.pk,
                "selection": "",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "1.60",
                "payment_method": "cash",
            },
        )

        sale = Sale.objects.get(
            source=Sale.Source.MANUAL,
        )

        self.assertRedirects(
            response,
            reverse(
                "sales:sale_detail",
                args=[
                    sale.pk,
                ],
            ),
        )

        self.assertIsNone(
            sale.event_id,
        )

        self.assertEqual(
            sale.machine,
            self.machine,
        )

        self.assertEqual(
            sale.product,
            self.product,
        )

        self.assertEqual(
            sale.status,
            Sale.Status.RESOLVED,
        )

        self.assertIsNone(
            sale.raw_payload,
        )

    def test_manual_free_sale_from_view_uses_zero_amount(self):
        self.create_stock()

        self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": self.product.pk,
                "selection": "",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.FREE,
                "unit_price": "",
                "amount_received": "",
                "payment_method": "",
            },
        )

        sale = Sale.objects.get(
            source=Sale.Source.MANUAL,
        )

        self.assertEqual(
            sale.amount_received,
            Decimal("0.00"),
        )

    def test_manual_sale_without_stock_is_not_created(self):
        response = self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": self.product.pk,
                "selection": "",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "1.60",
                "payment_method": "cash",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock insuficiente")
        self.assertFalse(Sale.objects.exists())

    def test_manual_sale_from_view_affects_inventory(self):
        self.create_stock()

        self.assertEqual(
            get_total_stock(self.product),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            6,
        )

        self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": self.product.pk,
                "selection": "",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 2,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "3.20",
                "payment_method": "cash",
            },
        )

        self.assertEqual(
            get_total_stock(self.product),
            8,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            4,
        )

    def test_manual_sale_cannot_duplicate_existing_event(self):
        Sale.objects.create(
            source=Sale.Source.TELEMETRY,
            event_id="evt-existing-manual-view",
            payload_hash="x" * 64,
            machine_identifier="VM-UNKNOWN",
            machine=None,
            selection="Z9",
            product=None,
            occurred_at=self.make_datetime(
                2026,
                9,
                3,
                17,
                0,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.PAID,
            status=Sale.Status.PENDING,
            raw_payload={
                "event_id": ("evt-existing-manual-view"),
                "machine_identifier": "VM-UNKNOWN",
                "selection": "Z9",
            },
        )

        response = self.client.post(
            self.url,
            {
                "event_id": ("evt-existing-manual-view"),
                "machine": self.machine.pk,
                "product": self.product.pk,
                "selection": "",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "1.60",
                "payment_method": "cash",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            ("Ya existe una recepción con este identificador de evento."),
        )

        self.assertEqual(
            Sale.objects.filter(
                event_id="evt-existing-manual-view",
            ).count(),
            1,
        )
