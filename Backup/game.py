import pygame
import sys
import random

# 初始化pygame
pygame.init()

# 设置屏幕大小
screen_width = 800
screen_height = 600
screen = pygame.display.set_mode((screen_width, screen_height))

# 设置颜色
black = (0, 0, 0)
white = (255, 255, 255)
red = (255, 0, 0)

# 设置游戏时钟
clock = pygame.time.Clock()
fps = 60

# 定义球的属性
ball_x = screen_width // 2
ball_y = screen_height // 2
ball_radius = 10
ball_speed_x = 5 * random.choice([-1, 1])
ball_speed_y = 5 * random.choice([-1, 1])

# 定义挡板的属性
paddle_width = 100
paddle_height = 20
paddle_x = (screen_width - paddle_width) // 2
paddle_y = screen_height - paddle_height - 10
paddle_speed = 15

# 游戏循环
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # 挡板控制
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT] and paddle_x > 0:
        paddle_x -= paddle_speed
    if keys[pygame.K_RIGHT] and paddle_x < screen_width - paddle_width:
        paddle_x += paddle_speed

    # 球的运动
    ball_x += ball_speed_x
    ball_y += ball_speed_y

    # 球碰撞边界的处理
    if ball_x <= 0 or ball_x >= screen_width:
        ball_speed_x = -ball_speed_x
    if ball_y <= 0:
        ball_speed_y = -ball_speed_y
    if ball_y >= screen_height:
        print("游戏结束")
        pygame.quit()
        sys.exit()

    # 球和挡板的碰撞
    if (paddle_x <= ball_x <= paddle_x + paddle_width) and (paddle_y <= ball_y + ball_radius <= paddle_y + paddle_height):
        ball_speed_y = -ball_speed_y

    # 清屏
    screen.fill(black)

    # 绘制球和挡板
    pygame.draw.circle(screen, red, (ball_x, ball_y), ball_radius)
    pygame.draw.rect(screen, white, (paddle_x, paddle_y, paddle_width, paddle_height))

    # 更新屏幕显示
    pygame.display.flip()

    # 控制游戏速度
    clock.tick(fps)

pygame.quit()