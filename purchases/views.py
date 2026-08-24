from django.shortcuts import get_object_or_404, render

from .forms import PurchaseFilterForm
from .models import Purchase


def purchase_list(request):
    purchases = Purchase.objects.prefetch_related("lines").order_by(
        "-purchased_at", "-pk"
    )

    filter_form = PurchaseFilterForm(request.GET)

    if filter_form.is_valid():
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")
        product = filter_form.cleaned_data.get("product")
        supplier = filter_form.cleaned_data.get("supplier")

        if date_from:
            purchases = purchases.filter(
                purchased_at__date__gte=date_from,
            )

        if date_to:
            purchases = purchases.filter(
                purchased_at__date__lte=date_to,
            )

        if product:
            purchases = purchases.filter(
                lines__product=product,
            )

        if supplier:
            purchases = purchases.filter(
                supplier__icontains=supplier,
            )

    purchases = purchases.distinct()

    return render(
        request,
        "purchases/purchase_list.html",
        {
            "purchases": purchases,
            "filter_form": filter_form,
        },
    )


def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.prefetch_related(
            "lines__product",
            "lines__product__category",
        ),
        pk=pk,
    )

    return render(
        request,
        "purchases/purchase_detail.html",
        {
            "purchase": purchase,
        },
    )
