from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import Machine, MachineLayout, MachinePosition
from machines.services.layouts import activate_machine_layout
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale
from sales.services import get_sales_projection


class SalesProjectionFixtures:
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas proyección",
            default_vat_rate=Decimal("21.00"),
        )
        self.product = Product.objects.create(
            name="Agua proyección",
            category=self.category,
            format_unit="500 ml",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
        )
        self.machine = self.make_machine("1")

    def aware(self, year, month, day, hour=12):
        return timezone.make_aware(datetime(year, month, day, hour))

    def make_machine(self, suffix):
        return Machine.objects.create(
            identifier=f"VM-PROJECTION-{suffix}",
            name=f"Máquina proyección {suffix}",
            serial_number=f"SN-PROJECTION-{suffix}",
            rows=2,
            columns=2,
        )

    def activate_product(self, machine, product=None):
        layout = MachineLayout.objects.create(
            machine=machine,
            name="Actual",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=product or self.product,
        )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save()

        activation_time = self.aware(2026, 8, 1)

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(layout)

    def make_sale(
        self,
        quantity,
        occurred_at,
        machine=None,
        status=Sale.Status.RESOLVED,
    ):
        machine = machine or self.machine
        extra_fields = {}

        if status == Sale.Status.CONFLICT:
            extra_fields["conflicts_with"] = Sale.objects.filter(
                status=Sale.Status.RESOLVED
            ).first()

        if status == Sale.Status.VOIDED:
            extra_fields.update(
                void_reason="Prueba",
                voided_at=occurred_at,
            )

        return Sale.objects.create(
            source=Sale.Source.MANUAL,
            machine_identifier=machine.identifier,
            machine=machine,
            product=self.product,
            occurred_at=occurred_at,
            quantity=quantity,
            dispense_type=Sale.DispenseType.PAID,
            status=status,
            **extra_fields,
        )

    def add_purchase(self, quantity):
        purchase = Purchase.objects.create(
            supplier="Proveedor proyección",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=quantity,
            unit_price_excl_vat=Decimal("0.50"),
        )

    def replenish(self, machine, quantity):
        replenishment = Replenishment.objects.create(
            machine=machine,
            replenished_at=self.aware(2026, 8, 1),
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=quantity,
        )

    def calculate(self):
        projections = get_sales_projection(
            date(2026, 8, 1),
            date(2026, 8, 7),
            date(2026, 8, 8),
            date(2026, 8, 14),
        )

        return projections[0]


