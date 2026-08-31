from django.urls import path

from . import views

app_name = "machines"

urlpatterns = [
    path("", views.machine_list, name="machine_list"),
    path("new/", views.machine_create, name="machine_create"),
    path("<int:pk>/", views.machine_detail, name="machine_detail"),
    path("edit/<int:pk>/", views.machine_update, name="machine_update"),
    path(
        "<int:pk>/pricing/",
        views.machine_pricing_profile_update,
        name="machine_pricing_profile_update",
    ),
    path(
        "<int:pk>/pricing/overrides/new/",
        views.machine_price_override_create,
        name="machine_price_override_create",
    ),
    path(
        "<int:machine_pk>/pricing/overrides/<int:override_pk>/edit/",
        views.machine_price_override_update,
        name="machine_price_override_update",
    ),
    path(
        "<int:machine_pk>/pricing/overrides/<int:override_pk>/delete/",
        views.machine_price_override_delete,
        name="machine_price_override_delete",
    ),
    path(
        "pricing-profiles/",
        views.pricing_profile_list,
        name="pricing_profile_list",
    ),
    path(
        "pricing-profiles/new/",
        views.pricing_profile_create,
        name="pricing_profile_create",
    ),
    path(
        "pricing-profiles/<int:pk>/delete/",
        views.pricing_profile_delete,
        name="pricing_profile_delete",
    ),
    path(
        "<int:machine_pk>/layouts/new/",
        views.machine_layout_create,
        name="machine_layout_create",
    ),
    path(
        "layouts/<int:pk>/edit/",
        views.machine_layout_edit,
        name="machine_layout_edit",
    ),
    path(
        "layouts/<int:pk>/activate/",
        views.machine_layout_activate,
        name="machine_layout_activate",
    ),
    path(
        "<int:machine_pk>/layouts/",
        views.machine_layout_list,
        name="machine_layout_list",
    ),
    path(
        "layouts/<int:pk>/",
        views.machine_layout_detail,
        name="machine_layout_detail",
    ),
]
