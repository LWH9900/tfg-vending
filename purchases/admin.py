from django.contrib import admin

from .models import Purchase, PurchaseLine

admin.site.register(Purchase)
admin.site.register(PurchaseLine)
