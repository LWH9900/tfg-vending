from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    path("", views.purchase_list, name="purchase_list"),
    path("<int:pk>/", views.purchase_detail, name="purchase_detail"),
]
