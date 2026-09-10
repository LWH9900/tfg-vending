from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.purchase_list, name="purchase_list"),
    path("<int:pk>/", views.purchase_detail, name="purchase_detail"),
    path(
        "new/",
        views.purchase_create,
        name="purchase_create",
    ),
    path(
        "<int:pk>/edit/",
        views.purchase_edit,
        name="purchase_edit",
    ),
    path(
        "<int:pk>/register/",
        views.purchase_register,
        name="purchase_register",
    ),
    path(
        "<int:pk>/delete/",
        views.purchase_delete,
        name="purchase_delete",
    ),
    path(
        "<int:pk>/cancel/",
        views.purchase_cancel,
        name="purchase_cancel",
    ),
]
