from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

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
    deactivate_machine_layout,
    get_current_machine_layout_activation,
    get_machine_layout_at,
    get_machine_layout_resolution_candidates,
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
        activation_time = timezone.now()

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        moment = activation_time + timedelta(
            minutes=10,
        )

        layout = get_machine_layout_at(
            self.machine,
            moment,
        )

        self.assertEqual(
            layout,
            self.layout_a,
        )

    def test_activation_uses_current_time(self):
        moment = timezone.now()

        with patch(
            "django.utils.timezone.now",
            return_value=moment,
        ):
            activation = activate_machine_layout(
                self.layout_a,
            )

        self.assertEqual(
            activation.effective_from,
            moment,
        )

        self.assertIsNone(
            activation.effective_to,
        )

    def test_get_machine_layout_at_uses_historical_layout(self):
        first_activation_time = timezone.now()

        second_activation_time = first_activation_time + timedelta(hours=2)

        with patch(
            "django.utils.timezone.now",
            return_value=first_activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation_time,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        moment_between = first_activation_time + timedelta(hours=1)

        layout = get_machine_layout_at(
            self.machine,
            moment_between,
        )

        self.assertEqual(
            layout,
            self.layout_a,
        )

    def test_old_layout_can_be_reactivated(self):
        first_moment = timezone.now()
        second_moment = first_moment + timedelta(hours=1)
        third_moment = first_moment + timedelta(hours=2)

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=third_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        current_activation = get_current_machine_layout_activation(self.machine)

        self.assertEqual(
            current_activation.layout,
            self.layout_a,
        )

        self.assertEqual(
            MachineLayoutActivation.objects.filter(
                layout=self.layout_a,
            ).count(),
            2,
        )

    def test_activating_layout_closes_previous_activation(self):
        first_moment = timezone.now()

        second_moment = first_moment + timedelta(hours=1)

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            activation_a = activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activation_b = activate_machine_layout(
                self.layout_b,
            )

        activation_a.refresh_from_db()
        activation_b.refresh_from_db()

        self.assertEqual(
            activation_a.effective_to,
            activation_b.effective_from,
        )

        self.assertIsNone(
            activation_b.effective_to,
        )

        self.assertEqual(
            MachineLayoutActivation.objects.filter(
                layout__machine=self.machine,
                effective_to__isnull=True,
            ).count(),
            1,
        )

    def test_draft_layout_cannot_be_activated(self):
        draft_layout = MachineLayout.objects.create(
            machine=self.machine,
            name="Borrador",
        )

        with self.assertRaises(ValidationError):
            activate_machine_layout(
                draft_layout,
            )

    def test_selection_resolves_product_from_active_layout(self):
        activation_time = self.make_datetime(
            2026,
            9,
            1,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
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
        activation_time = self.make_datetime(
            2026,
            9,
            1,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
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
        first_activation_time = self.make_datetime(
            2026,
            9,
            1,
        )

        second_activation_time = self.make_datetime(
            2026,
            9,
            10,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation_time,
        ):
            activate_machine_layout(
                self.layout_b,
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
        activation_time = self.make_datetime(
            2026,
            9,
            1,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
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

    def test_active_layout_cannot_be_activated_again(self):
        activation_time = self.make_datetime(
            2026,
            9,
            1,
            9,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with self.assertRaisesMessage(
            ValidationError,
            "Esta disposición ya está activa.",
        ):
            activate_machine_layout(
                self.layout_a,
            )

        self.assertEqual(
            MachineLayoutActivation.objects.filter(
                layout=self.layout_a,
            ).count(),
            1,
        )

    def test_resolution_candidates_are_empty_without_activations(self):
        moment = self.make_datetime(
            2026,
            9,
            5,
            12,
            0,
        )

        candidates = get_machine_layout_resolution_candidates(
            self.machine,
            moment,
        )

        self.assertEqual(
            candidates,
            [],
        )

    def test_resolution_candidates_identify_exact_and_future_layouts(self):
        first_activation_time = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )
        second_activation_time = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )
        moment = self.make_datetime(
            2026,
            9,
            1,
            11,
            0,
        )
        current_time = self.make_datetime(
            2026,
            9,
            1,
            13,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation_time,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=current_time,
        ):
            candidates = get_machine_layout_resolution_candidates(
                self.machine,
                moment,
            )

        candidates_by_layout = {
            candidate["layout"].pk: candidate for candidate in candidates
        }

        candidate_a = candidates_by_layout[self.layout_a.pk]
        candidate_b = candidates_by_layout[self.layout_b.pk]

        self.assertEqual(
            candidate_a["relation"],
            "exact",
        )
        self.assertEqual(
            candidate_a["distance"],
            timedelta(0),
        )
        self.assertTrue(
            candidate_a["is_nearest"],
        )
        self.assertFalse(
            candidate_a["is_current"],
        )

        self.assertEqual(
            candidate_b["relation"],
            "after",
        )
        self.assertEqual(
            candidate_b["distance"],
            timedelta(hours=1),
        )
        self.assertFalse(
            candidate_b["is_nearest"],
        )
        self.assertTrue(
            candidate_b["is_current"],
        )

    def test_resolution_candidates_identify_past_layout(self):
        first_activation_time = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )
        second_activation_time = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )
        moment = self.make_datetime(
            2026,
            9,
            1,
            13,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_activation_time,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=moment,
        ):
            candidates = get_machine_layout_resolution_candidates(
                self.machine,
                moment,
            )

        candidates_by_layout = {
            candidate["layout"].pk: candidate for candidate in candidates
        }

        candidate_a = candidates_by_layout[self.layout_a.pk]
        candidate_b = candidates_by_layout[self.layout_b.pk]

        self.assertEqual(
            candidate_a["relation"],
            "before",
        )
        self.assertEqual(
            candidate_a["distance"],
            timedelta(hours=1),
        )
        self.assertFalse(
            candidate_a["is_current"],
        )

        self.assertEqual(
            candidate_b["relation"],
            "exact",
        )
        self.assertEqual(
            candidate_b["distance"],
            timedelta(0),
        )
        self.assertTrue(
            candidate_b["is_nearest"],
        )
        self.assertTrue(
            candidate_b["is_current"],
        )

    def test_resolution_candidates_group_repeated_layout_activations(self):
        first_moment = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )
        second_moment = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )
        third_moment = self.make_datetime(
            2026,
            9,
            1,
            14,
            0,
        )
        resolution_moment = self.make_datetime(
            2026,
            9,
            1,
            11,
            0,
        )
        current_time = self.make_datetime(
            2026,
            9,
            1,
            15,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=first_moment,
        ):
            first_activation_a = activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=second_moment,
        ):
            activate_machine_layout(
                self.layout_b,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=third_moment,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=current_time,
        ):
            candidates = get_machine_layout_resolution_candidates(
                self.machine,
                resolution_moment,
            )

        self.assertEqual(
            len(candidates),
            2,
        )

        candidates_by_layout = {
            candidate["layout"].pk: candidate for candidate in candidates
        }

        candidate_a = candidates_by_layout[self.layout_a.pk]

        self.assertEqual(
            candidate_a["activation"].pk,
            first_activation_a.pk,
        )
        self.assertEqual(
            candidate_a["relation"],
            "exact",
        )
        self.assertEqual(
            candidate_a["distance"],
            timedelta(0),
        )

        self.assertTrue(
            candidate_a["is_current"],
        )
        self.assertTrue(
            candidate_a["is_nearest"],
        )

    def test_active_layout_can_be_deactivated(self):
        activation_time = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )
        deactivation_time = self.make_datetime(
            2026,
            9,
            1,
            12,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activation = activate_machine_layout(
                self.layout_a,
            )

        with patch(
            "django.utils.timezone.now",
            return_value=deactivation_time,
        ):
            deactivated_activation = deactivate_machine_layout(
                self.layout_a,
            )

        activation.refresh_from_db()

        self.assertEqual(
            deactivated_activation.pk,
            activation.pk,
        )
        self.assertEqual(
            activation.effective_to,
            deactivation_time,
        )
        self.assertIsNone(
            get_current_machine_layout_activation(
                self.machine,
            )
        )

        self.assertIsNone(
            get_machine_layout_at(
                self.machine,
                deactivation_time,
            )
        )

    def test_layout_cannot_be_deactivated_without_active_layout(self):
        with self.assertRaisesMessage(
            ValidationError,
            "La máquina no tiene ninguna disposición activa.",
        ):
            deactivate_machine_layout(
                self.layout_a,
            )

    def test_inactive_layout_cannot_be_deactivated(self):
        activation_time = self.make_datetime(
            2026,
            9,
            1,
            10,
            0,
        )

        with patch(
            "django.utils.timezone.now",
            return_value=activation_time,
        ):
            activate_machine_layout(
                self.layout_a,
            )

        with self.assertRaisesMessage(
            ValidationError,
            "Esta disposición no está activa.",
        ):
            deactivate_machine_layout(
                self.layout_b,
            )
