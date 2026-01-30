import pygame
import random
import json
import itertools
import time

LOOKAHEAD_DEPTH = 3
AGGRESSION = 0.6


settings = {}

try:
    with open('settings.json', 'r') as f:
        settings = json.load(f)
except json.JSONDecodeError:
    settings = {
        "player1": {
            "name": "Player 1",
            "color": [0, 255, 0]
        },
        "player2": {
            "name": "Player 2",
            "color": [255, 0, 0],
            "bot": True
        }
    }
    with open('settings.json', 'w') as fw:
        json.dump(settings, fw, indent=4)
except FileNotFoundError:
    settings = {
        "player1": {
            "name": "Player 1",
            "color": [0, 255, 0]
        },
        "player2": {
            "name": "Player 2",
            "color": [255, 0, 0],
            "bot": True
        }
    }
    with open('settings.json', 'w') as fw:
        json.dump(settings, fw, indent=4)

player_one_name = settings["player1"]["name"]
player_two_name = settings["player2"]["name"]


# Configuration du jeu
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
FPS = 30
GRID_SIZE = 5

# Couleurs
COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "player1": settings["player1"]["color"],
    "player2": settings["player2"]["color"]
}

pygame.init()
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("TRON")
clock = pygame.time.Clock()

class Player(pygame.sprite.Sprite):
    """Représente un joueur (vélo) dans le jeu Tron"""
    def __init__(self, x, y, color, direction=(1, 0)):
        super().__init__()
        self.color = color
        self.trail = [(x, y)]  # Traçage de la queue
        self.direction = direction
        self.next_direction = direction
        self.x = x
        self.y = y
        self.speed = GRID_SIZE
        self.alive = True
        self.image = pygame.Surface((GRID_SIZE, GRID_SIZE))
        self.image.fill(color)
        self.rect = self.image.get_rect()
        self.update_position()

    def set_direction(self, direction):
        """Change la direction du joueur (si pas opposée)"""
        # Empêche de faire demi-tour
        if (direction[0] * -1, direction[1] * -1) != self.direction:
            self.next_direction = direction

    def update(self):
        """Met à jour la position du joueur"""
        if not self.alive:
            return
        
        # Change de direction si besoin
        self.direction = self.next_direction
        
        # Nouvelle position
        self.x += self.direction[0] * self.speed
        self.y += self.direction[1] * self.speed
        
        # Vérification des limites
        if (self.x < 0 or self.x >= WINDOW_WIDTH or 
            self.y < 0 or self.y >= WINDOW_HEIGHT):
            self.alive = False
            return
        
        # Ajoute la position actuelle à la traîne
        self.trail.append((self.x, self.y))
        self.update_position()

    def check_collision(self, other_player=None):
        """Vérifie les collisions"""
        # Collision avec sa propre traîne
        if (self.x, self.y) in self.trail[:-1]:
            self.alive = False
            return True
        
        # Collision avec un autre joueur
        if other_player and (self.x, self.y) in other_player.trail:
            self.alive = False
            return True
        
        return False

    def update_position(self):
        """Met à jour l'affichage du joueur"""
        self.rect.x = self.x
        self.rect.y = self.y

    def draw_trail(self, surface):
        """Dessine la traîne du joueur"""
        for pos in self.trail:
            pygame.draw.rect(surface, self.color, (pos[0], pos[1], GRID_SIZE, GRID_SIZE))


