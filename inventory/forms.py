from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from .models import Product


class ProductForm(forms.ModelForm):
    vat_rate = forms.DecimalField(
        label="IVA (%)",
        required=False,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        error_messages={
            "invalid": "Introduce un IVA válido.",
            "min_value": "El IVA no puede ser inferior al 0 %.",
            "max_value": "El IVA no puede ser superior al 100 %.",
        },
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
            }
        ),
    )

    class Meta:
        model = Product

        fields = [
            "name",
            "category",
            "format_unit",
            "vat_rate",
            "default_sale_price",
        ]

        labels = {
            "name": "Nombre",
            "category": "Categoría",
            "format_unit": "Formato / unidad",
            "default_sale_price": ("Precio base de venta (sin IVA)"),
        }

        error_messages = {
            "name": {
                "required": "Introduce el nombre del producto.",
            },
            "category": {
                "required": "Selecciona una categoría.",
            },
            "format_unit": {
                "required": "Introduce el formato o unidad del producto.",
            },
            "default_sale_price": {
                "required": "Introduce el precio base de venta.",
                "invalid": "Introduce un precio válido.",
                "min_value": "El precio de venta no puede ser negativo.",
            },
            NON_FIELD_ERRORS: {
                "unique_together": (
                    "Ya existe un producto con el mismo nombre, "
                    "categoría y formato/unidad."
                ),
            },
        }

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "format_unit": forms.TextInput(attrs={"class": "form-control"}),
            "default_sale_price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
        }

    def clean_vat_rate(self):
        vat_rate = self.cleaned_data.get("vat_rate")

        if vat_rate is not None:
            return vat_rate

        category = self.cleaned_data.get("category")

        if category is not None:
            return category.default_vat_rate

        return vat_rate


class ProductChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, product):
        return f"{product.name} · {product.category.name} · {product.format_unit}"
