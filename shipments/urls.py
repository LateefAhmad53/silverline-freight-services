from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("services/", views.services, name="services"),
    path("backend/login/", views.backend_login, name="backend_login"),
    path("backend/logout/", views.backend_logout, name="backend_logout"),
    path("backend/dashboard/", views.dashboard, name="dashboard"),
    path("backend/orders/create/", views.create_order, name="create_order"),
    path("backend/orders/<int:order_id>/hold/", views.place_hold, name="place_hold"),
    path("backend/orders/<int:order_id>/release/", views.release_hold, name="release_hold"),
    path("backend/orders/<int:order_id>/status/", views.update_status, name="update_status"),
    path("backend/orders/<int:order_id>/progress/", views.update_progress, name="update_progress"),
    path("backend/orders/<int:order_id>/edit/", views.edit_order, name="edit_order"),
    path("backend/orders/<int:order_id>/delete/", views.delete_order, name="delete_order"),
    path("backend/orders/<int:order_id>/receipt.jpg", views.download_receipt_jpg, name="download_receipt_jpg"),
]