class Game:
    """Classe principale du jeu Tron"""
    def __init__(self):
        self.player1 = Player(150, 300, COLORS["player1"], (1, 0))
        self.player2 = Player(650, 300, COLORS["player2"], (-1, 0))
        self.running = True
        self.game_over = False
        self.winner = None
        self.font = pygame.font.Font(None, 36)
        self.last_bot_direction_change = 0  # Cooldown pour changements de direction
        # Temps du dernier calcul de l'IA (utilisé pour throttling)
        self.last_bot_think = 0.0

    def handle_events(self):
        """Gère les événements"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            elif event.type == pygame.KEYDOWN:
                # Joueur 1 (W, A, S, D)
                if event.key == pygame.K_w:
                    self.player1.set_direction((0, -1))
                elif event.key == pygame.K_s:
                    self.player1.set_direction((0, 1))
                elif event.key == pygame.K_a:
                    self.player1.set_direction((-1, 0))
                elif event.key == pygame.K_d:
                    self.player1.set_direction((1, 0))
                
                # Joueur 2 (Flèches)
                if settings["player2"]["bot"] == False:
                    if event.key == pygame.K_UP:
                        self.player2.set_direction((0, -1))
                    elif event.key == pygame.K_DOWN:
                        self.player2.set_direction((0, 1))
                    elif event.key == pygame.K_LEFT:
                        self.player2.set_direction((-1, 0))
                    elif event.key == pygame.K_RIGHT:
                        self.player2.set_direction((1, 0))
                
                
                # Redémarrer le jeu
                if event.key == pygame.K_r and self.game_over:
                    self.__init__()
                    global FPS
                    FPS = 30



    def verify_space(self, x, y):
        """Retourne le nombre de cases (unités GRID_SIZE) accessibles depuis la case
        contenant le pixel (x, y). Utilise un flood-fill 4-connexe.
        """
        # Convertir le pixel en coordonnée de case (coin supérieur gauche)
        start_x = (x // GRID_SIZE) * GRID_SIZE
        start_y = (y // GRID_SIZE) * GRID_SIZE

        # Ensemble des positions occupées par des murs/traînes
        occupied = set(self.player1.trail + self.player2.trail)

        # Si la case de départ est occupée, pas d'espace disponible
        if (start_x, start_y) in occupied:
            return 0

        visited = set()
        stack = [(start_x, start_y)]
        directions = [(GRID_SIZE, 0), (-GRID_SIZE, 0), (0, GRID_SIZE), (0, -GRID_SIZE)]

        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue

            # Vérifier limites et obstacles
            if cx < 0 or cx >= WINDOW_WIDTH or cy < 0 or cy >= WINDOW_HEIGHT:
                continue
            if (cx, cy) in occupied:
                continue

            visited.add((cx, cy))

            # Ajouter voisins 4-connexes
            for dx, dy in directions:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) not in visited and (nx, ny) not in occupied:
                    # Vérifier limites avant d'ajouter
                    if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                        stack.append((nx, ny))

        return len(visited)

    def get_valid_moves(self, player, occupied):
        dx, dy = player.direction
        x, y = player.x, player.y

        directions = [
            (dx, dy),
            (-dy, dx),
            (dy, -dx)
        ]

        valid = []
        for d in directions:
            nx = x + d[0] * GRID_SIZE
            ny = y + d[1] * GRID_SIZE
            if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT and (nx, ny) not in occupied:
                valid.append(d)
        return valid


    def bot_move(self, player, enemy, difficulty):
        if not player.alive:
            return

        now = time.time()
        if now - self.last_bot_think < 0.032:
            return
        self.last_bot_think = now

        occupied = set(self.player1.trail + self.player2.trail)

        valid_moves = self.get_valid_moves(player, occupied)
        if not valid_moves:
            return

        px, py = player.x, player.y
        ex, ey = enemy.x, enemy.y

        # ======================
        # DIFFICULTÉ 1 : RANDOM
        # ======================
        if difficulty == 1:
            player.set_direction(random.choice(valid_moves))
            return

        # ======================
        # DIFFICULTÉ 2 : SMART
        # ======================
        if difficulty == 2:
            best = max(
                valid_moves,
                key=lambda d: self.verify_space(
                    px + d[0] * GRID_SIZE,
                    py + d[1] * GRID_SIZE
                )
            )
            player.set_direction(best)
            return

        # ======================
        # DIFFICULTÉ 3 : AGGRESSIVE
        # ======================
        if difficulty == 3:
            best_score = -999999
            best_dir = None

            for d in valid_moves:
                nx = px + d[0] * GRID_SIZE
                ny = py + d[1] * GRID_SIZE
                space = self.verify_space(nx, ny)
                dist = abs(nx - ex) + abs(ny - ey)

                score = space * 0.3 - dist
                if score > best_score:
                    best_score = score
                    best_dir = d

            if best_dir:
                player.set_direction(best_dir)
            return

        # ======================
        # MINIMAX (4 & 5)
        # ======================
        def evaluate(x, y):
            space = self.verify_space(x, y)
            dist = abs(x - ex) + abs(y - ey)
            return space * (1 - AGGRESSION) - dist * AGGRESSION

        def simulate(x, y, occ, d, depth):
            if depth == 0:
                return evaluate(x, y)

            nx = x + d[0] * GRID_SIZE
            ny = y + d[1] * GRID_SIZE

            if nx < 0 or nx >= WINDOW_WIDTH or ny < 0 or ny >= WINDOW_HEIGHT or (nx, ny) in occ:
                return -999999

            new_occ = occ | {(nx, ny)}
            moves = self.get_valid_moves(player, new_occ)
            if not moves:
                return -999999

            return max(simulate(nx, ny, new_occ, nd, depth - 1) for nd in moves)

        best_dir = None
        best_score = -999999

        for d in valid_moves:
            nx = px + d[0] * GRID_SIZE
            ny = py + d[1] * GRID_SIZE
            score = simulate(nx, ny, occupied | {(nx, ny)}, d, LOOKAHEAD_DEPTH)

            if difficulty == 5:
                score += evaluate(nx, ny)  # ADAPTATIF

            if score > best_score:
                best_score = score
                best_dir = d

        if best_dir:
            player.set_direction(best_dir)


    def update(self):
        """Met à jour l'état du jeu"""
        if self.game_over:
            return
        
        self.player1.update()
        self.player2.update()

        # Déplacer les bots (si activés)
        if settings["player1"].get("bot", False):
            self.bot_move(self.player1, self.player2, settings["player1"]["difficulty"])

        if settings["player2"].get("bot", False):
            self.bot_move(self.player2, self.player1, settings["player2"]["difficulty"])


        # Vérifier les collisions
        self.player1.check_collision(self.player2)
        self.player2.check_collision(self.player1)
        
        # Vérifier si le jeu est terminé
        if not self.player1.alive and not self.player2.alive:
            self.game_over = True
            self.winner = "Égalité!"
        elif not self.player1.alive:
            self.game_over = True
            self.winner = player_two_name + " gagne!"
        elif not self.player2.alive:
            self.game_over = True
            self.winner = player_one_name + " gagne!"

    def draw(self):
        """Affiche le jeu"""
        screen.fill(COLORS["black"])
        
        # Dessiner les traînes
        self.player1.draw_trail(screen)
        self.player2.draw_trail(screen)
        
        # Afficher les joueurs
        screen.blit(self.player1.image, self.player1.rect)
        screen.blit(self.player2.image, self.player2.rect)
        
        # Afficher le message de fin si le jeu est terminé
        if self.game_over:
            text = self.font.render(self.winner, True, COLORS["white"])
            screen.blit(text, (WINDOW_WIDTH // 2 - text.get_width() // 2, WINDOW_HEIGHT // 2))
            
            restart_text = self.font.render("Appuyez sur R pour recommencer", True, COLORS["gray"])
            screen.blit(restart_text, (WINDOW_WIDTH // 2 - restart_text.get_width() // 2, WINDOW_HEIGHT // 2 + 50))
        
        pygame.display.flip()

    def run(self):
        global FPS
        """Boucle principale du jeu"""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            clock.tick(FPS)
            FPS+=0.01
        
        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()