from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
import os

@login_required
def dashboard_view(request):
    """需要登入才能訪問的儀表板"""
    static_file_path = os.path.join(settings.BASE_DIR, 'static', 'dashboard.html')
    try:
        with open(static_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='text/html')
    except FileNotFoundError:
        return HttpResponse('儀表板檔案未找到', status=404)

def home_redirect(request):
    """首頁重導向到儀表板"""
    return redirect('dashboard')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('dashboard.urls')),
    
    # 登入/登出頁面
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # 受保護的儀表板
    path('dashboard/', dashboard_view, name='dashboard'),
    path('', home_redirect, name='home'),
]

# 設定管理後台標題
admin.site.site_header = "太陽能追日系統管理"
admin.site.site_title = "太陽能追日系統"
admin.site.index_title = "歡迎使用太陽能追日系統管理後台"

# 開發環境下提供靜態檔案服務
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)