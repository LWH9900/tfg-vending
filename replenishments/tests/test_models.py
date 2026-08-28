from decimal import Decimal

from django.core.exceptions import ValidationError
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


class ReplenishmentModelTests(TestCase):
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

        cls.machine = Machine.objects.create(
            identifier="M-001",
            name="Máquina 1",
            serial_number="SN-001",
        )

    def test_new_replenishment_is_draft_by_default(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

    def test_quantity_zero_is_not_valid(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
        )

        line = ReplenishmentLine(
            replenishment=replenishment,
            product=self.product,
            quantity=0,
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_negative_quantity_is_not_valid(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
        )

        line = ReplenishmentLine(
            replenishment=replenishment,
            product=self.product,
            quantity=-1,
        )

        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_same_product_cannot_appear_twice(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=5,
        )

        duplicate = ReplenishmentLine(
            replenishment=replenishment,
            product=self.product,
            quantity=10,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()
