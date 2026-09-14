import pandas as pd
import os
import re

# 输入文件
input_file = r"C:\Users\Mi\Downloads\User Acquisition-2026-08-17-2026-09-04.xlsx"

# 输出目录
output_dir = r"C:\Users\Mi\Desktop\渠道拆分文件夹"
os.makedirs(output_dir, exist_ok=True)

# 读取文件
if input_file.endswith('.xlsx'):
    df = pd.read_excel(input_file)
else:
    df = pd.read_csv(input_file)
print(f"总行数: {len(df)}")

# 提取渠道分组 - 根据Sub Param 2列
def extract_channel(sub_param):
    if pd.isna(sub_param):
        return 'unknown'
    param_str = str(sub_param)
    # 提取第一个下划线前的数字
    match = re.match(r'^(\d+)', param_str)
    if match:
        return match.group(1)
    return 'unknown'

df['渠道'] = df['Sub Param 2'].apply(extract_channel)

# 统计各渠道数量
channel_counts = df['渠道'].value_counts()
print(f"\n渠道分布:")
print(channel_counts)

# 按渠道拆分并保存
for channel in channel_counts.index:
    channel_df = df[df['渠道'] == channel]
    # 删除临时的渠道列
    channel_df = channel_df.drop(columns=['渠道'])

    output_file = os.path.join(output_dir, f"tutu_{channel}.csv")
    channel_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"已保存: {output_file} ({len(channel_df)}行)")

print(f"\n拆分完成! 共 {len(channel_counts)} 个渠道文件")
