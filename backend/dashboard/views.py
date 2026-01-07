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
        from datetime import timedelta
        from django.utils import timezone
        
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
        
        # 日期範圍過濾 - 預設查詢最近 7 天
        days = self.request.query_params.get('days', '7')
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date and end_date:
            # 使用自訂日期範圍
            try:
                queryset = queryset.filter(
                    timestamp__date__gte=start_date,
                    timestamp__date__lte=end_date
                )
            except Exception:
                pass  # 日期格式錯誤時忽略
        elif days != 'all':
            # 使用天數過濾
            try:
                days_int = int(days)
                start_time = timezone.now() - timedelta(days=days_int)
                queryset = queryset.filter(timestamp__gte=start_time)
            except (ValueError, TypeError):
                # 預設使用 7 天
                start_time = timezone.now() - timedelta(days=7)
                queryset = queryset.filter(timestamp__gte=start_time)
        
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
    
    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """匯出CSV格式的數據記錄"""
        import csv
        from django.http import HttpResponse
        from datetime import datetime
        
        try:
            system_id = request.query_params.get('system')
            queryset = self.get_queryset()
            
            if system_id:
                try:
                    system_id = int(system_id)
                    queryset = queryset.filter(system_id=system_id)
                except (ValueError, TypeError):
                    pass
            
            # 建立HTTP response with CSV content type
            response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            response['Content-Disposition'] = f'attachment; filename="power_records_{timestamp}.csv"'
            
            writer = csv.writer(response)
            
            # CSV標頭
            writer.writerow([
                '時間戳',
                '系統',
                '太陽能板電壓(V)', '太陽能板電流(A)', '太陽能板功率(W)',
                '樹莓派電壓(V)', '樹莓派電流(mA)', '樹莓派功率(W)',
                '南北推桿角度(°)', '南北推桿伸展(mm)',
                '東西推桿角度(°)', '東西推桿伸展(mm)',
                '推桿總電壓(V)', '推桿總電流(mA)', '推桿總功率(W)',
                '光照強度(lux)', '溫度(°C)', '濕度(%)',
                '備註'
            ])
            
            # 寫入數據
            for record in queryset[:1000]:  # 限制最多1000筆
                writer.writerow([
                    record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    record.system.name if record.system else '',
                    f"{record.voltage:.2f}" if record.voltage else '',
                    f"{record.current:.3f}" if record.current else '',
                    f"{record.power_output:.2f}" if record.power_output else '',
                    f"{record.raspberry_pi_voltage:.2f}" if record.raspberry_pi_voltage else '',
                    f"{record.raspberry_pi_current:.1f}" if record.raspberry_pi_current else '',
                    f"{record.raspberry_pi_power:.2f}" if record.raspberry_pi_power else '',
                    f"{record.ns_actuator_angle:.1f}" if record.ns_actuator_angle else '',
                    f"{record.ns_actuator_extension:.0f}" if record.ns_actuator_extension else '',
                    f"{record.ew_actuator_angle:.1f}" if record.ew_actuator_angle else '',
                    f"{record.ew_actuator_extension:.0f}" if record.ew_actuator_extension else '',
                    f"{record.actuator_total_voltage:.2f}" if record.actuator_total_voltage else '',
                    f"{record.actuator_total_current:.1f}" if record.actuator_total_current else '',
                    f"{record.actuator_total_power:.2f}" if record.actuator_total_power else '',
                    f"{record.light_intensity:.1f}" if record.light_intensity else '',
                    f"{record.temperature:.1f}" if record.temperature else '',
                    f"{record.humidity:.1f}" if record.humidity else '',
                    record.notes or ''
                ])
            
            return response
            
        except Exception as e:
            return Response(
                {"error": f"匯出失敗: {str(e)}"}, 
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
                power_record = PowerRecord(
                    system_id=data['system_id'],
                    voltage=data['voltage'],
                    current=data['current'],
                    power_output=data.get('power_output', data['voltage'] * data['current']),
                    light_intensity=data.get('light_intensity'),
                    temperature=data.get('temperature'),
                    humidity=data.get('humidity'),
                    panel_azimuth=data.get('panel_azimuth'),
                    panel_tilt=data.get('panel_tilt'),
                    notes=data.get('notes', '')
                )
                
                # 樹莓派電源數據
                power_record.raspberry_pi_voltage = data.get('raspberry_pi_voltage')
                power_record.raspberry_pi_current = data.get('raspberry_pi_current')
                power_record.raspberry_pi_power = data.get('raspberry_pi_power')
                
                # 南北推桿
                power_record.ns_actuator_angle = data.get('ns_actuator_angle')
                power_record.ns_actuator_extension = data.get('ns_actuator_extension')
                
                # 東西推桿
                power_record.ew_actuator_angle = data.get('ew_actuator_angle')
                power_record.ew_actuator_extension = data.get('ew_actuator_extension')
                
                # 推桿總功率
                power_record.actuator_total_voltage = data.get('actuator_total_voltage')
                power_record.actuator_total_current = data.get('actuator_total_current')
                power_record.actuator_total_power = data.get('actuator_total_power')
                
                # 舊版推桿欄位（保留向下相容）
                power_record.actuator_voltage = data.get('actuator_voltage')
                power_record.actuator_current = data.get('actuator_current')
                power_record.actuator_power = data.get('actuator_power')
                power_record.actuator_angle = data.get('actuator_angle')
                power_record.actuator_extension = data.get('actuator_extension')
                
                # 保存記錄
                power_record.save()
                
                return Response({
                    "status": "success",
                    "message": "數據已保存",
                    "record_id": power_record.id
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": f"保存數據時發生錯誤: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                "status": "error",
                "message": "數據驗證失敗",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)