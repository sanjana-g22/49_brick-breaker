import array
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

DIFFICULTIES = {
    "easy":   {"speed": 3, "paddle_width": 140},
    "medium": {"speed": 4, "paddle_width": 100},
    "hard":   {"speed": 6, "paddle_width": 70},
}


class SoundBank:
    """Generates simple sound effects in code. If the mixer is unavailable,
    every play() call silently does nothing."""

    def __init__(self):
        self.sounds = {}
        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 1, 512)
            init = pygame.mixer.get_init()
            if init is None:
                return
            self.rate, fmt, self.channels = init
            if fmt != -16:  # only signed 16-bit output is supported here
                return

            self.sounds = {
                # (start_freq, end_freq, seconds, volume, wave)
                "brick":  self._make([(660, 880, 0.08, 0.30, "square")]),
                "paddle": self._make([(330, 300, 0.07, 0.45, "sine")]),
                "wall":   self._make([(220, 200, 0.05, 0.30, "square")]),
                "win":    self._make([(523, 523, 0.12, 0.35, "square"),
                                      (659, 659, 0.12, 0.35, "square"),
                                      (784, 784, 0.12, 0.35, "square"),
                                      (1047, 1047, 0.30, 0.35, "square")]),
                "lose":   self._make([(392, 392, 0.15, 0.35, "square"),
                                      (330, 330, 0.15, 0.35, "square"),
                                      (262, 262, 0.15, 0.35, "square"),
                                      (196, 150, 0.40, 0.35, "square")]),
            }
            self.enabled = True
        except Exception:
            self.sounds = {}
            self.enabled = False

    def _make(self, notes):
        samples = array.array("h")
        for f0, f1, dur, vol, wave in notes:
            n = int(self.rate * dur)
            phase = 0.0
            attack = max(1, int(self.rate * 0.005))  # 5 ms fade-in avoids clicks
            for i in range(n):
                t = i / n
                phase += 2 * math.pi * (f0 + (f1 - f0) * t) / self.rate
                s = math.sin(phase)
                if wave == "square":
                    s = 1.0 if s >= 0 else -1.0
                env = (1 - t) ** 2 * min(1.0, i / attack)
                value = int(32767 * vol * s * env)
                for _ in range(self.channels):
                    samples.append(value)
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def play(self, name):
        if not self.enabled:
            return
        try:
            self.sounds[name].play()
        except Exception:
            pass


class GameEngine:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rows, self.cols = 5, 8
        self.font = pygame.font.SysFont("Arial", 28)
        self.sounds = SoundBank()

        self.start("medium")

    def start(self, difficulty="medium"):
        """Fully (re)initialize the game for the given difficulty."""
        self.difficulty = difficulty
        settings = DIFFICULTIES[difficulty]
        self.speed = settings["speed"]

        pw = settings["paddle_width"]
        self.paddle = Paddle(self.width // 2 - pw // 2, self.height - 30, pw, 14)

        self.ball = Ball(self.width // 2, self.height - 50, radius=8)
        self._reset_ball()

        self.bricks = self._build_bricks(self.rows, self.cols)

        self.lives = 3
        self.score = 0
        self.game_over = False
        self.result = None  # "win" or "lose"

        # Re-arm the end screen for the next time it appears
        self._game_over_logged = False
        self._game_over_time = None

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
        if self.game_over and event.type == pygame.KEYDOWN:
            # Ignore input for 500 ms so a held key doesn't dismiss the screen
            shown_at = getattr(self, "_game_over_time", None)
            if shown_at is None or pygame.time.get_ticks() - shown_at <= 500:
                return

            if event.key == pygame.K_1:
                self.start("easy")
            elif event.key == pygame.K_2:
                self.start("medium")
            elif event.key == pygame.K_3:
                self.start("hard")
            elif event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

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
                self.sounds.play("paddle")

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
                self.sounds.play("brick")

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
            self.sounds.play("wall")
        elif ball.x + ball.radius >= self.width:
            ball.x = self.width - ball.radius
            ball.vx = -abs(ball.vx)
            self.sounds.play("wall")
        if ball.y - ball.radius <= 0:
            ball.y = ball.radius
            ball.vy = abs(ball.vy)
            self.sounds.play("wall")

        # ---------------- Lives / win ----------------
        if ball.y - ball.radius > self.height:
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self.result = "lose"
                self.sounds.play("lose")
            else:
                self._reset_ball()

        if not self.game_over and all(not b.alive for b in self.bricks):
            self.game_over = True
            self.result = "win"
            self.sounds.play("win")

    def _reset_ball(self):
        self.ball.x, self.ball.y = self.width // 2, self.height - 50
        self.ball.vx, self.ball.vy = self.speed, -self.speed

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

        if self.game_over:
            if not getattr(self, "_game_over_logged", False):
                self._game_over_time = pygame.time.get_ticks()
                self._game_over_logged = True

            w, h = screen.get_size()

            # Dim the game behind the text
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))

            if not hasattr(self, "_end_fonts"):
                self._end_fonts = (pygame.font.Font(None, 72), pygame.font.Font(None, 36))
            big, small = self._end_fonts

            title = "YOU WIN!" if self.result == "win" else "GAME OVER"
            lines = [
                (big, title, (255, 255, 255), h // 2 - 80),
                (small, f"Final score: {self.score}", (255, 255, 255), h // 2 - 25),
                (small, "Play again:  1 - Easy   2 - Medium   3 - Hard", (200, 200, 200), h // 2 + 25),
                (small, "Esc - Quit", (200, 200, 200), h // 2 + 65),
            ]
            for font, text, color, y in lines:
                surf = font.render(text, True, color)
                screen.blit(surf, surf.get_rect(center=(w // 2, y)))