from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import Machine, MachineLayout, MachinePosition, PricingProfile
from machines.services.layouts import activate_machine_layout
from purchases.models import Purchase, PurchaseLine
from purchases.services import get_purchase_profitability_warning


class ProductPurchaseCostTests(TestCase):
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

        cls.other_product = Product.objects.create(
            name="Agua",
            category=cls.category,
            format_unit="500 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.00"),
        )

    def test_product_without_purchases_has_no_costs(self):
        self.assertIsNone(self.product.latest_purchase_cost)

        self.assertIsNone(self.product.average_purchase_cost)

    def test_latest_purchase_cost_uses_most_recent_purchase(self):
        latest_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            purchased_at=timezone.make_aware(datetime(2026, 8, 20, 10, 0)),
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=latest_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("4.00"),
        )

        older_purchase = Purchase.objects.create(
            supplier="Proveedor A",
            purchased_at=timezone.make_aware(datetime(2026, 8, 10, 10, 0)),
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=older_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("4.00"),
        )

    def test_average_purchase_cost_is_weighted_by_quantity(self):
        first_purchase = Purchase.objects.create(
            supplier="Proveedor A",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=first_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.product,
            quantity=30,
            unit_price_excl_vat=Decimal("4.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("3.50"),
        )

    def test_other_products_do_not_affect_cost_calculation(self):
        purchase = Purchase.objects.create(
            supplier="Proveedor A",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.other_product,
            quantity=1000,
            unit_price_excl_vat=Decimal("99.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("2.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("2.00"),
        )

    def test_new_purchase_updates_latest_and_average_cost(self):
        first_purchase = Purchase.objects.create(
            supplier="Proveedor A",
            purchased_at=timezone.make_aware(datetime(2026, 8, 10, 10, 0)),
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=first_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("2.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("2.00"),
        )

        second_purchase = Purchase.objects.create(
            supplier="Proveedor B",
            purchased_at=timezone.make_aware(datetime(2026, 8, 20, 10, 0)),
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=second_purchase,
            product=self.product,
            quantity=30,
            unit_price_excl_vat=Decimal("4.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("4.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("3.50"),
        )

    def test_draft_purchase_does_not_affect_costs(self):
        purchase = Purchase.objects.create(
            supplier="Proveedor",
            status=Purchase.Status.DRAFT,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("5.00"),
        )

        self.assertIsNone(self.product.latest_purchase_cost)
        self.assertIsNone(self.product.average_purchase_cost)

    def test_cancelled_purchase_does_not_affect_costs(self):
        purchase = Purchase.objects.create(
            supplier="Proveedor",
            status=Purchase.Status.CANCELLED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("5.00"),
        )

        self.assertIsNone(self.product.latest_purchase_cost)
        self.assertIsNone(self.product.average_purchase_cost)

    def test_draft_and_cancelled_purchases_are_ignored(self):
        registered_purchase = Purchase.objects.create(
            supplier="Proveedor registrado",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=registered_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("2.00"),
        )

        draft_purchase = Purchase.objects.create(
            supplier="Proveedor borrador",
            status=Purchase.Status.DRAFT,
        )

        PurchaseLine.objects.create(
            purchase=draft_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("8.00"),
        )

        cancelled_purchase = Purchase.objects.create(
            supplier="Proveedor anulado",
            status=Purchase.Status.CANCELLED,
        )

        PurchaseLine.objects.create(
            purchase=cancelled_purchase,
            product=self.product,
            quantity=10,
            unit_price_excl_vat=Decimal("20.00"),
        )

        self.assertEqual(
            self.product.latest_purchase_cost,
            Decimal("2.00"),
        )

        self.assertEqual(
            self.product.average_purchase_cost,
            Decimal("2.00"),
        )


class PurchaseProfitabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Bebidas rentabilidad",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="VimaCola Rentabilidad",
            category=cls.category,
            format_unit="330 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("2.00"),
        )

        cls.other_product = Product.objects.create(
            name="VimaTea Rentabilidad",
            category=cls.category,
            format_unit="250 ml",
            vat_rate=Decimal("21.00"),
            default_sale_price=Decimal("1.50"),
        )

    def create_machine_with_product(
        self,
        *,
        identifier,
        product,
        percentage_adjustment=Decimal("0.00"),
    ):
        pricing_profile = None

        if percentage_adjustment != Decimal("0.00"):
            pricing_profile = PricingProfile.objects.create(
                name=f"Tarifa {identifier}",
                percentage_adjustment=percentage_adjustment,
            )

        machine = Machine.objects.create(
            identifier=identifier,
            name=f"Máquina {identifier}",
            serial_number=f"SN-{identifier}",
            rows=2,
            columns=2,
            pricing_profile=pricing_profile,
        )

        layout = MachineLayout.objects.create(
            machine=machine,
            name=f"Disposición {identifier}",
        )

        MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            row=1,
            column=1,
            product=product,
        )

        layout.status = MachineLayout.Status.REGISTERED

        layout.save()

        activate_machine_layout(layout)

        return machine

    def create_purchase_line(
        self,
        *,
        product=None,
        quantity=10,
        unit_price=Decimal("2.50"),
    ):
        purchase = Purchase.objects.create(
            supplier="Proveedor rentabilidad",
            status=Purchase.Status.DRAFT,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=product or self.product,
            quantity=quantity,
            unit_price_excl_vat=unit_price,
        )

        return purchase

    def test_no_warning_when_purchase_is_profitable_in_all_machines(
        self,
    ):
        self.create_machine_with_product(
            identifier="VM-PROFIT-001",
            product=self.product,
            percentage_adjustment=Decimal("20.00"),
        )

        purchase = self.create_purchase_line(
            unit_price=Decimal("2.00"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNone(warning)

    def test_warning_detects_machine_with_loss(
        self,
    ):
        losing_machine = self.create_machine_with_product(
            identifier="VM-LOSS-001",
            product=self.product,
        )

        self.create_machine_with_product(
            identifier="VM-PROFIT-002",
            product=self.product,
            percentage_adjustment=Decimal("50.00"),
        )

        purchase = self.create_purchase_line(
            quantity=10,
            unit_price=Decimal("2.50"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNotNone(warning)

        self.assertEqual(
            warning["loss_count"],
            1,
        )

        self.assertFalse(warning["all_machines_for_any_product"])

        self.assertFalse(warning["show_modal"])

        loss = warning["losses"][0]

        self.assertEqual(
            loss["machine"],
            losing_machine,
        )

        self.assertEqual(
            loss["purchase_price_excl_vat"],
            Decimal("2.50"),
        )

        self.assertEqual(
            loss["sale_price_excl_vat"],
            Decimal("2.00"),
        )

        self.assertEqual(
            loss["sale_price_incl_vat"],
            Decimal("2.42"),
        )

        self.assertEqual(
            loss["loss_per_unit"],
            Decimal("0.50"),
        )

        self.assertEqual(
            loss["theoretical_line_loss"],
            Decimal("5.00"),
        )

    def test_warning_uses_modal_when_product_loses_in_all_machines(
        self,
    ):
        self.create_machine_with_product(
            identifier="VM-ALL-001",
            product=self.product,
        )

        self.create_machine_with_product(
            identifier="VM-ALL-002",
            product=self.product,
            percentage_adjustment=Decimal("20.00"),
        )

        purchase = self.create_purchase_line(
            unit_price=Decimal("3.00"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNotNone(warning)

        self.assertEqual(
            warning["loss_count"],
            2,
        )

        self.assertTrue(warning["all_machines_for_any_product"])

        self.assertTrue(warning["show_modal"])

    def test_warning_uses_modal_when_more_than_three_losses_exist(
        self,
    ):
        adjustments = [
            Decimal("0.00"),
            Decimal("10.00"),
            Decimal("20.00"),
            Decimal("30.00"),
            Decimal("100.00"),
        ]

        for index, adjustment in enumerate(
            adjustments,
            start=1,
        ):
            self.create_machine_with_product(
                identifier=(f"VM-MANY-{index:03d}"),
                product=self.product,
                percentage_adjustment=adjustment,
            )

        purchase = self.create_purchase_line(
            unit_price=Decimal("3.00"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNotNone(warning)

        self.assertEqual(
            warning["loss_count"],
            4,
        )

        self.assertFalse(warning["all_machines_for_any_product"])

        self.assertTrue(warning["show_modal"])

        self.assertEqual(
            len(warning["inline_losses"]),
            3,
        )

    def test_machine_without_product_in_active_layout_is_ignored(
        self,
    ):
        relevant_machine = self.create_machine_with_product(
            identifier="VM-RELEVANT-001",
            product=self.product,
        )

        self.create_machine_with_product(
            identifier="VM-OTHER-001",
            product=self.other_product,
        )

        purchase = self.create_purchase_line(
            unit_price=Decimal("2.50"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNotNone(warning)

        self.assertEqual(
            warning["affected_machine_count"],
            1,
        )

        self.assertEqual(
            warning["losses"][0]["machine"],
            relevant_machine,
        )

    def test_product_without_active_machine_has_no_profitability_warning(
        self,
    ):
        purchase = self.create_purchase_line(
            unit_price=Decimal("100.00"),
        )

        warning = get_purchase_profitability_warning(purchase)

        self.assertIsNone(warning)
