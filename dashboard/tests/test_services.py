from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from dashboard.services import (
    _daily_sales,
    _date_range,
    _inventory_summary,
    _percentage_change,
    _top_machines,
    _top_products,
    get_dashboard_data,
)
from inventory.models import Category, Product
from machines.models import Machine
from sales.models import Sale


class DashboardServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Agua",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product_a = Product.objects.create(
            name="VimaAgua",
            category=cls.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        cls.product_b = Product.objects.create(
            name="VimaTea",
            category=cls.category,
            format_unit="250 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        cls.inactive_product = Product.objects.create(
            name="Producto inactivo",
            category=cls.category,
            format_unit="500 ml",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
            is_active=False,
        )

        cls.machine_a = Machine.objects.create(
            identifier="VM-DASH-001",
            name="Máquina dashboard A",
            serial_number="SN-DASH-001",
            rows=4,
            columns=4,
        )

        cls.machine_b = Machine.objects.create(
            identifier="VM-DASH-002",
            name="Máquina dashboard B",
            serial_number="SN-DASH-002",
            rows=4,
            columns=4,
        )

    def make_datetime(self, day, hour=12):
        return timezone.make_aware(
            datetime.combine(
                day,
                time(hour=hour),
            )
        )

    def create_sale(
        self,
        *,
        day,
        quantity=1,
        amount_received="1.50",
        product=None,
        machine=None,
        status=Sale.Status.RESOLVED,
        event_id=None,
        conflicts_with=None,
    ):
        product = self.product_a if product is None else product
        machine = self.machine_a if machine is None else machine

        return Sale.objects.create(
            source=Sale.Source.MANUAL,
            event_id=event_id,
            machine_identifier=machine.identifier,
            machine=machine,
            selection="",
            product=product,
            occurred_at=self.make_datetime(day),
            quantity=quantity,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal(amount_received),
            payment_method="cash",
            status=status,
            raw_payload=None,
            conflicts_with=conflicts_with,
        )

    def test_date_range_includes_requested_number_of_days(self):
        start_date, end_date = _date_range(
            date(2026, 9, 8),
            7,
        )

        self.assertEqual(
            start_date,
            date(2026, 9, 2),
        )
        self.assertEqual(
            end_date,
            date(2026, 9, 8),
        )

    def test_percentage_change(self):
        self.assertEqual(
            _percentage_change(15, 10),
            Decimal("50.0"),
        )

        self.assertEqual(
            _percentage_change(5, 10),
            Decimal("-50.0"),
        )

    def test_percentage_change_without_previous_data(self):
        self.assertIsNone(_percentage_change(10, 0))

    def test_daily_sales_returns_every_day_in_period(self):
        start_date = date(2026, 9, 2)
        end_date = date(2026, 9, 8)

        self.create_sale(
            day=start_date,
            quantity=2,
            amount_received="3.00",
        )

        self.create_sale(
            day=end_date,
            quantity=3,
            amount_received="4.50",
        )

        result = _daily_sales(
            start_date,
            end_date,
        )

        self.assertEqual(
            len(result),
            7,
        )

        self.assertEqual(
            result[0]["date"],
            start_date,
        )
        self.assertEqual(
            result[0]["units"],
            2,
        )
        self.assertEqual(
            result[0]["revenue"],
            Decimal("3.00"),
        )

        self.assertEqual(
            result[1]["units"],
            0,
        )
        self.assertEqual(
            result[1]["revenue"],
            Decimal("0.00"),
        )

        self.assertEqual(
            result[-1]["units"],
            3,
        )

    def test_daily_sales_only_uses_resolved_sales(self):
        day = date(2026, 9, 8)

        self.create_sale(
            day=day,
            quantity=2,
            amount_received="3.00",
        )

        self.create_sale(
            day=day,
            quantity=50,
            amount_received="75.00",
            status=Sale.Status.PENDING,
        )

        result = _daily_sales(
            day,
            day,
        )

        self.assertEqual(
            result[0]["units"],
            2,
        )
        self.assertEqual(
            result[0]["revenue"],
            Decimal("3.00"),
        )

    def test_top_products_are_ordered_by_units(self):
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 8)

        self.create_sale(
            day=date(2026, 9, 4),
            product=self.product_a,
            quantity=5,
        )

        self.create_sale(
            day=date(2026, 9, 5),
            product=self.product_b,
            quantity=3,
        )

        self.create_sale(
            day=date(2026, 9, 5),
            product=self.product_b,
            quantity=100,
            status=Sale.Status.PENDING,
        )

        result = _top_products(
            start_date,
            end_date,
        )

        self.assertEqual(
            len(result),
            2,
        )

        self.assertEqual(
            result[0]["product_id"],
            self.product_a.pk,
        )
        self.assertEqual(
            result[0]["units"],
            5,
        )

        self.assertEqual(
            result[1]["product_id"],
            self.product_b.pk,
        )
        self.assertEqual(
            result[1]["units"],
            3,
        )

    def test_top_machines_are_ordered_by_units(self):
        start_date = date(2026, 9, 1)
        end_date = date(2026, 9, 8)

        self.create_sale(
            day=date(2026, 9, 4),
            machine=self.machine_a,
            quantity=6,
        )

        self.create_sale(
            day=date(2026, 9, 5),
            machine=self.machine_b,
            quantity=2,
        )

        result = _top_machines(
            start_date,
            end_date,
        )

        self.assertEqual(
            len(result),
            2,
        )

        self.assertEqual(
            result[0]["machine_id"],
            self.machine_a.pk,
        )
        self.assertEqual(
            result[0]["units"],
            6,
        )

        self.assertEqual(
            result[1]["machine_id"],
            self.machine_b.pk,
        )
        self.assertEqual(
            result[1]["units"],
            2,
        )

    def test_inventory_summary_uses_only_active_products(self):
        total_stock = {
            self.product_a.pk: 10,
            self.product_b.pk: 20,
        }
        warehouse_stock = {
            self.product_a.pk: 6,
            self.product_b.pk: 12,
        }
        machine_stock = {
            self.product_a.pk: 4,
            self.product_b.pk: 8,
        }
        inventory_value = {
            self.product_a.pk: Decimal("12.50"),
            self.product_b.pk: Decimal("7.50"),
        }
        potential_value = {
            self.product_a.pk: Decimal("30.00"),
            self.product_b.pk: Decimal("40.00"),
        }

        with (
            patch(
                "dashboard.services.get_total_stock",
                side_effect=lambda product: total_stock[product.pk],
            ) as mock_total,
            patch(
                "dashboard.services.get_warehouse_stock",
                side_effect=lambda product: warehouse_stock[product.pk],
            ),
            patch(
                "dashboard.services.get_machines_stock",
                side_effect=lambda product: machine_stock[product.pk],
            ),
            patch(
                "dashboard.services.get_inventory_cost_value",
                side_effect=lambda product: inventory_value[product.pk],
            ),
            patch(
                "dashboard.services.get_potential_sale_value",
                side_effect=lambda product: potential_value[product.pk],
            ),
        ):
            result = _inventory_summary()

        self.assertEqual(
            result["total_units"],
            30,
        )
        self.assertEqual(
            result["warehouse_units"],
            18,
        )
        self.assertEqual(
            result["machine_units"],
            12,
        )
        self.assertEqual(
            result["inventory_value"],
            Decimal("20.00"),
        )
        self.assertEqual(
            result["potential_sale_value"],
            Decimal("70.00"),
        )

        self.assertEqual(
            mock_total.call_count,
            2,
        )

    def test_dashboard_data_calculates_week_metrics(self):
        today = date(2026, 9, 8)

        self.create_sale(
            day=date(2026, 9, 7),
            quantity=2,
            amount_received="3.00",
        )

        self.create_sale(
            day=today,
            quantity=3,
            amount_received="4.50",
        )

        self.create_sale(
            day=date(2026, 9, 1),
            quantity=2,
            amount_received="3.00",
        )

        inventory = {
            "total_units": 30,
            "warehouse_units": 20,
            "machine_units": 10,
            "inventory_value": Decimal("25.00"),
            "potential_sale_value": Decimal("60.00"),
        }

        with patch(
            "dashboard.services._inventory_summary",
            return_value=inventory,
        ):
            result = get_dashboard_data(
                today=today,
            )

        self.assertEqual(
            result["today_units"],
            3,
        )
        self.assertEqual(
            result["week_units"],
            5,
        )
        self.assertEqual(
            result["week_revenue"],
            Decimal("7.50"),
        )
        self.assertEqual(
            result["week_start"],
            date(2026, 9, 2),
        )
        self.assertEqual(
            result["week_end"],
            today,
        )
        self.assertEqual(
            result["week_units_change"],
            Decimal("150.0"),
        )

        self.assertEqual(
            len(result["daily_sales"]),
            7,
        )

        self.assertEqual(
            result["daily_sales"][-1]["units_percent"],
            100,
        )

        self.assertEqual(
            result["max_revenue"],
            Decimal("4.50"),
        )

    def test_dashboard_counts_pending_and_conflict_groups(self):
        today = date(2026, 9, 8)

        self.create_sale(
            day=today,
            status=Sale.Status.PENDING,
        )

        self.create_sale(
            day=today,
            status=Sale.Status.PENDING,
        )

        reference_sale = self.create_sale(
            day=date(2026, 1, 1),
            event_id="evt-dashboard-conflict",
        )

        self.create_sale(
            day=today,
            status=Sale.Status.CONFLICT,
            event_id="evt-dashboard-conflict",
            conflicts_with=reference_sale,
        )

        inventory = {
            "total_units": 0,
            "warehouse_units": 0,
            "machine_units": 0,
            "inventory_value": Decimal("0.00"),
            "potential_sale_value": Decimal("0.00"),
        }

        with patch(
            "dashboard.services._inventory_summary",
            return_value=inventory,
        ):
            result = get_dashboard_data(
                today=today,
            )

        self.assertEqual(
            result["pending_sales"],
            2,
        )
        self.assertEqual(
            result["conflict_sales"],
            1,
        )

        self.assertEqual(
            result["active_incidents"],
            2,
        )
