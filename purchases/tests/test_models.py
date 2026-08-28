from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from purchases.models import Purchase, PurchaseLine


class PurchaseModelTests(TestCase):
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

        cls.second_product = Product.objects.create(
            name="Nestea",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.70"),
        )

    def test_create_valid_purchase_with_one_line(self):
        purchase = Purchase.objects.create(
            purchased_at=timezone.now(),
            supplier="Makro",
            document_reference="F-001",
        )

        line = PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.50"),
        )

        self.assertEqual(Purchase.objects.count(), 1)
        self.assertEqual(PurchaseLine.objects.count(), 1)

        self.assertEqual(line.purchase, purchase)
        self.assertEqual(line.product, self.product)
        self.assertEqual(line.quantity, 10)
        self.assertEqual(
            line.unit_price_excl_vat,
            Decimal("0.50"),
        )

    def test_create_valid_purchase_with_multiple_lines(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.50"),
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.second_product,
            quantity=5,
            unit_price_excl_vat=Decimal("0.80"),
        )

        self.assertEqual(
            purchase.lines.count(),
            2,
        )

    def test_quantity_zero_is_not_valid(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        line = PurchaseLine(
            purchase=purchase,
            product=self.product,
            quantity=0,
            unit_price_excl_vat=Decimal("0.50"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_negative_quantity_is_not_valid(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        line = PurchaseLine(
            purchase=purchase,
            product=self.product,
            quantity=-5,
            unit_price_excl_vat=Decimal("0.50"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_negative_unit_price_is_not_valid(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        line = PurchaseLine(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("-0.50"),
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_line_total(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        line = PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=8,
            unit_price_excl_vat=Decimal("1.25"),
        )

        self.assertEqual(
            line.total,
            Decimal("10.00"),
        )

    def test_purchase_total_with_multiple_lines(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.50"),
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.second_product,
            quantity=5,
            unit_price_excl_vat=Decimal("0.80"),
        )

        self.assertEqual(
            purchase.total,
            Decimal("9.00"),
        )

    def test_same_product_cannot_appear_twice_in_purchase(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.50"),
        )

        duplicate = PurchaseLine(
            purchase=purchase,
            product=self.product,
            quantity=20,
            unit_price_excl_vat=Decimal("0.45"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_new_purchase_is_draft_by_default(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
        )

        self.assertEqual(
            purchase.status,
            Purchase.Status.DRAFT,
        )

    def test_purchase_can_be_registered(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
            status=Purchase.Status.REGISTERED,
        )

        self.assertEqual(
            purchase.status,
            Purchase.Status.REGISTERED,
        )

    def test_purchase_can_be_cancelled(self):
        purchase = Purchase.objects.create(
            supplier="Makro",
            status=Purchase.Status.CANCELLED,
        )

        self.assertEqual(
            purchase.status,
            Purchase.Status.CANCELLED,
        )
