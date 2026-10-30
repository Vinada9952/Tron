"""
TRON v3.1.0 - fusion de la v2.1.1 (settings.json, debug.log, niveaux de difficulté,
lookahead) et de la version "IA prédictive" (trails en set, apprentissage de
l'adversaire, piégeage, zone sûre).

Difficultés des bots :
  1 = aléatoire
  2 = glouton (choisit le côté avec le plus d'espace libre)
  3 = lookahead (recherche en profondeur + agressivité fixe)
  4 = prédictif (lookahead + flood fill + piégeage + agressivité adaptative)

Touches : J1 = WASD, J2 = flèches, R = rejouer, P = pause, Echap = menu
Menu principal + écran de paramètres (aussi accessible en jeu via Echap)
modifiables au clavier ou à la souris : nom, couleur, humain/bot, difficulté.
"""
import copy
import json
import os
import random
import sys
import traceback
from time import time

import pygame

# =====================
# CONFIG
# =====================
VERSION = "3.1.0"
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 5
FPS = 30

# Debug : niveau minimal écrit dans debug.log (1 = très verbeux, 5 = erreurs)
LOG_LEVEL = 2
LOG_FILE = "debug.log"
SETTINGS_FILE = "settings.json"

# IA
REACTION_TIME = 0.032
RADIUS_AI_VISION = 7
LOOKAHEAD_DEPTH = 3
BASE_AGGRESSION = 0.4
TRAP_WEIGHT = 2.2
PREDICT_DEPTH = 6
SAFE_MARGIN = 2
FLOOD_CAP = 200
DEAD = 1e9

VISION_OFFSETS = [
    (dx, dy)
    for dx in range(-RADIUS_AI_VISION, RADIUS_AI_VISION + 1)
    for dy in range(-RADIUS_AI_VISION, RADIUS_AI_VISION + 1)
]

DEFAULT_SETTINGS = {
    "player1": {"name": "Player 1", "color": [0, 255, 0], "bot": False, "difficulty": 2},
    "player2": {"name": "Player 2", "color": [255, 0, 0], "bot": True, "difficulty": 4},
    "version": VERSION,
}

COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (150, 150, 150),
}

# =====================
# DEBUG
# =====================
_log = None


def debugPrint(msg, level=2):
    if _log is None or level < LOG_LEVEL:
        return
    _log.write(f"[{time():.3f}] level:{level} {msg}\n")
    if level >= 4:
        _log.flush()


# =====================
# SETTINGS (chargement tolérant, sans perdre les valeurs valides)
# =====================
def merge_settings(loaded, defaults):
    """Garde chaque valeur valide du fichier, retombe sur le défaut sinon."""
    result = copy.deepcopy(defaults)
    if not isinstance(loaded, dict):
        return result
    for key, default in defaults.items():
        if key not in loaded:
            debugPrint(f"clé manquante dans settings.json : {key}", 4)
            continue
        if isinstance(default, dict):
            result[key] = merge_settings(loaded[key], default)
        elif type(loaded[key]) is type(default) or (
            isinstance(default, list) and isinstance(loaded[key], (list, tuple))
        ):
            result[key] = loaded[key]
        else:
            debugPrint(f"type invalide pour {key} : {loaded[key]!r}", 4)
    return result


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


def load_settings():
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
            if loaded.get("version") != VERSION:
                debugPrint(
                    f"version différente : fichier={loaded.get('version')} jeu={VERSION}", 4
                )
            settings = merge_settings(loaded, DEFAULT_SETTINGS)
        except (json.JSONDecodeError, OSError, AttributeError) as e:
            debugPrint(f"settings.json illisible : {e}", 5)
    else:
        debugPrint("pas de settings.json, création", 4)

    for p in ("player1", "player2"):
        settings[p]["difficulty"] = max(1, min(4, int(settings[p]["difficulty"])))
    settings["version"] = VERSION
    save_settings(settings)
    return settings


# =====================
# OUTILS GRILLE
# =====================
def in_bounds(p):
    return 0 <= p[0] < WINDOW_WIDTH and 0 <= p[1] < WINDOW_HEIGHT


def turns(d):
    """Tout droit, gauche, droite (jamais demi-tour)."""
    dx, dy = d
    return ((dx, dy), (-dy, dx), (dy, -dx))


