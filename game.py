import pygame
import random
import json
from time import time

def aprint( msg ):
    print( msg )
    with open( "debug.log", "a" ) as f:
        f.write( str(msg) + "\n" )

# =====================
# CONFIG IA
# =====================
LOOKAHEAD_DEPTH = 3
AGGRESSION = 0.6
BOT_THINK_DELAY = 0.032  # secondes

# =====================
# CONFIG JEU
# =====================
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 5
FPS = 30
VERSION = "1.0.0"

# =====================
# SETTINGS
# =====================
DEFAULT_SETTINGS = {
    "player": {
        "name": "Player 1",
        "color": [0, 255, 0]
    },
    "Robot": {
        "name": "Player 2",
        "color": [255, 0, 0],
        "bot": True,
        "difficulty": 3
    },
    "version": VERSION
}

try:
    with open( "debug.log", "w" ) as f:
        f.write( f"LOG START -- {time.time()}" )
except:
    with open( "debug.log", "x" ) as f:
        f.write( f"LOG START -- {time.time()}" )


try:
    with open("settings.json", "r") as f:
        settings = json.load(f)
    if settings["version"] != VERSION:
        aprint( f"Well it's not the good version, expected {VERSION}, got {settings["version"]}" )
        raise Exception( "Well it's not the good version" )
except:
    settings = DEFAULT_SETTINGS
    try:
        aprint( f"settings.json not formatted, expected {DEFAULT_SETTINGS}, got {settings}" )
        with open("settings.json", "w") as f:
            json.dump(settings, f, indent=4)
    except:
        aprint( f"No settings.json detected" )
        with open("settings.json", "w") as f:
            json.dump(settings, f, indent=4)

aprint( f"game settings : {settings}" )

# =====================
# PYGAME INIT
# =====================
pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("TRON")
clock = pygame.time.Clock()

# =====================
# COULEURS
# =====================
COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (150, 150, 150),
    "player1": settings["player1"]["color"],
    "player2": settings["player2"]["color"]
}

# =====================
# PLAYER
# =====================
class Player:
    def __init__(self, x, y, color, direction):
        self.x = x
        self.y = y
        self.direction = direction
        self.next_direction = direction
        self.color = color
        self.trail = [(x, y)]
        self.alive = True

    def set_direction(self, d):
        if (-d[0], -d[1]) != self.direction:
            self.next_direction = d
            aprint( f"direction set to {d}" )

    def update(self):
        if not self.alive:
            return

        self.direction = self.next_direction
        self.x += self.direction[0] * GRID_SIZE
        self.y += self.direction[1] * GRID_SIZE
        self.trail.append((self.x, self.y))

    def draw(self, surf):
        for x, y in self.trail:
            pygame.draw.rect(surf, self.color, (x, y, GRID_SIZE, GRID_SIZE))

# =====================
# GAME
# =====================
class Game:
    def __init__(self):
        self.player1 = Player(150, 300, COLORS["player1"], (1, 0))
        self.player2 = Player(650, 300, COLORS["player2"], (-1, 0))
        self.occupied = set(self.player1.trail + self.player2.trail)
        self.running = True
        self.game_over = False
        self.winner = ""
        self.font = pygame.font.Font(None, 36)
        self.last_bot_think = 0

    # =====================
    # INPUT
    # =====================
    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_w:
                    self.player1.set_direction((0, -1))
                if e.key == pygame.K_s:
                    self.player1.set_direction((0, 1))
                if e.key == pygame.K_a:
                    self.player1.set_direction((-1, 0))
                if e.key == pygame.K_d:
                    self.player1.set_direction((1, 0))
                if e.key == pygame.K_r and self.game_over:
                    self.__init__()

    # =====================
    # UTILS
    # =====================
    def valid_moves(self, x, y, direction):
        dx, dy = direction
        dirs = [(dx, dy), (-dy, dx), (dy, -dx)]
        moves = []
        for d in dirs:
            nx = x + d[0] * GRID_SIZE
            ny = y + d[1] * GRID_SIZE
            if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                if (nx, ny) not in self.occupied:
                    moves.append(d)
        return moves

    def fast_space(self, x, y, radius=8):
        score = 0
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx = x + dx * GRID_SIZE
                ny = y + dy * GRID_SIZE
                if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                    if (nx, ny) not in self.occupied:
                        score += 1
        return score

    # =====================
    # IA
    # =====================
    def bot_move(self, player, enemy, difficulty):
        now = time.time()
        if now - self.last_bot_think < BOT_THINK_DELAY:
            return
        self.last_bot_think = now

        moves = self.valid_moves(player.x, player.y, player.direction)
        if not moves:
            return

        if difficulty == 1:
            player.set_direction(random.choice(moves))
            return

        if difficulty == 2:
            best = max(moves, key=lambda d: self.fast_space(
                player.x + d[0]*GRID_SIZE,
                player.y + d[1]*GRID_SIZE
            ))
            player.set_direction(best)
            return

        def evaluate(x, y):
            space = self.fast_space(x, y)
            dist = abs(x - enemy.x) + abs(y - enemy.y)
            return space * (1 - AGGRESSION) - dist * AGGRESSION

        def simulate(x, y, direction, occ, depth):
            if depth == 0:
                return evaluate(x, y)

            best = -999999
            for d in self.valid_moves(x, y, direction):
                nx = x + d[0]*GRID_SIZE
                ny = y + d[1]*GRID_SIZE
                if (nx, ny) in occ:
                    continue
                score = simulate(
                    nx, ny, d,
                    occ | {(nx, ny)},
                    depth - 1
                )
                best = max(best, score)
            return best

        best_dir = None
        best_score = -999999

        for d in moves:
            nx = player.x + d[0]*GRID_SIZE
            ny = player.y + d[1]*GRID_SIZE
            score = simulate(
                nx, ny, d,
                self.occupied | {(nx, ny)},
                LOOKAHEAD_DEPTH
            )
            if score > best_score:
                best_score = score
                best_dir = d

        if best_dir:
            player.set_direction(best_dir)

    # =====================
    # UPDATE
    # =====================
    def update(self):
        if self.game_over:
            return

        if settings["player2"].get("bot", False):
            self.bot_move(self.player2, self.player1, settings["player2"]["difficulty"])

        self.player1.update()
        self.player2.update()

        for p in (self.player1, self.player2):
            if (p.x < 0 or p.x >= WINDOW_WIDTH or
                p.y < 0 or p.y >= WINDOW_HEIGHT or
                (p.x, p.y) in self.occupied):
                p.alive = False
            else:
                self.occupied.add((p.x, p.y))

        if not self.player1.alive or not self.player2.alive:
            self.game_over = True
            if self.player1.alive:
                self.winner = settings["player1"]["name"] + " gagne !"
            elif self.player2.alive:
                self.winner = settings["player2"]["name"] + " gagne !"
            else:
                self.winner = "Égalité !"

    # =====================
    # DRAW
    # =====================
    def draw(self):
        screen.fill(COLORS["black"])
        self.player1.draw(screen)
        self.player2.draw(screen)

        if self.game_over:
            txt = self.font.render(self.winner, True, COLORS["white"])
            screen.blit(txt, (WINDOW_WIDTH//2 - txt.get_width()//2, WINDOW_HEIGHT//2))

        pygame.display.flip()

    # =====================
    # RUN
    # =====================
    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            clock.tick(FPS)
        pygame.quit()

# =====================
# MAIN
# =====================
if __name__ == "__main__":
    Game().run()
