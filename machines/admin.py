from django.contrib import admin

from .models import Machine, MachinePriceOverride, PricingProfile

admin.site.register(Machine)
admin.site.register(PricingProfile)
admin.site.register(MachinePriceOverride)
