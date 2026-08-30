from django.core.exceptions import ValidationError
from django.db import transaction

from machines.models import (
    Machine,
    MachineLayoutActivation,
)


@transaction.atomic
def activate_machine_layout(
    layout,
    effective_from,
):
    Machine.objects.select_for_update().get(pk=layout.machine_id)

    activation_exists = MachineLayoutActivation.objects.filter(
        layout__machine=layout.machine,
        effective_from=effective_from,
    ).exists()

    if activation_exists:
        raise ValidationError(
            "Ya existe una disposición activada para esta máquina en esa fecha y hora."
        )

    return MachineLayoutActivation.objects.create(
        layout=layout,
        effective_from=effective_from,
    )


def get_machine_layout_at(
    machine,
    moment,
):
    activation = (
        MachineLayoutActivation.objects.filter(
            layout__machine=machine,
            effective_from__lte=moment,
        )
        .select_related("layout")
        .order_by(
            "-effective_from",
            "-pk",
        )
        .first()
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
