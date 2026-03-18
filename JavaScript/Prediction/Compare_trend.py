import json
import os

def process_kalshi_data(old_file_path, new_file_path, output_file_path):
    # 1. 读取旧文件并建立索引
    # 使用字典存储 name -> item_object，方便后续获取完整信息
    old_data_map = {}
    if os.path.exists(old_file_path):
        with open(old_file_path, 'r', encoding='utf-8') as f:
            try:
                old_data = json.load(f)
                for item in old_data:
                    old_data_map[item['name']] = item
            except json.JSONDecodeError:
                print(f"警告: {old_file_path} 格式错误，跳过旧数据读取。")

    # 2. 处理新文件并计算差值与标记
    result_data = []
    if os.path.exists(new_file_path):
        with open(new_file_path, 'r', encoding='utf-8') as f:
            try:
                new_data = json.load(f)
                for item in new_data:
                    name = item['name']
                    new_volume = int(item.get('volume', 0))
                    
                    # 判断是否为新出现的项目
                    if name in old_data_map:
                        # A类型：两者都有
                        old_volume = int(old_data_map[name].get('volume', 0))
                        trend = new_volume - old_volume
                        item['new'] = 0  # 标记为 0
                    else:
                        # B类型：只有新的有
                        trend = new_volume
                        item['new'] = 1  # 标记为 1
                    
                    # 将计算出的 trend 添加到当前对象中
                    item['volume_trend'] = trend
                    
                    # 将完整的对象存入列表
                    result_data.append(item)
            except json.JSONDecodeError:
                print(f"错误: {new_file_path} 格式错误，无法处理。")
                return

    # 3. 按 volume_trend 降序排序
    result_data.sort(key=lambda x: x['volume_trend'], reverse=True)

    # 4. 写入结果文件
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    print(f"处理完成，结果已保存至: {output_file_path}")

# 设置文件路径
base_dir = "/Users/yanzhang/Downloads"
old_file = os.path.join(base_dir, "kalshi_260317.json")
new_file = os.path.join(base_dir, "kalshi_260318.json")
output_file = os.path.join(base_dir, "kalshi_trend.json")

# 执行函数
process_kalshi_data(old_file, new_file, output_file)