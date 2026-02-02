try:
    import pygame
    import random
    import json
    from time import time
    import os.path
    import traceback
    import sys

    # debug function
    def debugPrint( msg, level ):
        # print( f"level:{level}", msg )
        with open( "debug.log", "a" ) as f:
            f.write(  f"level:{level} "+ str(msg) + "\n" )

    # game settings
    VERSION = "2.1.0"
    WINDOW_WIDTH = 800
    WINDOW_HEIGHT = 600
    GRID_SIZE = 5
    FPS = 30

    # AI settings
    REACTION_TIME = 0.032
    RADIUS_AI_VISION = 8
    AGGRESSION = 1
    LOOKAHEAD_DEPTH = 3


    # default settings
    DEFAULT_SETTINGS = {
        "player1": {
            "name": "Player 1",
            "color": (0, 255, 0),
            "bot": False,
            "difficulty": 2
        },
        "player2": {
            "name": "Player 2",
            "color": (255, 0, 0),
            "bot": True,
            "difficulty": 4
        },
        "version": VERSION
    }

    backup_load = 0
    TOTAL_LOAD = 9
    backup_settings = DEFAULT_SETTINGS

    # verify if files exists
    if os.path.exists( "./debug.log" ):
        with open( "debug.log", "w" ) as f:
            f.write( f"LOG START -- {time()}\n" )
        debugPrint( "modifying log", 2 )
    else:
        with open( "debug.log", "x" ) as f:
            f.write( f"LOG START -- {time()}\n" )
        debugPrint( "creating log", 2 )

    if os.path.exists( "./settings.json" ):
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
            backup_load += 1
            backup_settings["player1"]["name"] = settings["player1"]["name"]
            backup_load += 1
            backup_settings["player1"]["color"] = settings["player1"]["color"]
            backup_load += 1
            backup_settings["player2"]["name"] = settings["player2"]["name"]
            backup_load += 1
            backup_settings["player2"]["color"] = settings["player2"]["color"]
            backup_load += 1
            backup_settings["player1"]["bot"] = settings["player1"]["bot"]
            backup_load += 1
            backup_settings["player1"]["difficulty"] = settings["player1"]["difficulty"]
            backup_load += 1
            backup_settings["player2"]["bot"] = settings["player2"]["bot"]
            backup_load += 1
            backup_settings["player2"]["difficulty"] = settings["player2"]["difficulty"]
            backup_load += 1
            if settings["version"] != VERSION:
                raise KeyError( f"Not good version, expected {settings["version"]}, got {VERSION}" )
        except KeyError as e:
            debugPrint( str( e ), 5 )
            debugPrint( f"settings.json not formatted, expected {DEFAULT_SETTINGS}, got {settings}", 4 )
            debugPrint( f"backup is at {backup_load}, load is at {backup_load}/{TOTAL_LOAD}", 4 )
            
            
            if backup_load == TOTAL_LOAD:
                settings = backup_settings
            else:
                settings = DEFAULT_SETTINGS
            with open("settings.json", "w") as f:
                json.dump(settings, f, indent=4)
    else:
        debugPrint( f"No settings.json detected", 4 )
        with open("settings.json", "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)


    debugPrint( f"game settings : {settings}", 2 )

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("TRON")
    clock = pygame.time.Clock()
    font = pygame.font.Font( None, 36 )

    COLORS = {
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "gray": (150, 150, 150),
        "player1": tuple(settings["player1"]["color"]),
        "player2": tuple(settings["player2"]["color"])
    }

    debugPrint( f"all colors : {COLORS}", 1 )


    class Player( pygame.sprite.Sprite ):
        def __init__( self, x, y, direction, color, player ):
            global settings

            self.start_pos = (x, y)
            self.start_direction = direction
            self.last_bot_think = time()

            self.is_alive = True
            self.direction = direction
            self.color = color
            self.trail = []
            self.player = player
            self.image = pygame.Surface( [ GRID_SIZE, GRID_SIZE ] )
            self.image.fill( self.color )
            self.pos = self.image.get_rect()
            self.pos.x = x
            self.pos.y = y

        def update( self ):
            self.trail.append( (self.pos.x, self.pos.y) )
            self.pos.x += self.direction[0] * GRID_SIZE
            self.pos.y += self.direction[1] * GRID_SIZE

        def updatePlayer( self ):
            if not self.is_alive:
                return
            keys = pygame.key.get_pressed()
            if self.player == 1:
                if keys[pygame.K_w] and [0, 1] != self.direction:
                    self.direction = [0, -1]
                if keys[pygame.K_a] and [1, 0] != self.direction:
                    self.direction = [-1, 0]
                if keys[pygame.K_s] and [0, -1] != self.direction:
                    self.direction = [0, 1]
                if keys[pygame.K_d] and [-1, 0] != self.direction:
                    self.direction = [1, 0]
            if self.player == 2:
                if keys[pygame.K_UP] and [0, 1] != self.direction:
                    self.direction = [0, -1]
                if keys[pygame.K_LEFT] and [1, 0] != self.direction:
                    self.direction = [-1, 0]
                if keys[pygame.K_DOWN] and [0, -1] != self.direction:
                    self.direction = [0, 1]
                if keys[pygame.K_RIGHT] and [-1, 0] != self.direction:
                    self.direction = [1, 0]

        
        def updateBot( self, difficulty, trail, other_pos ):

            now = time()
            if now - self.last_bot_think < REACTION_TIME:
                return
            self.last_bot_think = now


            dx, dy = self.direction
            dirs = [(dx, dy), (-dy, dx), (dy, -dx)]
            moves = []
            for d in dirs:
                nx = self.pos.x + d[0] * GRID_SIZE
                ny = self.pos.y + d[1] * GRID_SIZE
                if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                    if (nx, ny) not in self.trail + trail:
                        moves.append(d)
            

            if not moves:
                return

            if difficulty == 1:
                self.direction = random.choice( moves )
                return

            def fast_space(x, y, trails):
                score = 0
                for dx in range(-RADIUS_AI_VISION, RADIUS_AI_VISION + 1):
                    for dy in range(-RADIUS_AI_VISION, RADIUS_AI_VISION + 1):
                        nx = x + dx * GRID_SIZE
                        ny = y + dy * GRID_SIZE
                        if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                            if (nx, ny) not in trails:
                                score += 1
                return score

            if difficulty == 2:
                best = max(
                    moves, key=lambda d: fast_space(
                        self.pos.x + d[0]*GRID_SIZE,
                        self.pos.y + d[1]*GRID_SIZE,
                        self.trail + trail
                    )
                )
                self.direction = best
                return
            
            def valid_moves(x, y, direction, trails):
                dx, dy = direction
                dirs = [(dx, dy), (-dy, dx), (dy, -dx)]
                moves = []
                for d in dirs:
                    nx = x + d[0] * GRID_SIZE
                    ny = y + d[1] * GRID_SIZE
                    if 0 <= nx < WINDOW_WIDTH and 0 <= ny < WINDOW_HEIGHT:
                        if (nx, ny) not in trails:
                            moves.append(d)
                return moves

            def evaluate(x, y, trails):
                space = fast_space(x, y, trails)
                dist = abs(x - other_pos[0]) + abs(y - other_pos[1])
                return space * (1 - AGGRESSION) - dist * AGGRESSION

            def simulate(x, y, direction, occ, depth, trails):
                if depth == 0:
                    return evaluate(x, y, trails)

                best = -999999
                for d in valid_moves(x, y, direction, trails):
                    nx = x + d[0]*GRID_SIZE
                    ny = y + d[1]*GRID_SIZE
                    if (nx, ny) in occ:
                        continue
                    score = simulate(
                        nx, ny, d,
                        occ | {(nx, ny)},
                        depth - 1,
                        trails
                    )
                    best = max(best, score)
                return best

            best_dir = None
            best_score = -999999

            for d in moves:
                nx = self.pos.x + d[0]*GRID_SIZE
                ny = self.pos.y + d[1]*GRID_SIZE
                score = simulate(
                    nx, ny, d,
                    set(self.trail+trail) | {(nx, ny)},
                    LOOKAHEAD_DEPTH,
                    self.trail+trail
                )
                if score > best_score:
                    best_score = score
                    best_dir = d

            if best_dir:
                self.direction = best_dir

        
        def isAlive( self, other_trail ):
            if ( self.pos.x, self.pos.y ) in self.trail + other_trail:
                self.is_alive = False
            if self.pos.x < 0 or self.pos.x > WINDOW_WIDTH:
                self.is_alive = False
            if self.pos.y < 0 or self.pos.y > WINDOW_HEIGHT:
                self.is_alive = False

        def drawTrail( self ):
            global screen
            for x, y in self.trail:
                pygame.draw.rect( screen, self.color, ( x, y, GRID_SIZE, GRID_SIZE ) )
        
        def getTrail( self ):
            return self.trail + [(self.pos.x, self.pos.y)]
        
        def getPossibleTrail( self ):
            to_return = self.trail + [
                (
                    self.pos.x,
                    self.pos.y
                ),
                (
                    self.pos.x+self.direction[0]*GRID_SIZE,
                    self.pos.y+self.direction[1]*GRID_SIZE
                )
            ]
            return to_return
        
        def reset( self ):
            self.trail = []
            self.pos.x = self.start_pos[0]
            self.pos.y = self.start_pos[1]
            self.direction = self.start_direction
            self.is_alive = True
        
        def getPos( self ):
            return (self.pos.x, self.pos.y)


    player1 = Player( 150, 300, [1, 0], COLORS["player1"], 1 )
    player2 = Player( 650, 300, [-1, 0], COLORS["player2"], 2 )

    debugPrint( f"player 1 color {COLORS["player1"]}", 1 )
    debugPrint( f"player 2 color {COLORS["player2"]}", 1 )

    running = True
    state = "running"
    last_state = state

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    player1.reset()
                    player2.reset()
                    state = "running"
                    debugPrint( "restart game", 1 )
        
        if state == "running":
            debugPrint( "update players", 1 )
            if not settings["player1"]["bot"]:
                player1.updatePlayer()
            else:
                player1.updateBot( settings["player1"]["difficulty"], player2.getPossibleTrail(), player2.getPos() )
            if not settings["player2"]["bot"]:
                player2.updatePlayer()
            else:
                player2.updateBot( settings["player2"]["difficulty"], player1.getPossibleTrail(), player1.getPos() )
            
            player1.update()
            player2.update()
            
            debugPrint( "check player lives", 1 )
            player1.isAlive( player2.getTrail() )
            player2.isAlive( player1.getTrail() )

        debugPrint( "check death", 1 )
        if player1.is_alive == False and player2.is_alive == False:
            state = "egality"
        if player1.is_alive and player2.is_alive == False:
            state = f"{settings["player1"]["name"]} win"
        if player1.is_alive == False and player2.is_alive:
            state = f"{settings["player2"]["name"]} win"
        
        debugPrint( "refresh screen", 1 )
        screen.fill(COLORS["black"])
        player1.drawTrail()
        player2.drawTrail()

        debugPrint( "print text if end game", 1 )
        if state != "running":
            text = font.render( state, True, COLORS["white"] )
            screen.blit( text, (WINDOW_WIDTH//2 - text.get_width()//2, WINDOW_HEIGHT//2) )
        
        debugPrint( "state debug", 1 )
        if last_state != state:
            debugPrint( f"state is now at {state}", 2 )
        last_state = state

        debugPrint( "pygame functionning", 1 )
        pygame.display.flip()

        clock.tick(FPS)
except Exception as e:
    tb = traceback.extract_tb(sys.exc_info()[2])
    line = tb[-1].lineno
    debugPrint( str( e ) + f" line:{line}", 5 )