def step(p, d):
    return (p[0] + d[0] * GRID_SIZE, p[1] + d[1] * GRID_SIZE)


# =====================
# PLAYER
# =====================
class Player:
    def __init__(self, x, y, direction, color, pid, name, bot=False, difficulty=2):
        self.start_pos = (x, y)
        self.start_dir = direction
        self.color = color
        self.pid = pid
        self.name = name
        self.bot = bot
        self.difficulty = difficulty
        self.last_think = time()
        self.reset()

    # ---------- état ----------
    def reset(self):
        self.pos = self.start_pos
        self.direction = self.start_dir
        self.last_dir = self.start_dir
        self.trail_list = []
        self.trail_set = set()
        self.is_alive = True
        self.enemy_stats = {"straight": 0, "turn": 0, "close": 0, "far": 0}

    def head(self):
        return self.pos

    def next_cell(self):
        return step(self.pos, self.direction)

    def getTrail(self):
        return self.trail_list + [self.pos]

    def update(self):
        """Avance d'une case. Retourne l'ancienne position (pour le dessin)."""
        old = self.pos
        self.trail_list.append(old)
        self.trail_set.add(old)
        self.last_dir = self.direction
        self.pos = step(old, self.direction)
        return old

    # ---------- joueur humain ----------
    def turn(self, d):
        if not self.is_alive or self.bot:
            return
        if d != (-self.last_dir[0], -self.last_dir[1]):
            self.direction = d

    # ---------- IA ----------
    def learn_enemy(self, enemy):
        if enemy.direction == enemy.last_dir:
            self.enemy_stats["straight"] += 1
        else:
            self.enemy_stats["turn"] += 1
        dist = abs(self.pos[0] - enemy.pos[0]) + abs(self.pos[1] - enemy.pos[1])
        self.enemy_stats["close" if dist < 120 else "far"] += 1

    def adaptive_aggression(self):
        s = self.enemy_stats
        straight_ratio = s["straight"] / (s["straight"] + s["turn"] + 1)
        close_ratio = s["close"] / (s["close"] + s["far"] + 1)
        return BASE_AGGRESSION + straight_ratio * 0.4 + close_ratio * 0.3

    @staticmethod
    def fast_space(p, occupied):
        """Espace libre dans un carré autour de p (rapide)."""
        s = 0
        for ox, oy in VISION_OFFSETS:
            n = (p[0] + ox * GRID_SIZE, p[1] + oy * GRID_SIZE)
            if in_bounds(n) and n not in occupied:
                s += 1
        return s

    @staticmethod
    def flood_space(p, occupied, cap=FLOOD_CAP):
        """Cases réellement accessibles depuis p (détecte les culs-de-sac)."""
        seen = {p}
        frontier = [p]
        while frontier and len(seen) < cap:
            nf = []
            for c in frontier:
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = step(c, d)
                    if n not in seen and in_bounds(n) and n not in occupied:
                        seen.add(n)
                        nf.append(n)
            frontier = nf
        return len(seen)

    @staticmethod
    def predict_area(start, d, occupied, depth=PREDICT_DEPTH):
        """Zone que l'adversaire peut atteindre en `depth` coups."""
        seen = set()
        frontier = [(start, d)]
        for _ in range(depth):
            nf = []
            for p, d0 in frontier:
                for nd in turns(d0):
                    n = step(p, nd)
                    if in_bounds(n) and n not in occupied and n not in seen:
                        seen.add(n)
                        nf.append((n, nd))
            frontier = nf
        return len(seen)

    def updateBot(self, enemy):
        now = time()
        if now - self.last_think < REACTION_TIME:
            return
        self.last_think = now

        # cases interdites : traînées + tête adverse + sa prochaine case
        occupied = self.trail_set | enemy.trail_set | {enemy.pos, enemy.next_cell()}

        valid = [d for d in turns(self.direction)
                 if in_bounds(step(self.pos, d)) and step(self.pos, d) not in occupied]
        if not valid:
            return

        # --- niveau 1 : aléatoire ---
        if self.difficulty <= 1:
            self.direction = random.choice(valid)
            return

        # --- niveau 2 : glouton sur l'espace libre ---
        if self.difficulty == 2:
            self.direction = max(
                valid, key=lambda d: self.fast_space(step(self.pos, d), occupied)
            )
            return

        # --- niveaux 3 et 4 : lookahead ---
        adaptive = self.difficulty >= 4
        if adaptive:
            self.learn_enemy(enemy)
            aggression = self.adaptive_aggression()
        else:
            aggression = BASE_AGGRESSION

        def leaf(p):
            dist = (abs(p[0] - enemy.pos[0]) + abs(p[1] - enemy.pos[1])) / GRID_SIZE
            if adaptive:
                return self.flood_space(p, occupied) - dist * aggression * 0.3
            return self.fast_space(p, occupied) * (1 - aggression) - dist * aggression

        def simulate(p, d, depth):
            if depth == 0:
                return leaf(p)
            best, found = -DEAD, False
            for nd in turns(d):
                n = step(p, nd)
                if in_bounds(n) and n not in occupied:
                    occupied.add(n)
                    best = max(best, simulate(n, nd, depth - 1))
                    occupied.discard(n)
                    found = True
            return best if found else -DEAD

        best_dir, best_score = None, -DEAD * 2
        for d in valid:
            n = step(self.pos, d)
            occupied.add(n)
            score = simulate(n, d, LOOKAHEAD_DEPTH)

            if adaptive:
                my_area = self.flood_space(n, occupied)
                enemy_area = self.predict_area(enemy.pos, enemy.direction, occupied)
                score -= enemy_area * TRAP_WEIGHT
                score += random.uniform(-0.5, 0.5)
                if my_area < SAFE_MARGIN * 10:
                    score -= 500  # zone trop petite : danger
            occupied.discard(n)

            if score > best_score:
                best_score, best_dir = score, d

        if best_dir:
            self.direction = best_dir


