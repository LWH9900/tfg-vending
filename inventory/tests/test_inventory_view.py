from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from machines.models import Machine
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine


class InventoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Coca cola",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.50"),
        )

        cls.product_without_movements = Product.objects.create(
            name="Agua",
            category=cls.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="M-001",
            name="Máquina 1",
            serial_number="SN-001",
        )

    def test_inventory_overview_shows_products_without_movements(self):
        response = self.client.get(reverse("inventory:inventory_overview"))

        self.assertEqual(
            response.status_code,
            200,
        )

        items = response.context["inventory_items"]

        item = next(
            item for item in items if item["product"] == self.product_without_movements
        )

        self.assertEqual(
            item["total_stock"],
            0,
        )

        self.assertEqual(
            item["warehouse_stock"],
            0,
        )

        self.assertEqual(
            item["machines_stock"],
            0,
        )

        self.assertEqual(
            item["inventory_value"],
            Decimal("0.00"),
        )

        self.assertEqual(
            item["potential_sale_value"],
            Decimal("0.00"),
        )

    def test_inventory_overview_shows_calculated_stock(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=100,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=30,
        )

        response = self.client.get(reverse("inventory:inventory_overview"))

        items = response.context["inventory_items"]

        item = next(item for item in items if item["product"] == self.product)

        self.assertEqual(
            item["total_stock"],
            100,
        )

        self.assertEqual(
            item["warehouse_stock"],
            70,
        )

        self.assertEqual(
            item["machines_stock"],
            30,
        )

        self.assertEqual(
            item["inventory_value"],
            Decimal("100.00"),
        )
        self.assertEqual(
            item["potential_sale_value"],
            Decimal("150.00"),
        )
