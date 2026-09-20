from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product


class CategoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

    def test_category_list_access_and_content(self):
        response = self.client.get(reverse("inventory:category_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/category_list.html")
        self.assertContains(response, "Bebidas")

    def test_empty_category_list_keeps_table_and_shows_message(self):
        Category.objects.all().delete()

        response = self.client.get(reverse("inventory:category_list"))

        self.assertContains(response, "<table", html=False)
        self.assertContains(response, "No hay categorías registradas.")

    def test_create_category(self):
        response = self.client.post(
            reverse("inventory:category_create"),
            {"name": "Aperitivos", "default_vat_rate": "10.00"},
        )

        self.assertRedirects(response, reverse("inventory:category_list"))
        category = Category.objects.get(name="Aperitivos")
        self.assertEqual(category.default_vat_rate, Decimal("10.00"))

    def test_create_duplicate_category_is_rejected_case_insensitively(self):
        response = self.client.post(
            reverse("inventory:category_create"),
            {"name": " bebidas ", "default_vat_rate": "10.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Category.objects.count(), 1)
        self.assertContains(
            response,
            "Ya existe una categoría con este nombre.",
        )

    def test_create_category_rejects_vat_outside_allowed_range(self):
        for vat_rate, expected_message in (
            ("-0.01", "El IVA no puede ser inferior al 0 %."),
            ("100.01", "El IVA no puede ser superior al 100 %."),
        ):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:category_create"),
                    {"name": f"Categoría {vat_rate}", "default_vat_rate": vat_rate},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_message)
                self.assertFalse(
                    Category.objects.filter(name=f"Categoría {vat_rate}").exists()
                )

    def test_create_category_accepts_vat_range_boundaries(self):
        for vat_rate in ("0.00", "100.00"):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:category_create"),
                    {"name": f"Categoría {vat_rate}", "default_vat_rate": vat_rate},
                )

                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    Category.objects.filter(
                        name=f"Categoría {vat_rate}",
                        default_vat_rate=Decimal(vat_rate),
                    ).exists()
                )

    def test_update_category(self):
        response = self.client.post(
            reverse("inventory:category_update", args=[self.category.pk]),
            {"name": "Bebidas frías", "default_vat_rate": "10.00"},
        )

        self.assertRedirects(response, reverse("inventory:category_list"))
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Bebidas frías")
        self.assertEqual(self.category.default_vat_rate, Decimal("10.00"))

    def test_update_category_only_updates_products_using_its_vat(self):
        inherited_product = Product.objects.create(
            name="Agua sin gas",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            uses_category_vat=True,
            default_sale_price=Decimal("1.50"),
        )
        custom_product = Product.objects.create(
            name="Agua con gas",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("15.00"),
            uses_category_vat=False,
            default_sale_price=Decimal("1.75"),
        )

        self.client.post(
            reverse("inventory:category_update", args=[self.category.pk]),
            {"name": "Bebidas", "default_vat_rate": "15.00"},
        )
        inherited_product.refresh_from_db()
        custom_product.refresh_from_db()
        self.assertEqual(inherited_product.vat_rate, Decimal("15.00"))
        self.assertEqual(custom_product.vat_rate, Decimal("15.00"))

        self.client.post(
            reverse("inventory:category_update", args=[self.category.pk]),
            {"name": "Bebidas", "default_vat_rate": "20.00"},
        )
        inherited_product.refresh_from_db()
        custom_product.refresh_from_db()
        self.assertEqual(inherited_product.vat_rate, Decimal("20.00"))
        self.assertEqual(custom_product.vat_rate, Decimal("15.00"))

    def test_update_category_cannot_duplicate_another_category(self):
        other = Category.objects.create(
            name="Aperitivos",
            default_vat_rate=Decimal("10.00"),
        )

        response = self.client.post(
            reverse("inventory:category_update", args=[other.pk]),
            {"name": "BEBIDAS", "default_vat_rate": "10.00"},
        )

        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.name, "Aperitivos")

    def test_update_category_rejects_vat_outside_allowed_range(self):
        for vat_rate, expected_message in (
            ("-0.01", "El IVA no puede ser inferior al 0 %."),
            ("100.01", "El IVA no puede ser superior al 100 %."),
        ):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:category_update", args=[self.category.pk]),
                    {"name": "Bebidas", "default_vat_rate": vat_rate},
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_message)
                self.category.refresh_from_db()
                self.assertEqual(self.category.default_vat_rate, Decimal("21.00"))

    def test_delete_category_without_products(self):
        response = self.client.post(
            reverse("inventory:category_delete", args=[self.category.pk])
        )

        self.assertRedirects(response, reverse("inventory:category_list"))
        self.assertFalse(Category.objects.filter(pk=self.category.pk).exists())

    def test_delete_category_with_products_is_rejected_with_clear_message(self):
        Product.objects.create(
            name="Agua",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("10.00"),
            default_sale_price=Decimal("1.50"),
        )

        list_response = self.client.get(reverse("inventory:category_list"))
        self.assertContains(
            list_response,
            reverse("inventory:category_delete", args=[self.category.pk]),
        )
        self.assertNotContains(
            list_response,
            "No se puede eliminar mientras tenga productos asociados.",
        )

        response = self.client.post(
            reverse("inventory:category_delete", args=[self.category.pk]),
            follow=True,
        )

        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertContains(
            response,
            "No se puede eliminar la categoría porque tiene productos asociados.",
        )

    def test_delete_category_only_accepts_post(self):
        response = self.client.get(
            reverse("inventory:category_delete", args=[self.category.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_sidebar_links_to_categories(self):
        response = self.client.get(reverse("inventory:category_list"))

        self.assertContains(response, reverse("inventory:category_list"))


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

    def test_empty_product_list_keeps_table_and_shows_message(self):
        Product.objects.all().delete()

        response = self.client.get(reverse("inventory:product_list"))

        self.assertContains(response, "<table", html=False)
        self.assertContains(response, "No hay productos registrados.")

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

    def test_create_product_rejects_vat_outside_allowed_range(self):
        for vat_rate, expected_message in (
            ("-0.01", "El IVA no puede ser inferior al 0 %."),
            ("100.01", "El IVA no puede ser superior al 100 %."),
        ):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:product_create"),
                    {
                        "name": f"Producto {vat_rate}",
                        "category": self.category.pk,
                        "format_unit": "1 ud.",
                        "vat_rate": vat_rate,
                        "default_sale_price": "1.00",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_message)
                self.assertFalse(
                    Product.objects.filter(name=f"Producto {vat_rate}").exists()
                )

    def test_create_product_accepts_vat_range_boundaries(self):
        for vat_rate in ("0.00", "100.00"):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:product_create"),
                    {
                        "name": f"Producto {vat_rate}",
                        "category": self.category.pk,
                        "format_unit": "1 ud.",
                        "vat_rate": vat_rate,
                        "default_sale_price": "1.00",
                    },
                )

                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    Product.objects.filter(
                        name=f"Producto {vat_rate}",
                        vat_rate=Decimal(vat_rate),
                    ).exists()
                )

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

    def test_update_product_rejects_vat_outside_allowed_range(self):
        for vat_rate, expected_message in (
            ("-0.01", "El IVA no puede ser inferior al 0 %."),
            ("100.01", "El IVA no puede ser superior al 100 %."),
        ):
            with self.subTest(vat_rate=vat_rate):
                response = self.client.post(
                    reverse("inventory:product_update", args=[self.product.pk]),
                    {
                        "name": "VimaCola",
                        "category": self.category.pk,
                        "format_unit": "330 ml",
                        "vat_rate": vat_rate,
                        "default_sale_price": "2.50",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_message)
                self.product.refresh_from_db()
                self.assertEqual(self.product.vat_rate, Decimal("21.00"))

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
