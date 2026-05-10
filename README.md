# AnberCC

**Claude Code w kieszeni.** SDL2-owy emulator terminala dla **Anbernic RG40XX V**, który odpala interaktywną sesję `claude` (Claude Code CLI) bez potrzeby SSH z laptopa. Pełnoekranowy, sterowany BT klawiaturą.

Dzięki niemu pracujesz z Claude Code wprost na konsoli — pisanie kodu, czytanie plików, używanie wszystkich narzędzi (Read, Write, Bash, Glob, Grep, Edit) — w trybie "in your hand".

## Możliwości

- Pełnoekranowy emulator terminala 640×480 oparty o `pyte`
- Renderowany przez SDL2 + PIL (działa wprost na DRM/KMS, bez X11)
- Scrollback historii (500 linii)
- Spawnuje `claude` w PTY — pełna kompatybilność z interaktywnym Claude Code
- Działa z BT klawiaturą lub klawiaturą USB OTG
- Integracja z App Center (`dmenu.bin`) — ikona w siatce aplikacji

## Wymagania

### Hardware

- **Anbernic RG40XX V** (Allwinner H700, 640×480 LCD landscape)
- BT klawiatura sparowana (lub USB OTG keyboard) — bez niej nie wpiszesz nic do Claude
- Inne RG40-serii **mogą działać** — niesprawdzone

### Firmware

Tworzone i testowane na **stock Anbernic firmware build `20251225`**:
- Ubuntu 22.04.x LTS (Jammy)
- Kernel `4.9.170` (Allwinner H700 BSP)
- App Center: `dmenu.bin` (vendor)
- File: `/mnt/vendor/oem/version.ini` → `20251225`
- File: `/mnt/vendor/oem/board.ini` → `RG40xxV`

Inne firmware (muOS, Knulli, garlicOS) — niesprawdzone.

### Claude Code CLI + logowanie

Wymagany **claude** CLI z aktywną subskrypcją Anthropic (testowane z **Claude Max**, działa też z **Claude Pro** lub kluczem API).

#### Krok 1: Zainstaluj Node.js (jeśli brakuje)

```bash
apt update && apt install -y nodejs npm
```

#### Krok 2: Zainstaluj Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Sprawdź:
```bash
which claude       # /root/.local/bin/claude lub /usr/local/bin/claude
claude --version
```

#### Krok 3: Zaloguj się — **rób to przez SSH, NIE z poziomu AnberCC**

Logowanie wymaga otwarcia URL w przeglądarce. Najprościej:

1. **Połącz się z konsolą po SSH z laptopa**:
    ```bash
    ssh root@<IP-konsoli>
    ```

2. **Uruchom logowanie**:
    ```bash
    claude /login
    ```
    (Claude Code wewnątrz interaktywnej sesji ma slash command `/login`. Możesz też wpisać `claude` żeby otworzyć sesję, potem `/login`).

    Wybierz tryb logowania (np. `Claude Max account`, `Anthropic API key`, etc.).

3. **Otwórz URL** który Claude wyświetli (długi link `https://claude.ai/...`) — wklej do przeglądarki na laptopie/telefonie. Zaloguj się do swojego konta Anthropic.

4. **Skopiuj kod autoryzacyjny** z przeglądarki, wklej w terminalu SSH gdzie czeka prompt.

5. **Zatwierdź** — Claude zapisze token OAuth w `/root/.claude/credentials.json`.

#### Krok 4: Test

```bash
echo "powiedz hej" | claude -p
```

Powinieneś dostać krótką odpowiedź. Jeśli tak — AnberCC będzie działać natychmiast.

#### Alternatywa: klucz API

Jeśli wolisz nie używać OAuth (nie potrzebujesz subskrypcji Max), tylko klucza API:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> /root/.bashrc
source /root/.bashrc
```

Następnie:
```bash
claude --bare -p "test"
```

> **Uwaga:** AnberCC domyślnie używa Claude Code w trybie OAuth (Max/Pro). Jeśli masz tylko klucz API, edytuj `app/main.py` żeby dodać `--bare` do polecenia spawn-ującego `claude`.

#### Gdzie jest token?

Po pierwszym `claude login` token OAuth znajduje się w `/root/.claude/`. NIE COMMITUJ tej ścieżki nigdzie — zawiera dane uwierzytelniające twojego konta Anthropic.

```bash
ls -la /root/.claude/
# credentials.json — tu jest token, plik chroń
```

AnberCC odpala `python3 main.py` które spawnuje `claude` w PTY, dziedzicząc dostęp do `/root/.claude/`.

### System packages

Stock firmware `20251225` już zawiera wszystko. Jeśli czegoś brakuje:
```bash
apt update
apt install python3 python3-pip libsdl2-2.0-0 fonts-dejavu nodejs npm
```

| Pakiet | Wersja stock | Rola |
|---|---|---|
| `libsdl2-2.0-0` | 2.0.20 | renderer |
| `python3` | 3.10.x | runtime |
| `fonts-dejavu` (DejaVuSansMono.ttf) | systemowy | font UI |
| `nodejs` + `npm` | dla `@anthropic-ai/claude-code` |

### Python packages

| Pakiet | Wersja testowana | Rola |
|---|---|---|
| `pysdl2` | 0.9.17 | bindings do SDL2 |
| `pyte` | 0.8.2 | emulator terminala (VT100/xterm) |
| `pillow` (PIL) | 12.2.0 | rysowanie do bufora |

Instalacja:
```bash
pip install pysdl2 pyte Pillow
```

## Instalacja

```bash
git clone https://github.com/karolfurtak/AnberCC.git
cd AnberCC
./scripts/install.sh
```

Skrypt:
- Kopiuje `app/main.py` do `/mnt/mmc/Roms/APPS/anbercc/main.py`
- Kopiuje launcher do `/mnt/mmc/Roms/APPS/AnberCC.sh`
- Generuje ikonę PNG do `/mnt/mmc/Roms/APPS/Imgs/AnberCC.png`

Po instalacji **AnberCC** pojawi się w App Center na konsoli. Uruchom, sparuj BT klawiaturę (jeśli nie sparowana), pisz `>>> ` jak w zwykłym terminalu.

## Sterowanie

Po uruchomieniu masz pełnoekranowy terminal. Wszystkie znaki idą do `claude`:

- **BT klawiatura** — pełna obsługa (litery, Enter, Backspace, strzałki, Ctrl+C, Ctrl+D)
- **Page Up / Page Down** — scrollback historii
- **Ctrl+C** — wysyła SIGINT do Claude (przerwij output)
- **Ctrl+D** — zamknij sesję / wyjdź
- **Esc dwukrotnie / Ctrl+\** — wyjście awaryjne

## Logi

- `/mnt/data/anbercc.log` — stdout / błędy launchera

## Licencja

MIT — patrz [LICENSE](LICENSE).

## Powiązane

- [Anbernet](https://github.com/karolfurtak/Anbernet) — manager WiFi (D-pad + on-screen klawiatura)
- AnberMon — monitor systemowy (CPU/RAM/Temp/Bat + wykresy + Discord activity)
- AnbernBot — Discord bot z Claude Code do tworzenia sprawozdań
