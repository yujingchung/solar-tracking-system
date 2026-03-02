import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.colors as mcolors
from matplotlib.cm import get_cmap
import colorsys
# 設定字體為標楷體
plt.rcParams['font.family'] = ['DFKai-SB', 'Microsoft JhengHei', 'SimHei', 'KaiTi', 'SimSun', 'NSimSun']
plt.rcParams['axes.unicode_minus'] = False

# 打印可用字體
print("可用字體:")
for font in fm.findSystemFonts():
    try:
        font_name = fm.FontProperties(fname=font).get_name()
        if '楷' in font_name:
            print(f"找到楷體相關字體: {font_name}")
    except:
        pass


# 生成多達40個不同的顏色
def generate_distinct_colors(n):
    if n <= 10:
        # 使用 matplotlib 的 tab10 顏色方案
        cmap = get_cmap('tab10')
        return [cmap(i) for i in range(n)]
    elif n <= 20:
        # 結合 tab10 和 tab20 顏色方案
        cmap1 = get_cmap('tab10')
        cmap2 = get_cmap('tab20c')
        return [cmap1(i) for i in range(10)] + [cmap2(i) for i in range(n - 10)]
    else:
        # 使用 HSV 顏色空間生成均勻分布的顏色
        HSV_tuples = [(x * 1.0 / n, 0.8, 0.9) for x in range(n)]
        RGB_tuples = list(map(lambda x: colorsys.hsv_to_rgb(*x), HSV_tuples))
        return RGB_tuples


