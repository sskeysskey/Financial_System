import cv2
import pyautogui
import numpy as np
from time import sleep
from PIL import ImageGrab

def capture_screen():
    # 使用PIL的ImageGrab直接截取屏幕
    screenshot = ImageGrab.grab()
    # 将截图对象转换为OpenCV格式
    screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return screenshot

# 查找图片
def find_image_on_screen(template_path, threshold=0.9):
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"模板图片未能正确读取于路径 {template_path}")
    screen = capture_screen()
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    # 释放截图和模板图像以节省内存
    del screen
    if max_val >= threshold:
        return max_loc, template.shape
    else:
        return None, None

# 主函数
def main():
    template_menuindex = '/Users/yanzhang/Documents/python_code/Resource/Stock_menu_index.png'
    template_searchlogo = '/Users/yanzhang/Documents/python_code/Resource/Stock_search_logo.png'
    template_shiftwatchlist = '/Users/yanzhang/Documents/python_code/Resource/Stock_shift_watchlist.png'
    template_watchlistindex = '/Users/yanzhang/Documents/python_code/Resource/Stock_watchlist_Index.png'
    
    found_watchlistindex = False
    while not found_watchlistindex:
        location, shape = find_image_on_screen(template_watchlistindex)
        if location:
            found_watchlistindex = True
            print(f"找到图片位置: {location}")
        else:
            print("未找到图片，继续监控...")
            location, shape = find_image_on_screen(template_shiftwatchlist)
            if location:
                print("找到图片，继续执行")
                # 计算中心坐标
                center_x = (location[0] + shape[1] // 2) // 2
                center_y = (location[1] + shape[0] // 2) // 2
                
                # 鼠标点击中心坐标
                pyautogui.click(center_x, center_y)
                sleep(1)
                location, shape = find_image_on_screen(template_menuindex)
                if location:
                    print("找到poe_stillwaiting图片，执行页面刷新操作...")
                    # 计算中心坐标
                    center_x = (location[0] + shape[1] // 2) // 2
                    center_y = (location[1] + shape[0] // 2) // 2
                    
                    # 鼠标点击中心坐标
                    pyautogui.click(center_x, center_y)
                    found_watchlistindex = True
                sleep(1)  # 简短暂停
            sleep(1)  # 简短暂停
    
    found_searchlogo = False
    while not found_searchlogo:
        location, shape = find_image_on_screen(template_searchlogo)
        if location:
            print("找到图片，继续监控...")
            # 计算中心坐标
            center_x = (location[0] + shape[1] // 2) // 2
            center_y = (location[1] + shape[0] // 2) // 2

            start_x = center_x - 18
            start_y = center_y + 70
            
            # 写入坐标到文件
            with open('/tmp/coordinates.txt', 'w') as f:
                f.write(f'{start_x}\n{start_y}\n')
            found_searchlogo = True
        else:
            print("图片没找到，继续找...")
            sleep(1)

if __name__ == '__main__':
    main()