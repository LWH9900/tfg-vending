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
]