# 主應用程式類別
class SolarDataAnalyzer:
    def __init__(self, root, file_path=None):
        self.root = root
        self.root.title("太陽能發電數據分析工具")
        self.root.geometry("1200x800")

        # 讀取CSV檔案
        if file_path:
            self.load_data(file_path)
        else:
            # 範例檔案路徑
            try:
                file_path = r'D:\宇靖\先鋒\太陽能板採集數據\20250301_20260219\combined_solar_data_20250301_20260219.csv'
                self.load_data(file_path)
            except:
                messagebox.showerror("錯誤", "找不到預設數據文件，請重新指定文件路徑")
                return

        # 創建年份選擇框架
        self.year_frame = ttk.LabelFrame(root, text="選擇要分析的年份")
        self.year_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # 默認選擇最新的年份
        self.year_var = tk.IntVar(value=self.available_years[-1] if self.available_years else 2025)

        # 創建年份標籤
        year_label = ttk.Label(self.year_frame, text="年份:", font=("Arial", 12))
        year_label.pack(side=tk.LEFT, padx=10, pady=10)

        # 為每個可用年份創建按鈕
        year_buttons_frame = ttk.Frame(self.year_frame)
        year_buttons_frame.pack(side=tk.LEFT, padx=10, pady=10)

        for year in self.available_years:
            year_btn = ttk.Button(
                year_buttons_frame,
                text=f"{year}年",
                width=8,
                command=lambda y=year: self.set_year(y)
            )
            year_btn.pack(side=tk.LEFT, padx=5)

        # 添加當前年份顯示標籤
        self.year_display_label = ttk.Label(
            self.year_frame,
            text=f"目前選擇: {self.year_var.get()}年",
            font=("Arial", 12, "bold")
        )
        self.year_display_label.pack(side=tk.RIGHT, padx=20, pady=10)

        # 創建月份選擇框架
        self.month_frame = ttk.LabelFrame(root, text="選擇要分析的月份")
        self.month_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        # 初始化當前年份的可用月份
        self.current_year_months = self.get_months_for_year(self.year_var.get())

        # 默認選擇第一個可用月份
        self.month_var = tk.IntVar(value=self.current_year_months[0] if self.current_year_months else 1)

        # 創建月份數值顯示標籤
        self.month_value_label = ttk.Label(self.month_frame, text=f"{self.month_var.get()}月", font=("Arial", 12))
        self.month_value_label.pack(side=tk.LEFT, padx=10, pady=10)

        # 創建快速選擇按鈕框架
        self.month_buttons_frame = ttk.Frame(self.month_frame)
        self.month_buttons_frame.pack(side=tk.LEFT, padx=20, pady=10)

        # 創建月份按鈕
        self.create_month_buttons()

        # 添加當前月份顯示標籤
        self.month_display_label = ttk.Label(
            self.month_frame,
            text=f"目前顯示: {self.year_var.get()}年{self.month_var.get()}月份數據",
            font=("Arial", 12, "bold")
        )
        self.month_display_label.pack(side=tk.RIGHT, padx=20, pady=10)

        # 創建一個筆記本(Notebook)控件，用於存放多個標籤頁
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 創建日期比較頁面
        self.date_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.date_frame, text="日期比較")

        # 創建面板比較頁面
        self.panel_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.panel_frame, text="面板比較")

        # 創建月度累計頁面（新增）
        self.monthly_stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.monthly_stats_frame, text="月度統計")

        # 初始化當前選擇的月份數據
        self.current_month_data = None
        self.current_pivot_data = None
        self.current_month_avg = None

        # 處理數據
        self.process_data()

        # 初始化日期比較頁面
        self.init_date_comparison()

        # 初始化面板比較頁面
        self.init_panel_comparison()

        # 初始化月度統計頁面
        self.init_monthly_stats()

    def load_data(self, file_path):
        # 讀取CSV檔案
        self.df = pd.read_csv(file_path)

        # 將日期轉換為datetime格式
        self.df['date'] = pd.to_datetime(self.df['date'], format='mixed', dayfirst=False)

        # 新增年份、月份和日期欄位
        self.df['month'] = self.df['date'].dt.month
        self.df['day'] = self.df['date'].dt.day
        self.df['year'] = self.df['date'].dt.year

        # 確保角度欄位為數值型
        if 'azimuth_angle' in self.df.columns:
            try:
                self.df['azimuth_angle'] = pd.to_numeric(self.df['azimuth_angle'], errors='coerce')
            except Exception as e:
                print(f"無法將 azimuth_angle 轉換為數值: {e}")
                # 假如無法全部轉換為數值，則全部轉為字串
                self.df['azimuth_angle'] = self.df['azimuth_angle'].astype(str)

        if 'tilt_angle' in self.df.columns:
            try:
                self.df['tilt_angle'] = pd.to_numeric(self.df['tilt_angle'], errors='coerce')
            except Exception as e:
                print(f"無法將 tilt_angle 轉換為數值: {e}")
                self.df['tilt_angle'] = self.df['tilt_angle'].astype(str)

        # 獲取可用的年份和月份列表
        self.available_years = sorted(self.df['year'].unique())
        self.available_months = sorted(self.df['month'].unique())

    def set_month(self, month):
        """設置月份並更新介面"""
        if month == self.month_var.get():
            return  # 如果月份沒變，則不執行後續操作

        self.month_var.set(month)
        self.month_value_label.config(text=f"{month}月")
        self.month_display_label.config(text=f"目前顯示: {self.year_var.get()}年{month}月份數據")

        self.process_data()

        # 重新初始化頁面
        for widget in self.date_frame.winfo_children():
            widget.destroy()
        for widget in self.panel_frame.winfo_children():
            widget.destroy()
        for widget in self.monthly_stats_frame.winfo_children():
            widget.destroy()

        self.init_date_comparison()
        self.init_panel_comparison()
        self.init_monthly_stats()

    def set_year(self, year):
        """設置年份並更新介面"""
        if year == self.year_var.get():
            return  # 如果年份沒變，則不執行後續操作

        self.year_var.set(year)
        self.year_display_label.config(text=f"目前選擇: {year}年")

        # 更新當前年份的可用月份
        self.current_year_months = self.get_months_for_year(year)

        # 如果當前選擇的月份在新年份中不存在，則選擇第一個可用月份
        if self.month_var.get() not in self.current_year_months:
            if self.current_year_months:
                self.month_var.set(self.current_year_months[0])
                self.month_value_label.config(text=f"{self.current_year_months[0]}月")

        # 更新月份顯示標籤
        self.month_display_label.config(text=f"目前顯示: {year}年{self.month_var.get()}月份數據")

        # 重新創建月份按鈕
        self.create_month_buttons()

        # 重新處理數據
        self.process_data()

        # 重新初始化頁面
        for widget in self.date_frame.winfo_children():
            widget.destroy()
        for widget in self.panel_frame.winfo_children():
            widget.destroy()
        for widget in self.monthly_stats_frame.winfo_children():
            widget.destroy()

        self.init_date_comparison()
        self.init_panel_comparison()
        self.init_monthly_stats()

    def get_months_for_year(self, year):
        """獲取指定年份的可用月份列表"""
        year_data = self.df[self.df['year'] == year]
        return sorted(year_data['month'].unique())

    def create_month_buttons(self):
        """創建或更新月份選擇按鈕"""
        # 清除現有的月份按鈕
        for widget in self.month_buttons_frame.winfo_children():
            widget.destroy()

        # 為當前年份的每個可用月份創建按鈕
        for month in self.current_year_months:
            month_btn = ttk.Button(
                self.month_buttons_frame,
                text=f"{month}月",
                width=5,
                command=lambda m=month: self.set_month(m)
            )
            month_btn.pack(side=tk.LEFT, padx=5)

    def process_data(self):
        """處理當前選擇年份和月份的數據"""
        selected_year = self.year_var.get()
        selected_month = self.month_var.get()

        # 篩選出選擇年份和月份的數據
        self.current_month_data = self.df[
            (self.df['year'] == selected_year) & (self.df['month'] == selected_month)
        ]

        # 使用整點數據進行發電量分析
        whole_hour_month = self.current_month_data[
            self.current_month_data['hour_decimal'].apply(lambda x: x.is_integer())]

        # 按日期和小時分組計算平均發電量
        daily_hourly_power = whole_hour_month.groupby(['day', 'hour_decimal'])['power_W'].mean().reset_index()

        # 將數據重塑為日期-小時矩陣
        self.current_pivot_data = daily_hourly_power.pivot(index='hour_decimal', columns='day', values='power_W')

        # 計算照度數據（使用所有十分鐘數據，不只是整點）
        if 'illumination' in self.current_month_data.columns:
            self.current_illumination_data = self.current_month_data.groupby('hour_decimal')['illumination'].mean()
        else:
            # 如果沒有照度數據，則使用發電量數據作為替代
            self.current_illumination_data = self.current_month_data.groupby('hour_decimal')['power_W'].mean()
            print("警告：找不到 illumination 欄位，使用發電量數據作為替代")

        # 計算每日累計發電量
        self.daily_total_power = whole_hour_month.groupby('day')['power_W'].sum()

        # 計算面板平均發電量（如果有面板ID數據）
        if 'panel_id' in whole_hour_month.columns:
            self.panel_total_power = whole_hour_month.groupby('panel_id')['power_W'].sum()
            self.panel_avg_power = whole_hour_month.groupby('panel_id')['power_W'].mean()
        else:
            self.panel_total_power = None
            self.panel_avg_power = None

    def init_date_comparison(self):
        # 創建框架
        control_frame = ttk.Frame(self.date_frame)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.date_plot_frame = ttk.Frame(self.date_frame)
        self.date_plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 日期選擇部分
        days_frame = ttk.LabelFrame(control_frame, text="選擇要顯示的日期")
        days_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 創建日期勾選框
        days = sorted(self.current_pivot_data.columns)
        self.day_vars = {}

        # 將選擇框分成4列，每列約8個日期
        cols = 4
        rows = (len(days) + cols - 1) // cols

        current_month = self.month_var.get()

        for i, day in enumerate(days):
            row = i // cols
            col = i % cols
            var = tk.BooleanVar(value=False)
            self.day_vars[day] = var
            cb = ttk.Checkbutton(days_frame, text=f"{current_month}月{day}日", variable=var)
            cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)

        # 圖例位置選擇
        legend_frame = ttk.LabelFrame(control_frame, text="圖例位置")
        legend_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        legend_positions = [
            ("右上", "upper right"),
            ("右中", "center right"),
            ("右下", "lower right"),
            ("左上", "upper left"),
            ("左中", "center left"),
            ("左下", "lower left"),
            ("上中", "upper center"),
            ("下中", "lower center"),
            ("中心", "center")
        ]

        self.legend_pos_var = tk.StringVar(value="upper right")

        for i, (text, value) in enumerate(legend_positions):
            ttk.Radiobutton(legend_frame, text=text, variable=self.legend_pos_var, value=value).grid(
                row=i // 3, column=i % 3, sticky=tk.W, padx=5, pady=2)

        # 按鈕部分
        buttons_frame = ttk.Frame(control_frame)
        buttons_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        ttk.Button(buttons_frame, text="全選",
                   command=self.select_all_days).pack(pady=5)
        ttk.Button(buttons_frame, text="取消全選",
                   command=self.deselect_all_days).pack(pady=5)
        ttk.Button(buttons_frame, text="選擇前5天",
                   command=lambda: self.select_n_days(5)).pack(pady=5)
        ttk.Button(buttons_frame, text="選擇後5天",
                   command=lambda: self.select_n_days(-5)).pack(pady=5)
        ttk.Button(buttons_frame, text="產生圖表",
                   command=self.generate_date_plot).pack(pady=5)

        # 初始化圖表區域
        self.generate_date_plot()

    def init_panel_comparison(self):
        # 創建框架
        control_frame = ttk.Frame(self.panel_frame)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        self.panel_plot_frame = ttk.Frame(self.panel_frame)
        self.panel_plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 日期選擇部分
        date_frame = ttk.LabelFrame(control_frame, text="選擇要分析的日期")
        date_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        days = sorted(self.current_month_data['day'].unique())
        self.selected_day = tk.IntVar(value=days[0] if days else 1)

        current_month = self.month_var.get()

        # 創建日期的滾動視窗，如果日期太多
        if len(days) > 20:
            date_canvas = tk.Canvas(date_frame, height=300)
            date_scrollbar = ttk.Scrollbar(date_frame, orient="vertical", command=date_canvas.yview)
            date_scrollable_frame = ttk.Frame(date_canvas)

            date_scrollable_frame.bind(
                "<Configure>",
                lambda e: date_canvas.configure(scrollregion=date_canvas.bbox("all"))
            )

            date_canvas.create_window((0, 0), window=date_scrollable_frame, anchor="nw")
            date_canvas.configure(yscrollcommand=date_scrollbar.set)

            date_canvas.pack(side="left", fill="both", expand=True)
            date_scrollbar.pack(side="right", fill="y")

            for i, day in enumerate(days):
                ttk.Radiobutton(
                    date_scrollable_frame,
                    text=f"{current_month}月{day}日",
                    variable=self.selected_day,
                    value=day
                ).grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
        else:
            # 如果日期數量不多，就直接顯示
            for i, day in enumerate(days):
                ttk.Radiobutton(
                    date_frame,
                    text=f"{current_month}月{day}日",
                    variable=self.selected_day,
                    value=day
                ).grid(row=i // 2, column=i % 2, sticky=tk.W, padx=5, pady=2)

        # 面板選擇部分
        if 'panel_id' in self.current_month_data.columns:
            panel_frame = ttk.LabelFrame(control_frame, text="選擇要顯示的面板")
            panel_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

            panels = sorted(self.current_month_data['panel_id'].unique())
            self.panel_vars = {}

            # 如果面板數量過多，使用滾動視窗
            if len(panels) > 32:  # 8行4列 = 32個面板
                panel_canvas = tk.Canvas(panel_frame)
                panel_scrollbar = ttk.Scrollbar(panel_frame, orient="vertical", command=panel_canvas.yview)
                panel_scrollable_frame = ttk.Frame(panel_canvas)

                panel_scrollable_frame.bind(
                    "<Configure>",
                    lambda e: panel_canvas.configure(scrollregion=panel_canvas.bbox("all"))
                )

                panel_canvas.create_window((0, 0), window=panel_scrollable_frame, anchor="nw")
                panel_canvas.configure(yscrollcommand=panel_scrollbar.set)

                panel_canvas.pack(side="left", fill="both", expand=True)
                panel_scrollbar.pack(side="right", fill="y")

                # 將選擇框分成4列
                cols = 4
                rows = (len(panels) + cols - 1) // cols

                for i, panel in enumerate(panels):
                    row = i // cols
                    col = i % cols
                    var = tk.BooleanVar(value=False)
                    self.panel_vars[panel] = var
                    cb = ttk.Checkbutton(panel_scrollable_frame, text=f"{panel}", variable=var)
                    cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            else:
                # 將選擇框分成4列
                cols = 4
                rows = (len(panels) + cols - 1) // cols

                for i, panel in enumerate(panels):
                    row = i // cols
                    col = i % cols
                    var = tk.BooleanVar(value=False)
                    self.panel_vars[panel] = var
                    cb = ttk.Checkbutton(panel_frame, text=f"{panel}", variable=var)
                    cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)

            # 面板快速選擇按鈕
            panel_buttons_frame = ttk.Frame(control_frame)
            panel_buttons_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

            ttk.Button(panel_buttons_frame, text="全選面板",
                       command=self.select_all_panels).pack(pady=5)
            ttk.Button(panel_buttons_frame, text="取消全選面板",
                       command=self.deselect_all_panels).pack(pady=5)
            ttk.Button(panel_buttons_frame, text="選擇前10個面板",
                       command=lambda: self.select_n_panels(10)).pack(pady=5)
        else:
            # 如果數據中沒有面板ID，則顯示提示
            ttk.Label(control_frame, text="數據中沒有面板ID信息").pack(side=tk.LEFT, padx=10)
            self.panel_vars = {}

        # 角度選擇部分
        angle_frame = ttk.LabelFrame(control_frame, text="按角度篩選")
        angle_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # 獲取所有可能的傾角和方位角
        tilt_angles = sorted(
            self.current_month_data['tilt_angle'].unique()) if 'tilt_angle' in self.current_month_data.columns else []
        azimuth_angles = sorted(self.current_month_data[
                                    'azimuth_angle'].unique()) if 'azimuth_angle' in self.current_month_data.columns else []

        # 創建傾角選擇部分
        tilt_label = ttk.Label(angle_frame, text="傾角:")
        tilt_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)

        self.tilt_var = tk.StringVar(value="所有")
        tilt_combo = ttk.Combobox(angle_frame, textvariable=self.tilt_var,
                                  values=["所有"] + [str(angle) for angle in tilt_angles])
        tilt_combo.grid(row=0, column=1, padx=5, pady=2)
        tilt_combo.bind("<<ComboboxSelected>>", lambda e: self.filter_panels_by_angle())

        # 創建方位角選擇部分
        azimuth_label = ttk.Label(angle_frame, text="方位角:")
        azimuth_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)

        self.azimuth_var = tk.StringVar(value="所有")
        azimuth_combo = ttk.Combobox(angle_frame, textvariable=self.azimuth_var,
                                     values=["所有"] + [str(angle) for angle in azimuth_angles])
        azimuth_combo.grid(row=1, column=1, padx=5, pady=2)
        azimuth_combo.bind("<<ComboboxSelected>>", lambda e: self.filter_panels_by_angle())

        # 圖例位置選擇
        legend_frame = ttk.LabelFrame(control_frame, text="圖例位置")
        legend_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        legend_positions = [
            ("右上", "upper right"),
            ("右中", "center right"),
            ("右下", "lower right"),
            ("左上", "upper left"),
            ("左中", "center left"),
            ("左下", "lower left"),
            ("上中", "upper center"),
            ("下中", "lower center"),
            ("中心", "center")
        ]

        self.panel_legend_pos_var = tk.StringVar(value="upper right")

        for i, (text, value) in enumerate(legend_positions):
            ttk.Radiobutton(legend_frame, text=text, variable=self.panel_legend_pos_var, value=value).grid(
                row=i // 3, column=i % 3, sticky=tk.W, padx=5, pady=2)

        # 生成圖表按鈕
        ttk.Button(control_frame, text="產生圖表",
                   command=self.generate_panel_plot).pack(side=tk.RIGHT, padx=10, pady=10)

        # 初始化圖表區域
        self.generate_panel_plot()

    def init_monthly_stats(self):
        """初始化月度統計頁面"""
        # 主控制框架
        control_frame = ttk.Frame(self.monthly_stats_frame)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # 圖表類型選擇
        chart_type_frame = ttk.LabelFrame(control_frame, text="圖表類型")
        chart_type_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.monthly_chart_type = tk.StringVar(value="daily_total")

        ttk.Radiobutton(chart_type_frame, text="每日總發電量",
                        variable=self.monthly_chart_type, value="daily_total").pack(anchor=tk.W, padx=5, pady=2)

        if 'panel_id' in self.current_month_data.columns:
            ttk.Radiobutton(chart_type_frame, text="面板總發電量",
                            variable=self.monthly_chart_type, value="panel_total").pack(anchor=tk.W, padx=5, pady=2)
            ttk.Radiobutton(chart_type_frame, text="面板平均發電量",
                            variable=self.monthly_chart_type, value="panel_avg").pack(anchor=tk.W, padx=5, pady=2)

        # 圖表顯示選項
        options_frame = ttk.LabelFrame(control_frame, text="顯示選項")
        options_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.show_values_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="顯示數值", variable=self.show_values_var).pack(anchor=tk.W, padx=5, pady=2)

        self.sort_values_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="數值排序", variable=self.sort_values_var).pack(anchor=tk.W, padx=5, pady=2)

        # 如果有面板數據，添加面板篩選控制項
        if 'panel_id' in self.current_month_data.columns and 'tilt_angle' in self.current_month_data.columns:
            panel_filter_frame = ttk.LabelFrame(control_frame, text="面板篩選")
            panel_filter_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

            # 創建與面板比較頁面相同的篩選控制項
            # 傾角選擇
            tilt_angles = sorted(self.current_month_data['tilt_angle'].unique())
            tilt_label = ttk.Label(panel_filter_frame, text="傾角:")
            tilt_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)

            self.monthly_tilt_var = tk.StringVar(value="所有")
            tilt_combo = ttk.Combobox(panel_filter_frame, textvariable=self.monthly_tilt_var,
                                      values=["所有"] + [str(angle) for angle in tilt_angles])
            tilt_combo.grid(row=0, column=1, padx=5, pady=2)

            # 方位角選擇
            azimuth_angles = sorted(self.current_month_data['azimuth_angle'].unique())
            azimuth_label = ttk.Label(panel_filter_frame, text="方位角:")
            azimuth_label.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)

            self.monthly_azimuth_var = tk.StringVar(value="所有")
            azimuth_combo = ttk.Combobox(panel_filter_frame, textvariable=self.monthly_azimuth_var,
                                         values=["所有"] + [str(angle) for angle in azimuth_angles])
            azimuth_combo.grid(row=1, column=1, padx=5, pady=2)

        # 生成圖表按鈕
        ttk.Button(control_frame, text="產生圖表",
                   command=self.generate_monthly_stats_plot).pack(side=tk.RIGHT, padx=10, pady=10)

        # 創建圖表框架
        self.monthly_stats_plot_frame = ttk.Frame(self.monthly_stats_frame)
        self.monthly_stats_plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 初始生成圖表
        self.generate_monthly_stats_plot()

    def select_all_days(self):
        """選擇所有日期"""
        for var in self.day_vars.values():
            var.set(True)

    def deselect_all_days(self):
        """取消選擇所有日期"""
        for var in self.day_vars.values():
            var.set(False)

    def select_n_days(self, n):
        """選擇前n天或後n天"""
        # 清除現有選擇
        self.deselect_all_days()

        # 獲取排序後的日期列表
        days = sorted(self.day_vars.keys())

        # 決定選擇的日期
        selected_days = days[:n] if n > 0 else days[n:]

        # 選擇指定的日期
        for day in selected_days:
            self.day_vars[day].set(True)

        # 更新圖表
        self.generate_date_plot()

    def select_all_panels(self):
        """選擇所有面板"""
        for var in self.panel_vars.values():
            var.set(True)

    def deselect_all_panels(self):
        """取消選擇所有面板"""
        for var in self.panel_vars.values():
            var.set(False)

    def select_n_panels(self, n):
        """選擇前n個面板"""
        # 清除現有選擇
        self.deselect_all_panels()

        # 獲取排序後的面板列表
        panels = sorted(self.panel_vars.keys())

        # 選擇前n個面板
        selected_panels = panels[:n]

        # 選擇指定的面板
        for panel in selected_panels:
            self.panel_vars[panel].set(True)

        # 更新圖表
        self.generate_panel_plot()

    def filter_panels_by_angle(self):
        # 根據選擇的角度篩選面板
        if not self.panel_vars:
            return

        tilt = self.tilt_var.get()
        azimuth = self.azimuth_var.get()

        # 重設所有面板的選擇
        for var in self.panel_vars.values():
            var.set(False)

        # 如果選擇了特定角度，則按角度篩選面板
        filtered_panels = self.current_month_data

        if tilt != "所有" and 'tilt_angle' in filtered_panels.columns:
            filtered_panels = filtered_panels[filtered_panels['tilt_angle'] == float(tilt)]

        if azimuth != "所有" and 'azimuth_angle' in filtered_panels.columns:
            filtered_panels = filtered_panels[filtered_panels['azimuth_angle'] == float(azimuth)]

        # 獲取篩選後的面板ID
        if 'panel_id' in filtered_panels.columns:
            panel_ids = filtered_panels['panel_id'].unique()

            # 選中符合條件的面板
            for panel_id in panel_ids:
                if panel_id in self.panel_vars:
                    self.panel_vars[panel_id].set(True)

    def generate_date_plot(self):
        # 清除原有圖表
        for widget in self.date_plot_frame.winfo_children():
            widget.destroy()

        # 創建新圖表
        fig, ax = plt.subplots(figsize=(10, 6))

        current_month = self.month_var.get()

        # 繪製選中的日期
        selected_days = [day for day, var in self.day_vars.items() if var.get()]

        if not selected_days:
            # 如果沒有選擇日期，只繪製照度平均曲線
            ax.plot(self.current_illumination_data.index, self.current_illumination_data.values, 'k--', linewidth=2.5,
                    label='照度平均')
        else:
            # 生成足夠的顏色
            colors = generate_distinct_colors(len(selected_days) + 1)

            # 繪製選中的日期
            for i, day in enumerate(selected_days):
                day_data = self.current_pivot_data[day].dropna()
                if len(day_data) > 5:  # 確保有足夠的數據點
                    ax.plot(day_data.index, day_data.values, 'o-', linewidth=2,
                            color=colors[i], label=f'{current_month}月{day}日')

            # 繪製照度曲線 - 如果只選擇了一天，就顯示該天的照度數據
            if len(selected_days) == 1:
                # 獲取當天的照度數據
                selected_day = selected_days[0]
                day_illumination_data = self.current_month_data[self.current_month_data['day'] == selected_day]

                if 'illumination' in day_illumination_data.columns:
                    day_illumination = day_illumination_data.groupby('hour_decimal')['illumination'].mean()
                    # 創建第二個y軸
                    ax2 = ax.twinx()
                    ax2.plot(day_illumination.index, day_illumination.values, 'k--', linewidth=2.5,
                             label=f'{current_month}月{selected_day}日照度')
                    ax2.set_ylabel('Illuminance(W/m$^{2}$)', fontsize=14)
                    ax2.tick_params(axis='y', labelcolor='black')

                    # 合併圖例
                    lines1, labels1 = ax.get_legend_handles_labels()
                    lines2, labels2 = ax2.get_legend_handles_labels()
                    legend_pos = self.legend_pos_var.get()
                    ax.legend(lines1 + lines2, labels1 + labels2, loc=legend_pos)
                else:
                    # 創建第二個y軸
                    ax2 = ax.twinx()
                    ax2.plot(self.current_illumination_data.index, self.current_illumination_data.values, 'k--',
                             linewidth=2.5, label='照度平均')
                    ax2.set_ylabel('Illuminance(W/m$^{2}$)', fontsize=14)
                    ax2.tick_params(axis='y', labelcolor='black')

                    # 合併圖例
                    lines1, labels1 = ax.get_legend_handles_labels()
                    lines2, labels2 = ax2.get_legend_handles_labels()
                    legend_pos = self.legend_pos_var.get()
                    ax.legend(lines1 + lines2, labels1 + labels2, loc=legend_pos)
            else:
                # 如果選擇了多天，顯示月平均照度
                ax.plot(self.current_illumination_data.index, self.current_illumination_data.values, 'k--',
                        linewidth=2.5,
                        label='照度平均')

        # 設定圖表屬性
        ax.set_title(f'{current_month}月份選定日期的日間發電曲線', fontsize=16)
        ax.set_xlabel('Time of day', fontsize=14)
        ax.set_ylabel('發電量 (W)', fontsize=14)
        ax.grid(True)

        # 使用選定的圖例位置
        legend_pos = self.legend_pos_var.get()
        ax.legend(loc=legend_pos)

        ax.set_xlim(4, 19)
        ax.set_ylim(0, None)
        ax.set_xticks(range(4, 19))

        # 將圖表添加到界面
        canvas = FigureCanvasTkAgg(fig, master=self.date_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def generate_panel_plot(self):
        # 清除原有圖表
        for widget in self.panel_plot_frame.winfo_children():
            widget.destroy()

        # 創建新圖表
        fig, ax = plt.subplots(figsize=(10, 6))

        current_month = self.month_var.get()

        # 獲取選中的日期
        selected_day = self.selected_day.get()

        # 獲取當天的照度數據
        day_illumination_data = self.current_month_data[self.current_month_data['day'] == selected_day]

        if 'illumination' in day_illumination_data.columns:
            day_illumination = day_illumination_data.groupby('hour_decimal')['illumination'].mean()

        # 獲取該日期的數據
        day_data = self.current_month_data[self.current_month_data['day'] == selected_day]


        if 'panel_id' in day_data.columns:
            # 選中的面板
            selected_panels = [panel for panel, var in self.panel_vars.items() if var.get()]

            # 篩選選中的面板數據
            if selected_panels:
                panel_data = day_data[day_data['panel_id'].isin(selected_panels)]
            else:
                panel_data = day_data

            # 按小時和面板分組計算平均發電量
            panel_hourly_power = panel_data.groupby(['panel_id', 'hour_decimal'])['power_W'].mean().reset_index()

            # 創建各面板的發電曲線
            panel_pivot = panel_hourly_power.pivot(index='hour_decimal', columns='panel_id', values='power_W')

            # 如果有數據，繪製各面板的發電曲線
            if not panel_pivot.empty:
                # 生成足夠的顏色
                colors = generate_distinct_colors(len(panel_pivot.columns) + 1)

                for i, panel in enumerate(panel_pivot.columns):
                    panel_series = panel_pivot[panel].dropna()
                    if len(panel_series) > 5:  # 確保有足夠的數據點
                        ax.plot(panel_series.index, panel_series.values, 'o-', linewidth=2,
                                color=colors[i], label=f'{panel}')

            # 計算所有面板的平均值
            if len(panel_pivot.columns) > 1:
                avg_power = panel_pivot.mean(axis=1)
                # 創建第二個y軸
                ax2 = ax.twinx()
                ax2.plot(day_illumination.index, day_illumination.values, 'k--', linewidth=2.5,
                         label=f'{current_month}月{selected_day}日照度')
                ax2.set_ylabel('Illuminance(W/m$^{2}$)', fontsize=14)
                ax2.tick_params(axis='y', labelcolor='black')

                # 合併圖例
                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                legend_pos = self.panel_legend_pos_var.get()
                ax.legend(lines1 + lines2, labels1 + labels2, loc=legend_pos)

            # 從選擇的角度獲取標題
            tilt_str = self.tilt_var.get() if hasattr(self, 'tilt_var') else '所有'
            azimuth_str = self.azimuth_var.get() if hasattr(self, 'azimuth_var') else '所有'

            angle_str = ""
            if tilt_str != "所有" or azimuth_str != "所有":
                angle_str = f" - 傾角: {tilt_str if tilt_str != '所有' else '全部'}, 方位角: {azimuth_str if azimuth_str != '所有' else '全部'}"

            # 設定圖表屬性
            ax.set_title(f'{current_month}月{selected_day}日不同面板的日間發電曲線{angle_str}', fontsize=16)
            ax.set_xlabel('Time of day', fontsize=14)
            ax.set_ylabel('Power output (W)', fontsize=14)
            ax.grid(True)

            # 使用選定的圖例位置
            legend_pos = self.panel_legend_pos_var.get()
            ax.legend(loc=legend_pos)

            ax.set_xlim(4, 19)
            ax.set_ylim(0, None)
            ax.set_xticks(range(4, 19))
        else:
            # 如果沒有面板ID，
            day_hourly = day_data.groupby('hour_decimal')['power_W'].mean()

            ax.plot(day_hourly.index, day_hourly.values, 'o-', linewidth=2,
                    label=f'{current_month}月{selected_day}日平均')
            # 創建第二個y軸
            ax2 = ax.twinx()
            ax2.plot(day_illumination.index, day_illumination.values, 'k--', linewidth=2.5,
                     label=f'{current_month}月{selected_day}日照度')
            ax2.set_ylabel('Illuminance(W/m$^{2}$)', fontsize=14)
            ax2.tick_params(axis='y', labelcolor='black')

            # 合併圖例
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            legend_pos = self.panel_legend_pos_var.get()
            ax.legend(lines1 + lines2, labels1 + labels2, loc=legend_pos)

            # 設定圖表屬性
            ax.set_title(f'{current_month}月{selected_day}日發電曲線 (無面板ID數據)', fontsize=16)
            ax.set_xlabel('Time of day', fontsize=14)
            ax.set_ylabel('Power output (W)', fontsize=14)
            ax.grid(True)

            # 使用選定的圖例位置
            legend_pos = self.panel_legend_pos_var.get()
            ax.legend(loc=legend_pos)

            ax.set_xlim(4, 19)
            ax.set_ylim(0, None)
            ax.set_xticks(range(4, 19))

        # 將圖表添加到界面
        canvas = FigureCanvasTkAgg(fig, master=self.panel_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def generate_monthly_stats_plot(self):
        """生成月度統計圖表"""
        # 清除原有圖表
        for widget in self.monthly_stats_plot_frame.winfo_children():
            widget.destroy()

        # 創建新圖表
        fig, ax = plt.subplots(figsize=(10, 6))

        current_month = self.month_var.get()
        chart_type = self.monthly_chart_type.get()
        show_values = self.show_values_var.get()
        sort_values = self.sort_values_var.get()

        # 根據圖表類型生成相應的數據
        if chart_type == "daily_total":
            # 獲取每日總發電量
            data = self.daily_total_power.copy() / 1000  # 轉換為 kWh
            title = f"{current_month}月份各日累計發電量"
            x_label = "日期"
            y_label = "累計發電量 (kWh)"  # 修改單位

            # 如果需要排序
            if sort_values:
                data = data.sort_values(ascending=False)

            # 繪製柱狀圖
            bars = ax.bar(data.index, data.values, color='skyblue')

            # 添加數值標籤
            if show_values:
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 0.5,  # 減小這個值，比如改為 +0.5
                            f'{height:.1f}', ha='center', va='bottom')

        elif chart_type == "panel_total" and self.panel_total_power is not None:
            # 篩選面板數據（如果有角度篩選）
            data = self.panel_total_power.copy() / 1000

            if hasattr(self, 'monthly_tilt_var') and hasattr(self, 'monthly_azimuth_var'):
                tilt = self.monthly_tilt_var.get()
                azimuth = self.monthly_azimuth_var.get()

                # 篩選符合條件的面板
                filtered_panels = self.current_month_data

                if tilt != "所有" and 'tilt_angle' in filtered_panels.columns:
                    filtered_panels = filtered_panels[filtered_panels['tilt_angle'] == float(tilt)]

                if azimuth != "所有" and 'azimuth_angle' in filtered_panels.columns:
                    filtered_panels = filtered_panels[filtered_panels['azimuth_angle'] == float(azimuth)]

                # 獲取符合條件的面板ID
                if 'panel_id' in filtered_panels.columns:
                    panel_ids = filtered_panels['panel_id'].unique()
                    data = data[data.index.isin(panel_ids)]

            # 如果需要排序
            if sort_values:
                data = data.sort_values(ascending=False)

            angle_str = ""
            if hasattr(self, 'monthly_tilt_var') and hasattr(self, 'monthly_azimuth_var'):
                tilt_str = self.monthly_tilt_var.get()
                azimuth_str = self.monthly_azimuth_var.get()

                if tilt_str != "所有" or azimuth_str != "所有":
                    angle_str = f" - 傾角: {tilt_str if tilt_str != '所有' else '全部'}, 方位角: {azimuth_str if azimuth_str != '所有' else '全部'}"

            title = f"{current_month}月份各面板累計發電量{angle_str}"
            x_label = "面板ID"
            y_label = "累計發電量 (kWh)"  # 修改單位

            # 繪製柱狀圖 - 使用前30個最高發電量的面板，如果太多的話
            if len(data) > 30:
                data = data.iloc[:30]
                title += " (前30名)"

            bars = ax.bar(data.index.astype(str), data.values, color='lightgreen')

            # 添加數值標籤

            if show_values:
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 1,  # 也是減小這個值
                            f'{height:.1f}', ha='center', va='bottom', rotation=45 if len(data) > 15 else 0)

        elif chart_type == "panel_avg" and self.panel_avg_power is not None:
            # 篩選面板數據（如果有角度篩選）
            data = self.panel_avg_power.copy()

            if hasattr(self, 'monthly_tilt_var') and hasattr(self, 'monthly_azimuth_var'):
                tilt = self.monthly_tilt_var.get()
                azimuth = self.monthly_azimuth_var.get()

                # 篩選符合條件的面板
                filtered_panels = self.current_month_data

                if tilt != "所有" and 'tilt_angle' in filtered_panels.columns:
                    filtered_panels = filtered_panels[filtered_panels['tilt_angle'] == float(tilt)]

                if azimuth != "所有" and 'azimuth_angle' in filtered_panels.columns:
                    filtered_panels = filtered_panels[filtered_panels['azimuth_angle'] == float(azimuth)]

                # 獲取符合條件的面板ID
                if 'panel_id' in filtered_panels.columns:
                    panel_ids = filtered_panels['panel_id'].unique()
                    data = data[data.index.isin(panel_ids)]

            # 如果需要排序
            if sort_values:
                data = data.sort_values(ascending=False)

            angle_str = ""
            if hasattr(self, 'monthly_tilt_var') and hasattr(self, 'monthly_azimuth_var'):
                tilt_str = self.monthly_tilt_var.get()
                azimuth_str = self.monthly_azimuth_var.get()

                if tilt_str != "所有" or azimuth_str != "所有":
                    angle_str = f" - 傾角: {tilt_str if tilt_str != '所有' else '全部'}, 方位角: {azimuth_str if azimuth_str != '所有' else '全部'}"

            title = f"{current_month}月份各面板平均發電量{angle_str}"
            x_label = "面板ID"
            y_label = "平均發電量 (W)"

            # 繪製柱狀圖 - 使用前30個最高發電量的面板，如果太多的話
            if len(data) > 30:
                data = data.iloc[:30]
                title += " (前30名)"

            bars = ax.bar(data.index.astype(str), data.values, color='salmon')

            # 添加數值標籤
            if show_values:
                for bar in bars:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 0.2,
                            f'{height:.1f}', ha='center', va='bottom', rotation=45 if len(data) > 15 else 0)

        # 設定圖表屬性
        ax.set_title(title, fontsize=16)
        ax.set_xlabel(x_label, fontsize=14)
        ax.set_ylabel(y_label, fontsize=14)
        ax.grid(True, axis='y')

        # 調整x軸標籤
        if len(data) > 15:
            plt.xticks(rotation=45, ha='right')
            plt.subplots_adjust(bottom=0.2)

        # 將圖表添加到界面
        canvas = FigureCanvasTkAgg(fig, master=self.monthly_stats_plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# 啟動應用程式
if __name__ == "__main__":
    root = tk.Tk()
    app = SolarDataAnalyzer(root)
    root.mainloop()