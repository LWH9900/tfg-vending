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
)
from machines.models import Machine, MachineLayout, MachinePosition
from machines.services.layouts import activate_machine_layout
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

        self.assertContains(
            response,
            reverse(
                "sales:manual_sale_product_status",
                args=[0],
            ),
        )

    def test_manual_product_status_returns_machine_stock_and_layout_state(self):
        self.create_stock()

        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición venta manual",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()
        activate_machine_layout(layout)

        response = self.client.get(
            reverse(
                "sales:manual_sale_product_status",
                args=[self.machine.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

        product_status = next(
            product
            for product in response.json()["products"]
            if product["id"] == self.product.pk
        )

        self.assertEqual(product_status["machine_stock"], 6)
        self.assertTrue(product_status["is_active"])

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

        detail_response = self.client.get(reverse("sales:sale_detail", args=[sale.pk]))
        self.assertContains(detail_response, "Efectivo")
        self.assertNotContains(detail_response, ">cash<")

    def test_manual_sale_infers_product_from_selection_and_historical_layout(self):
        self.create_stock()

        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición histórica manual",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        activation_time = self.make_datetime(2026, 9, 3, 12, 0)

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(layout)

        response = self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": "",
                "selection": "a1",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "1.60",
                "payment_method": "cash",
            },
        )

        sale = Sale.objects.get(source=Sale.Source.MANUAL)

        self.assertRedirects(
            response,
            reverse("sales:sale_detail", args=[sale.pk]),
        )
        self.assertEqual(sale.product, self.product)
        self.assertEqual(sale.selection, "a1")

    def test_manual_sale_without_product_reports_missing_historical_layout(self):
        response = self.client.post(
            self.url,
            {
                "event_id": "",
                "machine": self.machine.pk,
                "product": "",
                "selection": "A1",
                "occurred_at": "2026-09-03T18:00",
                "quantity": 1,
                "dispense_type": Sale.DispenseType.PAID,
                "unit_price": "1.60",
                "amount_received": "1.60",
                "payment_method": "cash",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No había ninguna disposición activa",
        )
        self.assertFalse(Sale.objects.exists())

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

        self.assertIsNone(sale.unit_price)
        self.assertEqual(sale.payment_method, "")

    def test_manual_paid_sale_accepts_unknown_payment_method(self):
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
                "payment_method": "unknown",
            },
        )

        sale = Sale.objects.get(source=Sale.Source.MANUAL)

        self.assertRedirects(
            response,
            reverse("sales:sale_detail", args=[sale.pk]),
        )
        self.assertEqual(sale.payment_method, "unknown")

        detail_response = self.client.get(reverse("sales:sale_detail", args=[sale.pk]))
        self.assertContains(detail_response, "Desconocido")

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
        self.assertContains(
            response,
            (
                "Stock insuficiente para registrar la venta. "
                "La máquina dispone de 0 unidades y se han solicitado 1."
            ),
        )
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(response.context["form"].errors.get("quantity"))
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
