from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from inventory.forms import ProductChoiceField
from inventory.models import Product
from machines.models import Machine
from replenishments.models import Replenishment, ReplenishmentLine


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
    status = forms.ChoiceField(
        choices=[
            ("", "Todos los estados"),
            *Replenishment.Status.choices,
        ],
        required=False,
        label="Estado",
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


class ReplenishmentForm(forms.ModelForm):
    machine = forms.ModelChoiceField(
        queryset=Machine.objects.all().order_by("identifier"),
        label="Máquina",
        empty_label="Selecciona una máquina",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
        error_messages={
            "required": "Selecciona la máquina que se va a reponer.",
            "invalid_choice": "La máquina seleccionada no es válida.",
        },
    )

    class Meta:
        model = Replenishment
        fields = [
            "replenished_at",
            "machine",
        ]

        labels = {
            "replenished_at": "Fecha / hora",
        }

        widgets = {
            "replenished_at": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
        }

        error_messages = {
            "replenished_at": {
                "required": "Introduce la fecha y hora de la reposición.",
                "invalid": "Introduce una fecha y hora válidas.",
            },
        }


class ReplenishmentLineForm(forms.ModelForm):
    product = ProductChoiceField(
        queryset=Product.objects.none(),
        label="Producto",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["product"].queryset = (
            Product.objects.select_related("category")
            .filter(is_active=True)
            .order_by("name")
        )

    class Meta:
        model = ReplenishmentLine

        fields = [
            "product",
            "quantity",
        ]

        labels = {
            "quantity": "Cantidad",
        }

        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                }
            ),
        }

        error_messages = {
            "product": {
                "required": "Selecciona un producto.",
                "invalid_choice": "El producto seleccionado no es válido.",
            },
            "quantity": {
                "required": "Introduce la cantidad.",
                "invalid": "Introduce una cantidad válida.",
                "min_value": "La cantidad debe ser mayor que cero.",
            },
        }


class BaseReplenishmentLineFormSet(BaseInlineFormSet):
    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(
            i,
            **kwargs,
        )
        form.empty_permitted = False

        return form

    def validate_unique(self):
        pass

    def clean(self):
        super().clean()

        products = set()
        has_non_deleted_form = False

        for form in self.forms:
            cleaned_data = getattr(
                form,
                "cleaned_data",
                None,
            )

            if cleaned_data is None:
                continue

            if cleaned_data.get("DELETE"):
                continue

            has_non_deleted_form = True

            product = cleaned_data.get("product")

            if product is None:
                continue

            if product.pk in products:
                form.add_error(
                    "product",
                    ("Este producto ya está incluido en la reposición."),
                )
                continue

            products.add(product.pk)

        if not has_non_deleted_form:
            raise forms.ValidationError("Añade al menos un producto a la reposición.")


ReplenishmentLineFormSet = inlineformset_factory(
    Replenishment,
    ReplenishmentLine,
    form=ReplenishmentLineForm,
    formset=BaseReplenishmentLineFormSet,
    extra=0,
    min_num=1,
    validate_min=False,
    can_delete=True,
)
