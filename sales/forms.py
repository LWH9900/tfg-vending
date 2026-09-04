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


class MachineResolutionChoiceField(forms.ModelChoiceField):
    def label_from_instance(
        self,
        machine,
    ):
        label = f"{machine.identifier} · {machine.name}"

        if machine.location:
            label += f" · {machine.location}"

        return label


class ResolvePendingMachineForm(forms.Form):
    machine = MachineResolutionChoiceField(
        queryset=Machine.objects.order_by("identifier"),
        label="Máquina",
        empty_label="Selecciona una máquina",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )


class ResolvePendingSaleForm(forms.Form):
    machine = forms.ModelChoiceField(
        queryset=Machine.objects.all(),
        widget=forms.HiddenInput(),
    )

    product = ProductChoiceField(
        queryset=Product.objects.none(),
        label="Producto",
        empty_label="Selecciona un producto",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    def __init__(
        self,
        *args,
        machine=None,
        candidate_products=None,
        automatic_product=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if machine is not None:
            self.fields["machine"].initial = machine

        if candidate_products is not None:
            self.fields["product"].queryset = candidate_products

        if automatic_product is not None:
            self.fields["product"].initial = automatic_product

            self.fields["product"].widget = forms.HiddenInput()


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


class ManualSaleForm(forms.Form):
    event_id = forms.CharField(
        required=False,
        label="Event ID",
        help_text=(
            "Déjalo vacío si la venta no dispone de un evento externo de telemetría."
        ),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": ("Opcional"),
            }
        ),
    )

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

    selection = forms.CharField(
        required=False,
        label="Selección",
        help_text=("Opcional si no se conoce qué selección originó la dispensación."),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej. A1",
            }
        ),
    )

    occurred_at = forms.DateTimeField(
        label="Fecha y hora de la venta",
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

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Cantidad",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": 1,
            }
        ),
    )

    dispense_type = forms.ChoiceField(
        label="Tipo de dispensación",
        choices=Sale.DispenseType.choices,
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    unit_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label="Precio unitario",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
            }
        ),
    )

    amount_received = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label="Importe recibido",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
            }
        ),
    )

    payment_method = forms.CharField(
        required=False,
        label="Medio de pago",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
