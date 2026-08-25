from django import forms

from inventory.forms import ProductChoiceField
from inventory.models import Product
from machines.models import Machine


class ReplenishmentFilterForm(forms.Form):
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

    machine = forms.ModelChoiceField(
        queryset=Machine.objects.all().order_by("identifier"),
        required=False,
        empty_label="Todas las máquinas",
        label="Máquina",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    product = ProductChoiceField(
        queryset=Product.objects.select_related("category").order_by("name"),
        required=False,
        empty_label="Todos los productos",
        label="Producto",
        widget=forms.Select(
            attrs={
                "class": "form-select",
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
