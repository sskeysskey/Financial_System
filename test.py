import pygame
import sys

# 初始化 Pygame
pygame.init()

# 屏幕大小
screen_width = 800
screen_height = 600

# 颜色定义
black = (0, 0, 0)
white = (255, 255, 255)

# 初始化屏幕
screen = pygame.display.set_mode((screen_width, screen_height))
pygame.display.set_caption('弹球游戏')

# 球类
class Ball:
    def __init__(self):
        self.rect = pygame.Rect(screen_width // 2, screen_height // 2, 15, 15)
        self.speed = [5, 5]
    
    def move(self):
        self.rect.x += self.speed[0]
        self.rect.y += self.speed[1]
        if self.rect.top <= 0 or self.rect.bottom >= screen_height:
            self.speed[1] = -self.speed[1]
        if self.rect.left <= 0 or self.rect.right >= screen_width:
            self.speed[0] = -self.speed[0]

    def draw(self):
        pygame.draw.ellipse(screen, white, self.rect)

# 玩家类
class Paddle:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 10, 100)
        self.speed = 5
    
    def move(self, up, down):
        keys = pygame.key.get_pressed()
        if keys[up] and self.rect.top > 0:
            self.rect.y -= self.speed
        if keys[down] and self.rect.bottom < screen_height:
            self.rect.y += self.speed

    def draw(self):
        pygame.draw.rect(screen, white, self.rect)

# 记分系统
class Score:
    def __init__(self):
        self.score = 0
        self.font = pygame.font.Font(None, 36)

    def increase(self):
        self.score += 1

    def draw(self):
        score_text = self.font.render(f'Score: {self.score}', True, white)
        screen.blit(score_text, (screen_width // 2 - score_text.get_width() // 2, 20))

# 游戏初始化
ball = Ball()
player1 = Paddle(screen_width - 20, screen_height // 2 - 50)
player2 = Paddle(10, screen_height // 2 - 50)
score = Score()

# 主游戏循环
clock = pygame.time.Clock()
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    ball.move()
    player1.move(pygame.K_UP, pygame.K_DOWN)
    player2.move(pygame.K_w, pygame.K_s)

    if ball.rect.colliderect(player1.rect) or ball.rect.colliderect(player2.rect):
        ball.speed[0] = -ball.speed[0]
        score.increase()

    screen.fill(black)
    ball.draw()
    player1.draw()
    player2.draw()
    score.draw()
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()