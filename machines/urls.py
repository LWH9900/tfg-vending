from django.urls import path

from . import views

app_name = "machines"

urlpatterns = [
    path("", views.machine_list, name="machine_list"),
    path("<int:pk>/", views.machine_detail, name="machine_detail"),
]
