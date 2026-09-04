from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class Sale(models.Model):
    class DispenseType(models.TextChoices):
        PAID = "paid", "Con pago"
        FREE = "free", "Gratuita"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"  # recibida, pero no podemos resolverla todavía
        RESOLVED = (
            "resolved",
            "Resuelta",
        )  # venta efectiva correctamente; cuenta para inventario
        CONFLICT = (
            "conflict",
            "En conflicto",
        )  # mismo event_id, distinto contenido; no cuenta para inventario
        REJECTED = "rejected", "Descartada"  # revisada y descartada; no cuenta
        VOIDED = (
            "voided",
            "Anulada",
        )  # antes fue efectiva, pero posteriormente se ha invalidado;
        # deja de contar para inventario

    class Source(models.TextChoices):
        TELEMETRY = "telemetry", "Telemetría"
        MANUAL = "manual", "Manual"

    void_reason = models.TextField(
        blank=True,
    )

    voided_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.TELEMETRY,
    )

    event_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    payload_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
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
        blank=True,
    )

    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )
    conflicts_with = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="conflicting_sales",
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

    raw_payload = models.JSONField(
        null=True,
        blank=True,
    )

    def clean(self):
        super().clean()

        if self.source == self.Source.TELEMETRY and not self.event_id:
            raise ValidationError(
                {
                    "event_id": (
                        "Una venta de telemetría debe tener un identificador de evento."
                    )
                }
            )

        if self.source == self.Source.TELEMETRY and self.raw_payload is None:
            raise ValidationError(
                {
                    "raw_payload": (
                        "Una venta de telemetría debe conservar el JSON recibido."
                    )
                }
            )

        if self.source == self.Source.TELEMETRY and not self.selection:
            raise ValidationError(
                {
                    "selection": (
                        "Una venta de telemetría debe indicar la selección recibida."
                    )
                }
            )

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

        if self.status == self.Status.VOIDED and not self.void_reason.strip():
            raise ValidationError(
                {
                    "void_reason": (
                        "Una venta anulada debe indicar el motivo de la anulación."
                    )
                }
            )

        if self.status == self.Status.VOIDED and self.voided_at is None:
            raise ValidationError(
                {
                    "voided_at": (
                        "Una venta anulada debe conservar la fecha de anulación."
                    )
                }
            )

        if self.status == self.Status.CONFLICT and self.conflicts_with is None:
            raise ValidationError(
                {
                    "conflicts_with": (
                        "Una venta en conflicto debe indicar "
                        "con qué venta entra en conflicto."
                    )
                }
            )

        if (
            self.conflicts_with is not None
            and self.pk is not None
            and self.conflicts_with_id == self.pk
        ):
            raise ValidationError(
                {
                    "conflicts_with": (
                        "Una venta no puede entrar en conflicto consigo misma."
                    )
                }
            )

        if (
            self.conflicts_with is not None
            and self.event_id != self.conflicts_with.event_id
        ):
            raise ValidationError(
                {
                    "conflicts_with": (
                        "Las ventas relacionadas por un conflicto "
                        "deben compartir el mismo identificador "
                        "de evento."
                    )
                }
            )

    def save(
        self,
        *args,
        **kwargs,
    ):
        if self.pk:
            original = type(self).objects.get(pk=self.pk)

            immutable_fields = (
                "source",
                "event_id",
                "payload_hash",
                "machine_identifier",
                "selection",
                "occurred_at",
                "quantity",
                "dispense_type",
                "unit_price",
                "amount_received",
                "payment_method",
                "raw_payload",
            )

            if original.source == self.Source.TELEMETRY:
                for field in immutable_fields:
                    if getattr(original, field) != getattr(self, field):
                        raise ValidationError(
                            "Los datos originales de una venta "
                            "de telemetría no pueden modificarse."
                        )

            if original.status == self.Status.RESOLVED:
                if self.status != self.Status.VOIDED:
                    raise ValidationError(
                        "Una venta resuelta solo puede pasar "
                        "a anulada mediante una operación "
                        "controlada."
                    )

                resolved_immutable_fields = (
                    "source",
                    "event_id",
                    "payload_hash",
                    "machine_identifier",
                    "machine_id",
                    "selection",
                    "product_id",
                    "occurred_at",
                    "quantity",
                    "dispense_type",
                    "unit_price",
                    "amount_received",
                    "payment_method",
                    "raw_payload",
                    "conflicts_with_id",
                )

                for field in resolved_immutable_fields:
                    if getattr(original, field) != getattr(self, field):
                        raise ValidationError(
                            "Los datos de una venta resuelta no pueden modificarse."
                        )

            if original.status in (
                self.Status.REJECTED,
                self.Status.VOIDED,
            ):
                raise ValidationError("Una venta finalizada no puede modificarse.")

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
        identifier = self.event_id if self.event_id else f"Manual #{self.pk or 'nueva'}"

        return (
            f"{identifier} - "
            f"{self.machine_identifier} - "
            f"{self.selection or 'sin selección'}"
        )

    class Meta:
        ordering = [
            "-occurred_at",
            "-pk",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "event_id",
                    "payload_hash",
                ],
                condition=models.Q(
                    source="telemetry",
                ),
                name=("unique_telemetry_event_payload"),
            ),
            models.UniqueConstraint(
                fields=[
                    "event_id",
                ],
                condition=models.Q(
                    status="resolved",
                    event_id__isnull=False,
                ),
                name=("unique_resolved_sale_per_event"),
            ),
        ]
