from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
)
from machines.services.layouts import (
    activate_machine_layout,
    get_machine_layout_at,
    get_product_for_selection,
)


class MachineLayoutServiceTests(TestCase):
    def setUp(self):
        self.machine = Machine.objects.create(
            identifier="VM-001",
            name="Máquina 1",
            serial_number="SN-001",
            rows=4,
            columns=4,
        )

        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.cola = Product.objects.create(
            name="VimaCola",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.tea = Product.objects.create(
            name="VimaTea",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.60"),
            vat_rate=Decimal("21.00"),
        )

        self.layout_a = MachineLayout.objects.create(
            machine=self.machine,
            name="Layout A",
        )

        MachinePosition.objects.create(
            layout=self.layout_a,
            identifier="A3",
            row=1,
            column=1,
            product=self.cola,
        )

        self.layout_a.status = MachineLayout.Status.REGISTERED
        self.layout_a.save()

        self.layout_b = MachineLayout.objects.create(
            machine=self.machine,
            name="Layout B",
        )

        MachinePosition.objects.create(
            layout=self.layout_b,
            identifier="A3",
            row=1,
            column=1,
            product=self.tea,
        )

        self.layout_b.status = MachineLayout.Status.REGISTERED
        self.layout_b.save()

    def make_datetime(
        self,
        year,
        month,
        day,
        hour=0,
        minute=0,
    ):
        return timezone.make_aware(
            datetime(
                year,
                month,
                day,
                hour,
                minute,
            )
        )

    def test_machine_without_activation_has_no_layout(self):
        moment = self.make_datetime(
            2026,
            9,
            1,
        )

        self.assertIsNone(
            get_machine_layout_at(
                self.machine,
                moment,
            )
        )

    def test_get_machine_layout_at_returns_active_layout(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        layout = get_machine_layout_at(
            self.machine,
            self.make_datetime(
                2026,
                9,
                5,
            ),
        )

        self.assertEqual(
            layout,
            self.layout_a,
        )

    def test_future_activation_is_not_active_before_effective_date(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                10,
            ),
        )

        layout = get_machine_layout_at(
            self.machine,
            self.make_datetime(
                2026,
                9,
                5,
            ),
        )

        self.assertIsNone(layout)

    def test_get_machine_layout_at_uses_historical_layout(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        activate_machine_layout(
            self.layout_b,
            self.make_datetime(
                2026,
                9,
                10,
            ),
        )

        old_layout = get_machine_layout_at(
            self.machine,
            self.make_datetime(
                2026,
                9,
                8,
            ),
        )

        current_layout = get_machine_layout_at(
            self.machine,
            self.make_datetime(
                2026,
                9,
                12,
            ),
        )

        self.assertEqual(
            old_layout,
            self.layout_a,
        )

        self.assertEqual(
            current_layout,
            self.layout_b,
        )

    def test_old_layout_can_be_reactivated(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        activate_machine_layout(
            self.layout_b,
            self.make_datetime(
                2026,
                9,
                10,
            ),
        )

        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                20,
            ),
        )

        layout = get_machine_layout_at(
            self.machine,
            self.make_datetime(
                2026,
                9,
                25,
            ),
        )

        self.assertEqual(
            layout,
            self.layout_a,
        )

    def test_machine_cannot_have_two_layouts_at_same_time(self):
        moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            30,
        )

        activate_machine_layout(
            self.layout_a,
            moment,
        )

        with self.assertRaises(ValidationError):
            activate_machine_layout(
                self.layout_b,
                moment,
            )

    def test_draft_layout_cannot_be_activated(self):
        draft_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Borrador",
        )

        with self.assertRaises(ValidationError):
            activate_machine_layout(
                draft_layout,
                self.make_datetime(
                    2026,
                    9,
                    1,
                ),
            )

    def test_selection_resolves_product_from_active_layout(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        product = get_product_for_selection(
            self.machine,
            "A3",
            self.make_datetime(
                2026,
                9,
                5,
            ),
        )

        self.assertEqual(
            product,
            self.cola,
        )

    def test_selection_resolution_is_case_insensitive(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        product = get_product_for_selection(
            self.machine,
            "a3",
            self.make_datetime(
                2026,
                9,
                5,
            ),
        )

        self.assertEqual(
            product,
            self.cola,
        )

    def test_selection_uses_product_from_historical_layout(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        activate_machine_layout(
            self.layout_b,
            self.make_datetime(
                2026,
                9,
                10,
            ),
        )

        product = get_product_for_selection(
            self.machine,
            "A3",
            self.make_datetime(
                2026,
                9,
                8,
            ),
        )

        self.assertEqual(
            product,
            self.cola,
        )

    def test_selection_returns_none_without_active_layout(self):
        product = get_product_for_selection(
            self.machine,
            "A3",
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        self.assertIsNone(product)

    def test_unknown_selection_returns_none(self):
        activate_machine_layout(
            self.layout_a,
            self.make_datetime(
                2026,
                9,
                1,
            ),
        )

        product = get_product_for_selection(
            self.machine,
            "Z9",
            self.make_datetime(
                2026,
                9,
                5,
            ),
        )

        self.assertIsNone(product)
