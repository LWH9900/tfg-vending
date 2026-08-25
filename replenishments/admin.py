from django.contrib import admin

from .models import Replenishment, ReplenishmentLine

admin.site.register(Replenishment)
admin.site.register(ReplenishmentLine)
