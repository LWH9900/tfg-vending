from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachinePriceOverride,
    PricingProfile,
)


class PricingProfileViewsTest(TestCase):
    def setUp(self):
        self.pricing_profile = PricingProfile.objects.create(
            name="Educativa",
            percentage_adjustment=Decimal("10.00"),
        )

        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina principal",
            serial_number="SN-001",
        )

    def test_pricing_profile_list_is_accessible(self):
        response = self.client.get(reverse("machines:pricing_profile_list"))

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_pricing_profile_list_shows_profiles(self):
        response = self.client.get(reverse("machines:pricing_profile_list"))

        self.assertContains(
            response,
            "Educativa",
        )

    def test_pricing_profile_can_be_created(self):
        response = self.client.post(
            reverse("machines:pricing_profile_create"),
            {
                "name": "Premium",
                "percentage_adjustment": "15.00",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            PricingProfile.objects.filter(
                name="Premium",
                percentage_adjustment=Decimal("15.00"),
            ).exists()
        )

    def test_duplicate_pricing_profile_is_not_created(self):
        response = self.client.post(
            reverse("machines:pricing_profile_create"),
            {
                "name": "educativa",
                "percentage_adjustment": "10.00",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            PricingProfile.objects.count(),
            1,
        )

    def test_duplicate_pricing_profile_reopens_modal_with_error(self):
        response = self.client.post(
            reverse("machines:pricing_profile_create"),
            {
                "name": "educativa",
                "percentage_adjustment": "10.00",
            },
        )

        self.assertTrue(response.context["open_pricing_profile_create_modal"])

        self.assertContains(
            response,
            "Ya existe una tarifa con el mismo nombre",
        )

    def test_pricing_profile_can_be_assigned_to_machine(self):
        response = self.client.post(
            reverse(
                "machines:machine_pricing_profile_update",
                args=[self.machine.pk],
            ),
            {
                "pricing_profile": self.pricing_profile.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.machine.refresh_from_db()

        self.assertEqual(
            self.machine.pricing_profile,
            self.pricing_profile,
        )

    def test_pricing_profile_can_be_removed_from_machine(self):
        self.machine.pricing_profile = self.pricing_profile
        self.machine.save()

        response = self.client.post(
            reverse(
                "machines:machine_pricing_profile_update",
                args=[self.machine.pk],
            ),
            {
                "pricing_profile": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.machine.refresh_from_db()

        self.assertIsNone(self.machine.pricing_profile)

    def test_pricing_profile_in_use_cannot_be_deleted(self):
        self.machine.pricing_profile = self.pricing_profile
        self.machine.save()

        response = self.client.post(
            reverse(
                "machines:pricing_profile_delete",
                args=[self.pricing_profile.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            PricingProfile.objects.filter(
                pk=self.pricing_profile.pk,
            ).exists()
        )

    def test_unused_pricing_profile_can_be_deleted(self):
        response = self.client.post(
            reverse(
                "machines:pricing_profile_delete",
                args=[self.pricing_profile.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            PricingProfile.objects.filter(
                pk=self.pricing_profile.pk,
            ).exists()
        )


class MachinePriceOverrideViewsTest(TestCase):
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

    def test_price_override_can_be_created(self):
        response = self.client.post(
            reverse(
                "machines:machine_price_override_create",
                args=[self.machine.pk],
            ),
            {
                "product": self.product.pk,
                "percentage_adjustment": "8.00",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            MachinePriceOverride.objects.filter(
                machine=self.machine,
                product=self.product,
                percentage_adjustment=Decimal("8.00"),
            ).exists()
        )

    def test_override_equal_to_general_profile_is_not_created(self):
        response = self.client.post(
            reverse(
                "machines:machine_price_override_create",
                args=[self.machine.pk],
            ),
            {
                "product": self.product.pk,
                "percentage_adjustment": "10.00",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(MachinePriceOverride.objects.exists())

        self.assertTrue(response.context["open_override_modal"])

    def test_duplicate_machine_product_override_is_not_created(self):
        MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_price_override_create",
                args=[self.machine.pk],
            ),
            {
                "product": self.product.pk,
                "percentage_adjustment": "5.00",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            MachinePriceOverride.objects.filter(
                machine=self.machine,
                product=self.product,
            ).count(),
            1,
        )

    def test_price_override_can_be_updated(self):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_price_override_update",
                args=[
                    self.machine.pk,
                    override.pk,
                ],
            ),
            {
                "percentage_adjustment": "5.00",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        override.refresh_from_db()

        self.assertEqual(
            override.percentage_adjustment,
            Decimal("5.00"),
        )

    def test_override_update_cannot_match_general_profile(self):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_price_override_update",
                args=[
                    self.machine.pk,
                    override.pk,
                ],
            ),
            {
                "percentage_adjustment": "10.00",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        override.refresh_from_db()

        self.assertEqual(
            override.percentage_adjustment,
            Decimal("8.00"),
        )

    def test_price_override_can_be_deleted(self):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_price_override_delete",
                args=[
                    self.machine.pk,
                    override.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            MachinePriceOverride.objects.filter(
                pk=override.pk,
            ).exists()
        )

        self.assertTrue(
            Product.objects.filter(
                pk=self.product.pk,
            ).exists()
        )


class PricingProfileChangeViewsTest(TestCase):
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

        self.current_profile = PricingProfile.objects.create(
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
            pricing_profile=self.current_profile,
        )

    def test_profile_change_with_redundant_override_requires_confirmation(
        self,
    ):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_pricing_profile_update",
                args=[self.machine.pk],
            ),
            {
                "pricing_profile": self.new_profile.pk,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.machine.refresh_from_db()

        self.assertEqual(
            self.machine.pricing_profile,
            self.current_profile,
        )

        self.assertTrue(
            MachinePriceOverride.objects.filter(
                pk=override.pk,
            ).exists()
        )

        self.assertTrue(response.context["open_pricing_modal"])

    def test_confirmed_profile_change_removes_redundant_override(
        self,
    ):
        override = MachinePriceOverride.objects.create(
            machine=self.machine,
            product=self.product,
            percentage_adjustment=Decimal("8.00"),
        )

        response = self.client.post(
            reverse(
                "machines:machine_pricing_profile_update",
                args=[self.machine.pk],
            ),
            {
                "pricing_profile": self.new_profile.pk,
                "confirm_redundant_overrides": "1",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.machine.refresh_from_db()

        self.assertEqual(
            self.machine.pricing_profile,
            self.new_profile,
        )

        self.assertFalse(
            MachinePriceOverride.objects.filter(
                pk=override.pk,
            ).exists()
        )

    def test_confirmed_profile_change_keeps_different_overrides(
        self,
    ):
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

        self.client.post(
            reverse(
                "machines:machine_pricing_profile_update",
                args=[self.machine.pk],
            ),
            {
                "pricing_profile": self.new_profile.pk,
                "confirm_redundant_overrides": "1",
            },
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
