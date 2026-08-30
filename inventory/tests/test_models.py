from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from inventory.models import Category, Product


class ProductModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas azucaradas",
            default_vat_rate=Decimal("21.00"),
        )

    def test_create_valid_product(self):
        product = Product.objects.create(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(product.name, "VimaCola")
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.format_unit, "330 ml")
        self.assertEqual(product.vat_rate, Decimal("21.00"))
        self.assertEqual(product.default_sale_price, Decimal("2.50"))
        self.assertTrue(product.is_active)

    def test_product_name_is_required(self):
        product = Product(
            name="",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_product_format_unit_is_required(self):
        product = Product(
            name="VimaCola",
            category=self.category,
            format_unit="",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_product_category_is_required(self):
        product = Product(
            name="VimaCola",
            category=None,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_sale_price_cannot_be_negative(self):
        product = Product(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("-1.00"),
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_duplicate_product_is_not_valid(self):
        Product.objects.create(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

        duplicate = Product(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("3.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