# =====================
# MENUS / PARAMÈTRES
# =====================
PALETTE = [
    (0, 255, 0), (255, 0, 0), (0, 170, 255), (255, 220, 0),
    (255, 0, 255), (0, 255, 255), (255, 128, 0), (180, 120, 255),
]
DIFF_NAMES = {1: "Facile", 2: "Normal", 3: "Difficile", 4: "Expert"}
MAX_NAME = 12
ACCENT = (0, 200, 255)

MAIN_ITEMS = ["Jouer", "Paramètres", "Quitter"]
PAUSE_ITEMS = ["Reprendre", "Rejouer", "Paramètres", "Menu principal"]

# lignes de l'écran de paramètres : (champ, joueur)
ROWS = [(f, k) for k in ("player1", "player2")
        for f in ("name", "color", "bot", "difficulty")] + [("reset", None), ("back", None)]


def row_label(field, key):
    n = "J1" if key == "player1" else "J2"
    return {
        "name": f"{n} - Nom",
        "color": f"{n} - Couleur",
        "bot": f"{n} - Contrôle",
        "difficulty": f"{n} - Difficulté IA",
        "reset": "Réinitialiser les paramètres",
        "back": "Retour",
    }[field]


# =====================
# MAIN
# =====================
def main():
    global _log
    _log = open(LOG_FILE, "w")
    _log.write(f"LOG START -- {time()}\n")

    settings = load_settings()
    debugPrint(f"settings : {settings}", 2)

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption(f"TRON {VERSION}")
    clock = pygame.time.Clock()
    title_font = pygame.font.Font(None, 120)
    font = pygame.font.Font(None, 36)
    small = pygame.font.Font(None, 24)

    s1, s2 = settings["player1"], settings["player2"]
    p1 = Player(150, 300, (1, 0), tuple(s1["color"]), 1, s1["name"], s1["bot"], s1["difficulty"])
    p2 = Player(650, 300, (-1, 0), tuple(s2["color"]), 2, s2["name"], s2["bot"], s2["difficulty"])

    keymap = {
        pygame.K_w: (p1, (0, -1)), pygame.K_s: (p1, (0, 1)),
        pygame.K_a: (p1, (-1, 0)), pygame.K_d: (p1, (1, 0)),
        pygame.K_UP: (p2, (0, -1)), pygame.K_DOWN: (p2, (0, 1)),
        pygame.K_LEFT: (p2, (-1, 0)), pygame.K_RIGHT: (p2, (1, 0)),
    }

    board = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    board.fill(COLORS["black"])
    scores = {1: 0, 2: 0}

    # état de l'interface
    ui = {
        "mode": "menu",        # menu | game | pause | settings
        "from": "menu",        # d'où on est venu dans les paramètres
        "sel": 0,
        "editing": False,      # édition d'un nom en cours
        "buf": "",
        "changed": False,      # paramètres modifiés depuis l'ouverture
        "running": True,
        "paused": False,
        "state": "running",
    }
    rects = []

    # ---------- actions ----------
    def apply_settings():
        for p, s in ((p1, settings["player1"]), (p2, settings["player2"])):
            p.name = s["name"]
            p.color = tuple(s["color"])
            p.bot = s["bot"]
            p.difficulty = s["difficulty"]

    def restart():
        p1.reset()
        p2.reset()
        board.fill(COLORS["black"])
        ui["state"] = "running"
        ui["paused"] = False
        debugPrint("restart game", 2)

    def menu_activate(label):
        if label == "Jouer":
            scores[1] = scores[2] = 0
            apply_settings()
            restart()
            ui["mode"] = "game"
        elif label == "Reprendre":
            ui["mode"] = "game"
        elif label == "Rejouer":
            restart()
            ui["mode"] = "game"
        elif label == "Paramètres":
            ui["from"] = ui["mode"]
            ui["mode"] = "settings"
            ui["sel"] = 0
        elif label == "Menu principal":
            ui["mode"] = "menu"
            ui["sel"] = 0
        elif label == "Quitter":
            ui["running"] = False

    def leave_settings():
        if ui["changed"]:
            apply_settings()
            if ui["from"] == "pause":
                restart()  # nouvelle manche avec les nouveaux paramètres
            ui["changed"] = False
        ui["mode"] = ui["from"]
        ui["sel"] = 0

    def change(field, key, delta):
        s = settings[key]
        other = settings["player2" if key == "player1" else "player1"]
        if field == "color":
            cur = tuple(s["color"])
            i = PALETTE.index(cur) if cur in PALETTE else -1
            for _ in range(len(PALETTE)):
                i = (i + delta) % len(PALETTE)
                if list(PALETTE[i]) != list(other["color"]):
                    break
            s["color"] = list(PALETTE[i])
        elif field == "bot":
            s["bot"] = not s["bot"]
        elif field == "difficulty":
            s["difficulty"] = max(1, min(4, s["difficulty"] + delta))
        else:
            return
        ui["changed"] = True
        save_settings(settings)

    def settings_activate(idx, delta=1):
        field, key = ROWS[idx]
        if field == "name":
            ui["editing"] = True
            ui["buf"] = settings[key]["name"]
        elif field == "reset":
            settings.clear()
            settings.update(copy.deepcopy(DEFAULT_SETTINGS))
            ui["changed"] = True
            save_settings(settings)
        elif field == "back":
            leave_settings()
        else:
            change(field, key, delta)

    # ---------- dessin ----------
    def blit_center(surface_text, y):
        screen.blit(surface_text, (WINDOW_WIDTH // 2 - surface_text.get_width() // 2, y))

    def draw_menu(items, title):
        screen.fill(COLORS["black"])
        blit_center(title_font.render(title, True, ACCENT), 90)
        out = []
        for i, label in enumerate(items):
            r = pygame.Rect(0, 0, 320, 46)
            r.center = (WINDOW_WIDTH // 2, 270 + i * 60)
            sel = i == ui["sel"]
            pygame.draw.rect(screen, (30, 30, 60) if sel else (15, 15, 25), r, border_radius=8)
            pygame.draw.rect(screen, ACCENT if sel else (70, 70, 90), r, 2, border_radius=8)
            t = font.render(label, True, COLORS["white"] if sel else COLORS["gray"])
            screen.blit(t, t.get_rect(center=r.center))
            out.append(r)
        hint = small.render("Haut/Bas : choisir   Entree : valider   souris acceptee", True, (90, 90, 110))
        blit_center(hint, WINDOW_HEIGHT - 40)
        ver = small.render(f"v{VERSION}", True, (90, 90, 110))
        screen.blit(ver, (10, WINDOW_HEIGHT - 28))
        return out

    def draw_settings():
        screen.fill(COLORS["black"])
        blit_center(font.render("PARAMÈTRES", True, ACCENT), 30)
        out = []
        for i, (field, key) in enumerate(ROWS):
            r = pygame.Rect(120, 85 + i * 42, 560, 36)
            sel = i == ui["sel"]
            editing_this = ui["editing"] and sel
            pygame.draw.rect(screen, (30, 30, 60) if sel else (15, 15, 25), r, border_radius=6)
            border = (0, 255, 120) if editing_this else (ACCENT if sel else (60, 60, 80))
            pygame.draw.rect(screen, border, r, 2, border_radius=6)

            dim = False
            if field in ("reset", "back"):
                t = font.render(row_label(field, key), True, COLORS["white"] if sel else COLORS["gray"])
                screen.blit(t, t.get_rect(center=r.center))
                out.append(r)
                continue

            s = settings[key]
            dim = field == "difficulty" and not s["bot"]
            label_col = (80, 80, 90) if dim else (COLORS["white"] if sel else COLORS["gray"])
            screen.blit(small.render(row_label(field, key), True, label_col), (r.x + 14, r.centery - 8))

            if field == "color":
                sw = pygame.Rect(r.right - 80, r.centery - 10, 50, 20)
                pygame.draw.rect(screen, tuple(s["color"]), sw)
                for txt, x in (("<", sw.x - 16), (">", sw.right + 6)):
                    screen.blit(small.render(txt, True, label_col), (x, r.centery - 8))
            else:
                if field == "name":
                    val = (ui["buf"] + "_") if editing_this else s["name"]
                elif field == "bot":
                    val = "< " + ("Bot" if s["bot"] else "Humain") + " >"
                else:
                    val = "(humain)" if dim else f"< {s['difficulty']} - {DIFF_NAMES[s['difficulty']]} >"
                t = small.render(val, True, label_col)
                screen.blit(t, (r.right - 14 - t.get_width(), r.centery - 8))
            out.append(r)

        if ui["editing"]:
            hint = "Tape le nom   Entree : valider   Echap : annuler"
        else:
            hint = "Haut/Bas : choisir   Gauche/Droite : modifier   Entree : valider   Echap : retour"
        blit_center(small.render(hint, True, (90, 90, 110)), WINDOW_HEIGHT - 32)
        return out

    def draw_game():
        screen.blit(board, (0, 0))
        for p in (p1, p2):
            if in_bounds(p.pos):
                pygame.draw.rect(screen, COLORS["white"], (p.pos[0], p.pos[1], GRID_SIZE, GRID_SIZE))
        hud = small.render(f"{p1.name} {scores[1]}  -  {scores[2]} {p2.name}", True, COLORS["gray"])
        blit_center(hud, 5)
        esc = small.render("Echap : menu", True, (90, 90, 110))
        screen.blit(esc, (10, WINDOW_HEIGHT - 24))

        if ui["state"] != "running":
            blit_center(font.render(ui["state"], True, COLORS["white"]), WINDOW_HEIGHT // 4)
            blit_center(font.render("Appuie sur R pour rejouer", True, COLORS["white"]),
                        WINDOW_HEIGHT // 4 + 30)
        elif ui["paused"]:
            blit_center(font.render("PAUSE", True, COLORS["white"]), WINDOW_HEIGHT // 4)

    # ---------- événements ----------
    def handle_menu_event(event, items):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                ui["sel"] = (ui["sel"] - 1) % len(items)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                ui["sel"] = (ui["sel"] + 1) % len(items)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                menu_activate(items[ui["sel"]])
            elif event.key == pygame.K_ESCAPE:
                if ui["mode"] == "pause":
                    ui["mode"] = "game"
                else:
                    ui["running"] = False
        elif event.type == pygame.MOUSEMOTION:
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos):
                    ui["sel"] = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos):
                    ui["sel"] = i
                    menu_activate(items[i])
                    break

    def handle_settings_event(event):
        if ui["editing"]:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    new = ui["buf"].strip()
                    if new:
                        key = ROWS[ui["sel"]][1]
                        settings[key]["name"] = new
                        ui["changed"] = True
                        save_settings(settings)
                    ui["editing"] = False
                elif event.key == pygame.K_ESCAPE:
                    ui["editing"] = False
                elif event.key == pygame.K_BACKSPACE:
                    ui["buf"] = ui["buf"][:-1]
                elif event.unicode and event.unicode.isprintable() and len(ui["buf"]) < MAX_NAME:
                    ui["buf"] += event.unicode
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                ui["sel"] = (ui["sel"] - 1) % len(ROWS)
            elif event.key == pygame.K_DOWN:
                ui["sel"] = (ui["sel"] + 1) % len(ROWS)
            elif event.key == pygame.K_LEFT:
                field, key = ROWS[ui["sel"]]
                change(field, key, -1) if key else None
            elif event.key == pygame.K_RIGHT:
                field, key = ROWS[ui["sel"]]
                change(field, key, 1) if key else None
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                settings_activate(ui["sel"], 1)
            elif event.key == pygame.K_ESCAPE:
                leave_settings()
        elif event.type == pygame.MOUSEMOTION:
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos):
                    ui["sel"] = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos):
                    ui["sel"] = i
                    settings_activate(i, 1 if event.button == 1 else -1)
                    break

    def handle_game_event(event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            ui["mode"] = "pause"
            ui["sel"] = 0
        elif event.key == pygame.K_r:
            restart()
        elif event.key == pygame.K_p:
            ui["paused"] = not ui["paused"]
        elif event.key in keymap:
            player, d = keymap[event.key]
            player.turn(d)

    def step_game():
        for p in (p1, p2):
            if p.bot:
                p.updateBot(p2 if p is p1 else p1)

        for p in (p1, p2):
            old = p.update()
            pygame.draw.rect(board, p.color, (old[0], old[1], GRID_SIZE, GRID_SIZE))

        # collisions simultanées (permet l'égalité sur un face-à-face)
        def crashed(me, other):
            h = me.pos
            return (not in_bounds(h) or h in me.trail_set
                    or h in other.trail_set or h == other.pos)

        p1.is_alive = not crashed(p1, p2)
        p2.is_alive = not crashed(p2, p1)

        if not p1.is_alive and not p2.is_alive:
            ui["state"] = "Égalité"
        elif p1.is_alive and not p2.is_alive:
            ui["state"] = f"{p1.name} gagne"
            scores[1] += 1
        elif p2.is_alive and not p1.is_alive:
            ui["state"] = f"{p2.name} gagne"
            scores[2] += 1
        if ui["state"] != "running":
            debugPrint(f"state is now at {ui['state']}", 2)

    # ---------- boucle principale ----------
    while ui["running"]:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                ui["running"] = False
            elif ui["mode"] == "menu":
                handle_menu_event(event, MAIN_ITEMS)
            elif ui["mode"] == "pause":
                handle_menu_event(event, PAUSE_ITEMS)
            elif ui["mode"] == "settings":
                handle_settings_event(event)
            else:
                handle_game_event(event)

        if ui["mode"] == "game" and ui["state"] == "running" and not ui["paused"]:
            step_game()

        mode = ui["mode"]
        if mode == "menu":
            rects = draw_menu(MAIN_ITEMS, "TRON")
        elif mode == "pause":
            draw_game()
            overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 170))
            screen.blit(overlay, (0, 0))
            blit_center(font.render("PAUSE", True, COLORS["white"]), 140)
            # on redessine les boutons par-dessus sans effacer l'écran
            out = []
            for i, label in enumerate(PAUSE_ITEMS):
                r = pygame.Rect(0, 0, 320, 46)
                r.center = (WINDOW_WIDTH // 2, 250 + i * 60)
                sel = i == ui["sel"]
                pygame.draw.rect(screen, (30, 30, 60) if sel else (15, 15, 25), r, border_radius=8)
                pygame.draw.rect(screen, ACCENT if sel else (70, 70, 90), r, 2, border_radius=8)
                t = font.render(label, True, COLORS["white"] if sel else COLORS["gray"])
                screen.blit(t, t.get_rect(center=r.center))
                out.append(r)
            rects = out
        elif mode == "settings":
            rects = draw_settings()
        else:
            draw_game()

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        if _log:
            debugPrint(tb, 5)
        else:
            with open(LOG_FILE, "a") as f:
                f.write(tb)
    finally:
        if _log:
            _log.close()