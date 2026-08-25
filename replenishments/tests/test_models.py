from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from machines.models import Machine
from replenishments.models import Replenishment, ReplenishmentLine


class ReplenishmentCreateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas test",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Coca Cola test",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.50"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-TEST-001",
            name="Máquina test",
            serial_number="SN-TEST-001",
            location="Ubicación test",
        )

    def test_replenishment_with_nonexistent_machine_is_invalid(self):
        data = {
            "replenished_at": "2026-08-25T12:00",
            "machine": "999999",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-quantity": "10",
        }

        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Replenishment.objects.count(),
            0,
        )

        self.assertEqual(
            ReplenishmentLine.objects.count(),
            0,
        )

        form = response.context["form"]

        self.assertIn(
            "machine",
            form.errors,
        )

    def test_replenishment_with_nonexistent_product_is_invalid(self):
        data = {
            "replenished_at": "2026-08-25T12:00",
            "machine": str(self.machine.pk),
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": "999999",
            "lines-0-quantity": "10",
        }

        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Replenishment.objects.count(),
            0,
        )

        self.assertEqual(
            ReplenishmentLine.objects.count(),
            0,
        )

        formset = response.context["formset"]

        self.assertIn(
            "product",
            formset.forms[0].errors,
        )
