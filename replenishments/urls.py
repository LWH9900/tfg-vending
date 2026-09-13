from django.urls import path

from . import views

app_name = "replenishments"

urlpatterns = [
    path(
        "",
        views.replenishment_list,
        name="replenishment_list",
    ),
    path(
        "<int:pk>/",
        views.replenishment_detail,
        name="replenishment_detail",
    ),
    path(
        "new/",
        views.replenishment_create,
        name="replenishment_create",
    ),
    path(
        "active-products/<int:machine_pk>/",
        views.active_products,
        name="active_products",
    ),
    path(
        "<int:pk>/edit/",
        views.replenishment_edit,
        name="replenishment_edit",
    ),
    path(
        "<int:pk>/register/",
        views.replenishment_register,
        name="replenishment_register",
    ),
    path(
        "<int:pk>/delete/",
        views.replenishment_delete,
        name="replenishment_delete",
    ),
    path(
        "<int:pk>/cancel/",
        views.replenishment_cancel,
        name="replenishment_cancel",
    ),
]
