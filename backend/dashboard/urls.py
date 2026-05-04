from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SystemGroupViewSet, PowerRecordViewSet, RealTimeDataViewSet
from .fixed_panel_api import (
    FixedPanelSummaryView,
    FixedPanelPowerCurveView,
    FixedPanelMonthlyView,
    FixedPanelDailyView,
    FixedPanelPanelListView,
    FixedPanelDayCurveView,
    FixedPanelPanelTrendView,
    FixedPanelRawCSVView,
    FixedPanelStatusView,
)
from .z3a_api import (
    Z3ADevicesView,
    Z3AHistoryView,
    Z3AStatusView,
    Z3ARefreshView,
)

router = DefaultRouter()
router.register(r'systems', SystemGroupViewSet)
router.register(r'power-records', PowerRecordViewSet)
router.register(r'realtime-data', RealTimeDataViewSet, basename='realtime-data')

urlpatterns = [
    path('', include(router.urls)),
    path('fixed-panels/summary/',      FixedPanelSummaryView.as_view(),     name='fp-summary'),
    path('fixed-panels/power-curve/',  FixedPanelPowerCurveView.as_view(),  name='fp-power-curve'),
    path('fixed-panels/monthly/',      FixedPanelMonthlyView.as_view(),     name='fp-monthly'),
    path('fixed-panels/daily/',        FixedPanelDailyView.as_view(),       name='fp-daily'),
    path('fixed-panels/panel-list/',   FixedPanelPanelListView.as_view(),   name='fp-panel-list'),
    path('fixed-panels/day-curve/',    FixedPanelDayCurveView.as_view(),    name='fp-day-curve'),
    path('fixed-panels/panel-trend/',  FixedPanelPanelTrendView.as_view(),  name='fp-panel-trend'),
    path('fixed-panels/raw-csv/',      FixedPanelRawCSVView.as_view(),      name='fp-raw-csv'),
    path('fixed-panels/status/',       FixedPanelStatusView.as_view(),      name='fp-status'),
    # Z3A IoT 採集裝置
    path('z3a/devices/',  Z3ADevicesView.as_view(),  name='z3a-devices'),
    path('z3a/history/',  Z3AHistoryView.as_view(),  name='z3a-history'),
    path('z3a/status/',   Z3AStatusView.as_view(),   name='z3a-status'),
    path('z3a/refresh/',  Z3ARefreshView.as_view(),  name='z3a-refresh'),
]
