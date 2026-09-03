from django import forms

from inventory.forms import ProductChoiceField
from inventory.models import Product
from machines.models import Machine
from sales.models import Sale


class SaleFilterForm(forms.Form):
    event_id = forms.CharField(
        required=False,
        label="Event ID",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Buscar event ID",
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

    date_from = forms.DateTimeField(
        required=False,
        label="Desde",
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local",
            },
            format="%Y-%m-%dT%H:%M",
        ),
    )

    date_to = forms.DateTimeField(
        required=False,
        label="Hasta",
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local",
            },
            format="%Y-%m-%dT%H:%M",
        ),
    )

    status = forms.ChoiceField(
        required=False,
        label="Estado",
        choices=[
            (
                "",
                "Todos los estados",
            ),
            *Sale.Status.choices,
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    source = forms.ChoiceField(
        required=False,
        label="Origen",
        choices=[
            (
                "",
                "Todos los orígenes",
            ),
            *Sale.Source.choices,
        ],
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    dispense_type = forms.ChoiceField(
        required=False,
        label="Dispensación",
        choices=[
            (
                "",
                "Todos los tipos",
            ),
            *Sale.DispenseType.choices,
        ],
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


class ResolvePendingSaleForm(forms.Form):
    machine = forms.ModelChoiceField(
        queryset=Machine.objects.order_by("identifier"),
        label="Máquina",
        empty_label="Selecciona una máquina",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    product = ProductChoiceField(
        queryset=Product.objects.select_related("category").order_by("name"),
        label="Producto",
        empty_label="Selecciona un producto",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )


class VoidSaleForm(forms.Form):
    reason = forms.CharField(
        label="Motivo de anulación",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": ("Indica por qué debe anularse esta venta."),
            }
        ),
    )

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()

        if not reason:
            raise forms.ValidationError("Debe indicarse el motivo de la anulación.")

        return reason
