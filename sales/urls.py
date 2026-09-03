from django.urls import path

from . import views

app_name = "sales"


urlpatterns = [
    path(
        "receive/",
        views.sale_receive,
        name="sale_receive",
    ),
]
