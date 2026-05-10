#!/usr/bin/env python3
"""AnberCC — Claude Code SDL2 terminal dla Anbernic RG40XX V.

GitHub: https://github.com/karolfurtak/AnberCC
"""
import os, sys, pty, fcntl, termios, struct, signal, ctypes
from PIL import Image, ImageDraw, ImageFont

# No SDL_VIDEODRIVER — let SDL auto-detect (Clock app pattern, avoids fbdev fail)
os.environ["PYSDL2_DLL_PATH"] = "/usr/lib"

import sdl2
import pyte
import time as _time


class HistoryScreen(pyte.Screen):
    """pyte.Screen extended with a manual scrollback buffer."""
    MAX_HIST = 500

    def __init__(self, cols, rows):
        super().__init__(cols, rows)
        self._hist = []  # list of {col: Char} dicts, oldest first

    def index(self):
        m = self.margins
        if m is None or (m.top == 0 and m.bottom == self.lines - 1):
            snap = {c: self.buffer[0][c] for c in range(self.columns)}
            self._hist.append(snap)
            if len(self._hist) > self.MAX_HIST:
                self._hist.pop(0)
        super().index()

    @property
    def hist_len(self):
        return len(self._hist)


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 13
W, H = 640, 480
CMD = ["/root/.local/bin/claude"]

EV_KEY = 1
EV_ABS = 3
_EV_STRUCT = struct.Struct('llHHI')
EV_SIZE = _EV_STRUCT.size

GAMEPAD_MAP = {
    304: b'\r',         # BTN_SOUTH (A)    → Enter
    305: b'\x1b',       # BTN_EAST  (B)    → Escape
    307: b'\t',         # BTN_NORTH (X)    → Tab
    310: b'\x1b[5~',    # BTN_TL    (L1)   → Page Up
    311: b'\x1b[6~',    # BTN_TR    (R1)   → Page Down
    314: b'\x03',       # BTN_SELECT       → Ctrl+C
}
DPAD_MAP = {
    (16,  1): b'\x1b[C',
    (16, -1): b'\x1b[D',
    (17,  1): b'\x1b[B',
    (17, -1): b'\x1b[A',
}
ANALOG_DEADZONE = 1200
ANALOG_INTERVAL = 0.15

PALETTE = [
    (0,0,0),(205,0,0),(0,205,0),(205,205,0),
    (0,0,238),(205,0,205),(0,205,205),(229,229,229),
    (127,127,127),(255,0,0),(0,255,0),(255,255,0),
    (92,92,255),(255,0,255),(0,255,255),(255,255,255),
]
NAMED = {
    'default':None,'black':0,'red':1,'green':2,'brown':3,
    'blue':4,'magenta':5,'cyan':6,'white':7,
    'brightblack':8,'brightred':9,'brightgreen':10,'brightyellow':11,
    'brightblue':12,'brightmagenta':13,'brightcyan':14,'brightwhite':15,
}

