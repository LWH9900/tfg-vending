from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from inventory.services import (
    get_machine_stock,
    get_machines_stock,
    get_total_stock,
    get_warehouse_stock,
)
from machines.models import Machine
from purchases.models import Purchase, PurchaseLine
from replenishments.models import (
    Replenishment,
    ReplenishmentLine,
)


class InventoryIntegrationTests(TestCase):
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

    def create_replenishment(
        self,
        product,
        machine,
        quantity,
    ):
        replenishment = Replenishment.objects.create(
            machine=machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=quantity,
        )

        return replenishment

    def test_purchase_increases_total_and_warehouse_stock(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.assertEqual(
            get_total_stock(self.product),
            100,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            100,
        )

    def test_purchase_does_not_increase_machine_stock(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            0,
        )

    def test_replenishment_moves_stock_from_warehouse_to_machine(self):
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

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            30,
        )

    def test_replenishment_does_not_change_total_stock(self):
        self.create_purchase(
            self.product,
            100,
        )

        total_before = get_total_stock(self.product)

        self.create_replenishment(
            self.product,
            self.machine,
            30,
        )

        total_after = get_total_stock(self.product)

        self.assertEqual(
            total_before,
            total_after,
        )

        self.assertEqual(
            total_after,
            100,
        )

    def test_multiple_purchases_and_replenishments_are_accumulated(self):
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
            30,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            20,
        )

        self.assertEqual(
            get_total_stock(self.product),
            150,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            100,
        )

        self.assertEqual(
            get_machines_stock(self.product),
            50,
        )

    def test_movements_of_other_products_do_not_affect_stock(self):
        self.create_purchase(
            self.product,
            100,
        )

        self.create_purchase(
            self.other_product,
            500,
        )

        self.create_replenishment(
            self.other_product,
            self.machine,
            300,
        )

        self.assertEqual(
            get_total_stock(self.product),
            100,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            100,
        )

        self.assertEqual(
            get_machines_stock(self.product),
            0,
        )

    def test_replenishment_does_not_affect_other_machine(self):
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
            get_machine_stock(
                self.product,
                self.machine,
            ),
            30,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.other_machine,
            ),
            0,
        )

    def test_total_equals_warehouse_plus_machines(self):
        self.create_purchase(
            self.product,
            150,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            30,
        )

        self.create_replenishment(
            self.product,
            self.other_machine,
            20,
        )

        total = get_total_stock(self.product)

        warehouse = get_warehouse_stock(self.product)

        machines = get_machines_stock(self.product)

        self.assertEqual(
            total,
            warehouse + machines,
        )

    def test_purchase_cannot_be_cancelled_if_warehouse_would_be_negative(self):
        purchase = self.create_purchase(
            self.product,
            100,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            80,
        )

        response = self.client.post(
            reverse(
                "purchases:purchase_cancel",
                args=[purchase.pk],
            )
        )

        purchase.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                "purchases:purchase_detail",
                args=[purchase.pk],
            ),
        )

        self.assertEqual(
            purchase.status,
            Purchase.Status.REGISTERED,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            20,
        )

    def test_purchase_can_be_cancelled_if_warehouse_remains_non_negative(self):
        purchase_to_cancel = self.create_purchase(
            self.product,
            100,
        )

        self.create_purchase(
            self.product,
            100,
        )

        self.create_replenishment(
            self.product,
            self.machine,
            50,
        )

        self.client.post(
            reverse(
                "purchases:purchase_cancel",
                args=[purchase_to_cancel.pk],
            )
        )

        purchase_to_cancel.refresh_from_db()

        self.assertEqual(
            purchase_to_cancel.status,
            Purchase.Status.CANCELLED,
        )

        self.assertEqual(
            get_total_stock(self.product),
            100,
        )

        self.assertEqual(
            get_warehouse_stock(self.product),
            50,
        )

        self.assertEqual(
            get_machine_stock(
                self.product,
                self.machine,
            ),
            50,
        )

    def test_multiline_purchase_is_not_cancelled_if_one_product_would_be_negative(
        self,
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor A",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=100,
            unit_price_excl_vat=Decimal("1.00"),
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.other_product,
            quantity=50,
            unit_price_excl_vat=Decimal("1.00"),
        )

        other_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=other_purchase,
            product=self.product,
            quantity=100,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=50,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.other_product,
            quantity=20,
        )

        self.client.post(
            reverse(
                "purchases:purchase_cancel",
                args=[purchase.pk],
            )
        )

        purchase.refresh_from_db()

        self.assertEqual(
            purchase.status,
            Purchase.Status.REGISTERED,
        )
