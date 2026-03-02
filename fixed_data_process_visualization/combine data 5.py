import pandas as pd
import os
from pathlib import Path
import glob
from datetime import datetime


def merge_multiple_csvs(file_paths=None, folder_path=None, output_filename=None):
    """
    整合多個CSV檔案

    參數:
    file_paths: 檔案路徑列表
    folder_path: 資料夾路徑（會讀取該資料夾下所有CSV檔案）
    output_filename: 輸出檔案名稱
    """

    # 方法1: 如果提供了檔案路徑列表
    if file_paths:
        csv_files = file_paths
    # 方法2: 如果提供了資料夾路徑，自動找出所有CSV檔案
    elif folder_path:
        if not os.path.exists(folder_path):
            print(f"錯誤：找不到資料夾：{folder_path}")
            return None

        # 使用glob找出所有CSV檔案
        pattern = os.path.join(folder_path, "*.csv")
        csv_files = glob.glob(pattern)

        if not csv_files:
            print(f"錯誤：在資料夾 {folder_path} 中找不到任何CSV檔案")
            return None

        print(f"找到 {len(csv_files)} 個CSV檔案：")
        for i, file in enumerate(csv_files, 1):
            print(f"  {i}. {os.path.basename(file)}")
    else:
        print("錯誤：請提供檔案路徑列表或資料夾路徑")
        return None

    # 確認所有檔案都存在
    missing_files = []
    for file_path in csv_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)

    if missing_files:
        print("錯誤：以下檔案不存在：")
        for file in missing_files:
            print(f"  - {file}")
        return None

    # 讀取所有CSV檔案
    dataframes = []
    total_rows = 0
    all_columns = set()

    print(f"\n開始讀取 {len(csv_files)} 個檔案...")

    for i, file_path in enumerate(csv_files, 1):
        try:
            print(f"正在讀取檔案 {i}/{len(csv_files)}: {os.path.basename(file_path)}")
            df = pd.read_csv(file_path)
            dataframes.append(df)

            # 統計資訊
            rows = len(df)
            cols = len(df.columns)
            total_rows += rows
            all_columns.update(df.columns)

            print(f"  → 資料量：{rows:,} 筆，欄位數：{cols}")

        except Exception as e:
            print(f"錯誤：讀取檔案 {file_path} 時發生錯誤：{str(e)}")
            return None

    # 分析欄位差異
    print(f"\n欄位分析：")
    print(f"總共有 {len(all_columns)} 個不同的欄位")

    # 檢查每個檔案的欄位
    for i, (df, file_path) in enumerate(zip(dataframes, csv_files)):
        missing_cols = all_columns - set(df.columns)
        if missing_cols:
            print(f"檔案 {os.path.basename(file_path)} 缺少的欄位：{missing_cols}")

    # 合併所有資料
    print(f"\n正在合併 {len(dataframes)} 個資料集...")
    try:
        combined_df = pd.concat(dataframes, ignore_index=True)
        print(f"合併成功！")
        print(f"  → 總資料量：{len(combined_df):,} 筆")
        print(f"  → 總欄位數：{len(combined_df.columns)}")

        # 檢查重複資料
        duplicates = combined_df.duplicated().sum()
        if duplicates > 0:
            print(f"  → 發現 {duplicates:,} 筆重複資料")
            remove_duplicates = input("是否要移除重複資料？(y/n): ").lower().strip()
            if remove_duplicates == 'y':
                combined_df = combined_df.drop_duplicates(ignore_index=True)
                print(f"  → 移除重複後：{len(combined_df):,} 筆")

    except Exception as e:
        print(f"錯誤：合併資料時發生錯誤：{str(e)}")
        return None

    # 決定輸出路徑
    if file_paths:
        output_dir = os.path.dirname(file_paths[0])
    else:
        output_dir = folder_path

    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"combined_data_{timestamp}.csv"

    output_path = os.path.join(output_dir, output_filename)

    # 儲存合併後的檔案
    try:
        print(f"\n正在儲存到：{output_path}")
        combined_df.to_csv(output_path, index=False)
        print("✅ 檔案合併完成！")
        return output_path

    except Exception as e:
        print(f"錯誤：儲存檔案時發生錯誤：{str(e)}")
        return None


# ==================== 使用範例 ====================

if __name__ == "__main__":
    # 方法1：指定多個檔案路徑
    file_paths = [
        r"D:\宇靖\先鋒\太陽能板採集數據\20250301_20260209\combined_solar_data_20250301_20260209.csv",
        r"D:\宇靖\先鋒\太陽能板採集數據\20260210_0219\已重命名\complete_solar_data.csv",

        # 可以繼續添加更多檔案路徑
        # r"路徑3.csv",
        # r"路徑4.csv",
    ]

    # 執行合併（使用指定檔案列表）
    print("=== 方法1：使用指定檔案列表 ===")
    result = merge_multiple_csvs(
        file_paths=file_paths,
        output_filename="combined_solar_data_20250301_20260219.csv"
    )

    # ==========================================

    # 方法2：指定資料夾，自動合併該資料夾下所有CSV檔案
    # folder_path = r"D:\宇靖\先鋒\太陽能板採集數據"
    #
    # print("\n=== 方法2：自動合併資料夾內所有CSV檔案 ===")
    # result = merge_multiple_csvs(
    #     folder_path=folder_path,
    #     output_filename="all_solar_data_merged.csv"
    # )

    # ==========================================

    # 方法3：互動式選擇檔案
    # print("\n=== 方法3：互動式選擇 ===")
    # choice = input("選擇合併方式：\n1. 指定檔案列表\n2. 合併資料夾內所有CSV\n請輸入 1 或 2: ").strip()
    #
    # if choice == "1":
    #     # 讓使用者輸入檔案路徑
    #     files = []
    #     print("請輸入要合併的檔案路徑（輸入空白行結束）：")
    #     while True:
    #         file_path = input("檔案路徑: ").strip()
    #         if not file_path:
    #             break
    #         files.append(file_path)
    #
    #     if files:
    #         output_name = input("輸出檔案名稱（可選，直接按Enter使用預設）: ").strip()
    #         result = merge_multiple_csvs(
    #             file_paths=files,
    #             output_filename=output_name if output_name else None
    #         )
    #
    # elif choice == "2":
    #     folder = input("請輸入資料夾路徑: ").strip()
    #     output_name = input("輸出檔案名稱（可選，直接按Enter使用預設）: ").strip()
    #     result = merge_multiple_csvs(
    #         folder_path=folder,
    #         output_filename=output_name if output_name else None
    #     )