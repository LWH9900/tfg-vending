from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_warehouse_stock,
)
from machines.models import Machine
from purchases.models import Purchase, PurchaseLine
from replenishments.forms import ReplenishmentLineFormSet
from replenishments.models import Replenishment, ReplenishmentLine


class ReplenishmentViewTests(TestCase):
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

        cls.machine = Machine.objects.create(
            identifier="M-001",
            name="Máquina 1",
            serial_number="SN-001",
        )

        cls.second_machine = Machine.objects.create(
            identifier="M-002",
            name="Máquina 2",
            serial_number="SN-002",
        )

    def replenishment_post_data(self, lines, machine=None):
        prefix = ReplenishmentLineFormSet.get_default_prefix()

        machine = machine or self.machine

        data = {
            "replenished_at": "2026-08-26T10:30",
            "machine": str(machine.pk),
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
                }
            )

        return data

    def create_registered_purchase(
        self,
        product,
        quantity,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=product,
            quantity=quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )

        return purchase

    def create_draft_replenishment(
        self,
        product,
        quantity,
        machine=None,
    ):
        machine = machine or self.machine

        replenishment = Replenishment.objects.create(
            machine=machine,
            status=Replenishment.Status.DRAFT,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=quantity,
        )

        return replenishment

    def test_create_replenishment_with_one_line(self):
        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                    }
                ]
            ),
        )

        replenishment = Replenishment.objects.get()

        self.assertRedirects(
            response,
            reverse(
                "replenishments:replenishment_detail",
                args=[replenishment.pk],
            ),
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            replenishment.machine,
            self.machine,
        )

        self.assertEqual(
            replenishment.lines.count(),
            1,
        )

        line = replenishment.lines.get()

        self.assertEqual(
            line.product,
            self.product,
        )

        self.assertEqual(
            line.quantity,
            10,
        )

    def test_create_replenishment_with_multiple_lines(self):
        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                    },
                    {
                        "product": self.second_product,
                        "quantity": 5,
                    },
                ]
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        replenishment = Replenishment.objects.get()

        self.assertEqual(
            replenishment.lines.count(),
            2,
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

    def test_replenishment_cannot_be_created_without_lines(self):
        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data([]),
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

        self.assertTrue(formset.non_form_errors())

    def test_invalid_line_does_not_create_partial_replenishment(self):
        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 0,
                    }
                ]
            ),
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
            "quantity",
            formset.forms[0].errors,
        )

    def test_same_product_cannot_be_added_twice(self):
        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                    },
                    {
                        "product": self.product,
                        "quantity": 20,
                    },
                ]
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            Replenishment.objects.count(),
            0,
        )

        formset = response.context["formset"]

        self.assertIn(
            "product",
            formset.forms[1].errors,
        )

        self.assertIn(
            "Este producto ya está incluido en la reposición.",
            formset.forms[1].errors["product"],
        )

    def test_nonexistent_machine_does_not_create_replenishment(self):
        data = self.replenishment_post_data(
            [
                {
                    "product": self.product,
                    "quantity": 10,
                }
            ]
        )

        data["machine"] = "999999"

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

        self.assertIn(
            "machine",
            response.context["form"].errors,
        )

    def test_nonexistent_product_does_not_create_replenishment(self):
        prefix = ReplenishmentLineFormSet.get_default_prefix()

        data = self.replenishment_post_data(
            [
                {
                    "product": self.product,
                    "quantity": 10,
                }
            ]
        )

        data[f"{prefix}-0-product"] = "999999"

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

        formset = response.context["formset"]

        self.assertIn(
            "product",
            formset.forms[0].errors,
        )

    def test_replenishment_detail_shows_all_lines(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=10,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.second_product,
            quantity=5,
        )

        response = self.client.get(
            reverse(
                "replenishments:replenishment_detail",
                args=[replenishment.pk],
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
            self.machine.identifier,
        )

    def test_filter_replenishments_by_machine(self):
        first = Replenishment.objects.create(
            machine=self.machine,
        )

        Replenishment.objects.create(
            machine=self.second_machine,
        )

        response = self.client.get(
            reverse("replenishments:replenishment_list"),
            {
                "machine": self.machine.pk,
            },
        )

        replenishments = list(response.context["replenishments"])

        self.assertEqual(
            replenishments,
            [first],
        )

    def test_filter_replenishments_by_product(self):
        first = self.create_draft_replenishment(
            self.product,
            10,
        )

        self.create_draft_replenishment(
            self.second_product,
            10,
            self.second_machine,
        )

        response = self.client.get(
            reverse("replenishments:replenishment_list"),
            {
                "product": self.product.pk,
            },
        )

        replenishments = list(response.context["replenishments"])

        self.assertEqual(
            replenishments,
            [first],
        )

    def test_filter_replenishments_by_status(self):
        draft = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.DRAFT,
        )

        registered = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        response = self.client.get(
            reverse("replenishments:replenishment_list"),
            {
                "status": Replenishment.Status.REGISTERED,
            },
        )

        replenishments = list(response.context["replenishments"])

        self.assertEqual(
            replenishments,
            [registered],
        )

        self.assertNotIn(
            draft,
            replenishments,
        )

    def test_filter_replenishments_by_date_range(self):
        now = timezone.now()

        old_replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=now - timedelta(days=20),
        )

        expected_replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=now - timedelta(days=5),
        )

        future_replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=now,
        )

        response = self.client.get(
            reverse("replenishments:replenishment_list"),
            {
                "date_from": (now - timedelta(days=10)).date().isoformat(),
                "date_to": (now - timedelta(days=2)).date().isoformat(),
            },
        )

        replenishments = list(response.context["replenishments"])

        self.assertEqual(
            replenishments,
            [expected_replenishment],
        )

        self.assertNotIn(
            old_replenishment,
            replenishments,
        )

        self.assertNotIn(
            future_replenishment,
            replenishments,
        )

    def test_draft_replenishment_can_be_edited(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.DRAFT,
        )

        response = self.client.get(
            reverse(
                "replenishments:replenishment_edit",
                args=[replenishment.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_registered_replenishment_cannot_be_edited(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        response = self.client.get(
            reverse(
                "replenishments:replenishment_edit",
                args=[replenishment.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_draft_replenishment_can_be_deleted(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.DRAFT,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_delete",
                args=[replenishment.pk],
            )
        )

        self.assertRedirects(
            response,
            reverse("replenishments:replenishment_list"),
        )

        self.assertFalse(Replenishment.objects.filter(pk=replenishment.pk).exists())

    def test_registered_replenishment_cannot_be_deleted(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_delete",
                args=[replenishment.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertTrue(Replenishment.objects.filter(pk=replenishment.pk).exists())

    def test_registered_replenishment_can_be_cancelled(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_cancel",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                "replenishments:replenishment_detail",
                args=[replenishment.pk],
            ),
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.CANCELLED,
        )

    def test_cancelled_replenishment_cannot_be_registered(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.CANCELLED,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.CANCELLED,
        )

    def test_cancelled_replenishment_cannot_be_cancelled_again(self):
        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.CANCELLED,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_cancel",
                args=[replenishment.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_replenishment_below_available_stock_can_be_registered(self):
        self.create_registered_purchase(
            self.product,
            10,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            5,
        )

        self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.REGISTERED,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            5,
        )

    def test_replenishment_equal_to_available_stock_can_be_registered(self):
        self.create_registered_purchase(
            self.product,
            10,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            10,
        )

        self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.REGISTERED,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            0,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            10,
        )

    def test_replenishment_above_available_stock_cannot_be_registered(self):
        self.create_registered_purchase(
            self.product,
            10,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            11,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

    def test_draft_can_be_saved_with_insufficient_stock(self):
        self.create_registered_purchase(
            self.product,
            5,
        )

        response = self.client.post(
            reverse("replenishments:replenishment_create"),
            self.replenishment_post_data(
                [
                    {
                        "product": self.product,
                        "quantity": 10,
                    }
                ]
            ),
        )

        replenishment = Replenishment.objects.get()

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

    def test_multiline_replenishment_is_not_partially_registered_without_stock(
        self,
    ):
        self.create_registered_purchase(
            self.product,
            20,
        )

        self.create_registered_purchase(
            self.second_product,
            5,
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.DRAFT,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=10,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.second_product,
            quantity=8,
        )

        self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            20,
        )

        self.assertEqual(
            get_warehouse_stock(self.second_product),
            5,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

        self.assertEqual(
            get_machine_stock(
                self.second_product,
                self.machine,
            ),
            0,
        )
