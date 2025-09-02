# 太陽能追日系統 (Solar Tracking System)

基於ANFIS演算法的智慧太陽能追日系統

## 專案概述

本專案是一個基於樹莓派的智慧太陽能追日系統，整合了ANFIS演算法，用於優化太陽能板的追日效率。

## 功能特色

-  智慧追日演算法 (ANFIS)
-  實時監控系統 (Django後端)  
-  硬體控制整合 (樹莓派)
-  數據分析與可視化

## 專案狀態

目前版本: **v0.1-alpha**

-  Django後端API
-  資料收集系統
-  基本監控介面
-  樹莓派控制程式 (開發中)
-  ANFIS演算法 (開發中)

## 快速開始

1. 啟動Docker環境: `docker-compose -f docker-compose-dev.yml up -d`
2. 訪問系統: http://192.168.0.100:8000/dashboard/

## 授權

MIT License