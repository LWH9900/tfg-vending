from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product


class ProductViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas azucaradas",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="VimaCola",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.50"),
        )

    def test_product_list_access(self):
        response = self.client.get(reverse("inventory:product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "inventory/product_list.html",
        )

    def test_product_appears_in_list(self):
        response = self.client.get(reverse("inventory:product_list"))

        self.assertContains(response, "VimaCola")
        self.assertContains(response, "Bebidas azucaradas")
        self.assertContains(response, "330 ml")

    def test_product_detail_access(self):
        response = self.client.get(
            reverse(
                "inventory:product_detail",
                args=[self.product.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "inventory/product_detail.html",
        )
        self.assertContains(response, "VimaCola")

    def test_create_product(self):
        response = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "Refresco naranja",
                "category": self.category.pk,
                "format_unit": "330 ml",
                "vat_rate": "21.00",
                "default_sale_price": "2.00",
            },
        )

        product = Product.objects.get(name="Refresco naranja")

        self.assertRedirects(
            response,
            reverse(
                "inventory:product_detail",
                args=[product.pk],
            ),
        )

        self.assertEqual(product.category, self.category)
        self.assertEqual(product.format_unit, "330 ml")
        self.assertEqual(
            product.default_sale_price,
            Decimal("2.00"),
        )

    def test_invalid_create_does_not_create_product(self):
        product_count_before = Product.objects.count()

        response = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "",
                "category": self.category.pk,
                "format_unit": "330 ml",
                "vat_rate": "21.00",
                "default_sale_price": "-1.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Product.objects.count(),
            product_count_before,
        )

        form = response.context["form"]

        self.assertIn("name", form.errors)
        self.assertIn("default_sale_price", form.errors)

    def test_update_product(self):
        response = self.client.post(
            reverse(
                "inventory:product_update",
                args=[self.product.pk],
            ),
            {
                "name": "VimaCola Zero",
                "category": self.category.pk,
                "format_unit": "330 ml",
                "vat_rate": "21.00",
                "default_sale_price": "2.75",
            },
        )

        self.product.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                "inventory:product_detail",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(
            self.product.name,
            "VimaCola Zero",
        )
        self.assertEqual(
            self.product.default_sale_price,
            Decimal("2.75"),
        )

    def test_invalid_update_does_not_modify_product(self):
        response = self.client.post(
            reverse(
                "inventory:product_update",
                args=[self.product.pk],
            ),
            {
                "name": "VimaCola",
                "category": self.category.pk,
                "format_unit": "330 ml",
                "vat_rate": "21.00",
                "default_sale_price": "-5.00",
            },
        )

        self.assertEqual(response.status_code, 200)

        form = response.context["form"]

        self.assertIn(
            "default_sale_price",
            form.errors,
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.default_sale_price,
            Decimal("2.50"),
        )

    def test_update_cannot_create_duplicate_product(self):
        other_product = Product.objects.create(
            name="Refresco naranja",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.00"),
        )

        response = self.client.post(
            reverse(
                "inventory:product_update",
                args=[other_product.pk],
            ),
            {
                "name": "VimaCola",
                "category": self.category.pk,
                "format_unit": "330 ml",
                "vat_rate": "21.00",
                "default_sale_price": "3.00",
            },
        )

        self.assertEqual(response.status_code, 200)

        form = response.context["form"]

        self.assertTrue(form.non_field_errors())

        other_product.refresh_from_db()

        self.assertEqual(other_product.name, "Refresco naranja")
        self.assertEqual(other_product.format_unit, "500 ml")
