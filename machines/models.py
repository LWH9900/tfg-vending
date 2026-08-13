from django.db import models


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

    def __str__(self):
        return f"{self.identifier} - {self.name}"
