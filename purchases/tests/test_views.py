from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from purchases.forms import PurchaseLineFormSet
from purchases.models import Purchase, PurchaseLine


class PurchaseViewTests(TestCase):
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

    def purchase_post_data(self, lines):
        prefix = PurchaseLineFormSet.get_default_prefix()

        data = {
            "purchased_at": "2026-08-25T10:30",
            "supplier": "Makro",
            "document_reference": "F-001",
            f"{prefix}-TOTAL_FORMS": str(len(lines)),
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "1",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }

        for index, line in enumerate(lines):
            data.update(
                {
                    f"{prefix}-{index}-product": str(line["product"].pk),
                    f"{prefix}-{index}-quantity": str(line["quantity"]),
                    f"{prefix}-{index}-unit_price_excl_vat": str(line["price"]),
                }
            )

        return data

    def test_create_purchase_with_one_line(self):
        response = self.client.post(
            reverse("purchases:purchase_create"),
            self.purchase_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                        "price": "0.50",
                    }
                ]
            ),
        )

        purchase = Purchase.objects.get()

        self.assertRedirects(
            response,
            reverse(
                "purchases:purchase_detail",
                args=[purchase.pk],
            ),
        )

        self.assertEqual(
            purchase.lines.count(),
            1,
        )

        line = purchase.lines.get()

        self.assertEqual(
            line.product,
            self.product,
        )
        self.assertEqual(line.quantity, 10)
        self.assertEqual(
            line.unit_price_excl_vat,
            Decimal("0.50"),
        )

    def test_create_purchase_with_multiple_lines(self):
        response = self.client.post(
            reverse("purchases:purchase_create"),
            self.purchase_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                        "price": "0.50",
                    },
                    {
                        "product": self.second_product,
                        "quantity": 5,
                        "price": "0.80",
                    },
                ]
            ),
        )

        self.assertEqual(response.status_code, 302)

        purchase = Purchase.objects.get()

        self.assertEqual(
            purchase.lines.count(),
            2,
        )

    def test_purchase_cannot_be_created_without_lines(self):
        data = self.purchase_post_data([])

        response = self.client.post(
            reverse("purchases:purchase_create"),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Purchase.objects.count(),
            0,
        )

        self.assertEqual(
            PurchaseLine.objects.count(),
            0,
        )

        formset = response.context["formset"]

        self.assertTrue(formset.non_form_errors())

    def test_invalid_line_does_not_create_partial_purchase(self):
        response = self.client.post(
            reverse("purchases:purchase_create"),
            self.purchase_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 0,
                        "price": "0.50",
                    }
                ]
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Purchase.objects.count(),
            0,
        )

        self.assertEqual(
            PurchaseLine.objects.count(),
            0,
        )

        formset = response.context["formset"]

        self.assertIn(
            "quantity",
            formset.forms[0].errors,
        )

    def test_same_product_cannot_be_added_twice(self):
        response = self.client.post(
            reverse("purchases:purchase_create"),
            self.purchase_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                        "price": "0.50",
                    },
                    {
                        "product": self.product,
                        "quantity": 20,
                        "price": "0.45",
                    },
                ]
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Purchase.objects.count(),
            0,
        )

        formset = response.context["formset"]

        self.assertIn(
            "product",
            formset.forms[1].errors,
        )

        self.assertIn(
            "Este producto ya está incluido en la compra.",
            formset.forms[1].errors["product"],
        )

    def test_filter_purchases_by_supplier(self):
        Purchase.objects.create(
            supplier="Makro",
        )

        Purchase.objects.create(
            supplier="Carrefour",
        )

        response = self.client.get(
            reverse("purchases:purchase_list"),
            {
                "supplier": "Mak",
            },
        )

        purchases = response.context["purchases"]

        self.assertEqual(
            purchases.count(),
            1,
        )

        self.assertEqual(
            purchases.first().supplier,
            "Makro",
        )

    def test_purchase_detail_shows_all_lines(self):
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

        response = self.client.get(
            reverse(
                "purchases:purchase_detail",
                args=[purchase.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Coca cola",
        )

        self.assertContains(
            response,
            "Nestea",
        )

        self.assertContains(
            response,
            "Makro",
        )

    def test_filter_purchases_by_product(self):
        first_purchase = Purchase.objects.create(
            supplier="Proveedor A",
        )

        PurchaseLine.objects.create(
            purchase=first_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.50"),
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.second_product,
            quantity=10,
            unit_price_excl_vat=Decimal("0.80"),
        )

        response = self.client.get(
            reverse("purchases:purchase_list"),
            {
                "product": self.product.pk,
            },
        )

        purchases = response.context["purchases"]

        self.assertEqual(
            list(purchases),
            [first_purchase],
        )

    def test_filter_purchases_by_date_range(self):
        now = timezone.now()

        old_purchase = Purchase.objects.create(
            supplier="Compra antigua",
            purchased_at=now - timedelta(days=20),
        )

        expected_purchase = Purchase.objects.create(
            supplier="Compra incluida",
            purchased_at=now - timedelta(days=5),
        )

        future_purchase = Purchase.objects.create(
            supplier="Compra posterior",
            purchased_at=now,
        )

        date_from = (now - timedelta(days=10)).date().isoformat()

        date_to = (now - timedelta(days=2)).date().isoformat()

        response = self.client.get(
            reverse("purchases:purchase_list"),
            {
                "date_from": date_from,
                "date_to": date_to,
            },
        )

        purchases = list(response.context["purchases"])

        self.assertEqual(
            purchases,
            [expected_purchase],
        )

        self.assertNotIn(
            old_purchase,
            purchases,
        )

        self.assertNotIn(
            future_purchase,
            purchases,
        )
