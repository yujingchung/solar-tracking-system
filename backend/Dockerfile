FROM python:3.12

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 安裝MySQL相關套件
RUN apt-get update
RUN apt-get install gcc default-libmysqlclient-dev mariadb-client -y
RUN apt-get install -y iputils-ping

# 安裝Python套件
RUN pip install -U pip setuptools wheel
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

# 複製專案檔案
COPY . .

# 轉換腳本格式
RUN apt-get install dos2unix
RUN dos2unix --newfile docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 安裝網路工具
RUN apt install netcat-traditional -y

ENTRYPOINT ["bash", "/usr/local/bin/docker-entrypoint.sh"]