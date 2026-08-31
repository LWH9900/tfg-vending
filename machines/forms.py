from django import forms
from django.forms import inlineformset_factory

from inventory.forms import ProductChoiceField
from inventory.models import Product

from .models import (
    Machine,
    MachineLayout,
    MachinePosition,
    MachinePriceOverride,
    PricingProfile,
)


class MachineForm(forms.ModelForm):
    class Meta:
        model = Machine
        fields = [
            "identifier",
            "name",
            "serial_number",
            "location",
        ]

        labels = {
            "identifier": "Identificador",
            "name": "Nombre",
            "serial_number": "Número de serie",
            "location": "Ubicación",
        }

        widgets = {
            "identifier": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "serial_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

        error_messages = {
            "identifier": {
                "required": "El identificador es obligatorio.",
                "unique": "Ya existe una máquina con este identificador.",
            },
            "name": {
                "required": "El nombre es obligatorio.",
            },
            "serial_number": {
                "required": "El número de serie es obligatorio.",
                "unique": "Ya existe una máquina con este número de serie.",
            },
        }


class MachinePricingProfileForm(forms.Form):
    pricing_profile = forms.ModelChoiceField(
        queryset=PricingProfile.objects.all().order_by("name"),
        required=False,
        empty_label="Sin tarifa",
        label="Tarifa",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )


class MachinePriceOverrideForm(forms.ModelForm):
    product = ProductChoiceField(
        queryset=Product.objects.none(),
        label="Producto",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    def __init__(self, *args, machine, **kwargs):
        super().__init__(*args, **kwargs)

        self.machine = machine
        self.instance.machine = machine

        self.fields["product"].queryset = (
            Product.objects.select_related("category")
            .filter(is_active=True)
            .exclude(
                machine_price_overrides__machine=machine,
            )
            .order_by("name")
        )

    def clean_percentage_adjustment(self):
        percentage_adjustment = self.cleaned_data["percentage_adjustment"]

        pricing_profile = self.machine.pricing_profile

        if (
            pricing_profile
            and percentage_adjustment == pricing_profile.percentage_adjustment
        ):
            raise forms.ValidationError(
                "El ajuste específico debe ser diferente "
                "al de la tarifa general de la máquina."
            )

        return percentage_adjustment

    class Meta:
        model = MachinePriceOverride

        fields = [
            "product",
            "percentage_adjustment",
        ]

        labels = {
            "percentage_adjustment": "Ajuste específico (%)",
        }

        widgets = {
            "percentage_adjustment": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
        }


class MachinePriceOverrideUpdateForm(forms.ModelForm):
    class Meta:
        model = MachinePriceOverride

        fields = [
            "percentage_adjustment",
        ]

        labels = {
            "percentage_adjustment": "Variación específica (%)",
        }

        widgets = {
            "percentage_adjustment": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
        }


class PricingProfileForm(forms.ModelForm):
    class Meta:
        model = PricingProfile

        fields = [
            "name",
            "percentage_adjustment",
        ]

        labels = {
            "name": "Nombre",
            "percentage_adjustment": "Variación (%)",
        }

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "percentage_adjustment": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
        }

        error_messages = {
            "name": {
                "required": "El nombre de la tarifa es obligatorio.",
                "max_length": (
                    "El nombre de la tarifa no puede superar los 100 caracteres."
                ),
            },
            "percentage_adjustment": {
                "required": "La variación porcentual es obligatoria.",
                "invalid": ("Introduce una variación porcentual válida."),
            },
        }


class MachineLayoutForm(forms.ModelForm):
    class Meta:
        model = MachineLayout
        fields = ["name"]
        labels = {
            "name": "Nombre",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Configuración principal",
                }
            ),
        }


class MachinePositionForm(forms.ModelForm):
    class Meta:
        model = MachinePosition
        fields = [
            "identifier",
            "product",
        ]
        labels = {
            "identifier": "Selección",
            "product": "Producto",
        }
        widgets = {
            "identifier": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. A1",
                }
            ),
            "product": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }


MachinePositionFormSet = inlineformset_factory(
    MachineLayout,
    MachinePosition,
    form=MachinePositionForm,
    extra=1,
    can_delete=True,
)


class MachineLayoutActivationForm(forms.Form):
    effective_from = forms.DateTimeField(
        label="Activa desde",
        widget=forms.DateTimeInput(
            attrs={
                "class": "form-control",
                "type": "datetime-local",
            },
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
    )
