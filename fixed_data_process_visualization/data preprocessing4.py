import pandas as pd
import numpy as np
import os
import re
import glob
from datetime import datetime, timedelta
import sqlite3
import pytz
import pvlib


class SolarAngleDataProcessor:
    def __init__(self, db_path='solar_angle_data.db'):
        """初始化數據處理器"""
        self.db_path = db_path
        self.conn = self._create_database()
        # 設置台灣時區
        self.location = {
            'latitude': 25.04,
            'longitude': 121.53,
            'altitude': 10,
            'tz': 'Asia/Taipei'
        }

    def _create_database(self):
        """創建或連接到SQLite數據庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 創建統一的太陽能數據表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS solar_panel_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            time TEXT,
            tilt_angle REAL,
            azimuth_angle TEXT,
            voltage REAL,
            current_mA REAL,
            current_A REAL,
            power_W REAL,
            daily_energy_Wh REAL,
            panel_id TEXT,
            is_tracking INTEGER,
            tracking_system TEXT,
            tracking_position TEXT,
            original_file TEXT
        )
        ''')

        # 創建處理後的分析數據表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_solar_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            time TEXT,
            tilt_angle REAL,
            azimuth_angle TEXT,
            power_W REAL,
            day_of_year INTEGER,
            hour_decimal REAL,
            solar_zenith REAL,
            solar_azimuth REAL,
            theoretical_poa REAL,
            panel_id TEXT,
            is_tracking INTEGER,
            tracking_system TEXT,
            tracking_position TEXT
        )
        ''')

        # 創建15分鐘平均數據表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS averaged_solar_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            time_interval TEXT,
            tilt_angle REAL,
            azimuth_angle TEXT,
            avg_power_W REAL,
            data_points INTEGER,
            day_of_year INTEGER,
            hour_decimal REAL,
            solar_zenith REAL,
            solar_azimuth REAL,
            theoretical_poa REAL,
            panel_id TEXT,
            is_tracking INTEGER,
            tracking_system TEXT,
            tracking_position TEXT
        )
        ''')

        conn.commit()
        return conn

    def import_csv_files(self, directory_path, clear_existing=True):
        """
        處理目錄中所有太陽能CSV文件，包括追日系統數據

        參數:
        - directory_path: 包含CSV文件的目錄路徑
        - clear_existing: 是否清空資料表中現有數據
        """
        # 在處理前先檢查並確保表結構正確
        self._ensure_tables_structure()

        # 如果需要，先清空資料表
        if clear_existing:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM solar_panel_data")
            self.conn.commit()
            print("已清空現有數據")

        # 獲取目錄中所有CSV文件
        csv_files = glob.glob(os.path.join(directory_path, "*.csv"))

        if not csv_files:
            print(f"在 {directory_path} 中沒有找到CSV文件")
            return False

        total_records = 0

        for csv_file in csv_files:
            filename = os.path.basename(csv_file)
            print(f"處理文件: {filename}")

            # 檢查是否為追日系統文件
            tracking_match = re.search(r'追日系統(\d+)\s*傾角(\d+)(上|下)', filename)

            if tracking_match:
                # 這是追日系統文件
                tracking_system = tracking_match.group(1)  # 追日系統編號
                tilt_angle = int(tracking_match.group(2))  # 傾角
                tracking_position = tracking_match.group(3)  # 上/下位置
                azimuth_angle = "tracking"  # 方位角設置為"追日"
                is_tracking = 1  # 標記為追日系統

                # 設置面板ID
                panel_id = f"Tracking_{tracking_system}_{tilt_angle}_{tracking_position}"

                print(f"  識別為追日系統: 系統{tracking_system}, 傾角{tilt_angle}度, 位置{tracking_position}")
            else:
                # 從文件名中提取傾角和方位角 (固定式系統)
                tilt_match = re.search(r'傾角(\d+)度', filename)
                azimuth_match = re.search(r'方位角(\d+)度', filename)

                if tilt_match and azimuth_match:
                    tilt_angle = int(tilt_match.group(1))
                    azimuth_angle = int(azimuth_match.group(1))
                    is_tracking = 0  # 標記為固定式系統
                    tracking_system = None
                    tracking_position = None

                    # 檢查方位角後面是否有"1"來識別面板
                    panel_type_match = re.search(r'方位角(\d+)度1', filename)
                    if panel_type_match:
                        panel_id = f"Panel_{tilt_angle}_{azimuth_angle}_B"  # B面板
                    else:
                        panel_id = f"Panel_{tilt_angle}_{azimuth_angle}_A"  # A面板
                else:
                    print(f"  無法從文件名 {filename} 中提取角度信息")
                    continue

            # 讀取CSV文件
            try:
                df = pd.read_csv(csv_file, encoding='utf-8')
                print(f"  讀取了 {len(df)} 行數據")

                # 獲取列名
                columns = df.columns.tolist()
                print(f"  檔案列名: {columns}")

                # 檢查並重命名列
                # 假設第一列是日期時間，基於您的截圖例子
                if len(columns) >= 1:
                    # 標準化列名
                    column_mapping = {}

                    # 根據位置設置標準列名 - 基於您提供的截圖
                    if len(columns) >= 1:
                        column_mapping[columns[0]] = '日期时间'
                    if len(columns) >= 2:
                        column_mapping[columns[1]] = '直流电压V'
                    if len(columns) >= 3:
                        column_mapping[columns[2]] = '直流电电流mA'
                    if len(columns) >= 4:
                        column_mapping[columns[3]] = '直流电电流A'
                    if len(columns) >= 5:
                        column_mapping[columns[4]] = 'datetime'
                    if len(columns) >= 6:
                        column_mapping[columns[5]] = 'Power(W)'
                    if len(columns) >= 7:
                        column_mapping[columns[6]] = 'Daily_Energy(Wh)'

                    # 重命名列
                    df.rename(columns=column_mapping, inplace=True)
                    print("  已對列進行標準化命名")

                # 標準化後的重命名
                if '日期时间' in df.columns:
                    df.rename(columns={
                        '日期时间': 'original_datetime',
                        '直流电压V': 'voltage',
                        '直流电电流mA': 'current_mA',
                        '直流电电流A': 'current_A',
                        'Power(W)': 'power_W',
                        'Daily_Energy(Wh)': 'daily_energy_Wh'
                    }, inplace=True)

                # 如果timestamp列不存在，嘗試從original_datetime或datetime轉換
                if 'timestamp' not in df.columns:
                    if 'original_datetime' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['original_datetime']).dt.strftime('%Y-%m-%d %H:%M:%S')
                    elif 'datetime' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d %H:%M:%S')

                # 添加角度和追日系統信息
                df['tilt_angle'] = tilt_angle
                df['azimuth_angle'] = azimuth_angle
                df['panel_id'] = panel_id
                df['is_tracking'] = is_tracking
                df['tracking_system'] = tracking_system
                df['tracking_position'] = tracking_position
                df['original_file'] = filename

                # 提取日期和時間
                df['date'] = pd.to_datetime(df['timestamp']).dt.date.astype(str)
                df['time'] = pd.to_datetime(df['timestamp']).dt.time.astype(str)

                # 選擇需要保存的列
                columns_to_save = [
                    'timestamp', 'date', 'time', 'tilt_angle', 'azimuth_angle',
                    'voltage', 'current_mA', 'current_A', 'power_W', 'daily_energy_Wh',
                    'panel_id', 'is_tracking', 'tracking_system', 'tracking_position', 'original_file'
                ]

                # 確保所有必要的列都存在
                for col in columns_to_save:
                    if col not in df.columns:
                        if col in ['voltage', 'current_mA', 'current_A', 'daily_energy_Wh']:
                            df[col] = np.nan  # 為可選列設置NaN
                        else:
                            df[col] = None  # 為其他必要列設置None
                            print(f"  已添加缺失列 {col}，值設為None")

                # 保存到數據庫
                df[columns_to_save].to_sql('solar_panel_data', self.conn, if_exists='append', index=False)
                total_records += len(df)
                print(f"  成功處理並保存 {len(df)} 行數據")

            except Exception as e:
                print(f"  處理文件 {filename} 時出錯: {str(e)}")
                import traceback
                traceback.print_exc()

        print(f"總共處理並保存了 {total_records} 條數據記錄")
        return total_records > 0

    def process_data(self, overwrite=True, filter_azimuth=False):
        """
        處理導入的數據並添加太陽位置信息，可選擇過濾太陽方位角

        參數:
        - overwrite: 是否覆蓋資料表中現有的處理後數據
        - filter_azimuth: 是否過濾掉太陽方位角 > 90 度的數據（太陽低於地平面）
        """
        # 從原始表中讀取數據
        query = "SELECT * FROM solar_panel_data"
        df = pd.read_sql_query(query, self.conn)

        if len(df) == 0:
            print("沒有數據可處理")
            return False

        print(f"處理 {len(df)} 條數據記錄...")

        # 轉換時間戳
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 添加時間特徵
        df['day_of_year'] = df['timestamp'].dt.dayofyear
        df['hour_decimal'] = df['timestamp'].dt.hour + df['timestamp'].dt.minute / 60

        # 創建時區感知的時間索引
        times = pd.DatetimeIndex(df['timestamp'])
        tz = pytz.timezone(self.location['tz'])
        times = times.tz_localize(tz, ambiguous='infer', nonexistent='shift_forward')

        # 計算太陽位置
        solar_position = pvlib.solarposition.get_solarposition(
            times,
            self.location['latitude'],
            self.location['longitude'],
            self.location['altitude']
        )

        # 添加太陽位置信息
        df['solar_zenith'] = solar_position['zenith'].values
        df['solar_azimuth'] = solar_position['azimuth'].values

        # 過濾掉太陽方位角 > 90 度的數據（如果需要）
        if filter_azimuth:
            initial_count = len(df)
            df = df[df['solar_zenith'] <= 90]  # 保留太陽在地平面以上的數據
            filtered_count = initial_count - len(df)
            print(f"已過濾掉 {filtered_count} 條太陽方位角 > 90 度的數據（太陽低於地平面）")

        # 計算理論平面輻照度 - 僅為固定式面板計算
        theoretical_poa = []

        for i, row in df.iterrows():
            try:
                # 如果是追日系統，設置為NaN
                if row['is_tracking'] == 1 or str(row['azimuth_angle']) == "追日":
                    theoretical_poa.append(np.nan)
                else:
                    # 為固定式面板計算理論POA
                    irradiance = pvlib.irradiance.get_total_irradiance(
                        row['tilt_angle'], row['azimuth_angle'],
                        row['solar_zenith'], row['solar_azimuth'],
                        dni=800, ghi=1000, dhi=200  # 使用默認值
                    )
                    theoretical_poa.append(irradiance['poa_global'])
            except:
                theoretical_poa.append(np.nan)

        df['theoretical_poa'] = theoretical_poa

        # 轉換回字符串格式以存儲到SQLite
        df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

        # 選擇要保存的列
        columns_to_save = [
            'timestamp', 'date', 'time', 'tilt_angle', 'azimuth_angle',
            'power_W', 'day_of_year', 'hour_decimal', 'solar_zenith',
            'solar_azimuth', 'theoretical_poa', 'panel_id', 'is_tracking',
            'tracking_system', 'tracking_position'
        ]

        # 清空目標表（如果需要）
        if overwrite:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM processed_solar_data")
            self.conn.commit()
            print("已清空處理後數據表")

        # 保存處理後的數據
        df[columns_to_save].to_sql('processed_solar_data', self.conn, if_exists='append', index=False)

        print(f"已成功處理並保存 {len(df)} 條記錄到 processed_solar_data 表")
        return True


    def filter_solar_zenith_data(self, max_zenith=90):
        """
        從processed_solar_data表中過濾掉太陽天頂角大於指定值的數據

        參數:
        - max_zenith: 最大允許的太陽天頂角（默認為90度，表示太陽在地平面以上）

        返回:
        - 被過濾掉的記錄數量
        """
        cursor = self.conn.cursor()

        # 先獲取總記錄數
        cursor.execute("SELECT COUNT(*) FROM processed_solar_data")
        total_before = cursor.fetchone()[0]

        # 刪除太陽天頂角大於指定值的記錄
        cursor.execute(f"DELETE FROM processed_solar_data WHERE solar_zenith > {max_zenith}")
        self.conn.commit()

        # 獲取剩餘記錄數
        cursor.execute("SELECT COUNT(*) FROM processed_solar_data")
        total_after = cursor.fetchone()[0]

        # 計算被過濾掉的記錄數
        filtered_count = total_before - total_after

        print(f"已過濾掉 {filtered_count} 條太陽天頂角 > {max_zenith} 度的數據（太陽低於地平面）")
        print(f"剩餘 {total_after} 條有效數據")

        return filtered_count

    def remove_duplicates(self):
        """從processed_solar_data表中移除重複記錄"""
        cursor = self.conn.cursor()

        # 先獲取總記錄數
        cursor.execute("SELECT COUNT(*) FROM processed_solar_data")
        total_count = cursor.fetchone()[0]

        # 創建一個臨時表來存儲唯一記錄
        cursor.execute("DROP TABLE IF EXISTS temp_unique_data")
        cursor.execute("""
        CREATE TABLE temp_unique_data AS
        SELECT DISTINCT * FROM processed_solar_data
        """)

        # 獲取唯一記錄數
        cursor.execute("SELECT COUNT(*) FROM temp_unique_data")
        unique_count = cursor.fetchone()[0]

        # 計算重複記錄數
        duplicate_count = total_count - unique_count
        print(f"發現 {duplicate_count} 條重複記錄")

        if duplicate_count > 0:
            # 清空原表
            cursor.execute("DELETE FROM processed_solar_data")

            # 將唯一記錄寫回原表
            cursor.execute("""
            INSERT INTO processed_solar_data
            SELECT * FROM temp_unique_data
            """)

            # 刪除臨時表
            cursor.execute("DROP TABLE temp_unique_data")

            self.conn.commit()
            print(f"已移除 {duplicate_count} 條重複記錄，保留 {unique_count} 條唯一記錄")
        else:
            # 刪除臨時表
            cursor.execute("DROP TABLE temp_unique_data")
            self.conn.commit()
            print("沒有發現重複記錄")

        return duplicate_count

    def import_illumination_data(self, path, clear_existing=False):
        """
        從CSV文件或目錄導入照度數據並整合到數據庫

        參數:
        - path: 包含照度數據的CSV文件路徑或目錄路徑
        - clear_existing: 是否清空現有照度數據
        """
        try:
            # 檢查是否為目錄
            if os.path.isdir(path):
                # 獲取目錄中所有CSV文件
                csv_files = glob.glob(os.path.join(path, "*.csv"))
                if not csv_files:
                    print(f"在 {path} 中沒有找到CSV文件")
                    return False
                print(f"在目錄 {path} 中找到 {len(csv_files)} 個CSV文件")
            else:
                # 單個文件
                if not os.path.exists(path):
                    print(f"文件 {path} 不存在")
                    return False
                csv_files = [path]
                print(f"將處理單個文件: {path}")

            # 在processed_solar_data表中添加照度列（如果不存在）
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(processed_solar_data)")
            columns = [info[1] for info in cursor.fetchall()]

            if 'illumination' not in columns:
                cursor.execute("ALTER TABLE processed_solar_data ADD COLUMN illumination REAL")
                print("已添加照度列到processed_solar_data表")

            # 同樣在averaged_solar_data表中添加照度列
            cursor.execute("PRAGMA table_info(averaged_solar_data)")
            columns = [info[1] for info in cursor.fetchall()]

            if 'illumination' not in columns:
                cursor.execute("ALTER TABLE averaged_solar_data ADD COLUMN illumination REAL")
                print("已添加照度列到averaged_solar_data表")

            self.conn.commit()

            # 處理每個CSV文件
            total_count = 0
            for csv_file in csv_files:
                filename = os.path.basename(csv_file)
                print(f"處理照度文件: {filename}")

                # 讀取照度數據CSV文件
                df = pd.read_csv(csv_file, encoding='utf-8')
                print(f"  讀取了 {len(df)} 行照度數據")

                # 假設CSV格式如下：第2列(B欄)是站點，第3列(C欄)是時間戳，第6列(F欄)是照度
                # 僅保留站點為 "PMP-TPE-TEMPLE" 的數據
                df = df[df.iloc[:, 1] == "PMP-TPE-TEMPLE"]
                print(f"  篩選後剩餘 {len(df)} 行 PMP-TPE-TEMPLE 站點的照度數據")

                if len(df) == 0:
                    print("  沒有符合條件的照度數據")
                    continue

                # 提取時間戳和照度值
                timestamps = df.iloc[:, 2].values  # C欄，時間戳
                illumination = df.iloc[:, 5].values  # F欄，照度

                # 更新數據庫中的照度值
                file_count = 0
                for i in range(len(timestamps)):
                    # 將時間戳轉換為標準格式 (如果需要)
                    timestamp = pd.to_datetime(timestamps[i]).strftime('%Y-%m-%d %H:%M:%S')

                    # 更新processed_solar_data表中的照度
                    cursor.execute("""
                    UPDATE processed_solar_data 
                    SET illumination = ? 
                    WHERE timestamp = ?
                    """, (float(illumination[i]), timestamp))

                    updated = cursor.rowcount
                    file_count += updated

                self.conn.commit()
                print(f"  已更新 {file_count} 條記錄的照度值")
                total_count += file_count

            # 更新15分鐘平均數據的照度
            self.update_averaged_illumination()

            print(f"總共更新了 {total_count} 條記錄的照度值")
            return True

        except Exception as e:
            print(f"導入照度數據時出錯: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def update_averaged_illumination(self):
        """更新15分鐘平均數據的照度值"""
        cursor = self.conn.cursor()

        # 從處理後的數據中計算15分鐘平均照度
        cursor.execute("""
        UPDATE averaged_solar_data AS avg
        SET illumination = (
            SELECT AVG(p.illumination)
            FROM processed_solar_data AS p
            WHERE strftime('%Y-%m-%d', p.timestamp) = avg.date
            AND strftime('%H', p.timestamp) || ':' || 
                (CAST(strftime('%M', p.timestamp) AS INTEGER) / 15 * 15) = avg.time_interval
            AND p.panel_id = avg.panel_id
        )
        """)

        updated = cursor.rowcount
        self.conn.commit()
        print(f"已更新 {updated} 條15分鐘平均記錄的照度值")

    def export_complete_data(self, output_file='complete_solar_data.csv'):
        """導出完整的數據集，包含所有欄位（包括照度）"""
        try:
            # 確保輸出目錄存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    print(f"已創建目錄: {output_dir}")
                except Exception as e:
                    print(f"創建目錄失敗: {str(e)}")
                    # 改用當前目錄
                    output_file = os.path.basename(output_file)
                    print(f"改用當前目錄: {output_file}")

            # 從處理後的數據表中讀取完整數據
            query = "SELECT * FROM processed_solar_data"
            data = pd.read_sql_query(query, self.conn)

            # 將方位角為數字類型的轉換為字符串類型，以統一數據類型
            data['azimuth_angle'] = data['azimuth_angle'].astype(str)

            # 保存到CSV檔案
            data.to_csv(output_file, index=False)
            print(f"已將 {len(data)} 條完整數據導出至 {output_file}")

            return data

        except Exception as e:
            print(f"導出完整數據時出錯: {str(e)}")
            return None

    def _ensure_tables_structure(self):
        """確保數據表有正確的結構"""
        cursor = self.conn.cursor()

        # 檢查solar_panel_data表的結構
        cursor.execute("PRAGMA table_info(solar_panel_data)")
        columns = {info[1]: info for info in cursor.fetchall()}

        # 確保需要的列都存在
        required_columns = [
            ('is_tracking', 'INTEGER'),
            ('tracking_system', 'TEXT'),
            ('tracking_position', 'TEXT')
        ]

        for col_name, col_type in required_columns:
            if col_name not in columns:
                print(f"添加缺失的列 {col_name} 到 solar_panel_data 表")
                cursor.execute(f"ALTER TABLE solar_panel_data ADD COLUMN {col_name} {col_type}")

        # 同樣檢查processed_solar_data表
        cursor.execute("PRAGMA table_info(processed_solar_data)")
        columns = {info[1]: info for info in cursor.fetchall()}

        for col_name, col_type in required_columns:
            if col_name not in columns:
                print(f"添加缺失的列 {col_name} 到 processed_solar_data 表")
                cursor.execute(f"ALTER TABLE processed_solar_data ADD COLUMN {col_name} {col_type}")

        # 檢查averaged_solar_data表(如果您使用)
        cursor.execute("PRAGMA table_info(averaged_solar_data)")
        columns = {info[1]: info for info in cursor.fetchall()}

        for col_name, col_type in required_columns:
            if col_name not in columns:
                print(f"添加缺失的列 {col_name} 到 averaged_solar_data 表")
                cursor.execute(f"ALTER TABLE averaged_solar_data ADD COLUMN {col_name} {col_type}")

        self.conn.commit()
        print("已確保所有表格結構正確")

    def export_15min_data(self, output_file='15min_solar_data.csv'):
        """導出15分鐘平均數據到CSV文件"""
        query = "SELECT * FROM averaged_solar_data"
        df = pd.read_sql_query(query, self.conn)

        if len(df) == 0:
            print("沒有15分鐘平均數據可導出")
            return False

        # 保存到CSV
        try:
            # 確保輸出目錄存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            df.to_csv(output_file, index=False)
            print(f"已將 {len(df)} 條15分鐘平均數據導出至 {output_file}")
            return True
        except Exception as e:
            print(f"導出15分鐘平均數據時出錯: {str(e)}")
            return False

    def export_daily_data(self, output_file='daily_solar_data.csv'):
        """導出按天整理的數據（每天每個角度組合的數據）"""
        # 從15分鐘平均數據中獲取按天整理的數據
        query = """
        SELECT 
            date, 
            tilt_angle, 
            azimuth_angle, 
            panel_id,
            is_tracking,
            tracking_system,
            tracking_position,
            COUNT(*) as intervals_count,
            AVG(avg_power_W) as daily_avg_power_W,
            MAX(avg_power_W) as max_power_W,
            SUM(avg_power_W * 0.25) as daily_energy_Wh  -- 每15分鐘數據乘以0.25小時
        FROM 
            averaged_solar_data
        GROUP BY 
            date, tilt_angle, azimuth_angle, panel_id, is_tracking, tracking_system, tracking_position
        ORDER BY 
            date, panel_id
        """

        try:
            daily_data = pd.read_sql_query(query, self.conn)

            # 確保輸出目錄存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            daily_data.to_csv(output_file, index=False)
            print(f"已將 {len(daily_data)} 條每日數據導出至 {output_file}")
            return daily_data
        except Exception as e:
            print(f"導出每日數據時出錯: {str(e)}")
            return None

    def export_pivot_power_data(self, output_file='pivot_power_data.csv'):
        """
        導出以panel_id為列，時間為行的15分鐘平均發電功率數據

        參數:
        - output_file: 輸出文件路徑
        """
        try:
            # 從數據庫讀取15分鐘平均數據
            query = """
            SELECT 
                date, time_interval, panel_id, avg_power_W
            FROM 
                averaged_solar_data
            ORDER BY 
                date, time_interval, panel_id
            """

            df = pd.read_sql_query(query, self.conn)

            if len(df) == 0:
                print("沒有15分鐘平均數據可導出")
                return False

            # 創建時間標籤（日期和時間區間組合）
            df['time_label'] = df['date'] + ' ' + df['time_interval']

            # 將數據透視為以panel_id為列的格式
            pivot_df = df.pivot(index='time_label', columns='panel_id', values='avg_power_W')

            # 重置索引，將時間標籤作為一列
            pivot_df = pivot_df.reset_index()

            # 確保輸出目錄存在
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # 保存到CSV
            pivot_df.to_csv(output_file, index=False)
            print(f"已將重組的發電功率數據導出至 {output_file}")

            return pivot_df

        except Exception as e:
            print(f"導出重組數據時出錯: {str(e)}")
            return None

    def close(self):
        """關閉數據庫連接"""
        if self.conn:
            self.conn.close()
            print("數據庫連接已關閉")
# 使用示例
if __name__ == "__main__":
    # 創建數據處理器
    processor = SolarAngleDataProcessor()

    # 導入CSV文件，清空現有數據
    processor.import_csv_files(r'D:\宇靖\先鋒\太陽能板採集數據\20260401_0406\已重命名', clear_existing=True)

    # 處理數據，覆蓋舊記錄，過濾太陽方位角
    processor.process_data(overwrite=True, filter_azimuth=False)

    # 移除重複記錄
    processor.remove_duplicates()

    # 導入照度資料（可以是單個文件或整個目錄）
    processor.import_illumination_data(r'D:\宇靖\先鋒\太陽能板採集數據\照度\solar.radiation-v2_20260407.csv')

    # 計算15分鐘平均值
    #processor.calculate_15min_averages(overwrite=True)

    # 指定輸出目錄
    output_dir = r'D:\宇靖\先鋒\太陽能板採集數據\20260401_0406\已重命名'

    # 確保輸出目錄存在
    import os

    os.makedirs(output_dir, exist_ok=True)

    # 導出各種時間尺度的數據
    processor.export_complete_data(os.path.join(output_dir, 'complete_solar_data.csv'))
    #processor.export_15min_data(os.path.join(output_dir, '15min_solar_data.csv'))
    #processor.export_daily_data(os.path.join(output_dir, 'daily_solar_data.csv'))
    #processor.export_pivot_power_data(os.path.join(output_dir, 'pivot_power_data.csv'))

    # 關閉連接
    processor.close()