def to_rgb(c, bg=False):
    default = (0,0,0) if bg else (229,229,229)
    if c is None or c == 'default':
        return default
    if isinstance(c, int):
        if c < 16: return PALETTE[c]
        if c >= 232: v=(c-232)*10+8; return (v,v,v)
        c -= 16; return ((c//36)*51, ((c//6)%6)*51, (c%6)*51)
    idx = NAMED.get(c)
    return PALETTE[idx] if idx is not None else default

KEY_MAP = {
    sdl2.SDLK_RETURN:    b'\r',
    sdl2.SDLK_KP_ENTER:  b'\r',
    sdl2.SDLK_BACKSPACE: b'\x7f',
    sdl2.SDLK_DELETE:    b'\x1b[3~',
    sdl2.SDLK_UP:        b'\x1b[A',
    sdl2.SDLK_DOWN:      b'\x1b[B',
    sdl2.SDLK_RIGHT:     b'\x1b[C',
    sdl2.SDLK_LEFT:      b'\x1b[D',
    sdl2.SDLK_HOME:      b'\x1b[H',
    sdl2.SDLK_END:       b'\x1b[F',
    sdl2.SDLK_PAGEUP:    b'\x1b[5~',
    sdl2.SDLK_PAGEDOWN:  b'\x1b[6~',
    sdl2.SDLK_ESCAPE:    b'\x1b',
    sdl2.SDLK_TAB:       b'\t',
    sdl2.SDLK_F1:  b'\x1bOP',  sdl2.SDLK_F2:  b'\x1bOQ',
    sdl2.SDLK_F3:  b'\x1bOR',  sdl2.SDLK_F4:  b'\x1bOS',
    sdl2.SDLK_F5:  b'\x1b[15~', sdl2.SDLK_F6: b'\x1b[17~',
    sdl2.SDLK_F7:  b'\x1b[18~', sdl2.SDLK_F8: b'\x1b[19~',
    sdl2.SDLK_F9:  b'\x1b[20~', sdl2.SDLK_F10:b'\x1b[21~',
    sdl2.SDLK_F11: b'\x1b[23~', sdl2.SDLK_F12:b'\x1b[24~',
}


def make_font_and_metrics():
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    ascent, descent = font.getmetrics()
    char_h = ascent + descent
    try:
        char_w = int(font.getlength("M"))
    except AttributeError:
        bbox = ImageDraw.Draw(Image.new('RGBA', (200, 50))).textbbox((0,0), "MM", font=font)
        char_w = (bbox[2] - bbox[0]) // 2
    return font, max(char_w, 1), max(char_h, 1), ascent


class Renderer:
    """Incremental terminal renderer: only redraws dirty rows, caches glyphs."""

    def __init__(self, font, char_w, char_h, cols, rows, ascent):
        self.font   = font
        self.cw     = char_w
        self.ch     = char_h
        self.cols   = cols
        self.rows   = rows
        self.asc    = ascent
        self.img    = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        self.draw   = ImageDraw.Draw(self.img)
        self._cache = {}          # (char, fg, bg) → PIL Image (cw × ch)
        self._pcx   = 0           # previous cursor x
        self._pcy   = 0           # previous cursor y
        self._force = True        # force full redraw on first frame
        self._pvo   = 0           # previous view_offset

    def _glyph(self, char, fg, bg):
        key = (char, fg, bg)
        g = self._cache.get(key)
        if g is None:
            g = Image.new('RGBA', (self.cw, self.ch), bg + (255,))
            if char and char != ' ':
                ImageDraw.Draw(g).text((0, self.asc), char, font=self.font,
                                       fill=fg + (255,), anchor='ls')
            self._cache[key] = g
        return g

    def _paste_row(self, screen_r, row, is_hist=False):
        y = screen_r * self.ch
        dc = self.default_char if is_hist else None
        for c in range(self.cols):
            ch = row.get(c, dc) if is_hist else row[c]
            if ch is None:
                ch = self.default_char
            fg = to_rgb(ch.fg, False)
            bg = to_rgb(ch.bg, True)
            if ch.reverse:
                fg, bg = bg, fg
            self.img.paste(self._glyph(ch.data, fg, bg), (c * self.cw, y))

    def _draw_cursor(self, cx, cy):
        x = cx * self.cw
        y = cy * self.ch
        self.draw.rectangle([x, y + self.ch - 2, x + self.cw, y + self.ch],
                            fill=(200, 200, 200, 255))

    def _full_redraw(self, terminal, view_offset):
        hist = terminal._hist
        hl   = len(hist)
        for r in range(self.rows):
            v = r - view_offset
            if v >= 0:
                self._paste_row(r, terminal.buffer[v])
            else:
                hi = hl + v
                if hi >= 0:
                    self._paste_row(r, hist[hi], is_hist=True)
                else:
                    y = r * self.ch
                    self.draw.rectangle([0, y, W, y + self.ch], fill=(0, 0, 0, 255))
        if view_offset == 0:
            self._draw_cursor(terminal.cursor.x, terminal.cursor.y)
            self._pcx = terminal.cursor.x
            self._pcy = terminal.cursor.y
        else:
            max_off = max(1, hl)
            bh = max(12, H * self.rows // max(1, hl + self.rows))
            by = (H - bh) * (max_off - view_offset) // max_off
            self.draw.rectangle([W-4, by, W-1, by+bh], fill=(160, 160, 160, 255))
        terminal.dirty.clear()
        self._force = False
        self._pvo   = view_offset

    def render(self, terminal, view_offset):
        self.default_char = terminal.default_char

        offset_changed = (view_offset != self._pvo)

        if self._force or offset_changed or view_offset != 0:
            self._full_redraw(terminal, view_offset)
            return self.img

        # Incremental update — only dirty rows
        dirty = set(terminal.dirty)
        cx, cy = terminal.cursor.x, terminal.cursor.y
        if (self._pcx, self._pcy) != (cx, cy):
            dirty.add(self._pcy)   # repaint row with old cursor
        dirty.add(cy)              # repaint row with new cursor
        terminal.dirty.clear()

        for r in dirty:
            if 0 <= r < self.rows:
                self._paste_row(r, terminal.buffer[r])

        self._draw_cursor(cx, cy)
        self._pcx, self._pcy = cx, cy
        return self.img


def upload_texture(sdl_renderer, img):
    rgba = img.tobytes()
    w, h = img.size
    surface = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(
        rgba, w, h, 32, w * 4, sdl2.SDL_PIXELFORMAT_RGBA32
    )
    if not surface:
        return None
    tex = sdl2.SDL_CreateTextureFromSurface(sdl_renderer, surface)
    sdl2.SDL_FreeSurface(surface)
    return tex


def main():
    if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_EVENTS) != 0:
        print("SDL_Init failed:", sdl2.SDL_GetError(), file=sys.stderr)
        return 1

    window = sdl2.SDL_CreateWindow(
        b"Claude",
        sdl2.SDL_WINDOWPOS_UNDEFINED, sdl2.SDL_WINDOWPOS_UNDEFINED,
        0, 0,
        sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_SHOWN,
    )
    if not window:
        print("SDL_CreateWindow failed:", sdl2.SDL_GetError(), file=sys.stderr)
        sdl2.SDL_Quit()
        return 1

    sdl_renderer = sdl2.SDL_CreateRenderer(window, -1, sdl2.SDL_RENDERER_SOFTWARE)
    if not sdl_renderer:
        sdl_renderer = sdl2.SDL_CreateRenderer(window, -1, 0)
    if not sdl_renderer:
        print("SDL_CreateRenderer failed:", sdl2.SDL_GetError(), file=sys.stderr)
        sdl2.SDL_DestroyWindow(window)
        sdl2.SDL_Quit()
        return 1

    # File picker przed startem Claude — wybór katalogu roboczego.
    # Można wymusić skip podając CC_WORKDIR + CC_SKIP_PICKER=1 w env.
    workdir = os.environ.get('CC_WORKDIR', '/root')
    if not os.environ.get('CC_SKIP_PICKER'):
        try:
            from filepicker import pick_workdir
            picked = pick_workdir(sdl_renderer, start=workdir)
            if picked is None:
                # MENU/ESC = anulowanie pickera = wyjście z apki
                sdl2.SDL_DestroyRenderer(sdl_renderer)
                sdl2.SDL_DestroyWindow(window)
                sdl2.SDL_Quit()
                return 0
            workdir = picked
        except Exception as e:
            print(f'pick_workdir error: {e} — fallback do {workdir}', file=sys.stderr)

    try:
        os.chdir(workdir)
    except Exception:
        os.chdir('/root')

    font, char_w, char_h, ascent = make_font_and_metrics()
    cols = W // char_w
    rows = H // char_h

    terminal  = HistoryScreen(cols, rows)
    stream    = pyte.ByteStream(terminal)
    renderer  = Renderer(font, char_w, char_h, cols, rows, ascent)

    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ,
                struct.pack('HHHH', rows, cols, W, H))

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    pid = os.fork()
    if pid == 0:
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        for fd in range(3):
            os.dup2(slave_fd, fd)
        if slave_fd > 2:
            os.close(slave_fd)
        os.execve(CMD[0], CMD, {
            'TERM': 'xterm-256color',
            'HOME': '/root',
            'LANG': 'en_US.UTF-8',
            'PATH': '/root/.local/bin:/usr/local/bin:/usr/bin:/bin',
            'COLORTERM': 'truecolor',
        })
        sys.exit(1)

    os.close(slave_fd)
    fcntl.fcntl(master_fd, fcntl.F_SETFL,
                fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

    sdl2.SDL_SetHint(sdl2.SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, b"0")
    sdl2.SDL_JoystickEventState(sdl2.SDL_IGNORE)

    gamepad_fd = -1
    try:
        gamepad_fd = os.open('/dev/input/event1', os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        pass

    sdl2.SDL_StartTextInput()
    event       = sdl2.SDL_Event()
    dirty       = True
    running     = True
    exit_reason = "loop_end"
    analog_y    = 0
    analog_next = 0.0
    view_offset = 0

    # POWER button → wygaszanie ekranu bez zamykania apki
    try:
        from power_screen import ScreenPowerToggle
        screen_pwr = ScreenPowerToggle()
    except Exception:
        screen_pwr = None

    def write_pty(seq):
        nonlocal running
        try:
            os.write(master_fd, seq)
        except OSError:
            running = False

    while running:
        # POWER button — toggle ekranu (nie zamyka apki)
        if screen_pwr is not None:
            screen_pwr.poll()
            screen_pwr.tick(sdl2.SDL_GetTicks())
            if screen_pwr.is_off:
                sdl2.SDL_Delay(50)
                continue

        # Drain PTY
        while True:
            try:
                data = os.read(master_fd, 8192)
                if data:
                    stream.feed(data)
                    dirty = True
                    view_offset = 0
            except BlockingIOError:
                break
            except OSError:
                exit_reason = "pty_closed"
                running = False
                break

        wpid, wstatus = os.waitpid(pid, os.WNOHANG)
        if wpid:
            exit_reason = f"claude_exited_status={wstatus}"
            break

        # Gamepad / console buttons (evdev)
        if gamepad_fd >= 0:
            while True:
                try:
                    raw = os.read(gamepad_fd, EV_SIZE)
                    if len(raw) < EV_SIZE:
                        break
                    _, _, ev_type, code, value = _EV_STRUCT.unpack(raw)
                    if value > 0x7FFFFFFF:
                        value -= 0x100000000
                    if ev_type == EV_KEY and value == 1:
                        if code in (312, 316):
                            exit_reason = "MENU"
                            running = False
                        else:
                            seq = GAMEPAD_MAP.get(code)
                            if seq:
                                write_pty(seq)
                    elif ev_type == EV_ABS:
                        if code in (16, 17):
                            seq = DPAD_MAP.get((code, value))
                            if seq:
                                write_pty(seq)
                        elif code == 3:
                            analog_y = value
                except BlockingIOError:
                    break
                except OSError:
                    break

        # Analog stick scroll
        if abs(analog_y) > ANALOG_DEADZONE:
            now = _time.monotonic()
            if now >= analog_next:
                if analog_y < 0:
                    view_offset = min(view_offset + 3, terminal.hist_len)
                else:
                    view_offset = max(0, view_offset - 3)
                dirty = True
                analog_next = now + ANALOG_INTERVAL

        # BT keyboard (SDL events)
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            if event.type == sdl2.SDL_QUIT:
                exit_reason = "SDL_QUIT"
                running = False
            elif event.type == sdl2.SDL_KEYDOWN:
                sym = event.key.keysym.sym
                mod = event.key.keysym.mod
                if sym in KEY_MAP:
                    write_pty(KEY_MAP[sym])
                elif mod & sdl2.KMOD_CTRL:
                    if sdl2.SDLK_a <= sym <= sdl2.SDLK_z:
                        write_pty(bytes([sym - sdl2.SDLK_a + 1]))
                    elif sym == sdl2.SDLK_LEFTBRACKET:
                        write_pty(b'\x1b')
            elif event.type == sdl2.SDL_TEXTINPUT:
                text = bytes(event.text.text).rstrip(b'\x00')
                if text:
                    write_pty(text)
                    dirty = True   # cursor moved — force redraw

        if dirty:
            img = renderer.render(terminal, view_offset)
            tex = upload_texture(sdl_renderer, img)
            if tex:
                sdl2.SDL_SetRenderDrawColor(sdl_renderer, 0, 0, 0, 255)
                sdl2.SDL_RenderClear(sdl_renderer)
                dst = sdl2.SDL_Rect(0, 0, W, H)
                sdl2.SDL_RenderCopy(sdl_renderer, tex, None, dst)
                sdl2.SDL_RenderPresent(sdl_renderer)
                sdl2.SDL_DestroyTexture(tex)
            dirty = False

        sdl2.SDL_Delay(10)

    print(f"EXIT: {exit_reason}", file=sys.stderr)
    if screen_pwr is not None:
        screen_pwr.restore()
    sdl2.SDL_StopTextInput()
    if gamepad_fd >= 0:
        try:
            os.close(gamepad_fd)
        except OSError:
            pass
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    os.close(master_fd)
    sdl2.SDL_DestroyRenderer(sdl_renderer)
    sdl2.SDL_DestroyWindow(window)
    sdl2.SDL_Quit()
    return 0


if __name__ == '__main__':
    sys.exit(main())
