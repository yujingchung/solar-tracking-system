from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.utils import timezone
from django.db import models
from .models import SystemGroup, PowerRecord
from .serializers import (
    SystemGroupSerializer, 
    PowerRecordSerializer, 
    RealTimeDataSerializer
)

class SystemGroupViewSet(viewsets.ModelViewSet):
    queryset = SystemGroup.objects.all()
    serializer_class = SystemGroupSerializer

class PowerRecordViewSet(viewsets.ModelViewSet):
    queryset = PowerRecord.objects.all()
    serializer_class = PowerRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # 修正過濾器設定
    filterset_fields = {
        'system': ['exact'],
        'timestamp': ['date', 'date__gte', 'date__lte'],
    }
    
    search_fields = ['system__name', 'notes']
    ordering_fields = ['timestamp', 'power_output']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        """優化查詢並處理過濾"""
        queryset = PowerRecord.objects.select_related('system').all()
        
        # 手動處理system過濾，避免過濾器錯誤
        system_id = self.request.query_params.get('system', None)
        if system_id is not None:
            try:
                system_id = int(system_id)
                queryset = queryset.filter(system_id=system_id)
            except (ValueError, TypeError):
                # 如果system_id不是有效整數，返回空查詢集
                queryset = queryset.none()
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        """獲取最新記錄"""
        try:
            system_id = request.query_params.get('system')
            
            if system_id:
                try:
                    system_id = int(system_id)
                    latest_record = self.get_queryset().filter(system_id=system_id).first()
                except (ValueError, TypeError):
                    return Response(
                        {"error": "無效的系統ID"}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                latest_record = self.get_queryset().first()
            
            if latest_record:
                serializer = self.get_serializer(latest_record)
                return Response(serializer.data)
            
            return Response(
                {"message": "沒有找到記錄"}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        except Exception as e:
            return Response(
                {"error": f"伺服器錯誤: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RealTimeDataViewSet(viewsets.ViewSet):
    """專門處理樹莓派實時數據的API"""
    
    def create(self, request):
        """接收實時數據"""
        serializer = RealTimeDataSerializer(data=request.data)
        
        if serializer.is_valid():
            data = serializer.validated_data
            
            try:
                # 檢查系統是否存在
                try:
                    system = SystemGroup.objects.get(id=data['system_id'])
                except SystemGroup.DoesNotExist:
                    return Response({
                        "status": "error",
                        "message": f"系統ID {data['system_id']} 不存在"
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # 創建PowerRecord
                power_record = PowerRecord.objects.create(
                    system=system,
                    voltage=data['voltage'],
                    current=data['current'],
                    power_output=data.get('power_output', data['voltage'] * data['current']),
                    light_intensity=data.get('light_intensity'),
                    temperature=data.get('temperature'),
                    humidity=data.get('humidity'),
                    panel_azimuth=data.get('panel_azimuth'),
                    panel_tilt=data.get('panel_tilt'),
                    notes=data.get('notes', f"設備: {data.get('device_id', 'unknown')}")
                )
                
                return Response({
                    "status": "success",
                    "message": "數據記錄成功",
                    "record_id": power_record.id,
                    "power": power_record.power_output
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": f"數據庫錯誤: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            "status": "error",
            "message": "數據驗證失敗",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        """系統狀態檢查"""
        try:
            return Response({
                "status": "online",
                "timestamp": timezone.now(),
                "message": "實時數據API正常運行"
            })
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"系統錯誤: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)