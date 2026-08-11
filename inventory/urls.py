from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("productos/", views.product_list, name="product_list"),
    path("productos/<int:pk>/", views.product_detail, name="product_detail"),
]
