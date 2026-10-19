# Radar93 - arcade retro de esquivar rascacielos con un avion comercial
# Python 3.15 + pygame. hay que hacer pip install pygame en terminal y luego python 93.py en la carpeta donde se ubica el archivo


import array
import math
import random
import sys
from dataclasses import dataclass

try:
    import pygame
except ImportError:
    sys.exit(
        "Falta pygame.\n"
        "  Instala con:  pip install pygame\n"
        "  Si no hay ruedas para tu sistema:  pip install pygame-ce\n"
        "  (ambos se importan como 'pygame', el código no cambia)"
    )

# ------------------------------------------------------------------ Constantes
WIDTH, HEIGHT = 800, 600
FPS = 60
GROUND_Y = 560
PLANE_X = 180
FLY_KEYS = (pygame.K_UP, pygame.K_w)
ENTER_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)

TEXT_COLOR = (255, 236, 170)
ACCENT_COLOR = (255, 120, 60)
SHADOW_COLOR = (24, 10, 40)

# CAMBIO 1: parámetros de los pares de obstáculos.
MIN_BODY = 80          # altura mínima visible de cada edificio del par
GAP_JITTER = 8         # variación aleatoria del tamaño del hueco
SPACING_JITTER = 20    # variación aleatoria de la separación entre pares

# CAMBIO 5: parámetros del parpadeo de ventanas.
BLINK_RATIO = 0.35     # fracción de ventanas que parpadean
BLINK_STEP = 1 / 12    # velocidad de la transición (12 frames)


# ---------------------------------------------------------------------- Niveles
@dataclass(frozen=True)
class Palette:
    # CAMBIO 2 y 4: colores propios de cada nivel (cielo, ciudad lejana, edificios, ventanas).
    sky_stops: tuple
    sun_color: tuple
    sun_pos: tuple
    sun_radius: int
    cloud_color: tuple
    skyline_color: tuple
    building_colors: tuple
    crown_tint: tuple
    edge_color: tuple
    window_lit: tuple
    window_dark: tuple


# CAMBIO 4: atardecer avanzado, azul-púrpura oscuro arriba y rojo-violeta en el horizonte.
PALETTE_HISTORICO = Palette(
    sky_stops=(
        (0.0, (16, 14, 62)), (0.28, (44, 20, 96)), (0.52, (108, 26, 122)),
        (0.76, (184, 36, 110)), (1.0, (238, 68, 76)),
    ),
    sun_color=(255, 110, 84),
    sun_pos=(560, 520),
    sun_radius=74,
    cloud_color=(150, 38, 116),
    skyline_color=(70, 24, 96),
    building_colors=((26, 18, 52), (34, 22, 62), (22, 26, 58), (40, 24, 56)),
    crown_tint=(110, 50, 110),
    edge_color=(170, 54, 96),
    window_lit=(255, 214, 102),
    window_dark=(50, 40, 82),
)

# CAMBIO 2: el nivel 2 usa una paleta más oscura y sangrienta para distinguirse a simple vista.
PALETTE_TERRORIFICO = Palette(
    sky_stops=(
        (0.0, (6, 4, 22)), (0.28, (26, 6, 44)), (0.52, (70, 8, 62)),
        (0.76, (150, 16, 50)), (1.0, (222, 40, 34)),
    ),
    sun_color=(190, 28, 34),
    sun_pos=(560, 530),
    sun_radius=80,
    cloud_color=(92, 12, 56),
    skyline_color=(40, 8, 40),
    building_colors=((22, 10, 26), (30, 12, 30), (18, 10, 34), (34, 14, 26)),
    crown_tint=(120, 30, 60),
    edge_color=(150, 34, 50),
    window_lit=(255, 150, 60),
    window_dark=(44, 18, 40),
)


@dataclass(frozen=True)
class LevelConfig:
    # CAMBIO 2: datos de un nivel (velocidad, hueco, separación, saltos del hueco y paleta).
    number: int
    name: str
    speed: float        # px por frame
    gap: int            # tamaño medio del hueco entre edificios
    spacing: int        # distancia horizontal entre pares de obstáculos
    min_shift: int      # cambio mínimo de altura del hueco entre pares consecutivos
    max_shift: int      # cambio máximo de altura del hueco entre pares consecutivos
    palette: Palette


