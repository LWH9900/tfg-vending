from django.contrib import admin

from .models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
    MachinePosition,
    MachinePriceOverride,
    PricingProfile,
)

admin.site.register(Machine)
admin.site.register(PricingProfile)
admin.site.register(MachinePriceOverride)
admin.site.register(MachineLayout)
admin.site.register(MachinePosition)
admin.site.register(MachineLayoutActivation)
