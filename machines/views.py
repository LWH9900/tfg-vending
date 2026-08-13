from django.shortcuts import get_object_or_404, render

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
