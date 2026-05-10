"""Drzewiasty picker katalogu dla AnberCC.

Sterowanie:
  D-pad → / Right    rozwiń gałąź (gdy zwinięta) lub wejdź do dziecka
  D-pad ← / Left     zwiń gałąź (gdy rozwinięta) lub przejdź do rodzica
  D-pad ↑↓           ruch kursora po widocznych gałęziach
  A / START / Enter  odpal Claude Code w zaznaczonym katalogu
  X                  toggle ukrytych (.dotfiles)
  MENU / ESC         anuluj
"""
import os
import select
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import sdl2
import ctypes

W, H = 640, 480
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
EV_KEY, EV_ABS = 1, 3

BG     = (10, 12, 20, 255)
FG     = (220, 225, 230, 255)
DIM    = (110, 120, 135, 255)
ACC    = (80, 180, 255, 255)
HL_BG  = (40, 80, 130, 255)
GRN    = (80, 220, 100, 255)
SEP    = (40, 50, 65, 255)


class Node:
    __slots__ = ('path', 'depth', 'parent', 'expanded', 'children')

    def __init__(self, path: Path, depth: int, parent=None):
        self.path = path
        self.depth = depth
        self.parent = parent
        self.expanded = False
        self.children = None  # None = nie wczytane, [] = pusto

    def load_children(self, show_hidden: bool):
        if self.children is not None:
            return
        kids = []
        try:
            for p in sorted(self.path.iterdir(),
                            key=lambda x: x.name.lower()):
                if not p.is_dir():
                    continue
                if p.name.startswith('.') and not show_hidden:
                    continue
                kids.append(Node(p, self.depth + 1, parent=self))
        except (PermissionError, OSError):
            pass
        self.children = kids


def flatten(root: Node) -> list:
    """DFS — wszystkie widoczne (rozwinięte) węzły."""
    out = [root]
    if root.expanded and root.children:
        for c in root.children:
            out.extend(flatten(c))
    return out


def find_index(visible: list, node: Node) -> int:
    for i, n in enumerate(visible):
        if n is node:
            return i
    return 0


