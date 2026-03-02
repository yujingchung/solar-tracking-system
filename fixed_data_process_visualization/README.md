# 固定式太陽能板數據處理系統

## 🚀 快速開始

### 方法一：使用整合界面（推薦新手）

```bash
python solar_data_pipeline.py
```

然後按照界面指示操作即可！

### 方法二：手動執行（適合進階用戶）

1. **檔案重命名**
   ```bash
   python "convert name1.py"
   ```

2. **功率計算**
   ```bash
   python "power calculation2.py"
   ```

3. **發電量匯總**
   ```bash
   python "power summary3.py"
   ```

4. **數據預處理**
   ```bash
   python "data preprocessing4.py"
   ```

5. **數據合併**（如有多個時段）
   ```bash
   python "combine data 5.py"
   ```

6. **視覺化分析**
   ```bash
   python fixed_panel_data_visualization.py
   ```

## 📚 完整文檔

詳細的使用說明請查看：**[使用手冊.md](使用手冊.md)**

## 💻 環境需求

- Python 3.8+
- 必要套件：
  ```bash
  pip install pandas numpy matplotlib pytz pvlib
  ```

## 📁 系統文件列表

| 文件名 | 功能 |
|-------|------|
| `solar_data_pipeline.py` | 整合界面（主程式） |
| `convert name1.py` | 步驟1: 檔案重命名 |
| `power calculation2.py` | 步驟2: 功率計算 |
| `power summary3.py` | 步驟3: 發電量匯總 |
| `data preprocessing4.py` | 步驟4: 數據預處理 |
| `combine data 5.py` | 步驟5: 數據合併 |
| `fixed_panel_data_visualization.py` | 步驟6: 數據視覺化 |
| `使用手冊.md` | 完整使用手冊 |
| `README.md` | 本文件 |

## 🎯 處理流程圖

```
原始CSV → [1]重命名 → [2]功率計算 → [3]發電量匯總 
           → [4]數據預處理 → [5]合併（可選） → [6]視覺化
```

## ⭐ 主要特色

- ✅ 自動處理多個太陽能板數據
- ✅ 計算太陽位置信息
- ✅ 支援多年份、多月份數據分析
- ✅ 互動式圖表視覺化
- ✅ 完整的數據處理管線
- ✅ 圖形化界面，操作簡單

## 📊 視覺化工具功能

- 📅 日期比較圖表
- 🔆 面板比較圖表
- 📈 月度統計圖表
- 🗓️ 年份/月份選擇
- 🎨 可自訂圖例位置
- 📐 角度篩選功能

## 🆘 需要幫助？

1. 查看 **[使用手冊.md](使用手冊.md)** 了解詳細操作步驟
2. 檢查「常見問題」章節
3. 確認 Python 版本和套件是否正確安裝

## 📝 版本資訊

- **版本**: 2.0
- **更新日期**: 2026-01-21
- **新功能**: 
  - ✨ 新增整合界面 `solar_data_pipeline.py`
  - ✨ 視覺化工具支援年份選擇
  - ✨ 完整的使用手冊

## 👨‍💻 開發者

宇靖 - 太陽能追蹤系統研究

---

**開始使用**: `python solar_data_pipeline.py` 🚀
