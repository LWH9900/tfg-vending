from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from inventory.forms import ProductChoiceField
from inventory.models import Product

from .models import Purchase, PurchaseLine


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
    status = forms.ChoiceField(
        choices=[
            ("", "Todos los estados"),
            *Purchase.Status.choices,
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


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase

        fields = [
            "purchased_at",
            "supplier",
            "document_reference",
        ]

        labels = {
            "purchased_at": "Fecha / hora",
            "supplier": "Proveedor",
            "document_reference": "N.º factura / albarán",
        }

        widgets = {
            "purchased_at": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "supplier": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "document_reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }

        error_messages = {
            "purchased_at": {
                "required": "Introduce la fecha y hora de la compra.",
                "invalid": "Introduce una fecha y hora válidas.",
            },
            "supplier": {
                "required": "Introduce el proveedor de la compra.",
            },
        }


class PurchaseLineForm(forms.ModelForm):
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
        model = PurchaseLine

        fields = [
            "product",
            "quantity",
            "unit_price_excl_vat",
        ]

        labels = {
            "quantity": "Cantidad",
            "unit_price_excl_vat": "Precio unitario sin IVA",
        }

        widgets = {
            "quantity": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                }
            ),
            "unit_price_excl_vat": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),
        }

        error_messages = {
            "product": {
                "required": "Selecciona un producto.",
            },
            "quantity": {
                "required": "Introduce la cantidad.",
                "invalid": "Introduce una cantidad válida.",
                "min_value": "La cantidad debe ser mayor que cero.",
            },
            "unit_price_excl_vat": {
                "required": "Introduce el precio unitario sin IVA.",
                "invalid": "Introduce un precio válido.",
                "min_value": "El precio no puede ser negativo.",
            },
        }


class BasePurchaseLineFormSet(BaseInlineFormSet):
    default_error_messages = {
        "too_few_forms": "Añade al menos un producto a la compra.",
    }

    def validate_unique(self):
        pass

    def clean(self):
        super().clean()

        products = set()

        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", None)

            if not cleaned_data:
                continue

            if cleaned_data.get("DELETE"):
                continue

            product = cleaned_data.get("product")

            if product is None:
                continue

            if product.pk in products:
                form.add_error(
                    "product",
                    "Este producto ya está incluido en la compra.",
                )
                continue

            products.add(product.pk)


PurchaseLineFormSet = inlineformset_factory(
    Purchase,
    PurchaseLine,
    form=PurchaseLineForm,
    formset=BasePurchaseLineFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
