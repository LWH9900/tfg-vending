from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("categories/", views.category_list, name="category_list"),
    path("categories/new/", views.category_create, name="category_create"),
    path(
        "categories/<int:pk>/edit/",
        views.category_update,
        name="category_update",
    ),
    path(
        "categories/<int:pk>/delete/",
        views.category_delete,
        name="category_delete",
    ),
    path("products/", views.product_list, name="product_list"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/new/", views.product_create, name="product_create"),
    path("products/edit/<int:pk>", views.product_update, name="product_update"),
    path(
        "products/<int:pk>/stock/",
        views.product_stock_detail,
        name="product_stock_detail",
    ),
    path(
        "stock/",
        views.inventory_overview,
        name="inventory_overview",
    ),
]
