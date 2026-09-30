from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('listings/', views.listings, name='listings'),
    path('listings/<int:pk>/reserve/', views.reserve, name='reserve'),
    path('courier/', views.courier_dashboard, name='courier'),
    path('courier/<int:pk>/<str:action>/', views.pickup_action, name='pickup_action'),
    path('notifications/', views.notifications, name='notifications'),
    path('impact/', views.impact, name='impact'),
    path('api/impact/', views.impact_api, name='impact_api'),
]