LEVELS = (
    LevelConfig(1, "Histórico", 3.0, 190, 380, 90, 170, PALETTE_HISTORICO),
    LevelConfig(2, "Terrorífico", 4.0, 150, 290, 80, 130, PALETTE_TERRORIFICO),
)


# -------------------------------------------------------------------- Utilidades
def lerp_color(a, b, t):
    # Interpola linealmente entre dos colores RGB con t acotado a [0, 1].
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ------------------------------------------------------------------------ Sonido
class SoundManager:
    RATE = 22050

    def __init__(self):
        # Inicia el mixer y genera los sonidos por código; si algo falla, queda en silencio.
        self._flap = None
        self._crash = None
        self._channels = 1
        try:
            pygame.mixer.init(frequency=self.RATE, size=-16, channels=1, allowedchanges=0)
            info = pygame.mixer.get_init()
            if info is None or info[1] != -16:
                return
            self._channels = info[2]
            self._flap = self._build(self._flap_samples())
            self._crash = self._build(self._crash_samples())
        except Exception:
            self._flap = None
            self._crash = None

    def _flap_samples(self):
        # Genera un pitido corto ascendente para el impulso del avión.
        n = int(self.RATE * 0.14)
        phase = 0.0
        out = []
        for i in range(n):
            freq = 380 + (i / n) * 520
            phase += 2 * math.pi * freq / self.RATE
            env = 1.0 - i / n
            out.append(int(0.30 * 32767 * env * math.sin(phase)))
        return out

    def _crash_samples(self):
        # Genera ruido con un rumor grave que se apaga, para el choque.
        n = int(self.RATE * 0.7)
        out = []
        noise = 0.0
        for i in range(n):
            if i % 4 == 0:
                noise = random.uniform(-1.0, 1.0)
            env = (1.0 - i / n) ** 2
            low = math.sin(2 * math.pi * 70 * i / self.RATE)
            out.append(int(0.55 * 32767 * env * (0.7 * noise + 0.5 * low)))
        return out

    def _build(self, samples):
        # Convierte las muestras en un objeto Sound, duplicando canales si hace falta.
        samples = [max(-32767, min(32767, s)) for s in samples]
        if self._channels == 2:
            stereo = []
            for s in samples:
                stereo.extend((s, s))
            samples = stereo
        return pygame.mixer.Sound(buffer=array.array("h", samples).tobytes())

    def _play(self, sound):
        # Reproduce un sonido ignorando cualquier error de audio.
        if sound is None:
            return
        try:
            sound.play()
        except Exception:
            pass

    def play_flap(self):
        # Reproduce el sonido de impulso.
        self._play(self._flap)

    def play_crash(self):
        # Reproduce el sonido de choque.
        self._play(self._crash)


# ---------------------------------------------------------------------- Partículas
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    max_life: int
    radius: float
    is_fire: bool


