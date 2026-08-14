from django.urls import path

from . import views

app_name = "machines"

urlpatterns = [
    path("", views.machine_list, name="machine_list"),
    path("new/", views.machine_create, name="machine_create"),
    path("<int:pk>/", views.machine_detail, name="machine_detail"),
    path("edit/<int:pk>/", views.machine_update, name="machine_update"),
]
