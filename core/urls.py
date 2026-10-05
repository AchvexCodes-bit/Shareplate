from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("listings/", views.listings, name="listings"),
    path("listings/create/", views.create_listing, name="create_listing"),
    path("listings/<int:pk>/reserve/", views.reserve, name="reserve"),
    path("listings/<int:pk>/<str:action>/", views.listing_action, name="listing_action"),
    path("reservations/<int:pk>/cancel/", views.cancel_reservation_view, name="cancel_reservation"),
    path("reservations/<int:pk>/<str:action>/", views.reservation_action, name="reservation_action"),
    path("pickups/<int:pk>/confirm/", views.confirm_delivery, name="confirm_delivery"),
    path("courier/", views.courier_dashboard, name="courier"),
    path("courier/<int:pk>/<str:action>/", views.pickup_action, name="pickup_action"),
    path("admin/organizations/<int:pk>/<str:action>/", views.admin_organization_action, name="admin_organization_action"),
    path("admin/pickups/<int:pk>/assign/", views.admin_assign_pickup, name="admin_assign_pickup"),
    path("complaints/create/", views.complaint_create, name="complaint_create"),
    path("complaints/<int:pk>/<str:action>/", views.complaint_action, name="complaint_action"),
    path("notifications/", views.notifications, name="notifications"),
    path("impact/", views.impact, name="impact"),
    path("api/impact/", views.impact_api, name="impact_api"),
]
