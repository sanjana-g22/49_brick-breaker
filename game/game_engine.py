import math
import pygame
from .paddle import Paddle
from .ball import Ball
from .brick import Brick

# Game Engine

WHITE = (255, 255, 255)
BG = (15, 15, 25)
BRICK_COLORS = [
    (200, 60, 60),
    (200, 140, 60),
    (200, 200, 60),
    (80, 180, 80),
    (80, 140, 200),
]

class GameEngine:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.paddle = Paddle(width // 2 - 50, height - 30, 100, 14)

        self.ball = Ball(width // 2, height - 50, radius=8)
        self.ball.vx, self.ball.vy = 4, -4

        self.rows, self.cols = 5, 8
        self.bricks = self._build_bricks(self.rows, self.cols)

        self.lives = 3
        self.score = 0
        self.font = pygame.font.SysFont("Arial", 28)
        self.game_over = False
        self.result = None  # "win" or "lose"

    def _build_bricks(self, rows, cols):
        bricks = []
        margin, gap, top = 30, 6, 60
        brick_w = (self.width - margin * 2 - gap * (cols - 1)) // cols
        brick_h = 22
        for r in range(rows):
            for c in range(cols):
                x = margin + c * (brick_w + gap)
                y = top + r * (brick_h + gap)
                bricks.append(Brick(x, y, brick_w, brick_h))
        return bricks

    def handle_event(self, event):
        # This game only needs continuously-held-key input for the
        # paddle, handled in handle_input each frame.
        pass

    def handle_input(self):
        if self.game_over:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.paddle.move(-self.paddle.speed, self.width)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.paddle.move(self.paddle.speed, self.width)

    def update(self):
        if self.game_over:
            return

        ball = self.ball

        # Sub-stepping: move the ball in small increments so it can never
        # travel far enough in one step to skip over a brick or the paddle.
        max_step = max(1.0, ball.radius * 0.5)
        steps = max(1, math.ceil(max(abs(ball.vx), abs(ball.vy)) / max_step))

        for _ in range(steps):
            ball.x += ball.vx / steps
            ball.y += ball.vy / steps

            # ---------------- Paddle ----------------
            ball_rect = ball.rect()
            paddle_rect = self.paddle.rect()

            # Only bounce when moving downward and hitting from above,
            # which prevents re-colliding / jittering while inside the paddle.
            if (ball.vy > 0
                    and ball_rect.colliderect(paddle_rect)
                    and ball_rect.centery < paddle_rect.centery):
                # Push the ball out so it sits on top of the paddle
                ball.y -= ball_rect.bottom - paddle_rect.top

                # Bounce angle depends on where the ball hit: -1 (left edge) to +1 (right edge)
                offset = (ball_rect.centerx - paddle_rect.centerx) / (paddle_rect.width / 2)
                offset = max(-1.0, min(1.0, offset))

                max_angle = math.radians(60)  # max deviation from vertical
                angle = offset * max_angle
                speed = math.hypot(ball.vx, ball.vy)

                ball.vx = speed * math.sin(angle)
                ball.vy = -speed * math.cos(angle)  # always upward

            # ---------------- Bricks ----------------
            ball_rect = ball.rect()
            hit_brick = None
            best_area = 0

            # If several bricks overlap, resolve against the one with the most overlap
            for brick in self.bricks:
                if brick.alive and ball_rect.colliderect(brick.rect()):
                    overlap = ball_rect.clip(brick.rect())
                    area = overlap.width * overlap.height
                    if area > best_area:
                        best_area = area
                        hit_brick = brick

            if hit_brick is not None:
                brick_rect = hit_brick.rect()
                hit_brick.alive = False
                self.score += 1

                # Penetration depth from each side of the brick
                over_left = ball_rect.right - brick_rect.left      # ball entered from the left
                over_right = brick_rect.right - ball_rect.left     # ball entered from the right
                over_top = ball_rect.bottom - brick_rect.top       # ball entered from the top
                over_bottom = brick_rect.bottom - ball_rect.top    # ball entered from the bottom

                min_x = min(over_left, over_right)
                min_y = min(over_top, over_bottom)

                if min_x < min_y:
                    # Side hit: flip vx and push out horizontally
                    if over_left < over_right:
                        ball.x -= over_left
                        ball.vx = -abs(ball.vx)
                    else:
                        ball.x += over_right
                        ball.vx = abs(ball.vx)
                else:
                    # Top/bottom hit: flip vy and push out vertically
                    if over_top < over_bottom:
                        ball.y -= over_top
                        ball.vy = -abs(ball.vy)
                    else:
                        ball.y += over_bottom
                        ball.vy = abs(ball.vy)

        # ---------------- Walls ----------------
        if ball.x - ball.radius <= 0:
            ball.x = ball.radius
            ball.vx = abs(ball.vx)
        elif ball.x + ball.radius >= self.width:
            ball.x = self.width - ball.radius
            ball.vx = -abs(ball.vx)
        if ball.y - ball.radius <= 0:
            ball.y = ball.radius
            ball.vy = abs(ball.vy)

        # ---------------- Lives / win ----------------
        if ball.y - ball.radius > self.height:
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self.result = "lose"
            else:
                self._reset_ball()

        if all(not b.alive for b in self.bricks):
            self.game_over = True
            self.result = "win"

    def _reset_ball(self):
        self.ball.x, self.ball.y = self.width // 2, self.height - 50
        self.ball.vx, self.ball.vy = 4, -4

    def render(self, screen):
        screen.fill(BG)

        pygame.draw.rect(screen, WHITE, self.paddle.rect())
        pygame.draw.circle(screen, WHITE, (int(self.ball.x), int(self.ball.y)), self.ball.radius)

        for i, brick in enumerate(self.bricks):
            if brick.alive:
                row = i // self.cols
                color = BRICK_COLORS[row % len(BRICK_COLORS)]
                pygame.draw.rect(screen, color, brick.rect())

        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        screen.blit(score_text, (10, 10))
        lives_text = self.font.render(f"Lives: {self.lives}", True, WHITE)
        screen.blit(lives_text, (self.width - 130, 10))

        if self.game_over and not getattr(self, "_game_over_logged", False):
            # NOTE: no proper end screen yet - see Task 2 in the README.
            if self.result == "win":
                print("You win! Final score:", self.score)
            else:
                print("Game over! Final score:", self.score)
            self._game_over_logged = True