class SalesProjectionTests(SalesProjectionFixtures, TestCase):
    def test_aggregates_machine_needs_before_calculating_purchase(self):
        machine_two = self.make_machine("2")

        self.activate_product(self.machine)
        self.activate_product(machine_two)

        self.add_purchase(22)

        self.replenish(self.machine, 10)
        self.replenish(machine_two, 7)

        self.make_sale(
            10,
            self.aware(2026, 8, 3),
        )
        self.make_sale(
            5,
            self.aware(2026, 8, 4),
            machine=machine_two,
        )

        item = self.calculate()

        self.assertEqual(
            item["historical_sales"],
            15,
        )
        self.assertEqual(
            item["daily_average"],
            Decimal(15) / Decimal(7),
        )
        self.assertEqual(
            item["estimated_consumption"],
            15,
        )
        self.assertEqual(
            item["total_stock"],
            7,
        )
        self.assertEqual(
            item["warehouse_stock"],
            5,
        )
        self.assertEqual(
            item["total_machine_need"],
            13,
        )
        self.assertEqual(
            item["suggested_purchase"],
            8,
        )
        self.assertEqual(
            [detail["machine_need"] for detail in item["machine_details"]],
            [10, 3],
        )

    def test_date_ranges_are_inclusive_and_quantity_counts_units(self):
        self.activate_product(self.machine)

        self.make_sale(
            2,
            self.aware(2026, 8, 1, 0),
        )
        self.make_sale(
            3,
            self.aware(2026, 8, 7, 23),
        )
        self.make_sale(
            9,
            self.aware(2026, 8, 8, 0),
        )

        item = self.calculate()

        self.assertEqual(
            item["historical_sales"],
            5,
        )
        self.assertEqual(
            item["estimated_consumption"],
            5,
        )

    def test_only_resolved_sales_are_used(self):
        self.activate_product(self.machine)

        self.make_sale(
            2,
            self.aware(2026, 8, 2),
        )

        excluded_statuses = (
            Sale.Status.PENDING,
            Sale.Status.CONFLICT,
            Sale.Status.REJECTED,
            Sale.Status.VOIDED,
        )

        for status in excluded_statuses:
            self.make_sale(
                7,
                self.aware(2026, 8, 3),
                status=status,
            )

        item = self.calculate()

        self.assertEqual(
            item["historical_sales"],
            2,
        )

    def test_historical_pair_outside_active_layout_has_no_current_need(self):
        self.make_sale(
            7,
            self.aware(2026, 8, 3),
        )

        item = self.calculate()
        detail = item["machine_details"][0]

        self.assertEqual(
            detail["estimated_consumption"],
            7,
        )
        self.assertFalse(detail["is_in_active_layout"])
        self.assertEqual(
            detail["machine_need"],
            0,
        )
        self.assertEqual(
            item["estimated_consumption"],
            0,
        )
        self.assertEqual(
            item["suggested_purchase"],
            0,
        )

    def test_negative_machine_stock_is_an_incident_and_counts_as_zero(self):
        self.activate_product(self.machine)

        self.make_sale(
            1,
            self.aware(2026, 8, 3),
        )

        item = self.calculate()
        detail = item["machine_details"][0]

        self.assertEqual(
            detail["machine_stock"],
            -1,
        )
        self.assertEqual(
            detail["usable_machine_stock"],
            0,
        )
        self.assertTrue(detail["has_stock_incident"])
        self.assertEqual(
            detail["estimated_consumption"],
            1,
        )
        self.assertEqual(
            detail["machine_need"],
            1,
        )
        self.assertEqual(
            item["suggested_purchase"],
            1,
        )

    def test_inconsistent_negative_warehouse_stock_is_treated_as_zero(self):
        self.activate_product(self.machine)

        self.replenish(
            self.machine,
            1,
        )
        self.make_sale(
            1,
            self.aware(2026, 8, 3),
        )

        item = self.calculate()

        self.assertEqual(
            item["warehouse_stock"],
            -1,
        )
        self.assertEqual(
            item["usable_warehouse_stock"],
            0,
        )
        self.assertEqual(
            item["total_machine_need"],
            1,
        )
        self.assertEqual(
            item["suggested_purchase"],
            1,
        )

    def test_projection_does_not_modify_inventory_data(self):
        self.activate_product(self.machine)
        self.add_purchase(5)

        self.make_sale(
            2,
            self.aware(2026, 8, 2),
        )

        counts_before = (
            Sale.objects.count(),
            PurchaseLine.objects.count(),
        )

        self.calculate()

        counts_after = (
            Sale.objects.count(),
            PurchaseLine.objects.count(),
        )

        self.assertEqual(
            counts_after,
            counts_before,
        )

    def test_rejects_reversed_periods(self):
        with self.assertRaises(ValueError):
            get_sales_projection(
                date(2026, 8, 7),
                date(2026, 8, 1),
                date(2026, 8, 8),
                date(2026, 8, 14),
            )


class SalesProjectionViewTests(SalesProjectionFixtures, TestCase):
    def test_calendar_mode_uses_both_inclusive_intervals(self):
        self.activate_product(self.machine)

        self.make_sale(
            8,
            self.aware(2026, 8, 4),
        )

        params = {
            "mode": "dates",
            "history_start": "2026-08-03",
            "history_end": "2026-08-06",
            "forecast_start": "2026-08-07",
            "forecast_end": "2026-08-15",
        }

        response = self.client.get(
            reverse("sales:sales_projection"),
            params,
        )

        item = response.context["projections"][0]

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            response.context["periods"]["history_days"],
            4,
        )
        self.assertEqual(
            response.context["periods"]["forecast_days"],
            9,
        )
        self.assertEqual(
            item["daily_average"],
            Decimal("2"),
        )
        self.assertEqual(
            item["estimated_consumption"],
            18,
        )

    def test_product_detail_preserves_projection_and_lists_machines(self):
        self.activate_product(self.machine)

        self.make_sale(
            7,
            self.aware(2026, 8, 3),
        )

        params = {
            "mode": "dates",
            "history_start": "2026-08-01",
            "history_end": "2026-08-07",
            "forecast_start": "2026-08-08",
            "forecast_end": "2026-08-14",
        }

        response = self.client.get(
            reverse(
                "sales:sales_projection_detail",
                args=[self.product.pk],
            ),
            params,
        )

        projection = response.context["projection"]

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            projection["historical_sales"],
            7,
        )
        self.assertEqual(
            len(projection["machine_details"]),
            1,
        )
        self.assertEqual(
            response.context["sales_history_query"],
            (
                f"product={self.product.pk}"
                "&date_from=2026-08-01T00%3A00"
                "&date_to=2026-08-07T23%3A59"
            ),
        )
        self.assertContains(
            response,
            reverse(
                "inventory:product_detail",
                args=[self.product.pk],
            ),
        )

    def test_invalid_calendar_range_is_shown_as_form_error(self):
        params = {
            "mode": "dates",
            "history_start": "2026-08-07",
            "history_end": "2026-08-01",
            "forecast_start": "2026-08-08",
            "forecast_end": "2026-08-14",
        }

        response = self.client.get(
            reverse("sales:sales_projection"),
            params,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(
            response.context["projections"],
            [],
        )
