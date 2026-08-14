from django import forms

from .models import Machine


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
