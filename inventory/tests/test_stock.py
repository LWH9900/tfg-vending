from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from inventory.services import (
    get_inventory_cost_value,
    get_machine_product_stocks,
    get_machine_stock,
    get_product_machine_stocks,
    get_total_stock,
    get_warehouse_stock,
)
from machines.models import Machine
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine


class StockServiceTests(TestCase):
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

        cls.other_product = Product.objects.create(
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

        cls.other_machine = Machine.objects.create(
            identifier="M-002",
            name="Máquina 2",
            serial_number="SN-002",
        )

    def create_purchase(
        self,
        product,
        quantity,
        status=Purchase.Status.REGISTERED,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor",
            status=status,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=product,
            quantity=quantity,
            unit_price_excl_vat=Decimal("1.00"),
        )

        return purchase

    def create_replenishment(
        self,
        product,
        machine,
        quantity,
        status=Replenishment.Status.REGISTERED,
    ):
        replenishment = Replenishment.objects.create(
            machine=machine,
            status=status,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=quantity,
        )

        return replenishment

    def test_product_without_movements_returns_zero(self):
        self.assertEqual(
            get_total_stock(self.product),
            0,
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
            0,
        )

    def test_total_stock_accumulates_multiple_purchases(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_purchase(
            self.product,
            50,
        )

        self.assertEqual(
            get_total_stock(self.product),
            150,
        )

    def test_total_stock_ignores_other_products(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_purchase(
            self.other_product,
            500,
        )

        self.assertEqual(
            get_total_stock(self.product),
            100,
        )

    def test_total_stock_only_counts_registered_purchases(self):
        self.create_purchase(
            self.product,
            100,
            Purchase.Status.REGISTERED,
        )

        self.create_purchase(
            self.product,
            50,
            Purchase.Status.DRAFT,
        )

        self.create_purchase(
            self.product,
            25,
            Purchase.Status.CANCELLED,
        )

        self.assertEqual(
            get_total_stock(self.product),
            100,
        )

    def test_warehouse_stock_is_purchases_minus_replenishments(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            30,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            70,
        )

    def test_warehouse_stock_accumulates_multiple_replenishments(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_purchase(
            self.product,
            50,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            30,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            100,
        )

    def test_warehouse_stock_ignores_non_registered_replenishments(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            20,
            Replenishment.Status.REGISTERED,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            30,
            Replenishment.Status.DRAFT,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            40,
            Replenishment.Status.CANCELLED,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            80,
        )

    def test_warehouse_stock_ignores_other_products(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            50,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            100,
        )

    def test_machine_stock_accumulates_replenishments(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            15,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            35,
        )

    def test_machine_stock_ignores_other_machines(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            50,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            20,
        )

    def test_machine_stock_ignores_other_products(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            100,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            20,
        )

    def test_machine_stock_only_counts_registered_replenishments(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
            Replenishment.Status.REGISTERED,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            30,
            Replenishment.Status.DRAFT,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            40,
            Replenishment.Status.CANCELLED,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            20,
        )

    def test_inventory_cost_value_uses_average_purchase_cost(self):
        self.create_purchase(
            self.product,
            10,
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.product,
            quantity=30,
            unit_price_excl_vat=Decimal("2.00"),
        )

        self.assertEqual(
            get_inventory_cost_value(self.product),
            Decimal("70.00"),
        )

    def test_product_without_purchases_has_zero_inventory_cost_value(self):
        self.assertEqual(
            get_inventory_cost_value(self.product),
            Decimal("0.00"),
        )

    def test_product_machine_stocks_are_grouped_by_machine(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            15,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            10,
        )

        machine_stocks = list(get_product_machine_stocks(self.product))

        self.assertEqual(
            len(machine_stocks),
            2,
        )

        stocks = {machine.pk: machine.product_stock for machine in machine_stocks}

        self.assertEqual(
            stocks[self.machine.pk],
            35,
        )

        self.assertEqual(
            stocks[self.other_machine.pk],
            10,
        )

    def test_product_machine_stocks_ignore_other_products_and_states(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
            Replenishment.Status.REGISTERED,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            30,
            Replenishment.Status.DRAFT,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            40,
            Replenishment.Status.CANCELLED,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            100,
            Replenishment.Status.REGISTERED,
        )

        machine_stocks = list(get_product_machine_stocks(self.product))

        self.assertEqual(
            len(machine_stocks),
            1,
        )

        self.assertEqual(
            machine_stocks[0].pk,
            self.machine.pk,
        )

        self.assertEqual(
            machine_stocks[0].product_stock,
            20,
        )

    def test_machine_product_stocks_are_grouped_by_product(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            10,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            15,
        )

        product_stocks = list(get_machine_product_stocks(self.machine))

        stocks = {product.pk: product.machine_stock for product in product_stocks}

        self.assertEqual(
            stocks[self.product.pk],
            30,
        )

        self.assertEqual(
            stocks[self.other_product.pk],
            15,
        )

    def test_machine_product_stocks_ignore_other_machines(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            100,
        )

        product_stocks = list(get_machine_product_stocks(self.machine))

        self.assertEqual(
            len(product_stocks),
            1,
        )

        self.assertEqual(
            product_stocks[0].pk,
            self.product.pk,
        )

        self.assertEqual(
            product_stocks[0].machine_stock,
            20,
        )

    def test_machine_product_stocks_ignore_non_registered_replenishments(self):
        self.create_replenishment(
            self.product,
            self.machine,
            20,
            Replenishment.Status.REGISTERED,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            30,
            Replenishment.Status.DRAFT,
        )

        product_stocks = list(get_machine_product_stocks(self.machine))

        self.assertEqual(
            len(product_stocks),
            1,
        )

        self.assertEqual(
            product_stocks[0].pk,
            self.product.pk,
        )

        self.assertEqual(
            product_stocks[0].machine_stock,
            20,
        )

    def test_product_stock_detail_shows_stock_breakdown(self):
        response = self.client.get(
            reverse(
                "inventory:product_stock_detail",
                args=[self.product.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("total_stock", response.context)
        self.assertIn("warehouse_stock", response.context)
        self.assertIn("machines_stock", response.context)
        self.assertIn("machine_stocks", response.context)
