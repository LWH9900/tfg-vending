from concurrent.futures import ThreadPoolExecutor
from datetime import (
    datetime,
    timedelta,
)
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections
from django.db.models.query import QuerySet
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_warehouse_stock,
)
from machines.models import Machine, MachineLayout, MachinePosition
from machines.services.layouts import activate_machine_layout
from purchases.models import Purchase, PurchaseLine
from replenishments.forms import ReplenishmentLineFormSet
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale


class ReplenishmentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="VimaCola",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.50"),
        )

        cls.second_product = Product.objects.create(
            name="VimaTea",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.70"),
        )

        cls.machine = Machine.objects.create(
            identifier="M-001",
            name="Máquina 1",
            serial_number="SN-001",
            rows=2,
            columns=2,
        )

        cls.second_machine = Machine.objects.create(
            identifier="M-002",
            name="Máquina 2",
            serial_number="SN-002",
        )
        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Disposición inicial",
        )

        MachinePosition.objects.create(
            layout=cls.layout,
            identifier="A1",
            row=1,
            column=1,
            product=cls.product,
        )

        MachinePosition.objects.create(
            layout=cls.layout,
            identifier="A2",
            row=1,
            column=2,
            product=cls.second_product,
        )

        cls.layout.status = MachineLayout.Status.REGISTERED
        cls.layout.save()

        activation_time = timezone.make_aware(
            datetime(
                2026,
                8,
                25,
                8,
                0,
            )
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(cls.layout)

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

    def test_create_replenishment_prefills_machine_from_query_string(self):
        response = self.client.get(
            reverse("replenishments:replenishment_create"),
            {"machine": self.second_machine.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].initial["machine"],
            self.second_machine,
        )

    def test_create_replenishment_marks_products_active_in_machine_layout(self):
        response = self.client.get(
            reverse("replenishments:replenishment_create"),
            {"machine": self.machine.pk},
        )

        self.assertEqual(response.status_code, 200)
        labels = [
            str(label)
            for value, label in response.context["formset"]
            .empty_form.fields["product"]
            .choices
        ]
        self.assertTrue(
            any("VimaCola" in label and "· Activo" in label for label in labels)
        )

    def test_create_replenishment_does_not_mark_products_without_active_layout(self):
        response = self.client.get(
            reverse("replenishments:replenishment_create"),
            {"machine": self.second_machine.pk},
        )

        self.assertEqual(response.status_code, 200)
        labels = [
            str(label)
            for value, label in response.context["formset"]
            .empty_form.fields["product"]
            .choices
        ]
        self.assertFalse(any("· Activo" in label for label in labels))

    def test_active_products_endpoint_respects_layout_history(self):
        second_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Segunda disposición",
        )

        MachinePosition.objects.create(
            layout=second_layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.second_product,
        )

        second_layout.status = MachineLayout.Status.REGISTERED
        second_layout.save()

        second_activation_time = timezone.make_aware(
            datetime(
                2026,
                8,
                25,
                12,
                0,
            )
        )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation_time,
        ):
            activate_machine_layout(second_layout)

        response_before_change = self.client.get(
            reverse(
                "replenishments:active_products",
                args=[self.machine.pk],
            ),
            {
                "moment": "2026-08-25T10:30",
            },
        )

        response_after_change = self.client.get(
            reverse(
                "replenishments:active_products",
                args=[self.machine.pk],
            ),
            {
                "moment": "2026-08-25T13:00",
            },
        )

        self.assertEqual(
            response_before_change.status_code,
            200,
        )

        self.assertEqual(
            response_after_change.status_code,
            200,
        )

        self.assertEqual(
            set(response_before_change.json()["product_ids"]),
            {
                self.product.pk,
                self.second_product.pk,
            },
        )

        self.assertEqual(
            set(response_after_change.json()["product_ids"]),
            {
                self.second_product.pk,
            },
        )

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
            "VimaCola",
        )

        self.assertContains(
            response,
            "VimaTea",
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
        self.create_registered_purchase(
            self.product,
            5,
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=5,
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

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            5,
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

    def test_replenishment_cannot_be_registered_when_warehouse_stock_is_negative(self):
        self.create_registered_purchase(
            self.product,
            5,
        )

        existing_replenishment = self.create_draft_replenishment(
            self.product,
            6,
        )
        existing_replenishment.status = Replenishment.Status.REGISTERED
        existing_replenishment.save(update_fields=["status"])

        replenishment = self.create_draft_replenishment(
            self.product,
            1,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[replenishment.pk],
            )
        )

        replenishment.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(replenishment.status, Replenishment.Status.DRAFT)
        self.assertEqual(get_warehouse_stock(self.product), -1)

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

    def test_product_outside_historical_layout_cannot_be_registered(
        self,
    ):
        outside_product = Product.objects.create(
            name="VimaOutside",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.00"),
        )

        self.create_registered_purchase(
            outside_product,
            10,
        )

        replenishment = self.create_draft_replenishment(
            outside_product,
            5,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[
                    replenishment.pk,
                ],
            )
        )

        replenishment.refresh_from_db()

        self.assertRedirects(
            response,
            (
                reverse(
                    "replenishments:replenishment_detail",
                    args=[
                        replenishment.pk,
                    ],
                )
                + "?layout_error=1"
            ),
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            get_warehouse_stock(outside_product),
            10,
        )

        self.assertEqual(
            get_machine_stock(
                outside_product,
                self.machine,
            ),
            0,
        )

    def test_stock_and_layout_warnings_share_a_single_alert(self):
        outside_product = Product.objects.create(
            name="VimaOutsideNoStock",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.00"),
        )

        replenishment = self.create_draft_replenishment(
            outside_product,
            2,
        )

        response = self.client.get(
            reverse(
                "replenishments:replenishment_detail",
                args=[replenishment.pk],
            )
        )

        self.assertContains(
            response,
            "El borrador contiene cantidades superiores",
        )
        self.assertContains(
            response,
            "compatibles con la disposición histórica",
        )
        self.assertContains(
            response,
            "alert-warning",
            count=1,
        )

    def test_replenishment_without_historical_layout_cannot_be_registered(
        self,
    ):
        self.create_registered_purchase(
            self.product,
            10,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            5,
            machine=self.second_machine,
        )

        response = self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[
                    replenishment.pk,
                ],
            )
        )

        replenishment.refresh_from_db()

        self.assertRedirects(
            response,
            (
                reverse(
                    "replenishments:replenishment_detail",
                    args=[
                        replenishment.pk,
                    ],
                )
                + "?layout_error=1"
            ),
        )

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.second_machine,
            ),
            0,
        )

    def test_replenishment_uses_layout_active_at_replenished_at(
        self,
    ):
        later_product = Product.objects.create(
            name="VimaLater",
            category=self.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.00"),
        )

        later_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición posterior",
        )

        MachinePosition.objects.create(
            layout=later_layout,
            identifier="B1",
            row=1,
            column=1,
            product=later_product,
        )

        later_layout.status = MachineLayout.Status.REGISTERED
        later_layout.save()

        later_activation_time = timezone.make_aware(
            datetime(
                2026,
                9,
                1,
                8,
                0,
            )
        )

        with patch(
            "django.utils.timezone.now",
            return_value=(later_activation_time),
        ):
            activate_machine_layout(later_layout)

        self.create_registered_purchase(
            self.product,
            10,
        )

        historical_replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=(
                timezone.make_aware(
                    datetime(
                        2026,
                        8,
                        26,
                        10,
                        30,
                    )
                )
            ),
            status=(Replenishment.Status.DRAFT),
        )

        ReplenishmentLine.objects.create(
            replenishment=(historical_replenishment),
            product=self.product,
            quantity=5,
        )

        self.client.post(
            reverse(
                "replenishments:replenishment_register",
                args=[
                    historical_replenishment.pk,
                ],
            )
        )

        historical_replenishment.refresh_from_db()

        self.assertEqual(
            historical_replenishment.status,
            Replenishment.Status.REGISTERED,
        )

    def test_active_products_endpoint_uses_requested_moment(self):
        response = self.client.get(
            reverse(
                "replenishments:active_products",
                args=[self.machine.pk],
            ),
            {"moment": "2026-08-26T10:30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.product.pk, response.json()["product_ids"])

    def test_replenishment_can_register_when_it_corrects_negative_machine_stock(
        self,
    ):
        self.create_registered_purchase(
            self.product,
            7,
        )

        existing_replenishment = self.create_draft_replenishment(
            self.product,
            5,
        )
        existing_replenishment.status = Replenishment.Status.REGISTERED
        existing_replenishment.save(
            update_fields=["status"],
        )

        Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            product=self.product,
            occurred_at=timezone.now(),
            quantity=6,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("9.00"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            -1,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            1,
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
            Replenishment.Status.REGISTERED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

    def test_replenishment_can_register_even_if_machine_stock_remains_negative(
        self,
    ):
        self.create_registered_purchase(
            self.product,
            8,
        )

        existing_replenishment = self.create_draft_replenishment(
            self.product,
            5,
        )
        existing_replenishment.status = Replenishment.Status.REGISTERED
        existing_replenishment.save(
            update_fields=["status"],
        )

        Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            product=self.product,
            occurred_at=timezone.now(),
            quantity=7,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("10.50"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            -2,
        )

        replenishment = self.create_draft_replenishment(
            self.product,
            1,
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
            Replenishment.Status.REGISTERED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            -1,
        )
        self.assertEqual(
            replenishment.status,
            Replenishment.Status.REGISTERED,
        )

    def test_replenishment_cannot_be_cancelled_if_machine_stock_would_be_negative(
        self,
    ):
        self.create_registered_purchase(
            self.product,
            5,
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=5,
        )

        Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=self.machine.identifier,
            machine=self.machine,
            product=self.product,
            occurred_at=timezone.now(),
            quantity=4,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("6.00"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
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
            Replenishment.Status.REGISTERED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            1,
        )


class ReplenishmentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas concurrencia reposiciones",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaCola Replenishment Concurrency",
            category=self.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.50"),
        )

        self.machine = Machine.objects.create(
            identifier="M-REPL-CONCURRENCY",
            name="Máquina concurrencia reposiciones",
            serial_number="SN-REPL-CONCURRENCY",
            rows=2,
            columns=2,
        )

        self.layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Disposición concurrencia",
        )

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=1,
            column=1,
            product=self.product,
        )

        self.layout.status = MachineLayout.Status.REGISTERED
        self.layout.save()

        activation_time = timezone.make_aware(
            datetime(
                2026,
                9,
                2,
                9,
                0,
            )
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(self.layout)

        purchase = Purchase.objects.create(
            supplier="Proveedor concurrencia",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment_time = timezone.make_aware(
            datetime(
                2026,
                9,
                2,
                10,
                0,
            )
        )

        self.replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=replenishment_time,
            status=Replenishment.Status.DRAFT,
        )

        ReplenishmentLine.objects.create(
            replenishment=self.replenishment,
            product=self.product,
            quantity=4,
        )

    def test_register_and_delete_cannot_both_win_concurrently(self):
        barrier = Barrier(2)

        original_select_for_update = QuerySet.select_for_update

        def synchronized_select_for_update(
            queryset,
            *args,
            **kwargs,
        ):
            if queryset.model is Replenishment:
                barrier.wait(timeout=5)

            return original_select_for_update(
                queryset,
                *args,
                **kwargs,
            )

        register_url = reverse(
            "replenishments:replenishment_register",
            args=[self.replenishment.pk],
        )

        delete_url = reverse(
            "replenishments:replenishment_delete",
            args=[self.replenishment.pk],
        )

        def worker(url):
            close_old_connections()

            try:
                client = Client()
                response = client.post(url)

                return response.status_code

            finally:
                close_old_connections()

        with patch(
            "django.db.models.query.QuerySet.select_for_update",
            new=synchronized_select_for_update,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                register_future = executor.submit(
                    worker,
                    register_url,
                )

                delete_future = executor.submit(
                    worker,
                    delete_url,
                )

                status_codes = [
                    register_future.result(timeout=10),
                    delete_future.result(timeout=10),
                ]

        self.assertEqual(
            status_codes.count(302),
            1,
        )

        self.assertTrue(any(status_code in (403, 404) for status_code in status_codes))

        replenishment_exists = Replenishment.objects.filter(
            pk=self.replenishment.pk,
        ).exists()

        if replenishment_exists:
            replenishment = Replenishment.objects.get(
                pk=self.replenishment.pk,
            )

            self.assertEqual(
                replenishment.status,
                Replenishment.Status.REGISTERED,
            )

            self.assertEqual(
                get_machine_stock(
                    self.product,
                    self.machine,
                ),
                4,
            )

            self.assertEqual(
                get_warehouse_stock(self.product),
                6,
            )

        else:
            self.assertEqual(
                get_machine_stock(
                    self.product,
                    self.machine,
                ),
                0,
            )

            self.assertEqual(
                get_warehouse_stock(self.product),
                10,
            )
