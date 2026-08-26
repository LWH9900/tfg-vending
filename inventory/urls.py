from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/new/", views.product_create, name="product_create"),
    path("products/edit/<int:pk>", views.product_update, name="product_update"),
    path(
        "products/<int:pk>/stock/",
        views.product_stock_detail,
        name="product_stock_detail",
    ),
]
