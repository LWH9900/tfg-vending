from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .models import Category, Product


def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    queryset = Product.objects.select_related(
        "category",
    ).filter(
        is_active=True,
    )

    if self.instance.pk and self.instance.product_id:
        queryset = Product.objects.select_related(
            "category",
        ).filter(Q(is_active=True) | Q(pk=self.instance.product_id))

    self.fields["product"].queryset = queryset.order_by(
        "name",
        "category__name",
        "format_unit",
    )


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "inventory/product_list.html",
        {"products": products},
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "is_edit": False,
        },
    )


def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)

        if form.is_valid():
            product = form.save()

            return redirect(
                "inventory:product_detail",
                pk=product.pk,
            )
    else:
        form = ProductForm()

    category_vat_rates = {
        str(category.pk): str(category.default_vat_rate)
        for category in Category.objects.all()
    }

    return render(
        request,
        "inventory/product_form.html",
        {
            "form": form,
            "category_vat_rates": category_vat_rates,
        },
    )


def product_update(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
    )

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )

        if form.is_valid():
            form.save()

            return redirect(
                "inventory:product_detail",
                pk=product.pk,
            )

    else:
        form = ProductForm(
            instance=product,
        )

    category_vat_rates = {
        str(category.pk): str(category.default_vat_rate)
        for category in Category.objects.all()
    }

    return render(
        request,
        "inventory/product_detail.html",
        {
            "product": product,
            "form": form,
            "is_edit": True,
            "category_vat_rates": category_vat_rates,
        },
    )
