from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SystemGroupViewSet, PowerRecordViewSet, RealTimeDataViewSet

router = DefaultRouter()
router.register(r'systems', SystemGroupViewSet)
router.register(r'power-records', PowerRecordViewSet)
router.register(r'realtime-data', RealTimeDataViewSet, basename='realtime-data')

urlpatterns = [
    path('', include(router.urls)),
]