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
