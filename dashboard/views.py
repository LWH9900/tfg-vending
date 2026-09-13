from django.shortcuts import render

from dashboard.services import get_dashboard_data


def dashboard_home(request):
    context = get_dashboard_data()

    return render(
        request,
        "dashboard/home.html",
        context,
    )
