import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 安全設定
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-default-secret-key')
DEBUG = int(os.environ.get('DEBUG', default=0))
YOUR_PUBLIC_IP = "140.114.59.214"  # 替換為實際IP
YOUR_LOCAL_IP = "192.168.0.100"
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1', 
    '192.168.0.124',
    YOUR_PUBLIC_IP, # 192.168.0.100  # 你的公網IP
    YOUR_LOCAL_IP,     
]

#DEBUG = False  # 生產環境設定
# 應用程式
INSTALLED_APPS = [
    'admin_interface',          # 美化後台
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # 第三方套件
    'rest_framework',
    'django_filters',
    'corsheaders',
    'drf_spectacular',
    'import_export',
    
    # 自己的應用程式
    'dashboard',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pmp_solar_dashboard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],  # 添加模板目錄
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# 資料庫設定
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('SQL_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.environ.get('SQL_DATABASE', 'solar_tracking_db'),
        'USER': os.environ.get('SQL_USER', 'solar_user'),
        'PASSWORD': os.environ.get('SQL_PASSWORD', 'userpassword123'),
        'HOST': os.environ.get('SQL_HOST', 'localhost'),
        'PORT': os.environ.get('SQL_PORT', '3306'),
    }
}

# 國際化
LANGUAGE_CODE = 'zh-hant'
TIME_ZONE = 'Asia/Taipei'
USE_I18N = True
USE_TZ = True

# 靜態檔案
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 添加靜態檔案目錄
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# REST Framework設定
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,  # 每頁顯示 20 筆記錄
}

# CORS設定
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://140.114.59.214:3000",
    "http://140.114.59.214:8000",
    "http://192.168.0.100:3000",
    "http://192.168.0.100:8000",
]

# 認證設定
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'