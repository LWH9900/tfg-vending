from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
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
        )

        self.category = Category.objects.create(
            name="Bebidas",
            default_vat_rate=Decimal("21.00"),
        )

        self.cola = Product.objects.create(
            name="Cola",
            category=self.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        self.VimaTea = Product.objects.create(
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
            product=self.cola,
        )

        self.layout_b = MachineLayout.objects.create(
            machine=self.machine,
            name="Layout B",
        )

        MachinePosition.objects.create(
            layout=self.layout_b,
            identifier="A3",
            product=self.VimaTea,
        )

    def make_datetime(
        self,
        year,
        month,
        day,
        hour=0,
    ):
        return timezone.make_aware(
            datetime(
                year,
                month,
                day,
                hour,
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

    def test_machine_cannot_have_two_layouts_at_same_time(self):
        moment = self.make_datetime(
            2026,
            9,
            1,
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

    def test_layout_that_has_never_been_activated_can_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Original",
        )

        layout.name = "Modificado"
        layout.save()

        layout.refresh_from_db()

        self.assertEqual(
            layout.name,
            "Modificado",
        )

    def test_activated_layout_cannot_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        layout.name = "Modificado"

        with self.assertRaises(ValidationError):
            layout.save()

    def test_activated_layout_cannot_be_deleted(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            layout.delete()

    def test_position_in_unused_layout_can_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            product=self.cola,
        )

        position.identifier = "A2"
        position.save()

        position.refresh_from_db()

        self.assertEqual(
            position.identifier,
            "A2",
        )

    def test_position_in_activated_layout_cannot_be_edited(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            product=self.cola,
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        position.identifier = "A2"

        with self.assertRaises(ValidationError):
            position.save()

    def test_position_cannot_be_added_to_activated_layout(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            MachinePosition.objects.create(
                layout=layout,
                identifier="A1",
                product=self.cola,
            )

    def test_position_in_activated_layout_cannot_be_deleted(self):
        layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Principal",
        )

        position = MachinePosition.objects.create(
            layout=layout,
            identifier="A1",
            product=self.cola,
        )

        MachineLayoutActivation.objects.create(
            layout=layout,
            effective_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            position.delete()
