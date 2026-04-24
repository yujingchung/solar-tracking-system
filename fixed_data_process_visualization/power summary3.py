import pandas as pd
import os
import re


def extract_system_info(file_name):
    """
    從檔案名稱中提取系統類型和角度信息
    返回: (系統類型, 傾角, 方位角/方向)
    """
    try:
        # 處理追日系統的情況
        tracking_match = re.search(r'(追日系統[12])\s*傾角(\d+)(上|下)', file_name)
        if tracking_match:
            system = tracking_match.group(1)
            angle = int(tracking_match.group(2))
            direction = tracking_match.group(3)
            return system, angle, direction

        # 處理一般固定角度的情況
        # 移除檔案名稱末尾的數字（如果有的話）
        base_name = re.sub(r'\d+$', '', file_name)
        fixed_match = re.search(r'傾角(\d+)度方位角(\d+)度', base_name)
        if fixed_match:
            angle = int(fixed_match.group(1))
            azimuth = int(fixed_match.group(2))
            return "固定式", angle, azimuth

        return None
    except Exception:
        return None


def find_matching_panels(pivot_table):
    """
    找出具有相同角度組合的面板對
    """
    matching_pairs = []

    # 獲取index的多級索引值
    index_values = pivot_table.index.values

    # 創建一個字典來存儲相同組合的面板
    combination_dict = {}

    for idx in index_values:
        system_type, angle, direction, panel = idx
        # 創建不包含面板編號的key
        key = (system_type, angle, direction)

        if key not in combination_dict:
            combination_dict[key] = []
        combination_dict[key].append(panel)

    # 找出有多個面板的組合
    for key, panels in combination_dict.items():
        if len(panels) > 1:
            # 為每對面板創建比較組合
            for i in range(len(panels) - 1):
                for j in range(i + 1, len(panels)):
                    matching_pairs.append((key, panels[i], panels[j]))

    return matching_pairs


def create_comparison_table(pivot_table, matching_pairs):
    """
    創建面板比較表，以日期為主要排序依據
    """
    comparison_data = []

    # 獲取所有日期
    all_dates = pivot_table.columns

    # 對每個日期進行處理
    for date in all_dates:
        # 對每對匹配的面板進行比較
        for (system_type, angle, direction), panel1, panel2 in matching_pairs:
            # 獲取兩個面板的數據
            value1 = pivot_table.loc[(system_type, angle, direction, panel1), date]
            value2 = pivot_table.loc[(system_type, angle, direction, panel2), date]

            if pd.notna(value1) and pd.notna(value2) and value1 != 0:
                difference = value2 - value1
                relative_error = (difference / value1) * 100  # 轉換為百分比

                comparison_data.append({
                    '日期': date,
                    '系統類型': system_type,
                    '傾角': angle,
                    '方位角/方向': direction,
                    '面板1': panel1,
                    '面板2': panel2,
                    '面板1發電量(Wh)': value1,
                    '面板2發電量(Wh)': value2,
                    '發電量差異(Wh)': difference,
                    '相對誤差(%)': relative_error
                })

    if comparison_data:
        # 創建DataFrame並按日期和其他欄位排序
        df = pd.DataFrame(comparison_data)
        df = df.sort_values(['日期', '系統類型', '傾角', '方位角/方向'])
        return df
    return None


