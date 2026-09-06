from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from machines.models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
)


@transaction.atomic
def activate_machine_layout(
    layout,
):
    if layout.status != MachineLayout.Status.REGISTERED:
        raise ValidationError("Solo se puede activar una disposición registrada.")

    machine = Machine.objects.select_for_update().get(pk=layout.machine_id)

    current_activation = get_current_machine_layout_activation(machine)

    if current_activation is not None and current_activation.layout_id == layout.pk:
        raise ValidationError("Esta disposición ya está activa.")

    new_activation = MachineLayoutActivation(
        layout=layout,
    )

    new_activation.save()

    if current_activation is not None:
        current_activation.effective_to = new_activation.effective_from

        current_activation.save()

    return new_activation


def get_machine_layout_at(
    machine,
    moment,
):
    activation = get_machine_layout_activation_at(
        machine,
        moment,
    )

    if activation is None:
        return None

    return activation.layout


def get_machine_layout_resolution_candidates(
    machine,
    moment,
):
    activations = list(
        MachineLayoutActivation.objects.filter(
            layout__machine=machine,
        )
        .select_related(
            "layout",
        )
        .order_by(
            "effective_from",
            "pk",
        )
    )

    if not activations:
        return []

    now = timezone.now()

    current_activation = (
        MachineLayoutActivation.objects.filter(
            layout__machine=machine,
            effective_from__lte=now,
            effective_to__isnull=True,
        )
        .select_related("layout")
        .order_by("-effective_from")
        .first()
    )

    current_layout_id = current_activation.layout_id if current_activation else None

    candidates_by_layout = {}

    for activation in activations:
        if moment < activation.effective_from:
            distance = activation.effective_from - moment

            relation = "after"

        elif activation.effective_to is not None and moment >= activation.effective_to:
            distance = moment - activation.effective_to

            relation = "before"

        else:
            distance = timedelta(0)
            relation = "exact"

        candidate = {
            "layout": activation.layout,
            "activation": activation,
            "distance": distance,
            "relation": relation,
            "is_nearest": False,
            "is_current": (activation.layout_id == current_layout_id),
        }

        existing = candidates_by_layout.get(activation.layout_id)

        if existing is None or distance < existing["distance"]:
            candidates_by_layout[activation.layout_id] = candidate

        elif activation.layout_id == current_layout_id:
            existing["is_current"] = True

    candidates = sorted(
        candidates_by_layout.values(),
        key=lambda candidate: (
            candidate["distance"],
            candidate["activation"].effective_from,
        ),
    )

    if candidates:
        candidates[0]["is_nearest"] = True

    return candidates


def get_product_for_selection(
    machine,
    selection_code,
    moment,
):
    layout = get_machine_layout_at(
        machine,
        moment,
    )

    if layout is None:
        return None

    position = (
        layout.positions.select_related("product")
        .filter(
            identifier__iexact=selection_code,
        )
        .first()
    )

    if position is None:
        return None

    return position.product


def get_current_machine_layout_activation(
    machine,
):
    return (
        MachineLayoutActivation.objects.filter(
            layout__machine=machine,
            effective_to__isnull=True,
        )
        .select_related(
            "layout",
            "layout__machine",
        )
        .order_by(
            "-effective_from",
            "-pk",
        )
        .first()
    )


@transaction.atomic
def deactivate_machine_layout(
    layout,
):
    machine = Machine.objects.select_for_update().get(pk=layout.machine_id)

    current_activation = get_current_machine_layout_activation(machine)

    if current_activation is None:
        raise ValidationError("La máquina no tiene ninguna disposición activa.")

    if current_activation.layout_id != layout.pk:
        raise ValidationError("Esta disposición no está activa.")

    current_activation.effective_to = timezone.now()

    current_activation.save()

    return current_activation


def get_machine_layout_activation_at(
    machine,
    moment,
):
    return (
        MachineLayoutActivation.objects.filter(
            layout__machine=machine,
            effective_from__lte=moment,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=moment))
        .select_related(
            "layout",
        )
        .order_by(
            "-effective_from",
            "-pk",
        )
        .first()
    )
