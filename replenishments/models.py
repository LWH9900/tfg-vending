from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Replenishment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        REGISTERED = "REGISTERED", "Registrada"
        CANCELLED = "CANCELLED", "Anulada"

    replenished_at = models.DateTimeField(
        default=timezone.now,
    )

    machine = models.ForeignKey(
        "machines.Machine",
        on_delete=models.PROTECT,
        related_name="replenishments",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    def __str__(self):
        return f"Reposición {self.pk} - {self.machine.identifier}"


class ReplenishmentLine(models.Model):
    replenishment = models.ForeignKey(
        Replenishment,
        on_delete=models.CASCADE,
        related_name="lines",
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="replenishment_lines",
    )

    quantity = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
        ],
    )

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="replenishment_line_quantity_gt_0",
            ),
            models.UniqueConstraint(
                fields=[
                    "replenishment",
                    "product",
                ],
                name="unique_product_per_replenishment",
            ),
        ]
