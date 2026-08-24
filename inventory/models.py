from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    default_vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
    )

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=100)

    format_unit = models.CharField(max_length=100)

    default_sale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(0),
        ],
    )

    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )

    is_active = models.BooleanField(default=True)

    @property
    def latest_purchase_cost(self):
        latest_line = (
            self.purchase_lines.select_related("purchase")
            .order_by(
                "-purchase__purchased_at",
                "-purchase_id",
                "-pk",
            )
            .first()
        )

        if latest_line is None:
            return None

        return latest_line.unit_price_excl_vat

    @property
    def average_purchase_cost(self):
        totals = self.purchase_lines.aggregate(
            total_quantity=Sum("quantity"),
            total_cost=Sum(
                ExpressionWrapper(
                    F("quantity") * F("unit_price_excl_vat"),
                    output_field=DecimalField(
                        max_digits=20,
                        decimal_places=2,
                    ),
                )
            ),
        )

        total_quantity = totals["total_quantity"]
        total_cost = totals["total_cost"]

        if not total_quantity:
            return None

        return total_cost / Decimal(total_quantity)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "category", "format_unit"],
                name="unique_product_name_category_format",
            ),
        ]
