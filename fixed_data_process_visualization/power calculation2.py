import pandas as pd
import os


def process_csv_file(file_path):
    """
    處理單個CSV檔案
    """
    try:
        # 讀取CSV檔案
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='big5')

        # 將時間欄位轉換為datetime格式
        df['datetime'] = pd.to_datetime(df.iloc[:, 0])

        # 計算功率 (W) = 電壓 (V) × 電流 (A)
        df['Power(W)'] = df.iloc[:, 1] * df.iloc[:, 3]

        # 添加日期欄位用於計算
        df['date'] = df['datetime'].dt.date

        # 篩選整點數據
        hourly_data = df[df['datetime'].dt.minute == 0].copy()

        # 計算每日發電量 (Wh)
        daily_energy = (hourly_data.groupby('date')['Power(W)']
                        .sum()
                        .reset_index())

        # 將每日發電量數據合併回原始資料框
        df['Daily_Energy(Wh)'] = df['date'].map(
            dict(zip(daily_energy['date'], daily_energy['Power(W)']))
        )

        # 移除暫時使用的日期欄位
        df = df.drop('date', axis=1)

        # 儲存結果到原始檔案
        df.to_csv(file_path, index=False)
        return True, daily_energy['Power(W)'].sum()

    except Exception as e:
        print(f"處理檔案 {os.path.basename(file_path)} 時發生錯誤: {str(e)}")
        return False, 0


def batch_process_folder(folder_path):
    """
    批次處理資料夾內的所有CSV檔案
    """
    try:
        # 確保資料夾路徑存在
        if not os.path.exists(folder_path):
            print(f"找不到資料夾: {folder_path}")
            return

        # 取得所有CSV檔案
        csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]

        if not csv_files:
            print("資料夾中沒有找到CSV檔案")
            return

        print(f"找到 {len(csv_files)} 個CSV檔案")

        # 處理結果統計
        successful_files = 0
        failed_files = 0
        total_energy = 0

        # 處理每個檔案
        for file_name in csv_files:
            file_path = os.path.join(folder_path, file_name)
            print(f"\n處理檔案: {file_name}")

            success, energy = process_csv_file(file_path)
            if success:
                successful_files += 1
                total_energy += energy
                print(f"已完成處理: {file_name}")
            else:
                failed_files += 1

        # 印出總結報告
        print("\n處理完成統計：")
        print(f"成功處理檔案數: {successful_files}")
        print(f"失敗處理檔案數: {failed_files}")
        print(f"總發電量: {total_energy:.2f} Wh")

    except Exception as e:
        print(f"批次處理時發生錯誤: {str(e)}")


# 使用範例
folder_path = r'D:\宇靖\先鋒\太陽能板採集數據\20260210_0219\已重命名'  # 替換成您的資料夾路徑
batch_process_folder(folder_path)