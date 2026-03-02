"""
固定式太陽能板數據處理整合程式
整合所有數據處理步驟，提供統一的處理介面
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import subprocess

class SolarDataPipeline:
    def __init__(self, root):
        self.root = root
        self.root.title("固定式太陽能板數據處理系統")
        self.root.geometry("900x700")
        
        # 當前腳本所在目錄
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 各個處理腳本的路徑
        self.scripts = {
            'convert': os.path.join(self.script_dir, 'convert name1.py'),
            'power_calc': os.path.join(self.script_dir, 'power calculation2.py'),
            'power_summary': os.path.join(self.script_dir, 'power summary3.py'),
            'preprocessing': os.path.join(self.script_dir, 'data preprocessing4.py'),
            'combine': os.path.join(self.script_dir, 'combine data 5.py'),
            'visualization': os.path.join(self.script_dir, 'fixed_panel_data_visualization.py')
        }
        
        # 處理狀態
        self.processing_status = {
            'step1': False,
            'step2': False,
            'step3': False,
            'step4': False,
            'step5': False
        }
        
        # 資料夾路徑
        self.base_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        
        self.create_ui()
    
    def create_ui(self):
        """創建使用者介面"""
        # 標題
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=10, padx=10, fill=tk.X)
        
        ttk.Label(
            title_frame, 
            text="固定式太陽能板數據處理系統",
            font=("Arial", 16, "bold")
        ).pack()
        
        # 路徑設置區
        path_frame = ttk.LabelFrame(self.root, text="資料夾設置", padding=10)
        path_frame.pack(pady=10, padx=10, fill=tk.X)
        
        # 輸入資料夾
        ttk.Label(path_frame, text="原始數據資料夾:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(path_frame, textvariable=self.base_folder, width=50).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(path_frame, text="瀏覽", command=self.browse_base_folder).grid(row=0, column=2, pady=5)
        
        # 說明標籤
        ttk.Label(
            path_frame, 
            text="提示: 選擇包含各個子資料夾的主資料夾 (如: 20260111_0120)",
            font=("Arial", 9),
            foreground="gray"
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=2)
        
        # 處理步驟區
        steps_frame = ttk.LabelFrame(self.root, text="處理步驟", padding=10)
        steps_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        # 創建處理步驟按鈕
        self.create_step_buttons(steps_frame)
        
        # 控制按鈕區
        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=10, padx=10, fill=tk.X)
        
        ttk.Button(
            control_frame, 
            text="🚀 執行完整處理流程",
            command=self.run_full_pipeline,
            width=30
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            control_frame, 
            text="📊 開啟視覺化工具",
            command=self.open_visualization,
            width=30
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            control_frame, 
            text="📖 開啟使用手冊",
            command=self.open_manual,
            width=30
        ).pack(side=tk.LEFT, padx=5)
        
        # 狀態顯示區
        status_frame = ttk.LabelFrame(self.root, text="處理狀態", padding=10)
        status_frame.pack(pady=10, padx=10, fill=tk.X)
        
        self.status_text = tk.Text(status_frame, height=8, width=80)
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(status_frame, command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
        
        self.log_message("系統已啟動，請選擇原始數據資料夾開始處理")
    
    def create_step_buttons(self, parent):
        """創建處理步驟按鈕"""
        steps = [
            {
                'num': '1',
                'name': '檔案重命名',
                'desc': '將原始檔名轉換為包含角度信息的檔名',
                'script': 'convert',
                'status_key': 'step1'
            },
            {
                'num': '2',
                'name': '功率計算',
                'desc': '計算功率 (P=V×I) 和每日發電量',
                'script': 'power_calc',
                'status_key': 'step2'
            },
            {
                'num': '3',
                'name': '發電量匯總',
                'desc': '創建面板發電量匯總表',
                'script': 'power_summary',
                'status_key': 'step3'
            },
            {
                'num': '4',
                'name': '數據預處理',
                'desc': '添加太陽位置信息並整合照度數據',
                'script': 'preprocessing',
                'status_key': 'step4'
            },
            {
                'num': '5',
                'name': '數據合併',
                'desc': '合併多個時段的數據文件',
                'script': 'combine',
                'status_key': 'step5'
            }
        ]
        
        for i, step in enumerate(steps):
            step_frame = ttk.Frame(parent)
            step_frame.pack(fill=tk.X, pady=5)
            
            # 步驟編號
            ttk.Label(
                step_frame, 
                text=f"步驟 {step['num']}:",
                font=("Arial", 10, "bold"),
                width=8
            ).pack(side=tk.LEFT, padx=5)
            
            # 步驟名稱和描述
            info_frame = ttk.Frame(step_frame)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            ttk.Label(
                info_frame,
                text=step['name'],
                font=("Arial", 10, "bold")
            ).pack(anchor=tk.W)
            
            ttk.Label(
                info_frame,
                text=step['desc'],
                font=("Arial", 9),
                foreground="gray"
            ).pack(anchor=tk.W)
            
            # 執行按鈕
            ttk.Button(
                step_frame,
                text="執行此步驟",
                command=lambda s=step: self.run_single_step(s),
                width=15
            ).pack(side=tk.RIGHT, padx=5)
            
            # 狀態指示器
            status_label = ttk.Label(step_frame, text="⚪ 未執行", width=10)
            status_label.pack(side=tk.RIGHT, padx=5)
            setattr(self, f"status_label_{step['status_key']}", status_label)
    
    def browse_base_folder(self):
        """瀏覽並選擇基礎資料夾"""
        folder = filedialog.askdirectory(title="選擇原始數據資料夾")
        if folder:
            self.base_folder.set(folder)
            self.log_message(f"已選擇資料夾: {folder}")
            
            # 檢查是否有"已重命名"子資料夾
            renamed_folder = os.path.join(folder, "已重命名")
            if os.path.exists(renamed_folder):
                self.output_folder.set(renamed_folder)
                self.log_message(f"找到處理資料夾: {renamed_folder}")
    
    def log_message(self, message):
        """記錄訊息到狀態文本框"""
        self.status_text.insert(tk.END, f"[{self.get_timestamp()}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update()
    
    def get_timestamp(self):
        """獲取當前時間戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def update_step_status(self, step_key, success):
        """更新步驟狀態"""
        status_label = getattr(self, f"status_label_{step_key}", None)
        if status_label:
            if success:
                status_label.config(text="✅ 完成", foreground="green")
                self.processing_status[step_key] = True
            else:
                status_label.config(text="❌ 失敗", foreground="red")
    
    def run_single_step(self, step):
        """執行單個處理步驟"""
        if not self.base_folder.get():
            messagebox.showerror("錯誤", "請先選擇原始數據資料夾")
            return
        
        self.log_message(f"開始執行: {step['name']}")
        
        # 這裡應該調用相應的處理腳本
        # 由於原始腳本需要修改路徑，這裡提供手動執行的提示
        messagebox.showinfo(
            "執行步驟",
            f"請手動編輯並執行以下腳本:\n\n{self.scripts[step['script']]}\n\n"
            f"將腳本中的資料夾路徑修改為:\n{self.base_folder.get()}"
        )
    
    def run_full_pipeline(self):
        """執行完整處理流程"""
        if not self.base_folder.get():
            messagebox.showerror("錯誤", "請先選擇原始數據資料夾")
            return
        
        self.log_message("=" * 50)
        self.log_message("開始執行完整處理流程")
        self.log_message("=" * 50)
        
        steps_info = """
完整處理流程包含以下步驟:

1️⃣ 檔案重命名 - 將原始檔名轉換為包含角度信息
2️⃣ 功率計算 - 計算每筆數據的功率值
3️⃣ 發電量匯總 - 生成匯總報表
4️⃣ 數據預處理 - 添加太陽位置等信息
5️⃣ 數據合併 - 合併多個時段的數據

由於需要修改各個腳本中的路徑，建議按照使用手冊逐步執行。

點擊「開啟使用手冊」查看詳細步驟。
        """
        
        messagebox.showinfo("完整處理流程", steps_info)
        self.log_message("請參考使用手冊執行各個步驟")
    
    def open_visualization(self):
        """開啟視覺化工具"""
        visualization_script = self.scripts['visualization']
        
        if not os.path.exists(visualization_script):
            messagebox.showerror("錯誤", f"找不到視覺化工具:\n{visualization_script}")
            return
        
        self.log_message("正在啟動視覺化工具...")
        
        try:
            # 在新的Python進程中運行視覺化工具
            subprocess.Popen([sys.executable, visualization_script])
            self.log_message("視覺化工具已啟動")
        except Exception as e:
            self.log_message(f"啟動視覺化工具失敗: {str(e)}")
            messagebox.showerror("錯誤", f"無法啟動視覺化工具:\n{str(e)}")
    
    def open_manual(self):
        """開啟使用手冊"""
        manual_path = os.path.join(self.script_dir, "使用手冊.md")
        
        if os.path.exists(manual_path):
            try:
                os.startfile(manual_path)
                self.log_message("使用手冊已開啟")
            except:
                messagebox.showinfo("使用手冊路徑", f"使用手冊位置:\n{manual_path}")
        else:
            messagebox.showwarning("提示", "使用手冊文件不存在，請查看README文件")

if __name__ == "__main__":
    root = tk.Tk()
    app = SolarDataPipeline(root)
    root.mainloop()
