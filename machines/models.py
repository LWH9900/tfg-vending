from django.core.exceptions import ValidationError
from django.db import models


class PricingProfile(models.Model):
    name = models.CharField(
        max_length=100,
    )

    percentage_adjustment = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.name} ({self.percentage_adjustment:+.2f} %)"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "name",
                    "percentage_adjustment",
                ],
                name="unique_pricing_profile_name_adjustment",
            ),
        ]


class Machine(models.Model):
    identifier = models.CharField(
        max_length=50,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
    )

    location = models.CharField(
        max_length=255,
        blank=True,
    )

    serial_number = models.CharField(
        max_length=100,
        unique=True,
    )

    pricing_profile = models.ForeignKey(
        PricingProfile,
        on_delete=models.PROTECT,
        related_name="machines",
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"{self.identifier} - {self.name}"


class MachinePriceOverride(models.Model):
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="price_overrides",
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        related_name="machine_price_overrides",
    )

    percentage_adjustment = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    def clean(self):
        super().clean()

        pricing_profile = self.machine.pricing_profile

        if (
            pricing_profile
            and self.percentage_adjustment == pricing_profile.percentage_adjustment
        ):
            raise ValidationError(
                {
                    "percentage_adjustment": (
                        "El ajuste específico debe ser diferente "
                        "al de la tarifa general de la máquina."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.machine.identifier} - "
            f"{self.product.name} "
            f"({self.percentage_adjustment:+.2f} %)"
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "machine",
                    "product",
                ],
                name="unique_machine_product_price_override",
            ),
        ]
