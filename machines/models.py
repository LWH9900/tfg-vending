from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class PricingProfile(models.Model):
    name = models.CharField(max_length=100)

    percentage_adjustment = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.name} ({self.percentage_adjustment:+.2f} %)"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "percentage_adjustment",
                name="unique_pricing_profile_name_adjustment_ci",
                violation_error_message=(
                    "Ya existe una tarifa con el mismo nombre y la misma variación."
                ),
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


class MachineLayout(models.Model):
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="layouts",
    )
    name = models.CharField(max_length=100)

    @property
    def has_been_activated(self):
        return self.activations.exists()

    def save(self, *args, **kwargs):
        if self.pk:
            original = MachineLayout.objects.get(pk=self.pk)

            if original.has_been_activated:
                raise ValidationError(
                    "Una disposición que ya ha sido activada no puede modificarse."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.has_been_activated:
            raise ValidationError(
                "Una disposición que ya ha sido activada no puede eliminarse."
            )

        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.machine.identifier} - {self.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "machine",
                name="unique_machine_layout_name_ci",
            ),
        ]


class MachinePosition(models.Model):
    layout = models.ForeignKey(
        MachineLayout,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    identifier = models.CharField(max_length=20)
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="machine_positions",
        blank=True,
        null=True,
    )

    def save(self, *args, **kwargs):
        if self.pk:
            original = MachinePosition.objects.select_related("layout").get(pk=self.pk)

            if original.layout.has_been_activated:
                raise ValidationError(
                    "Las posiciones de una disposición que ya "
                    "ha sido activada no pueden modificarse."
                )

        if self.layout.has_been_activated:
            raise ValidationError(
                "No se pueden añadir o modificar posiciones "
                "en una disposición que ya ha sido activada."
            )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.layout.has_been_activated:
            raise ValidationError(
                "Las posiciones de una disposición que ya "
                "ha sido activada no pueden eliminarse."
            )

        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.layout.machine.identifier} - {self.identifier}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("identifier"),
                "layout",
                name="unique_layout_position_identifier_ci",
            ),
        ]


class MachineLayoutActivation(models.Model):
    layout = models.ForeignKey(
        MachineLayout,
        on_delete=models.PROTECT,
        related_name="activations",
    )

    effective_from = models.DateTimeField()

    def __str__(self):
        return f"{self.layout} - {self.effective_from:%d/%m/%Y %H:%M}"

    class Meta:
        ordering = [
            "effective_from",
            "pk",
        ]
