from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachinePriceOverride,
    PricingProfile,
)


class PricingModelsTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.product = Product.objects.create(
            name="Coca cola",
            format_unit="Lata 330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
            category=self.category,
        )

        self.pricing_profile = PricingProfile.objects.create(
            name="Educativa",
            percentage_adjustment=Decimal("10.00"),
        )

        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina principal",
            serial_number="SN-001",
            pricing_profile=self.pricing_profile,
        )

    def test_pricing_profile_is_valid(self):
        pricing_profile = PricingProfile(
            name="Premium",
            percentage_adjustment=Decimal("15.00"),
        )

        pricing_profile.full_clean()

    def test_pricing_profile_duplicate_is_case_insensitive(self):
        duplicate = PricingProfile(
            name="educativa",
            percentage_adjustment=Decimal("10.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_pricing_profile_allows_same_name_with_different_adjustment(
        self,
    ):
        pricing_profile = PricingProfile(
            name="Educativa",
            percentage_adjustment=Decimal("5.00"),
        )

        pricing_profile.full_clean()

    def test_machine_price_override_is_valid(self):
        override = MachinePriceOverride(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        override.full_clean()

    def test_override_cannot_match_general_pricing_profile(self):
        override = MachinePriceOverride(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("10.00"),
        )

        with self.assertRaises(ValidationError):
            override.full_clean()

    def test_machine_product_can_only_have_one_override(self):
        MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        duplicate = MachinePriceOverride(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("5.00"),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_pricing_profile_in_use_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.pricing_profile.delete()

    def test_unused_pricing_profile_can_be_deleted(self):
        pricing_profile = PricingProfile.objects.create(
            name="Temporal",
            percentage_adjustment=Decimal("5.00"),
        )

        pricing_profile.delete()

        self.assertFalse(
            PricingProfile.objects.filter(
                pk=pricing_profile.pk,
            ).exists()
        )
