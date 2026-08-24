from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Purchase(models.Model):
    purchased_at = models.DateTimeField(
        default=timezone.now,
    )
    supplier = models.CharField(
        max_length=255,
    )
    document_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    @property
    def total(self):
        return sum(
            (line.total for line in self.lines.all()),
            start=Decimal("0.00"),
        )

    def __str__(self):
        return f"Compra {self.pk} - {self.supplier}"


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="purchase_lines",
    )
    quantity = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
        ],
    )
    unit_price_excl_vat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
        ],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="purchase_line_quantity_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price_excl_vat__gte=0),
                name="purchase_line_price_gte_0",
            ),
        ]

    @property
    def total(self):
        return self.quantity * self.unit_price_excl_vat

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
