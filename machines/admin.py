from django.contrib import admin

from .models import Machine,PricingProfile, MachinePriceOverride, MachineLayout, MachinePosition, MachineLayoutActivation

admin.site.register(Machine)
admin.site.register(PricingProfile)
admin.site.register(MachinePriceOverride)
admin.site.register(MachineLayout)
admin.site.register(MachinePosition)
admin.site.register(MachineLayoutActivation)


