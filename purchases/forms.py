from django import forms

from inventory.forms import ProductChoiceField
from inventory.models import Product


class PurchaseFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False,
        label="Desde",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    date_to = forms.DateField(
        required=False,
        label="Hasta",
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
            }
        ),
    )

    product = ProductChoiceField(
        queryset=Product.objects.select_related("category").order_by("name"),
        required=False,
        label="Producto",
        empty_label="Todos los productos",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    supplier = forms.CharField(
        required=False,
        label="Proveedor",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Buscar por proveedor",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError(
                "La fecha inicial no puede ser posterior a la fecha final."
            )

        return cleaned_data
