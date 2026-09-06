from decimal import Decimal

from django.test import TestCase

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachinePriceOverride,
    PricingProfile,
)
from machines.services.pricing import (
    build_product_price_details,
    calculate_adjusted_price,
    calculate_price_with_vat,
    change_machine_pricing_profile,
    get_product_price_for_machine,
    get_redundant_price_overrides,
)


class PricingServicesTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="VimaCola",
            format_unit="Lata 330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
            category=self.category,
        )

        self.general_profile = PricingProfile.objects.create(
            name="General",
            percentage_adjustment=Decimal("10.00"),
        )

        self.new_profile = PricingProfile.objects.create(
            name="Premium",
            percentage_adjustment=Decimal("8.00"),
        )

        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina principal",
            serial_number="SN-001",
            pricing_profile=self.general_profile,
        )

    def test_calculate_adjusted_price_with_increase(self):
        result = calculate_adjusted_price(
            Decimal("1.50"),
            Decimal("10.00"),
        )

        self.assertEqual(
            result,
            Decimal("1.65"),
        )

    def test_calculate_adjusted_price_with_discount(self):
        result = calculate_adjusted_price(
            Decimal("2.00"),
            Decimal("-10.00"),
        )

        self.assertEqual(
            result,
            Decimal("1.80"),
        )

    def test_get_redundant_price_overrides(self):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        redundant = get_redundant_price_overrides(
            self.machine,
            self.new_profile,
        )

        self.assertIn(
            override,
            redundant,
        )

    def test_profile_change_does_not_remove_redundant_override_without_confirmation(
        self,
    ):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        result = change_machine_pricing_profile(
            self.machine,
            self.new_profile,
        )

        self.machine.refresh_from_db()

        self.assertTrue(
            MachinePriceOverride.objects.filter(
                pk=override.pk,
            ).exists()
        )

        self.assertEqual(
            self.machine.pricing_profile,
            self.general_profile,
        )

        self.assertTrue(result.exists())

    def test_profile_change_removes_only_redundant_overrides(self):
        second_product = Product.objects.create(
            name="Agua",
            format_unit="Botella 500 ml",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
            category=self.category,
        )

        redundant_override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        different_override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=second_product,
            percentage_adjustment=Decimal("5.00"),
        )

        change_machine_pricing_profile(
            self.machine,
            self.new_profile,
            remove_redundant_overrides=True,
        )

        self.machine.refresh_from_db()

        self.assertEqual(
            self.machine.pricing_profile,
            self.new_profile,
        )

        self.assertFalse(
            MachinePriceOverride.objects.filter(
                pk=redundant_override.pk,
            ).exists()
        )

        self.assertTrue(
            MachinePriceOverride.objects.filter(
                pk=different_override.pk,
            ).exists()
        )

    def test_profile_change_does_not_modify_product_default_price(self):
        original_price = self.product.default_sale_price

        change_machine_pricing_profile(
            self.machine,
            self.new_profile,
            remove_redundant_overrides=True,
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.default_sale_price,
            original_price,
        )

    def test_machine_pricing_profile_can_be_removed(self):
        change_machine_pricing_profile(
            self.machine,
            None,
        )

        self.machine.refresh_from_db()

        self.assertIsNone(self.machine.pricing_profile)

    def test_product_price_uses_override_first(self):
        MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        result = get_product_price_for_machine(
            self.machine,
            self.product,
        )

        self.assertEqual(
            result,
            Decimal("1.96"),
        )

    def test_product_price_uses_general_profile_without_override(
        self,
    ):
        result = get_product_price_for_machine(
            self.machine,
            self.product,
        )

        self.assertEqual(
            result,
            Decimal("2.00"),
        )

    def test_product_price_uses_base_price_without_pricing_policy(
        self,
    ):
        self.machine.pricing_profile = None
        self.machine.save(update_fields=["pricing_profile"])

        result = get_product_price_for_machine(
            self.machine,
            self.product,
        )

        self.assertEqual(
            result,
            Decimal("1.82"),
        )

    def test_calculate_price_with_vat(
        self,
    ):
        result = calculate_price_with_vat(
            Decimal("1.20"),
            Decimal("21.00"),
        )

        self.assertEqual(
            result,
            Decimal("1.45"),
        )

    def test_price_details_apply_adjustment_before_vat(
        self,
    ):
        product = Product.objects.create(
            name="VimaTest Precio",
            format_unit="330 ml",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
            category=self.category,
        )

        profile = PricingProfile.objects.create(
            name="Tarifa 20",
            percentage_adjustment=Decimal("20.00"),
        )

        machine = Machine.objects.create(
            identifier="VM-PRICE-020",
            name="Máquina precio",
            serial_number="SN-PRICE-020",
            pricing_profile=profile,
        )

        details = build_product_price_details(
            machine,
            product,
            None,
        )

        self.assertEqual(
            details["base_price"],
            Decimal("1.00"),
        )

        self.assertEqual(
            details["adjustment_amount"],
            Decimal("0.20"),
        )

        self.assertEqual(
            details["price_excl_vat"],
            Decimal("1.20"),
        )

        self.assertEqual(
            details["vat_amount"],
            Decimal("0.25"),
        )

        self.assertEqual(
            details["final_price"],
            Decimal("1.45"),
        )
