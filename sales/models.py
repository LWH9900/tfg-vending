from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Sale(models.Model):
    class DispenseType(models.TextChoices):
        PAID = "paid", "Con pago"
        FREE = "free", "Gratuita"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RESOLVED = "resolved", "Resuelta"

    event_id = models.CharField(
        max_length=100,
        unique=True,
    )

    machine_identifier = models.CharField(
        max_length=100,
    )

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )

    selection = models.CharField(
        max_length=20,
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )

    occurred_at = models.DateTimeField()

    received_at = models.DateTimeField(
        auto_now_add=True,
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    dispense_type = models.CharField(
        max_length=10,
        choices=DispenseType.choices,
    )

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    amount_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    payment_method = models.CharField(
        max_length=50,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )

    raw_payload = models.JSONField()

    def clean(self):
        super().clean()

        if self.product is not None and self.machine is None:
            raise ValidationError(
                {
                    "product": (
                        "No se puede asociar un producto sin haber resuelto la máquina."
                    )
                }
            )

        if self.status == self.Status.RESOLVED and self.machine is None:
            raise ValidationError(
                {"machine": ("Una venta resuelta debe tener una máquina asociada.")}
            )

        if self.status == self.Status.RESOLVED and self.product is None:
            raise ValidationError(
                {"product": ("Una venta resuelta debe tener un producto asociado.")}
            )

    def save(
        self,
        *args,
        **kwargs,
    ):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)

            if original.status == self.Status.RESOLVED:
                raise ValidationError("Una venta resuelta no puede modificarse.")

        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def delete(
        self,
        *args,
        **kwargs,
    ):
        raise ValidationError("Las ventas recibidas no pueden eliminarse.")

    def __str__(self):
        return f"{self.event_id} - {self.machine_identifier} - {self.selection}"

    class Meta:
        ordering = [
            "-occurred_at",
            "-pk",
        ]
