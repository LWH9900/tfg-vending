from django.shortcuts import render, get_object_or_404, redirect

from .models import Category, Product
from .forms import ProductForm


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "inventory/product_list.html",
        {"products": products},
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product,
        pk=pk,
        is_active=True,
    )

    return render(
        request,
        "inventory/product_detail.html",
        {"product": product},
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
    product = get_object_or_404(Product, pk=pk, is_active=True)

    if request.method == "POST":
        form = ProductForm(
            request.POST,
            instance=product,
        )

        if form.is_valid():
            product = form.save()

            return redirect(
                "inventory:product_detail",
                pk=product.pk,
            )
    else:
        form = ProductForm(instance=product)

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
            "is_editing": True,
            "product": product,
        },
    )
