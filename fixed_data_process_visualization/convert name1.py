import os
import re
from datetime import datetime


def convert_filename(old_filename):
    """
    將原始檔名轉換為包含傾角和方位角的新檔名
    例如: Z3A0412097(20241227150146).csv -> 傾角20度方位角180度.csv

    Args:
        old_filename (str): 原始檔名

    Returns:
        str: 轉換後的新檔名
    """
    # 產品代碼對應的傾角和方位角，加入編號
    product_mapping = {
        'Z3A0412097': {'tilt': 20, 'azimuth': 180, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412118': {'tilt': 20, 'azimuth': 180, 'type': 'normal'},  # 不加編號
        'Z3A0412115': {'tilt': 30, 'azimuth': 180, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412106': {'tilt': 30, 'azimuth': 180, 'type': 'normal'},  # 不加編號
        'Z3A0412107': {'tilt': 30, 'azimuth': 160, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0512127': {'tilt': 30, 'azimuth': 160, 'type': 'normal'},  # 不加編號
        'Z3A0512134': {'tilt': 20, 'azimuth': 160, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412116': {'tilt': 20, 'azimuth': 160, 'type': 'normal'},  # 不加編號
        'Z3A0412095': {'tilt': 20, 'azimuth': 200, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0512128': {'tilt': 20, 'azimuth': 200, 'type': 'normal'},  # 不加編號
        'Z3A0512135': {'tilt': 30, 'azimuth': 200, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412112': {'tilt': 30, 'azimuth': 200, 'type': 'normal'},  # 不加編號
        'Z3A0512133': {'tilt': 10, 'azimuth': 180, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412122': {'tilt': 10, 'azimuth': 180, 'type': 'normal'},  # 不加編號
        'Z3A0412099': {'tilt': 15, 'azimuth': 180, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412108': {'tilt': 15, 'azimuth': 180, 'type': 'normal'},  # 不加編號
        'Z3A0512132': {'tilt': 10, 'azimuth': 160, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0512129': {'tilt': 10, 'azimuth': 160, 'type': 'normal'},  # 不加編號
        'Z3A0412098': {'tilt': 15, 'azimuth': 160, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412113': {'tilt': 15, 'azimuth': 160, 'type': 'normal'},  # 不加編號
        'Z3A0512125': {'tilt': 15, 'azimuth': 200, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412105': {'tilt': 15, 'azimuth': 200, 'type': 'normal'},  # 不加編號
        'Z3A0512126': {'tilt': 10, 'azimuth': 200, 'type': 'normal', 'number': 1},  # 編號1
        'Z3A0412120': {'tilt': 10, 'azimuth': 200, 'type': 'normal'},  # 不加編號
        'Z3A0412111': {'tilt': 25, 'azimuth': 0, 'type': 'tracker_up'},  # 追日系統2 傾角25 上
        'Z3A0512124': {'tilt': 25, 'azimuth': 0, 'type': 'tracker_down'},  # 追日系統2 傾角25 下
        'Z3A0412103': {'tilt': 20, 'azimuth': 0, 'type': 'tracker_up'},  # 追日系統1 傾角20 上
        'Z3A0312076': {'tilt': 20, 'azimuth': 0, 'type': 'tracker_down'},  # 追日系統1 傾角20 下
        'Z3A0512130': {'tilt': 0, 'azimuth': 0, 'type': 'spare'},  # 備用1
        'Z3A0512131': {'tilt': 0, 'azimuth': 0, 'type': 'spare'},  # 備用2
    }

    # 使用正則表達式提取產品代碼
    match = re.match(r'([A-Z0-9]+)\(.*?\)', old_filename)
    if not match:
        raise ValueError(f"無法解析檔名格式: {old_filename}")

    product_code = match.group(1)

    # 檢查產品代碼是否在對應表中
    if product_code not in product_mapping:
        raise ValueError(f"找不到產品代碼的對應資料: {product_code}")

    # 取得對應的傾角和方位角資料
    data = product_mapping[product_code]

    # 根據類型建立新檔名
    if data['type'] == 'normal':
        base_name = f"傾角{data['tilt']}度方位角{data['azimuth']}度"
        # 如果有編號，加上編號
        if 'number' in data:
            new_filename = f"{base_name}{data['number']}"
        else:
            new_filename = base_name
    elif data['type'] == 'tracker_up':
        new_filename = f"追日系統{2 if data['tilt'] == 25 else 1} 傾角{data['tilt']}上"
    elif data['type'] == 'tracker_down':
        new_filename = f"追日系統{2 if data['tilt'] == 25 else 1} 傾角{data['tilt']}下"
    elif data['type'] == 'spare':
        spare_number = '1' if product_code == 'Z3A0512130' else '2'
        new_filename = f"備用{spare_number}"

    # 保留原始檔案的副檔名
    original_extension = os.path.splitext(old_filename)[1]
    new_filename = new_filename + original_extension

    return new_filename


def find_csv_in_folder(folder_path):
    """
    在資料夾中找到符合條件的CSV檔案

    Args:
        folder_path (str): 子資料夾路徑

    Returns:
        tuple: (找到的CSV檔案名, 檔案完整路徑) 或 (None, None)
    """
    for file in os.listdir(folder_path):
        if file.lower().endswith('.csv'):
            # 您可以在這裡添加更多條件，比如檢查文件名是否符合特定格式
            file_path = os.path.join(folder_path, file)
            return file, file_path

    return None, None


def batch_rename_files(base_directory):
    """
    處理基礎目錄中的所有子資料夾，每個子資料夾尋找並重命名CSV檔案

    Args:
        base_directory (str): 基礎目錄路徑
    """
    # 確保目錄存在
    if not os.path.exists(base_directory):
        print(f"錯誤: 目錄不存在 - {base_directory}")
        return

    # 建立輸出目錄
    output_directory = os.path.join(base_directory, "已重命名")
    os.makedirs(output_directory, exist_ok=True)

    # 處理計數器
    processed_count = 0
    error_count = 0

    # 遍歷基礎目錄中的所有子資料夾
    for subfolder_name in os.listdir(base_directory):
        subfolder_path = os.path.join(base_directory, subfolder_name)

        # 跳過非目錄和輸出目錄
        if not os.path.isdir(subfolder_path) or subfolder_name == "已重命名":
            continue

        # 在子資料夾中尋找CSV檔案
        csv_file, csv_file_path = find_csv_in_folder(subfolder_path)

        if csv_file:
            try:
                # 轉換檔名
                new_filename = convert_filename(csv_file)

                # 建立新的檔案路徑
                new_file_path = os.path.join(output_directory, new_filename)

                # 複製檔案(不移動原檔)
                import shutil
                shutil.copy2(csv_file_path, new_file_path)

                print(f"已處理: {subfolder_name}/{csv_file} -> {new_filename}")
                processed_count += 1

            except ValueError as e:
                print(f"錯誤 ({subfolder_name}): {e}")
                error_count += 1
            except Exception as e:
                print(f"處理資料夾 {subfolder_name} 時發生錯誤: {e}")
                error_count += 1
        else:
            print(f"警告: 在資料夾 {subfolder_name} 中未找到CSV檔案")

    # 輸出摘要
    print(f"\n處理完成！")
    print(f"總共處理: {processed_count} 個檔案")
    print(f"發生錯誤: {error_count} 個檔案")
    print(f"重命名後的檔案已儲存至: {output_directory}")


# 使用範例
if __name__ == "__main__":
    # 使用原始字串（在字串前加上 r）來避免轉義字元問題
    directory_path = r"D:\宇靖\先鋒\太陽能板採集數據\20260401_0406"

    # 輸出當前處理的目錄
    print(f"正在處理目錄: {directory_path}")
    print("開始掃描子資料夾中的CSV檔案...")

    # 執行批次重新命名
    batch_rename_files(directory_path)