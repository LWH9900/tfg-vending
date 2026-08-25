from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from purchases.models import Purchase, PurchaseLine


class ProductPurchaseCostTests(TestCase):
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

        cls.other_product = Product.objects.create(
            name="Agua",
            category=cls.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.00"),
        )

    def test_product_without_purchases_has_no_costs(self):
        self.assertIsNone(self.product.latest_purchase_cost)

        self.assertIsNone(self.product.average_purchase_cost)

    def test_latest_purchase_cost_uses_most_recent_purchase(self):
        latest_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            purchased_at=timezone.make_aware(datetime(2026, 8, 20, 10, 0)),
        )

        PurchaseLine.objects.create(
            purchase=latest_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("4.00"),
        )

        older_purchase = Purchase.objects.create(
            supplier="Proveedor A",
            purchased_at=timezone.make_aware(datetime(2026, 8, 10, 10, 0)),
        )

        PurchaseLine.objects.create(
            purchase=older_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("4.00"),
        )

    def test_average_purchase_cost_is_weighted_by_quantity(self):
        first_purchase = Purchase.objects.create(
            supplier="Proveedor A",
        )

        PurchaseLine.objects.create(
            purchase=first_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.product,
            quantity=30,
            unit_price_excl_vat=Decimal("4.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("3.50"),
        )

    def test_other_products_do_not_affect_cost_calculation(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.other_product,
            quantity=1000,
            unit_price_excl_vat=Decimal("99.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("2.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("2.00"),
        )

    def test_new_purchase_updates_latest_and_average_cost(self):
        first_purchase = Purchase.objects.create(
            supplier="Proveedor A",
            purchased_at=timezone.make_aware(datetime(2026, 8, 10, 10, 0)),
        )

        PurchaseLine.objects.create(
            purchase=first_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("2.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("2.00"),
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            purchased_at=timezone.make_aware(datetime(2026, 8, 20, 10, 0)),
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.product,
            quantity=30,
            unit_price_excl_vat=Decimal("4.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("4.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("3.50"),
        )
