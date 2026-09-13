from decimal import Decimal

from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from dashboard.views import dashboard_home
from inventory.models import Category, Product
from machines.models import Machine
from sales.models import Sale


class DashboardViewTests(TestCase):
    def test_dashboard_access(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "dashboard/home.html",
        )

    def test_dashboard_url_resolves_dashboard_view(self):
        match = resolve(reverse("dashboard:home"))

        self.assertEqual(
            match.func,
            dashboard_home,
        )

    def test_dashboard_shows_main_sections(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(
            response,
            "Resumen del negocio",
        )
        self.assertContains(
            response,
            "Tendencia de ventas",
        )
        self.assertContains(
            response,
            "Tendencia de ingresos",
        )
        self.assertContains(
            response,
            "Productos más vendidos",
        )
        self.assertContains(
            response,
            "Máquinas con más ventas",
        )

    def test_dashboard_loads_own_stylesheet(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(
            response,
            static("dashboard/css/dashboard.css"),
        )

    def test_dashboard_stylesheet_exists(self):
        stylesheet = finders.find("dashboard/css/dashboard.css")

        self.assertIsNotNone(stylesheet)

    def test_dashboard_context_contains_expected_data(self):
        response = self.client.get(reverse("dashboard:home"))

        expected_keys = (
            "today_units",
            "week_units",
            "week_revenue",
            "week_start",
            "week_end",
            "week_units_change",
            "daily_sales",
            "top_products",
            "top_machines",
            "inventory",
            "pending_sales",
            "conflict_sales",
            "active_incidents",
            "inventory_value",
            "potential_sale_value",
            "stock_total",
        )

        for key in expected_keys:
            self.assertIn(
                key,
                response.context,
            )


class DashboardRankingViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Agua dashboard",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="VimaAgua",
            category=cls.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-DASH-VIEW-001",
            name="Máquina dashboard",
            serial_number="SN-DASH-VIEW-001",
            rows=4,
            columns=4,
        )

        cls.sale = Sale.objects.create(
            source=Sale.Source.MANUAL,
            event_id=None,
            machine_identifier=cls.machine.identifier,
            machine=cls.machine,
            selection="",
            product=cls.product,
            occurred_at=timezone.now(),
            quantity=4,
            dispense_type=Sale.DispenseType.PAID,
            unit_price=Decimal("1.50"),
            amount_received=Decimal("6.00"),
            payment_method="cash",
            status=Sale.Status.RESOLVED,
            raw_payload=None,
        )

    def test_product_ranking_links_to_product_detail(self):
        response = self.client.get(reverse("dashboard:home"))

        product_url = reverse(
            "inventory:product_detail",
            args=[self.product.pk],
        )

        self.assertContains(
            response,
            f'data-href="{product_url}"',
        )

        self.assertContains(
            response,
            "VimaAgua",
        )

    def test_machine_ranking_links_to_machine_detail(self):
        response = self.client.get(reverse("dashboard:home"))

        machine_url = reverse(
            "machines:machine_detail",
            args=[self.machine.pk],
        )

        self.assertContains(
            response,
            f'data-href="{machine_url}"',
        )

        self.assertContains(
            response,
            "VM-DASH-VIEW-001",
        )
