from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "default_vat_rate"]
        labels = {
            "name": "Nombre",
            "default_vat_rate": "IVA por defecto (%)",
        }
        error_messages = {
            "name": {
                "required": "Introduce el nombre de la categoría.",
                "unique": "Ya existe una categoría con este nombre.",
            },
            "default_vat_rate": {
                "required": "Introduce el IVA por defecto.",
                "invalid": "Introduce un IVA válido.",
                "min_value": "El IVA no puede ser inferior al 0 %%.",
                "max_value": "El IVA no puede ser superior al 100 %%.",
            },
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "default_vat_rate": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = Category.objects.filter(name__iexact=name)

        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)

        if duplicates.exists():
            raise forms.ValidationError("Ya existe una categoría con este nombre.")

        return name


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
            "min_value": "El IVA no puede ser inferior al 0 %%.",
            "max_value": "El IVA no puede ser superior al 100 %%.",
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
        category = self.cleaned_data.get("category")
        raw_vat_rate = self.data.get(self.add_prefix("vat_rate"), "").strip()

        if not raw_vat_rate:
            self._uses_category_vat = True
            if category is not None:
                return category.default_vat_rate
            return vat_rate

        if self.instance._state.adding:
            self._uses_category_vat = bool(
                category is not None and vat_rate == category.default_vat_rate
            )
        else:
            self._uses_category_vat = bool(
                self.instance.uses_category_vat
                and category is not None
                and vat_rate == category.default_vat_rate
            )

        return vat_rate

    def save(self, commit=True):
        product = super().save(commit=False)
        product.uses_category_vat = getattr(
            self,
            "_uses_category_vat",
            product.uses_category_vat,
        )

        if commit:
            product.save()
            self.save_m2m()

        return product


class ProductChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        classes = self.widget.attrs.get("class", "").split()

        if "product-search-select" not in classes:
            classes.append("product-search-select")

        self.widget.attrs["class"] = " ".join(classes)

    def label_from_instance(self, product):
        return f"{product.name} · {product.category.name} · {product.format_unit}"
