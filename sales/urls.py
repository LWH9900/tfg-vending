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
    path(
        "<int:pk>/resolve/",
        views.sale_resolve,
        name="sale_resolve",
    ),
    path(
        "<int:pk>/void/",
        views.sale_void,
        name="sale_void",
    ),
    path(
        "<int:pk>/conflict/",
        views.sale_conflict_review,
        name="sale_conflict_review",
    ),
    path(
        "<int:pk>/conflict/accept/",
        views.sale_conflict_accept,
        name="sale_conflict_accept",
    ),
    path(
        "<int:pk>/conflict/reject/",
        views.sale_conflict_reject,
        name="sale_conflict_reject",
    ),
]