def pick_workdir(renderer, start: str = '/root') -> str | None:
    start_p = Path(start).expanduser().resolve()
    if not start_p.is_dir():
        start_p = Path('/root')

    # zaczynamy od /  i auto-rozwijamy ścieżkę do start
    root = Node(Path('/'), depth=0)
    show_hidden = False

    # rozwiń ścieżkę aż do start_p
    parts = start_p.parts  # ('/', 'root') itp.
    cur = root
    cur.load_children(show_hidden)
    cur.expanded = True
    for part in parts[1:]:
        target = next((c for c in cur.children if c.path.name == part), None)
        if target is None:
            break
        target.load_children(show_hidden)
        target.expanded = True
        cur = target

    # cursor na start_p
    visible = flatten(root)
    cursor_node = next((n for n in visible if n.path == start_p), root)
    cursor = find_index(visible, cursor_node)
    scroll = 0

    font   = ImageFont.truetype(FONT_PATH, 13)
    font_b = ImageFont.truetype(FONT_PATH, 14)
    font_s = ImageFont.truetype(FONT_PATH, 11)

    # evdev
    gp = None
    try:
        import evdev
        gp = evdev.InputDevice('/dev/input/event1')
        try: gp.grab()
        except Exception: pass
    except Exception:
        gp = None

    def render_tree():
        nonlocal scroll
        img = Image.new('RGBA', (W, H), BG)
        d = ImageDraw.Draw(img)

        d.text((8, 6), '⬡  Wybierz katalog dla Claude Code', font=font_b, fill=ACC)
        d.text((8, 26), str(cursor_node.path), font=font_s, fill=GRN)
        d.line([(0, 44), (W, 44)], fill=SEP, width=1)

        line_h = 18
        max_visible = (H - 80 - 26) // line_h

        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + max_visible:
            scroll = cursor - max_visible + 1

        y = 50
        for i in range(scroll, min(len(visible), scroll + max_visible)):
            n = visible[i]
            if i == cursor:
                d.rectangle([(0, y - 1), (W, y + line_h - 3)], fill=HL_BG)
            indent = '  ' * n.depth
            if n.children is None:
                arrow = '▸'   # nie zbadane
            elif not n.children:
                arrow = '·'   # liść / pusty
            elif n.expanded:
                arrow = '▾'   # rozwinięte
            else:
                arrow = '▸'   # zwinięte
            label = n.path.name if n.depth > 0 else '/'
            color = GRN if i == cursor else (ACC if n.expanded else FG)
            d.text((8, y), f'{indent}{arrow} {label}', font=font, fill=color)
            y += line_h

        # legenda
        d.line([(0, H - 28), (W, H - 28)], fill=SEP, width=1)
        d.text((8, H - 22),
               '↑↓=ruch (analog=szybko)  →=rozwiń  ←=zwiń  A/START=wybierz  X=ukryte  MENU=anuluj',
               font=font_s, fill=DIM)

        raw = img.tobytes()
        surf = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(
            raw, W, H, 32, W * 4, sdl2.SDL_PIXELFORMAT_RGBA32)
        tex = sdl2.SDL_CreateTextureFromSurface(renderer, surf)
        sdl2.SDL_FreeSurface(surf)
        sdl2.SDL_RenderClear(renderer)
        sdl2.SDL_RenderCopy(renderer, tex, None, None)
        sdl2.SDL_RenderPresent(renderer)
        sdl2.SDL_DestroyTexture(tex)

    def expand_current():
        nonlocal visible, cursor_node, cursor
        cursor_node.load_children(show_hidden)
        if cursor_node.children:
            if not cursor_node.expanded:
                cursor_node.expanded = True
            else:
                # już rozwinięte — przeskocz do pierwszego dziecka
                cursor_node = cursor_node.children[0]
        visible = flatten(root)
        cursor = find_index(visible, cursor_node)

    def collapse_current():
        nonlocal visible, cursor_node, cursor
        if cursor_node.expanded:
            cursor_node.expanded = False
        elif cursor_node.parent is not None:
            cursor_node = cursor_node.parent
        visible = flatten(root)
        cursor = find_index(visible, cursor_node)

    def move(delta: int):
        nonlocal cursor, cursor_node
        cursor = max(0, min(len(visible) - 1, cursor + delta))
        cursor_node = visible[cursor]

    def reload_with_hidden():
        nonlocal visible, cursor
        # invaliduj children, ale zachowaj expanded state
        def _reset(n: Node):
            n.children = None
            # nie znamy stanu — załaduj jeśli expanded
        _reset(root)
        # rebuild od korzenia rozwijając tam gdzie expanded
        def _rebuild(n: Node):
            n.load_children(show_hidden)
            if n.expanded and n.children:
                for c in n.children:
                    # zachowaj stan rozwinięcia jeśli był
                    pass
                # uproszczone: po toggle ukrytych zwijamy wszystkie poza root
        _rebuild(root)
        visible = flatten(root)
        cursor = min(cursor, len(visible) - 1)

    render_tree()
    ev = sdl2.SDL_Event()
    last_dpad_t = 0
    last_analog_t = 0
    analog_y = 0       # ostatnia wartość prawego analoga Y (ABS code 3)
    REPEAT_MS = 150
    ANALOG_DEADZONE = 1200
    ANALOG_MAX      = 32000
    ANALOG_SLOW_MS  = 200  # przy progu deadzone
    ANALOG_FAST_MS  = 30   # przy maksymalnym wychyleniu

    try:
        while True:
            need_render = False

            if gp is not None:
                if select.select([gp.fd], [], [], 0)[0]:
                    try:
                        for e in gp.read():
                            if e.type == EV_KEY and e.value == 1:
                                if e.code in (354, 316):           # MENU
                                    return None
                                elif e.code in (304, 315):         # A or START
                                    return str(cursor_node.path)
                                elif e.code == 307:                # X — toggle hidden
                                    show_hidden = not show_hidden
                                    reload_with_hidden()
                                    need_render = True
                                elif e.code == 305:                # B = collapse / parent
                                    collapse_current(); need_render = True
                            elif e.type == EV_ABS:
                                ms = sdl2.SDL_GetTicks()
                                if e.code == 3:                    # prawy analog Y
                                    analog_y = e.value
                                elif e.code == 17:                 # D-pad Y
                                    if ms - last_dpad_t < REPEAT_MS:
                                        continue
                                    if e.value == -1:
                                        move(-1); need_render = True; last_dpad_t = ms
                                    elif e.value == 1:
                                        move(1); need_render = True; last_dpad_t = ms
                                elif e.code == 16:                 # D-pad X
                                    if ms - last_dpad_t < REPEAT_MS:
                                        continue
                                    if e.value == 1:               # right = expand
                                        expand_current(); need_render = True; last_dpad_t = ms
                                    elif e.value == -1:            # left = collapse
                                        collapse_current(); need_render = True; last_dpad_t = ms
                    except OSError:
                        pass

            # Analog stick — prędkość proporcjonalna do wychylenia
            # (lekko = wolno, mocno = bardzo szybko)
            ay = abs(analog_y)
            if ay > ANALOG_DEADZONE:
                # 0..1 wychylenie ponad deadzone, znormalizowane
                deflect = min(1.0, (ay - ANALOG_DEADZONE) / max(1, ANALOG_MAX - ANALOG_DEADZONE))
                # interp delay: deadzone→SLOW, max→FAST
                repeat_ms = int(ANALOG_SLOW_MS - deflect * (ANALOG_SLOW_MS - ANALOG_FAST_MS))
                ms_now = sdl2.SDL_GetTicks()
                if ms_now - last_analog_t > repeat_ms:
                    move(-1 if analog_y < 0 else 1)
                    need_render = True
                    last_analog_t = ms_now

            while sdl2.SDL_PollEvent(ctypes.byref(ev)):
                if ev.type == sdl2.SDL_KEYDOWN:
                    sym = ev.key.keysym.sym
                    if sym == sdl2.SDLK_ESCAPE:
                        return None
                    elif sym in (sdl2.SDLK_RETURN, sdl2.SDLK_KP_ENTER):
                        return str(cursor_node.path)
                    elif sym == sdl2.SDLK_RIGHT:
                        expand_current(); need_render = True
                    elif sym == sdl2.SDLK_LEFT:
                        collapse_current(); need_render = True
                    elif sym == sdl2.SDLK_UP:
                        move(-1); need_render = True
                    elif sym == sdl2.SDLK_DOWN:
                        move(1); need_render = True

            if need_render:
                render_tree()
            sdl2.SDL_Delay(20)
    finally:
        if gp is not None:
            try: gp.ungrab()
            except Exception: pass
