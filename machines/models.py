from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

MAX_MACHINE_ROWS = 20
MAX_MACHINE_COLUMNS = 20


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

    rows = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(MAX_MACHINE_ROWS),
        ],
    )

    columns = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(MAX_MACHINE_COLUMNS),
        ],
    )

    def clean(self):
        super().clean()

        if (self.rows is None) != (self.columns is None):
            raise ValidationError(
                {
                    "rows": (
                        "Las filas y columnas deben configurarse al mismo tiempo."
                    ),
                    "columns": (
                        "Las filas y columnas deben configurarse al mismo tiempo."
                    ),
                }
            )

        if self.pk:
            original = Machine.objects.get(pk=self.pk)

            dimensions_were_configured = (
                original.rows is not None and original.columns is not None
            )

            dimensions_changed = (
                original.rows != self.rows or original.columns != self.columns
            )

            if dimensions_were_configured and dimensions_changed:
                raise ValidationError(
                    "Las dimensiones de una máquina no pueden "
                    "modificarse una vez establecidas."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.identifier} - {self.name}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(rows__isnull=True, columns__isnull=True)
                    | Q(rows__isnull=False, columns__isnull=False)
                ),
                name="machine_grid_dimensions_both_set_or_null",
            ),
        ]


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
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        REGISTERED = "REGISTERED", "Registrada"

    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="layouts",
    )

    name = models.CharField(
        max_length=100,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    @property
    def has_been_activated(self):
        return self.activations.exists()

    def save(self, *args, **kwargs):
        if self.pk:
            original = MachineLayout.objects.get(pk=self.pk)

            if original.status == self.Status.REGISTERED:
                raise ValidationError(
                    "Una disposición registrada no puede modificarse."
                )

        super().save(*args, **kwargs)

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

    identifier = models.CharField(
        max_length=20,
    )

    row = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
        ],
    )

    column = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
        ],
    )

    width = models.PositiveSmallIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    height = models.PositiveSmallIntegerField(
        default=1,
        validators=[
            MinValueValidator(1),
        ],
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="machine_positions",
        blank=True,
        null=True,
    )

    def clean(self):
        super().clean()

        machine = self.layout.machine

        if machine.rows is None or machine.columns is None:
            raise ValidationError(
                "La cuadrícula de la máquina debe estar configurada "
                "antes de crear posiciones."
            )

        last_row = self.row + self.height - 1
        last_column = self.column + self.width - 1

        if last_row > machine.rows:
            raise ValidationError(
                {"height": ("La posición supera el número de filas de la máquina.")}
            )

        if last_column > machine.columns:
            raise ValidationError(
                {"width": ("La posición supera el número de columnas de la máquina.")}
            )

        other_positions = MachinePosition.objects.filter(
            layout=self.layout,
        )

        if self.pk:
            other_positions = other_positions.exclude(
                pk=self.pk,
            )

        for other in other_positions:
            other_last_row = other.row + other.height - 1
            other_last_column = other.column + other.width - 1

            rows_overlap = self.row <= other_last_row and last_row >= other.row

            columns_overlap = (
                self.column <= other_last_column and last_column >= other.column
            )

            if rows_overlap and columns_overlap:
                raise ValidationError(
                    "La posición se solapa con otra posición de la disposición."
                )

    def save(self, *args, **kwargs):
        if self.pk:
            original = MachinePosition.objects.select_related("layout").get(pk=self.pk)

            if original.layout.status == MachineLayout.Status.REGISTERED:
                raise ValidationError(
                    "Las posiciones de una disposición registrada "
                    "no pueden modificarse."
                )

        if self.layout.status == MachineLayout.Status.REGISTERED:
            raise ValidationError(
                "No se pueden añadir o modificar posiciones "
                "en una disposición registrada."
            )

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.layout.status == MachineLayout.Status.REGISTERED:
            raise ValidationError(
                "Las posiciones de una disposición registrada no pueden eliminarse."
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

    def clean(self):
        super().clean()

        if self.layout.status != MachineLayout.Status.REGISTERED:
            raise ValidationError(
                {"layout": ("Solo se puede activar una disposición registrada.")}
            )

    def __str__(self):
        return f"{self.layout} - {self.effective_from:%d/%m/%Y %H:%M}"

    class Meta:
        ordering = [
            "effective_from",
            "pk",
        ]