class ParticleSystem:
    # CAMBIO 3: más partículas, más grandes, con más alcance y mucha más duración.
    BURN_FRAMES = 190
    FLASH_FRAMES = 14

    def __init__(self):
        # Crea un sistema vacío de partículas de fuego y humo.
        self.particles = []
        self.burn_left = 0
        self.flash_left = 0
        self.origin = (0, 0)

    def start(self, x, y):
        # CAMBIO 3: inicia una explosión grande (destello, ráfaga y fuego sostenido).
        self.origin = (x, y)
        self.burn_left = self.BURN_FRAMES
        self.flash_left = self.FLASH_FRAMES
        for _ in range(45):
            self._emit(True, burst=True)
        for _ in range(30):
            self._emit(False, burst=True)

    def _emit(self, is_fire, burst=False):
        # Crea una partícula de fuego o de humo cerca del origen (más amplia en la ráfaga).
        x, y = self.origin
        spread = 24 if burst else 12
        px = x + random.uniform(-spread, spread)
        py = y + random.uniform(-spread, spread)
        if is_fire:
            life = random.randint(30, 60)
            vx_max = 3.2 if burst else 1.8
            vy_min = -4.2 if burst else -3.0
            radius = random.uniform(10, 20) if burst else random.uniform(8, 16)
            particle = Particle(px, py, random.uniform(-vx_max, vx_max),
                                random.uniform(vy_min, -0.8), life, life, radius, True)
        else:
            life = random.randint(120, 220)
            radius = random.uniform(14, 26) if burst else random.uniform(12, 22)
            particle = Particle(px, py - 6, random.uniform(-1.8, 1.0),
                                random.uniform(-2.2, -0.6), life, life, radius, False)
        self.particles.append(particle)

    def update(self):
        # Avanza las partículas, emite nuevas mientras dure el fuego y descarta las muertas.
        if self.burn_left > 0:
            for _ in range(2 if self.burn_left > 90 else 1):
                self._emit(True)
            if self.burn_left % 2 == 0:
                self._emit(False)
            self.burn_left -= 1
        if self.flash_left > 0:
            self.flash_left -= 1
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.life -= 1
            if p.is_fire:
                p.vy *= 0.985
            else:
                p.radius += 0.14
                p.vx *= 0.995
        self.particles = [p for p in self.particles if p.life > 0]

    def draw(self, screen, overlay):
        # Dibuja destello, humo y fuego (en ese orden) con transparencia.
        if not self.particles and self.flash_left <= 0:
            return
        overlay.fill((0, 0, 0, 0))
        if self.flash_left > 0:
            k = self.flash_left / self.FLASH_FRAMES
            radius = int(30 + (1 - k) * 130)
            center = (int(self.origin[0]), int(self.origin[1]))
            pygame.draw.circle(overlay, (255, 200, 90, int(120 * k)), center, radius)
            pygame.draw.circle(overlay, (255, 244, 200, int(220 * k)), center, max(1, radius // 2))
        for p in self.particles:
            if p.is_fire:
                continue
            t = 1.0 - p.life / p.max_life
            color = lerp_color((40, 40, 50), (110, 110, 120), t)
            pygame.draw.circle(overlay, (*color, int(200 * (1 - t))), (int(p.x), int(p.y)), max(1, int(p.radius)))
        for p in self.particles:
            if not p.is_fire:
                continue
            t = 1.0 - p.life / p.max_life
            if t < 0.5:
                color = lerp_color((255, 224, 96), (255, 120, 30), t * 2)
            else:
                color = lerp_color((255, 120, 30), (190, 40, 24), (t - 0.5) * 2)
            radius = p.radius * (1 - 0.5 * t)
            pygame.draw.circle(overlay, (*color, int(230 * (1 - t))), (int(p.x), int(p.y)), max(1, int(radius)))
        screen.blit(overlay, (0, 0))


# ------------------------------------------------------------------------- Avión
class Plane:
    GRAVITY = 0.42
    FLAP_SPEED = -7.2
    MAX_FALL = 10.0

    def __init__(self):
        # Coloca el avión en el centro vertical, sin movimiento.
        self.x = float(PLANE_X)
        self.y = HEIGHT / 2
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.spin = 0.0

    def flap(self):
        # Da un impulso hacia arriba.
        self.vy = self.FLAP_SPEED

    def hover(self, frames):
        # Balancea el avión suavemente mientras espera el inicio.
        self.y = HEIGHT / 2 + math.sin(frames * 0.08) * 6
        self.angle = 0.0

    def update_flying(self):
        # Aplica gravedad, mueve el avión y lo mantiene dentro del borde superior.
        self.vy = min(self.vy + self.GRAVITY, self.MAX_FALL)
        self.y += self.vy
        if self.y < 14:
            self.y = 14
            self.vy = 0.0
        self.angle = max(-60.0, min(30.0, -self.vy * 4))

    def crash(self):
        # Inicia la caída tras el choque: pequeño rebote hacia atrás y giro de morro.
        self.vx = -1.6
        self.vy = -2.5
        self.spin = -2.5

    def update_crashing(self):
        # Hace caer y girar al avión estrellado hasta que toca el suelo.
        self.vy += self.GRAVITY
        self.y += self.vy
        self.x += self.vx
        self.vx *= 0.99
        self.angle = max(-80.0, self.angle + self.spin)
        if self.y >= GROUND_Y - 8:
            self.y = GROUND_Y - 8
            self.vx = self.vy = self.spin = 0.0

    def hitbox(self):
        # Devuelve el rectángulo de colisión centrado en el avión.
        rect = pygame.Rect(0, 0, 56, 12)
        rect.center = (int(self.x), int(self.y))
        return rect


# ---------------------------------------------------------------------- Edificios
class Window:
    # CAMBIO 5: ventana que se enciende o apaga de forma independiente.
    def __init__(self, rect, lit):
        # Guarda su rectángulo, su brillo actual (0-1) y un temporizador propio aleatorio.
        self.rect = rect
        self.value = 1.0 if lit else 0.0
        self.target = self.value
        self.timer = random.randint(20, 300)


class Building:
    def __init__(self, x, tip, width, palette, hanging):
        # CAMBIO 1: crea un edificio de suelo o colgante; "tip" es la punta que mira al hueco.
        self.x = float(x)
        self.width = width
        self.palette = palette
        self.hanging = hanging
        self.blinkers = []
        self.crown_h = random.randint(14, 30)
        self.crown_w = int(width * random.choice((0.5, 0.6, 0.7)))
        self.antenna_h = 0 if hanging else random.choice((0, 0, 16, 24, 34))
        if hanging:
            self.body_bottom = tip - self.crown_h
            self.surface_top = 0
            body_h = self.body_bottom
        else:
            self.body_top = tip + self.crown_h
            self.surface_top = tip - self.antenna_h
            body_h = GROUND_Y - self.body_top
        self.surface = self._render(body_h)

    def _render(self, body_h):
        # Dibuja cuerpo, remate, antena y ventanas; si cuelga, voltea la imagen verticalmente.
        pal = self.palette
        total_h = self.antenna_h + self.crown_h + body_h
        surf = pygame.Surface((self.width, total_h), pygame.SRCALPHA)
        self.surface = surf
        body_color = random.choice(pal.building_colors)
        crown_color = lerp_color(body_color, pal.crown_tint, 0.35)
        crown_x = (self.width - self.crown_w) // 2
        if self.antenna_h:
            mid = self.width // 2
            pygame.draw.line(surf, (150, 150, 165), (mid, 0), (mid, self.antenna_h), 2)
            pygame.draw.circle(surf, (255, 70, 60), (mid, 2), 3)
        crown = pygame.Rect(crown_x, self.antenna_h, self.crown_w, self.crown_h)
        body = pygame.Rect(0, self.antenna_h + self.crown_h, self.width, body_h)
        pygame.draw.rect(surf, crown_color, crown)
        pygame.draw.rect(surf, body_color, body)
        pygame.draw.rect(surf, pal.edge_color, (0, body.y, 3, body.h))
        pygame.draw.rect(surf, pal.edge_color, (crown.x, crown.y, 2, crown.h))
        self._draw_windows(body)
        self._draw_windows(crown)
        if self.hanging:
            surf = pygame.transform.flip(surf, False, True)
            for w in self.blinkers:
                w.rect.y = total_h - w.rect.bottom
        return surf

    def _draw_windows(self, area):
        # Rellena un área con ventanas; algunas quedan registradas para parpadear (CAMBIO 5).
        cols = (area.w - 8) // 12
        rows = (area.h - 8) // 16
        if cols <= 0 or rows <= 0:
            return
        start_x = area.x + (area.w - cols * 12 + 6) // 2
        start_y = area.y + 8
        for r in range(rows):
            for c in range(cols):
                lit = random.random() < 0.5
                rect = pygame.Rect(start_x + c * 12, start_y + r * 16, 6, 8)
                window = Window(rect, lit)
                self._paint_window(window)
                if random.random() < BLINK_RATIO:
                    self.blinkers.append(window)

    def _paint_window(self, window):
        # Pinta una ventana con el brillo intermedio entre apagada y encendida.
        color = lerp_color(self.palette.window_dark, self.palette.window_lit, window.value)
        pygame.draw.rect(self.surface, color, window.rect)

    def update_lights(self):
        # CAMBIO 5: cambia el objetivo de cada ventana en su momento y la transiciona suavemente.
        for w in self.blinkers:
            w.timer -= 1
            if w.timer <= 0:
                w.target = 1.0 - w.target
                w.timer = random.randint(60, 420)
            if w.value != w.target:
                if w.value < w.target:
                    w.value = min(w.target, w.value + BLINK_STEP)
                else:
                    w.value = max(w.target, w.value - BLINK_STEP)
                self._paint_window(w)

    def rects(self):
        # Devuelve los rectángulos de colisión del cuerpo y del remate.
        x = int(self.x)
        crown_x = x + (self.width - self.crown_w) // 2
        if self.hanging:
            return [
                pygame.Rect(x, 0, self.width, self.body_bottom),
                pygame.Rect(crown_x, self.body_bottom, self.crown_w, self.crown_h),
            ]
        return [
            pygame.Rect(x, self.body_top, self.width, GROUND_Y - self.body_top),
            pygame.Rect(crown_x, self.body_top - self.crown_h, self.crown_w, self.crown_h),
        ]

    def right(self):
        # Devuelve la coordenada x del borde derecho del edificio.
        return self.x + self.width


class World:
    def __init__(self, level):
        # Prepara el generador de pares de edificios con los parámetros del nivel.
        self.level = level
        self.speed = level.speed
        self.buildings = []
        self.cursor = float(WIDTH + 250)
        self._last_center = None
        self._fill()

    def _next_center(self, lo, hi):
        # CAMBIO 1: elige el centro del siguiente hueco forzando un cambio de altura notable.
        prev = self._last_center
        if prev is None:
            a, b = max(lo, 220), min(hi, 380)
            if a > b:
                a, b = lo, hi
            return random.randint(a, b)
        lv = self.level
        options = []
        for a, b in ((prev - lv.max_shift, prev - lv.min_shift),
                     (prev + lv.min_shift, prev + lv.max_shift)):
            a, b = max(a, lo), min(b, hi)
            if a <= b:
                options.append((a, b))
        if not options:
            return random.randint(lo, hi)
        a, b = random.choice(options)
        return random.randint(a, b)

    def _spawn_pair(self):
        # CAMBIO 1: crea un edificio colgante y uno de suelo con un hueco entre ambos.
        lv = self.level
        gap = lv.gap + random.randint(-GAP_JITTER, GAP_JITTER)
        lo = MIN_BODY + gap // 2
        hi = GROUND_Y - MIN_BODY - gap // 2
        center = self._next_center(lo, hi)
        self._last_center = center
        top_tip = center - gap // 2
        bottom_tip = top_tip + gap
        self.buildings.append(Building(self.cursor, top_tip, random.randint(70, 110), lv.palette, True))
        self.buildings.append(Building(self.cursor, bottom_tip, random.randint(70, 110), lv.palette, False))

    def _fill(self):
        # Genera pares hasta cubrir el borde derecho de la pantalla.
        while self.cursor < WIDTH + 300:
            self._spawn_pair()
            self.cursor += self.level.spacing + random.randint(-SPACING_JITTER, SPACING_JITTER)

    def update(self):
        # Desplaza los edificios, descarta los que salieron y genera nuevos.
        for b in self.buildings:
            b.x -= self.speed
        self.cursor -= self.speed
        self.buildings = [b for b in self.buildings if b.right() > -10]
        self._fill()

    def update_lights(self):
        # CAMBIO 5: hace parpadear las ventanas de todos los edificios.
        for b in self.buildings:
            b.update_lights()

    def collides(self, hitbox):
        # Indica si el rectángulo toca algún edificio, superior o inferior.
        for b in self.buildings:
            if b.x > hitbox.right + 10 or b.right() < hitbox.left - 10:
                continue
            for rect in b.rects():
                if hitbox.colliderect(rect):
                    return True
        return False


# --------------------------------------------------------------------- Renderizado
class Renderer:
    def __init__(self, screen):
        # Prepara fuentes y superficies prerenderizadas (escenas por nivel, avión).
        self.screen = screen
        self.font_title = self._font(72)
        self.font_big = self._font(52)
        self.font_mid = self._font(30)
        self.font_small = self._font(22)
        self.scenes = {lv.number: self._build_scene(lv) for lv in LEVELS}
        self.plane_sprite = self._build_plane_sprite()
        self.overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    def _font(self, size):
        # Carga una fuente monoespaciada en negrita; si no existe, usa la de pygame.
        try:
            return pygame.font.SysFont("consolas,couriernew,dejavusansmono,monospace", size, bold=True)
        except Exception:
            return pygame.font.Font(None, size)

    def _build_scene(self, level):
        # CAMBIO 2 y 4: dibuja cielo (degradado de tarde-noche), sol, nubes y silueta lejana del nivel.
        pal = level.palette
        background = pygame.Surface((WIDTH, HEIGHT))
        stops = pal.sky_stops
        for y in range(HEIGHT):
            t = min(1.0, y / GROUND_Y)
            color = stops[-1][1]
            for i in range(len(stops) - 1):
                t0, c0 = stops[i]
                t1, c1 = stops[i + 1]
                if t <= t1:
                    color = lerp_color(c0, c1, (t - t0) / (t1 - t0))
                    break
            pygame.draw.line(background, color, (0, y), (WIDTH, y))
        pygame.draw.circle(background, pal.sun_color, pal.sun_pos, pal.sun_radius)
        rng = random.Random(7 + level.number)
        for _ in range(7):
            w = rng.randint(120, 230)
            pygame.draw.ellipse(background, pal.cloud_color,
                                (rng.randint(-40, WIDTH - 80), rng.randint(110, 320), w, rng.randint(10, 18)))
        skyline = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        rng = random.Random(93 + level.number)
        x = 0
        while x < WIDTH:
            w = min(rng.randint(30, 70), WIDTH - x)
            h = rng.randint(70, 230)
            pygame.draw.rect(skyline, pal.skyline_color, (x, GROUND_Y - h, w, h))
            if rng.random() < 0.4:
                pygame.draw.line(skyline, pal.skyline_color, (x + w // 2, GROUND_Y - h - 18), (x + w // 2, GROUND_Y - h), 2)
            x += w + rng.randint(0, 8)
        return background, skyline

    def _build_plane_sprite(self):
        # Dibuja el avión comercial mirando a la derecha con formas simples.
        s = pygame.Surface((72, 34), pygame.SRCALPHA)
        pygame.draw.polygon(s, (214, 60, 64), [(4, 2), (16, 2), (26, 15), (10, 15)])
        pygame.draw.polygon(s, (150, 156, 178), [(34, 15), (48, 15), (38, 5), (30, 5)])
        pygame.draw.ellipse(s, (244, 244, 250), (6, 13, 62, 14))
        pygame.draw.rect(s, (40, 90, 170), (14, 19, 50, 3))
        pygame.draw.ellipse(s, (40, 60, 100), (52, 15, 9, 4))
        for i in range(7):
            pygame.draw.circle(s, (60, 90, 150), (22 + i * 5, 17), 1)
        pygame.draw.polygon(s, (200, 206, 222), [(30, 20), (44, 20), (30, 32), (20, 32)])
        pygame.draw.ellipse(s, (120, 126, 146), (30, 24, 12, 5))
        return s

    def text(self, text, font, color, center, shadow=True):
        # Dibuja texto centrado con sombra estilo arcade y devuelve su rectángulo.
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=center)
        if shadow:
            self.screen.blit(font.render(text, True, SHADOW_COLOR), rect.move(3, 3))
        self.screen.blit(surf, rect)
        return rect

    def draw_background(self, level, offset):
        # Dibuja el cielo y la silueta lejana del nivel con desplazamiento paralaje.
        background, skyline = self.scenes[level.number]
        self.screen.blit(background, (0, 0))
        x = -(int(offset * 0.3) % WIDTH)
        self.screen.blit(skyline, (x, 0))
        self.screen.blit(skyline, (x + WIDTH, 0))

    def draw_buildings(self, buildings):
        # Dibuja los rascacielos visibles (de suelo y colgantes).
        for b in buildings:
            self.screen.blit(b.surface, (int(b.x), b.surface_top))

    def draw_ground(self, offset):
        # Dibuja el suelo con una línea discontinua que da sensación de velocidad.
        pygame.draw.rect(self.screen, (18, 14, 28), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.line(self.screen, (96, 56, 100), (0, GROUND_Y), (WIDTH, GROUND_Y), 2)
        shift = int(offset) % 48
        for x in range(-shift, WIDTH, 48):
            pygame.draw.rect(self.screen, (230, 190, 90), (x, 582, 26, 4))

    def draw_plane(self, plane):
        # Dibuja el avión rotado según su ángulo.
        rotated = pygame.transform.rotate(self.plane_sprite, plane.angle)
        self.screen.blit(rotated, rotated.get_rect(center=(int(plane.x), int(plane.y))))

    def draw_particles(self, particles):
        # Dibuja el fuego y el humo del choque.
        particles.draw(self.screen, self.overlay)

    def draw_timer(self, seconds):
        # Muestra el tiempo de la partida en la esquina superior derecha.
        label = self.font_mid.render(f"TIEMPO {seconds:.1f} s", True, TEXT_COLOR)
        shadow = self.font_mid.render(f"TIEMPO {seconds:.1f} s", True, SHADOW_COLOR)
        rect = label.get_rect(topright=(WIDTH - 16, 12))
        self.screen.blit(shadow, rect.move(3, 3))
        self.screen.blit(label, rect)

    def draw_level_banner(self, level):
        # CAMBIO 2: muestra el número y el nombre del nivel al empezar.
        self.text(f"NIVEL {level.number}", self.font_big, ACCENT_COLOR, (WIDTH // 2, 70))
        self.text(level.name.upper(), self.font_mid, TEXT_COLOR, (WIDTH // 2, 112))

    def draw_instructions(self, frames):
        # Muestra el aviso de controles antes de empezar a volar.
        self.text("SOLO FLECHA ARRIBA Y W", self.font_mid, TEXT_COLOR, (WIDTH // 2, 170))
        self.text("SIRVEN PARA VOLAR", self.font_mid, TEXT_COLOR, (WIDTH // 2, 208))
        if (frames // 30) % 2 == 0:
            self.text("PULSA UNA PARA DESPEGAR", self.font_small, ACCENT_COLOR, (WIDTH // 2, 262))

    def draw_menu(self, rects, levels, mouse_pos, frames):
        # Dibuja el menú principal con un botón por nivel.
        self.draw_background(levels[0], frames * 1.0)
        self.draw_ground(frames * 1.0)
        self.text("RADAR93", self.font_title, TEXT_COLOR, (WIDTH // 2, 120))
        self.text("ELIGE NIVEL", self.font_mid, ACCENT_COLOR, (WIDTH // 2, 210))
        for rect, level in zip(rects, levels):
            hover = rect.collidepoint(mouse_pos)
            fill = (255, 150, 70) if hover else (60, 30, 80)
            pygame.draw.rect(self.screen, SHADOW_COLOR, rect.move(4, 4))
            pygame.draw.rect(self.screen, fill, rect)
            pygame.draw.rect(self.screen, TEXT_COLOR, rect, 3)
            color = SHADOW_COLOR if hover else TEXT_COLOR
            self.text(level.name.upper(), self.font_mid, color, rect.center, shadow=False)

    def draw_game_over(self, snapshot, seconds, frames):
        # Dibuja la pantalla de derrota sobre la última imagen de la partida.
        self.screen.blit(snapshot, (0, 0))
        self.overlay.fill((10, 4, 24, 180))
        self.screen.blit(self.overlay, (0, 0))
        self.text("PERDISTE", self.font_big, ACCENT_COLOR, (WIDTH // 2, 170))
        self.text("MÁS SUERTE LA PRÓXIMA", self.font_mid, TEXT_COLOR, (WIDTH // 2, 245))
        self.text(f"TIEMPO {seconds:.1f} s", self.font_mid, TEXT_COLOR, (WIDTH // 2, 330))
        if (frames // 30) % 2 == 0:
            self.text("ENTER PARA VOLVER AL MENÚ", self.font_small, TEXT_COLOR, (WIDTH // 2, 420))


# ----------------------------------------------------------------------- Estados
class State:
    def __init__(self, game):
        # Guarda la referencia al juego para acceder a recursos compartidos.
        self.game = game

    def handle_event(self, event):
        # Procesa un evento de pygame (lo implementa cada estado).
        pass

    def update(self):
        # Avanza la lógica un frame (lo implementa cada estado).
        pass

    def draw(self):
        # Dibuja el estado en pantalla (lo implementa cada estado).
        pass


class MenuState(State):
    def __init__(self, game):
        # Crea los botones de selección de nivel.
        super().__init__(game)
        self.frames = 0
        self.rects = []
        for i in range(len(LEVELS)):
            rect = pygame.Rect(0, 0, 320, 64)
            rect.center = (WIDTH // 2, 310 + i * 90)
            self.rects.append(rect)

    def handle_event(self, event):
        # Inicia el nivel cuyo botón se pulsa con el clic izquierdo.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, level in zip(self.rects, LEVELS):
                if rect.collidepoint(event.pos):
                    self.game.start_level(level)
                    return

    def update(self):
        # Avanza la animación del fondo del menú.
        self.frames += 1

    def draw(self):
        # Dibuja el menú principal.
        self.game.renderer.draw_menu(self.rects, LEVELS, pygame.mouse.get_pos(), self.frames)


class PlayState(State):
    READY, FLYING, CRASHING = "ready", "flying", "crashing"
    CRASH_FRAMES = 210      # CAMBIO 3: más tiempo para apreciar la explosión y el humo
    BANNER_FRAMES = 100     # CAMBIO 2: frames que el rótulo de nivel sigue visible al despegar

    def __init__(self, game, level):
        # Prepara una partida nueva para el nivel elegido.
        super().__init__(game)
        self.level = level
        self.world = World(level)
        self.plane = Plane()
        self.particles = ParticleSystem()
        self.phase = self.READY
        self.frames = 0
        self.flight_frames = 0
        self.start_ticks = 0
        self.elapsed = 0.0
        self.bg_offset = 0.0
        self.crash_frames = 0

    def handle_event(self, event):
        # Reacciona solo a flecha arriba o W: inicia el vuelo o da impulso.
        if event.type != pygame.KEYDOWN or event.key not in FLY_KEYS:
            return
        if self.phase == self.READY:
            self.phase = self.FLYING
            self.start_ticks = pygame.time.get_ticks()
        if self.phase == self.FLYING:
            self.plane.flap()
            self.game.sound.play_flap()

    def update(self):
        # Avanza la fase actual: espera, vuelo o caída tras el choque.
        self.frames += 1
        self.world.update_lights()
        if self.phase == self.READY:
            self.plane.hover(self.frames)
        elif self.phase == self.FLYING:
            self._update_flying()
        else:
            self._update_crashing()

    def _update_flying(self):
        # Mueve mundo y avión, actualiza el tiempo y detecta choques.
        self.flight_frames += 1
        self.elapsed = (pygame.time.get_ticks() - self.start_ticks) / 1000.0
        self.world.update()
        self.bg_offset += self.level.speed
        self.plane.update_flying()
        hitbox = self.plane.hitbox()
        if self.world.collides(hitbox):
            self._crash(hitbox.midright)
        elif hitbox.bottom >= GROUND_Y:
            self._crash((int(self.plane.x), GROUND_Y - 4))

    def _crash(self, point):
        # Congela el tiempo, lanza fuego y humo y empieza la caída del avión.
        self.phase = self.CRASHING
        self.plane.crash()
        self.particles.start(*point)
        self.game.sound.play_crash()

    def _update_crashing(self):
        # Hace caer el avión y, pasado un momento, muestra la pantalla de derrota.
        self.plane.update_crashing()
        self.particles.update()
        self.crash_frames += 1
        if self.crash_frames >= self.CRASH_FRAMES:
            self.game.show_game_over(self.game.screen.copy(), self.elapsed)

    def draw(self):
        # Dibuja la escena completa de la partida.
        r = self.game.renderer
        r.draw_background(self.level, self.bg_offset)
        r.draw_buildings(self.world.buildings)
        r.draw_ground(self.bg_offset)
        r.draw_plane(self.plane)
        r.draw_particles(self.particles)
        r.draw_timer(self.elapsed)
        if self.phase == self.READY or (self.phase == self.FLYING and self.flight_frames < self.BANNER_FRAMES):
            r.draw_level_banner(self.level)
        if self.phase == self.READY:
            r.draw_instructions(self.frames)


class GameOverState(State):
    def __init__(self, game, snapshot, seconds):
        # Guarda la última imagen de la partida y el tiempo final.
        super().__init__(game)
        self.snapshot = snapshot
        self.seconds = seconds
        self.frames = 0

    def handle_event(self, event):
        # Con ENTER vuelve al menú principal.
        if event.type == pygame.KEYDOWN and event.key in ENTER_KEYS:
            self.game.go_menu()

    def update(self):
        # Avanza el parpadeo del mensaje.
        self.frames += 1

    def draw(self):
        # Dibuja la pantalla de derrota.
        self.game.renderer.draw_game_over(self.snapshot, self.seconds, self.frames)


# --------------------------------------------------------------------------- Juego
class Game:
    def __init__(self):
        # Inicia pygame, la ventana de 800x600, el sonido y el menú principal.
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Radar93")
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.sound = SoundManager()
        self.state = MenuState(self)

    def go_menu(self):
        # Cambia al menú principal.
        self.state = MenuState(self)

    def start_level(self, level):
        # Cambia a una partida nueva en el nivel indicado.
        self.state = PlayState(self, level)

    def show_game_over(self, snapshot, seconds):
        # Cambia a la pantalla de derrota con el tiempo final.
        self.state = GameOverState(self, snapshot, seconds)

    def run(self):
        # Bucle principal: eventos, lógica, dibujo y control de 60 FPS.
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.state.handle_event(event)
            self.state.update()
            self.state.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()


def main():
    # Punto de entrada del programa.
    Game().run()


if __name__ == "__main__":
    main()