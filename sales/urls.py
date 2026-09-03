from django.urls import path

from . import views

app_name = "sales"


urlpatterns = [
    path(
        "",
        views.sale_list,
        name="sale_list",
    ),
    path(
        "<int:pk>/",
        views.sale_detail,
        name="sale_detail",
    ),
    path(
        "receive/",
        views.sale_receive,
        name="sale_receive",
    ),
    path(
        "<int:pk>/payload/",
        views.sale_payload_download,
        name="sale_payload_download",
    ),
]