def create_power_summary(base_folder):
    """
    創建發電量匯總表，自動為相同角度組合的面板編號
    """
    try:
        # 首先收集所有檔案並進行分組
        file_groups = {}
        for root, dirs, files in os.walk(base_folder):
            for file in files:
                if file.endswith('.csv'):
                    system_info = extract_system_info(file)
                    if system_info:
                        key = system_info  # 使用系統類型和角度作為分組鍵
                        if key not in file_groups:
                            file_groups[key] = []
                        file_groups[key].append((file, os.path.join(root, file)))

        all_data = []

        # 處理每個分組
        for system_info, file_list in file_groups.items():
            # 為每個檔案分配面板編號
            for panel_num, (file, file_path) in enumerate(sorted(file_list), 1):
                try:
                    # 讀取CSV檔案
                    df = pd.read_csv(file_path)

                    if 'Daily_Energy(Wh)' not in df.columns:
                        print(f"檔案缺少Daily_Energy(Wh)欄位: {file}")
                        continue

                    # 將datetime轉換為日期
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df['date'] = df['datetime'].dt.date

                    # 取得每日發電量
                    daily_energy = df.groupby('date')['Daily_Energy(Wh)'].first().reset_index()

                    # 添加系統信息
                    system_type, angle, direction = system_info
                    daily_energy['系統類型'] = system_type
                    daily_energy['傾角'] = angle
                    daily_energy['方位角/方向'] = direction
                    daily_energy['面板編號'] = f'#{panel_num}'

                    all_data.append(daily_energy)

                except Exception as e:
                    print(f"處理檔案 {file} 時發生錯誤: {str(e)}")
                    continue

        if not all_data:
            print("沒有找到可用的數據")
            return

        # 合併所有數據
        combined_data = pd.concat(all_data, ignore_index=True)

        # 創建樞紐表
        pivot_table = pd.pivot_table(
            combined_data,
            values='Daily_Energy(Wh)',
            index=['系統類型', '傾角', '方位角/方向', '面板編號'],
            columns=['date'],
            aggfunc='first'
        )

        # 找出相同組合的面板對
        matching_pairs = find_matching_panels(pivot_table)

        # 創建比較表
        comparison_df = create_comparison_table(pivot_table, matching_pairs)

        # 創建輸出檔案路徑
        output_file = os.path.join(base_folder, '發電量統計表_編號區分.xlsx')

        # 將結果寫入Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # 寫入面板數據
            pivot_table.to_excel(writer, sheet_name='日發電量統計')

            # 創建總發電量統計表
            total_power = pivot_table.sum(axis=1).reset_index()
            total_power.columns = ['系統類型', '傾角', '方位角/方向', '面板編號', '總發電量(Wh)']
            total_power.to_excel(writer, sheet_name='總發電量統計', index=False)

            # 修改: 創建角度組合平均值表，而不是總和
            angle_summary = combined_data.groupby(['系統類型', '傾角', '方位角/方向', 'date'])[
                'Daily_Energy(Wh)'].mean().reset_index()  # 改用mean()而不是sum()
            angle_pivot = pd.pivot_table(
                angle_summary,
                values='Daily_Energy(Wh)',
                index=['系統類型', '傾角', '方位角/方向'],
                columns=['date'],
                aggfunc='first'
            )
            # 修改工作表名稱以反映這是平均值
            angle_pivot.to_excel(writer, sheet_name='角度組合平均發電量')

            # 寫入面板比較表（以日期排序）
            if comparison_df is not None:
                # 設定數字格式
                workbook = writer.book
                worksheet = workbook.create_sheet('面板比較分析')
                comparison_df.to_excel(writer, sheet_name='面板比較分析', index=False)

                # 獲取工作表
                worksheet = writer.sheets['面板比較分析']

                # 設定欄寬
                for column in worksheet.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

        print(f"統計表已儲存至: {output_file}")
        print("\n檔案包含四個工作表:")
        print("1. 日發電量統計: 顯示每個面板的每日發電量")
        print("2. 總發電量統計: 顯示每個面板的總發電量")
        print("3. 角度組合平均發電量: 顯示每個角度組合的平均發電量")
        print("4. 面板比較分析: 以日期為主要排序，顯示相同組合面板間的發電量差異和相對誤差")

    except Exception as e:
        print(f"創建統計表時發生錯誤: {str(e)}")


if __name__ == "__main__":
    # 使用範例
    base_folder = r'D:\宇靖\先鋒\太陽能板採集數據\20260401_0406\已重命名'  # 替換成您的資料夾路徑
    create_power_summary(base_folder)