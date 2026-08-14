from django.shortcuts import get_object_or_404, redirect, render

from .forms import MachineForm
from .models import Machine


def machine_list(request):
    machines = Machine.objects.all().order_by("identifier")

    return render(
        request,
        "machines/machine_list.html",
        {"machines": machines},
    )


def machine_detail(request, pk):
    machine = get_object_or_404(
        Machine,
        pk=pk,
    )

    return render(
        request,
        "machines/machine_detail.html",
        {"machine": machine},
    )


def machine_create(request):
    if request.method == "POST":
        form = MachineForm(request.POST)

        if form.is_valid():
            machine = form.save()

            return redirect(
                "machines:machine_detail",
                pk=machine.pk,
            )
    else:
        form = MachineForm()

    return render(
        request,
        "machines/machine_form.html",
        {
            "form": form,
            "is_editing": False,
        },
    )


def machine_update(request, pk):
    machine = get_object_or_404(Machine, pk=pk)

    if request.method == "POST":
        form = MachineForm(
            request.POST,
            instance=machine,
        )

        if form.is_valid():
            machine = form.save()

            return redirect(
                "machines:machine_detail",
                pk=machine.pk,
            )
    else:
        form = MachineForm(
            instance=machine,
        )

    return render(
        request,
        "machines/machine_form.html",
        {
            "form": form,
            "machine": machine,
            "is_editing": True,
        },
    )
