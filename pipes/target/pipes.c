/*
 * pipes.c - C port of pipes-py (a pipes.sh clone), native Windows.
 *
 * Build with MSVC (Developer Command Prompt):
 *     cl /W4 /O2 pipes.c
 *
 * Build with MinGW-w64:
 *     gcc -O2 -Wall -Wextra -o pipes.exe pipes.c -lwinmm
 *
 * curses does not exist on Windows, so rendering uses the Win32 Console API
 * (WriteConsoleOutputCharacterW / WriteConsoleOutputAttribute) and input uses
 * conio.h (_kbhit / _getch). Behaviour, keybindings, config file format and
 * on-screen output match the Python version.
 */

#define _CRT_SECURE_NO_WARNINGS
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <mmsystem.h>   /* timeBeginPeriod - 1 ms timer resolution */
#include <conio.h>
#include <ctype.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _MSC_VER
#pragma comment(lib, "winmm.lib")
#endif

#define APP_VERSION   "2.0.0"
#define NUM_SETS      10
#define SET_LEN       16
#define NUM_COLORS    8
#define MAX_PIPES     10000   /* guard against a malloc bomb from -p */

/* ------------------------------------------------------------------ */
/* types.py                                                            */
/* ------------------------------------------------------------------ */

enum Direction { DIR_UP = 0, DIR_RIGHT = 1, DIR_DOWN = 2, DIR_LEFT = 3 };

typedef struct {
    int pipes;
    int fps;
    int steady;
    int limit;
    int random_start;
    int bold;
    int color;
    int keep_style;
    int colors[NUM_COLORS];
    int n_colors;
    int pipe_types[NUM_SETS];
    int n_pipe_types;
} PipeConfig;

typedef struct {
    int  x, y;
    int  direction;
    int  pipe_type;
    int  color;
    WORD attr;
} Pipe;

/* ------------------------------------------------------------------ */
/* renderer.py - the 10 pipe character sets                            */
/* Written as \u escapes so the file stays pure ASCII: MSVC mis-reads   */
/* raw UTF-8 source without a BOM.                                     */
/* ------------------------------------------------------------------ */

static const wchar_t PIPE_SETS[NUM_SETS][SET_LEN] = {
    /* 0 HEAVY  */ { 0x2503,0x250F,L' ',0x2513,0x251B,0x2501,0x2513,L' ',
                     L' ',0x2517,0x2503,0x251B,0x2517,L' ',0x250F,0x2501 },
    /* 1 CURVED */ { 0x2502,0x256D,L' ',0x256E,0x256F,0x2500,0x256E,L' ',
                     L' ',0x2570,0x2502,0x256F,0x2570,L' ',0x256D,0x2500 },
    /* 2 LIGHT  */ { 0x2502,0x250C,L' ',0x2510,0x2518,0x2500,0x2510,L' ',
                     L' ',0x2514,0x2502,0x2518,0x2514,L' ',0x250C,0x2500 },
    /* 3 DOUBLE */ { 0x2551,0x2554,L' ',0x2557,0x255D,0x2550,0x2557,L' ',
                     L' ',0x255A,0x2551,0x255D,0x255A,L' ',0x2554,0x2550 },
    /* 4 KNOBBY */ { L'|',L'+',L' ',L'+',L'+',L'-',L'+',L' ',
                     L' ',L'+',L'|',L'+',L'+',L' ',L'+',L'-' },
    /* 5 ANGLES */ { L'|',L'/',L' ',L'\\',L' ',L'/',L'-',L'\\',
                     L' ',L' ',L'\\',L'|',L'/',L'\\',L' ',L'/' },
    /* 6 DOTS   */ { L'.',L'o',L' ',L'.',L'.',L'.',L'.',L' ',
                     L' ',L'.',L'.',L'.',L'.',L' ',L'.',L'o' },
    /* 7 DOTS_O */ { L'.',L'o',L' ',L'o',L'o',L'.',L'o',L' ',
                     L' ',L'o',L'.',L'o',L'o',L' ',L'o',L'.' },
    /* 8 SLASH  */ { L'-',L'\\',L' ',L'/',L'\\',L'|',L'/',L' ',
                     L' ',L'/',L'-',L'\\',L'/',L' ',L'\\',L'|' },
    /* 9 MIXED  */ { 0x257F,0x250D,L' ',0x2511,0x251A,0x257C,0x2512,L' ',
                     L' ',0x2515,0x257D,0x2519,0x2516,L' ',0x250E,0x257E }
};

/* curses colour index -> Win32 foreground bits */
static const WORD COLOR_MAP[NUM_COLORS] = {
    0,                                                  /* 0 black   */
    FOREGROUND_RED,                                     /* 1 red     */
    FOREGROUND_GREEN,                                   /* 2 green   */
    FOREGROUND_RED | FOREGROUND_GREEN,                  /* 3 yellow  */
    FOREGROUND_BLUE,                                    /* 4 blue    */
    FOREGROUND_RED | FOREGROUND_BLUE,                   /* 5 magenta */
    FOREGROUND_GREEN | FOREGROUND_BLUE,                 /* 6 cyan    */
    FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE /* 7 white   */
};

/* ------------------------------------------------------------------ */
/* small helpers                                                       */
/* ------------------------------------------------------------------ */

/* Python's % : result always takes the sign of the divisor. C's % does not. */
static int pymod(int a, int b)
{
    int m;
    if (b == 0) return 0;
    m = a % b;
    if (m != 0 && ((m < 0) != (b < 0))) m += b;
    return m;
}

/* uniform integer in [0, n) */
static int rnd_below(int n)
{
    if (n <= 1) return 0;
    return (int)(((double)rand() / ((double)RAND_MAX + 1.0)) * n);
}

static int clampi(int v, int lo, int hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

/* ------------------------------------------------------------------ */
/* config.py                                                           */
/* ------------------------------------------------------------------ */

static PipeConfig default_config(void)
{
    PipeConfig c;
    int i;

    memset(&c, 0, sizeof(c));
    c.pipes        = 1;
    c.fps          = 75;
    c.steady       = 13;
    c.limit        = 2000;
    c.random_start = 0;
    c.bold         = 1;
    c.color        = 1;
    c.keep_style   = 0;

    for (i = 0; i < 7; i++) c.colors[i] = i + 1;   /* 1..7 */
    c.colors[7]    = 0;                            /* then 0 */
    c.n_colors     = 8;

    c.pipe_types[0] = 0;
    c.n_pipe_types  = 1;
    return c;
}

/* %LOCALAPPDATA%\pipes-py - same location the Python version uses. */
static int get_config_dir(char *out, size_t n)
{
    const char *base = getenv("LOCALAPPDATA");
    char fallback[MAX_PATH];

    if (base == NULL || base[0] == '\0') {
        const char *home = getenv("USERPROFILE");
        if (home == NULL || home[0] == '\0') return 0;
        if (_snprintf(fallback, sizeof(fallback),
                      "%s\\AppData\\Local", home) < 0) return 0;
        fallback[sizeof(fallback) - 1] = '\0';
        base = fallback;
    }
    if (_snprintf(out, n, "%s\\pipes-py", base) < 0) return 0;
    out[n - 1] = '\0';
    return 1;
}

static int get_config_file(char *out, size_t n)
{
    char dir[MAX_PATH];
    if (!get_config_dir(dir, sizeof(dir))) return 0;
    if (_snprintf(out, n, "%s\\config.json", dir) < 0) return 0;
    out[n - 1] = '\0';
    return 1;
}

/* --- minimal JSON reading (only what this config file contains) ---- */

/* Returns a pointer just past the ':' following "key", or NULL. */
static const char *json_find(const char *json, const char *key)
{
    char token[64];
    const char *p;

    if (_snprintf(token, sizeof(token), "\"%s\"", key) < 0) return NULL;
    token[sizeof(token) - 1] = '\0';

    p = strstr(json, token);
    if (p == NULL) return NULL;
    p = strchr(p, ':');
    if (p == NULL) return NULL;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    return p;
}

static void json_int(const char *json, const char *key, int *dst)
{
    const char *p = json_find(json, key);
    char *end;
    long v;

    if (p == NULL) return;
    v = strtol(p, &end, 10);
    if (end == p) return;                    /* not a number - keep default */
    if (v < INT_MIN || v > INT_MAX) return;
    *dst = (int)v;
}

static void json_bool(const char *json, const char *key, int *dst)
{
    const char *p = json_find(json, key);
    if (p == NULL) return;
    if (strncmp(p, "true", 4) == 0)       *dst = 1;
    else if (strncmp(p, "false", 5) == 0) *dst = 0;
}

static void json_int_array(const char *json, const char *key,
                           int *arr, int cap, int *count)
{
    const char *p = json_find(json, key);
    int n = 0;
    char *end;

    if (p == NULL || *p != '[') return;
    p++;
    while (*p != '\0' && *p != ']' && n < cap) {
        long v;
        while (*p == ' ' || *p == ',' || *p == '\n' ||
               *p == '\r' || *p == '\t') p++;
        if (*p == ']' || *p == '\0') break;
        v = strtol(p, &end, 10);
        if (end == p) return;                /* malformed - discard */
        arr[n++] = (int)v;
        p = end;
    }
    if (n > 0) *count = n;
}

static void load_config(PipeConfig *cfg)
{
    char path[MAX_PATH];
    FILE *f;
    long size;
    char *buf;
    size_t got;

    if (!get_config_file(path, sizeof(path))) return;

    f = fopen(path, "rb");
    if (f == NULL) return;                   /* no file -> defaults */

    if (fseek(f, 0, SEEK_END) != 0)  { fclose(f); return; }
    size = ftell(f);
    if (size <= 0 || size > 1024 * 1024) { fclose(f); return; }
    if (fseek(f, 0, SEEK_SET) != 0)  { fclose(f); return; }

    buf = (char *)malloc((size_t)size + 1);
    if (buf == NULL) { fclose(f); return; }

    got = fread(buf, 1, (size_t)size, f);
    fclose(f);
    buf[got] = '\0';

    json_int(buf,  "pipes",        &cfg->pipes);
    json_int(buf,  "fps",          &cfg->fps);
    json_int(buf,  "steady",       &cfg->steady);
    json_int(buf,  "limit",        &cfg->limit);
    json_bool(buf, "random_start", &cfg->random_start);
    json_bool(buf, "bold",         &cfg->bold);
    json_bool(buf, "color",        &cfg->color);
    json_bool(buf, "keep_style",   &cfg->keep_style);
    json_int_array(buf, "colors",     cfg->colors,     NUM_COLORS, &cfg->n_colors);
    json_int_array(buf, "pipe_types", cfg->pipe_types, NUM_SETS,   &cfg->n_pipe_types);

    free(buf);

    /* A hand-edited config must not be able to crash us. */
    cfg->pipes  = clampi(cfg->pipes, 1, MAX_PIPES);
    cfg->fps    = clampi(cfg->fps, 20, 100);
    cfg->steady = clampi(cfg->steady, 3, 15);
    if (cfg->limit < 0) cfg->limit = 0;
    {
        int i;
        for (i = 0; i < cfg->n_colors; i++)
            cfg->colors[i] = pymod(cfg->colors[i], NUM_COLORS);
        for (i = 0; i < cfg->n_pipe_types; i++)
            cfg->pipe_types[i] = pymod(cfg->pipe_types[i], NUM_SETS);
    }
}

static void save_config(const PipeConfig *cfg)
{
    char dir[MAX_PATH];
    char path[MAX_PATH];
    FILE *f;
    int i;

    if (!get_config_dir(dir, sizeof(dir))) return;
    if (!get_config_file(path, sizeof(path))) return;

    if (!CreateDirectoryA(dir, NULL) &&
        GetLastError() != ERROR_ALREADY_EXISTS) {
        return;                              /* mirrors the Python except OSError: pass */
    }

    f = fopen(path, "w");
    if (f == NULL) return;

    fprintf(f, "{\n");
    fprintf(f, "  \"pipes\": %d,\n", cfg->pipes);
    fprintf(f, "  \"fps\": %d,\n", cfg->fps);
    fprintf(f, "  \"steady\": %d,\n", cfg->steady);
    fprintf(f, "  \"limit\": %d,\n", cfg->limit);
    fprintf(f, "  \"random_start\": %s,\n", cfg->random_start ? "true" : "false");
    fprintf(f, "  \"bold\": %s,\n",         cfg->bold ? "true" : "false");
    fprintf(f, "  \"color\": %s,\n",        cfg->color ? "true" : "false");
    fprintf(f, "  \"keep_style\": %s,\n",   cfg->keep_style ? "true" : "false");

    fprintf(f, "  \"colors\": [");
    for (i = 0; i < cfg->n_colors; i++)
        fprintf(f, "%s%d", i ? ", " : "", cfg->colors[i]);
    fprintf(f, "],\n");

    fprintf(f, "  \"pipe_types\": [");
    for (i = 0; i < cfg->n_pipe_types; i++)
        fprintf(f, "%s%d", i ? ", " : "", cfg->pipe_types[i]);
    fprintf(f, "]\n}\n");

    if (fclose(f) != 0)
        fprintf(stderr, "warning: could not write %s\n", path);
}

/* ------------------------------------------------------------------ */
/* renderer.py                                                         */
/* ------------------------------------------------------------------ */

typedef struct {
    HANDLE hOut;
    int    width, height;
    SHORT  left, top;
    WORD   saved_attr;
    CONSOLE_CURSOR_INFO saved_cursor;
    WORD   color_attr[NUM_COLORS];
    const PipeConfig *cfg;
} Renderer;

static Renderer *g_renderer = NULL;          /* for the Ctrl+C handler */

static void renderer_init_colors(Renderer *r)
{
    int i;
    for (i = 0; i < NUM_COLORS; i++) {
        WORD fg;
        if (!r->cfg->color) {                /* == curses.A_NORMAL */
            r->color_attr[i] = r->saved_attr;
            continue;
        }
        fg = COLOR_MAP[i];
        if (r->cfg->bold) fg |= FOREGROUND_INTENSITY;
        /* keep the user's background colour */
        r->color_attr[i] = (WORD)(fg | (r->saved_attr & 0x00F0));
    }
}

static WORD renderer_color_attr(const Renderer *r, int color)
{
    return r->color_attr[pymod(color, NUM_COLORS)];
}

static int renderer_update_size(Renderer *r)
{
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (!GetConsoleScreenBufferInfo(r->hOut, &csbi)) return 0;
    r->left   = csbi.srWindow.Left;
    r->top    = csbi.srWindow.Top;
    r->width  = csbi.srWindow.Right  - csbi.srWindow.Left + 1;
    r->height = csbi.srWindow.Bottom - csbi.srWindow.Top  + 1;
    if (r->width < 1)  r->width  = 1;
    if (r->height < 1) r->height = 1;
    return 1;
}

static void renderer_clear(Renderer *r)
{
    COORD pos;
    DWORD written;
    int y;

    for (y = 0; y < r->height; y++) {
        pos.X = r->left;
        pos.Y = (SHORT)(r->top + y);
        if (!FillConsoleOutputCharacterW(r->hOut, L' ',
                                         (DWORD)r->width, pos, &written)) return;
        if (!FillConsoleOutputAttribute(r->hOut, r->saved_attr,
                                        (DWORD)r->width, pos, &written)) return;
    }
}

static int renderer_init(Renderer *r, const PipeConfig *cfg)
{
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    CONSOLE_CURSOR_INFO ci;

    memset(r, 0, sizeof(*r));
    r->cfg  = cfg;
    r->hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    if (r->hOut == INVALID_HANDLE_VALUE || r->hOut == NULL) {
        fprintf(stderr, "error: no console output handle (%lu)\n",
                (unsigned long)GetLastError());
        return 0;
    }
    if (!GetConsoleScreenBufferInfo(r->hOut, &csbi)) {
        fprintf(stderr, "error: not attached to a real console - "
                        "run pipes.exe from cmd.exe or Windows Terminal, "
                        "not through a pipe.\n");
        return 0;
    }
    r->saved_attr = csbi.wAttributes;

    if (GetConsoleCursorInfo(r->hOut, &r->saved_cursor)) {
        ci = r->saved_cursor;
        ci.bVisible = FALSE;                 /* == curses.curs_set(0) */
        if (!SetConsoleCursorInfo(r->hOut, &ci))
            fprintf(stderr, "warning: could not hide the cursor\n");
    } else {
        r->saved_cursor.dwSize   = 25;
        r->saved_cursor.bVisible = TRUE;
    }

    if (!renderer_update_size(r)) return 0;
    renderer_init_colors(r);
    renderer_clear(r);
    return 1;
}

static void renderer_restore(Renderer *r)
{
    if (r == NULL || r->hOut == NULL || r->hOut == INVALID_HANDLE_VALUE) return;
    SetConsoleCursorInfo(r->hOut, &r->saved_cursor);
    SetConsoleTextAttribute(r->hOut, r->saved_attr);
    renderer_clear(r);
    {
        COORD home;
        home.X = r->left;
        home.Y = r->top;
        SetConsoleCursorPosition(r->hOut, home);
    }
}

/* One glyph, no cursor movement -> no scrolling at the bottom-right cell.
   Out-of-range writes are ignored, matching the Python
   `with contextlib.suppress(curses.error)`. */
static void renderer_draw(Renderer *r, int x, int y, wchar_t ch, WORD attr)
{
    COORD pos;
    DWORD written;

    if (x < 0 || y < 0 || x >= r->width || y >= r->height) return;
    pos.X = (SHORT)(r->left + x);
    pos.Y = (SHORT)(r->top + y);
    if (!WriteConsoleOutputCharacterW(r->hOut, &ch, 1, pos, &written)) return;
    if (!WriteConsoleOutputAttribute(r->hOut, &attr, 1, pos, &written)) return;
}

static void renderer_draw_pipe(Renderer *r, const Pipe *p,
                               int old_dir, int new_dir)
{
    int index = p->pipe_type * SET_LEN + old_dir * 4 + new_dir;
    wchar_t ch;

    if (index < 0 || index >= NUM_SETS * SET_LEN) ch = L'?';
    else ch = PIPE_SETS[index / SET_LEN][index % SET_LEN];

    renderer_draw(r, p->x, p->y, ch, p->attr);
}

/* ------------------------------------------------------------------ */
/* pipes.py                                                            */
/* ------------------------------------------------------------------ */

typedef struct {
    Renderer   *r;
    PipeConfig *cfg;
    Pipe       *pipes;
    int         n_pipes;
    int         width, height;
    int         count;
    UINT        delay_ms;
} PipesScreen;

static int pipes_init(PipesScreen *ps, Renderer *r, PipeConfig *cfg)
{
    int i;

    ps->r        = r;
    ps->cfg      = cfg;
    ps->n_pipes  = cfg->pipes;
    ps->width    = r->width;
    ps->height   = r->height;
    ps->count    = 0;
    ps->delay_ms = (UINT)(1000 / (cfg->fps > 0 ? cfg->fps : 1));

    ps->pipes = (Pipe *)malloc(sizeof(Pipe) * (size_t)ps->n_pipes);
    if (ps->pipes == NULL) {
        fprintf(stderr, "error: out of memory for %d pipes\n", ps->n_pipes);
        return 0;
    }

    for (i = 0; i < ps->n_pipes; i++) {
        Pipe *p = &ps->pipes[i];
        p->direction = cfg->random_start ? rnd_below(4) : DIR_UP;
        p->x = cfg->random_start ? rnd_below(r->width)  : r->width  / 2;
        p->y = cfg->random_start ? rnd_below(r->height) : r->height / 2;
        p->pipe_type = cfg->pipe_types[rnd_below(cfg->n_pipe_types)];
        p->color     = cfg->colors[rnd_below(cfg->n_colors)];
        p->attr      = renderer_color_attr(r, p->color);
    }
    return 1;
}

static void pipes_update_colors(PipesScreen *ps)
{
    int i;
    for (i = 0; i < ps->n_pipes; i++)
        ps->pipes[i].attr = renderer_color_attr(ps->r, ps->pipes[i].color);
}

/* returns 0 when the user wants to quit */
static int pipes_handle_key(PipesScreen *ps, int key)
{
    PipeConfig *cfg = ps->cfg;
    int c = (key >= 0 && key <= 255) ? toupper(key) : 0;

    if (c == 'P' && cfg->steady < 15) {
        cfg->steady++;
    } else if (c == 'O' && cfg->steady > 3) {
        cfg->steady--;
    } else if (c == 'F' && cfg->fps < 100) {
        cfg->fps++;
        ps->delay_ms = (UINT)(1000 / cfg->fps);
    } else if (c == 'D' && cfg->fps > 20) {
        cfg->fps--;
        ps->delay_ms = (UINT)(1000 / cfg->fps);
    } else if (c == 'B') {
        cfg->bold = !cfg->bold;
        renderer_init_colors(ps->r);
        pipes_update_colors(ps);
    } else if (c == 'C') {
        cfg->color = !cfg->color;
        renderer_init_colors(ps->r);
        pipes_update_colors(ps);
    } else if (c == 'K') {
        cfg->keep_style = !cfg->keep_style;
    } else if (c == '?' || key == 27) {      /* ESC */
        return 0;
    }
    return 1;
}

static void pipes_move(PipesScreen *ps)
{
    int i;
    PipeConfig *cfg = ps->cfg;

    for (i = 0; i < ps->n_pipes; i++) {
        Pipe *p = &ps->pipes[i];
        int x = p->x, y = p->y;
        int old_dir = p->direction;
        int new_dir = old_dir;

        if (old_dir % 2) x += -old_dir + 2;  /* RIGHT: +1, LEFT: -1 */
        else             y += old_dir - 1;   /* UP: -1,   DOWN: +1  */

        if (x < 0 || x >= ps->width || y < 0 || y >= ps->height) {
            if (!cfg->keep_style) {
                p->pipe_type = cfg->pipe_types[rnd_below(cfg->n_pipe_types)];
                p->color     = cfg->colors[rnd_below(cfg->n_colors)];
                p->attr      = renderer_color_attr(ps->r, p->color);
            }
            x = pymod(x, ps->width);
            y = pymod(y, ps->height);
        }

        if (rnd_below(cfg->steady) <= 1) {
            int turn = 2 * rnd_below(2) - 1; /* -1 or +1 */
            new_dir = pymod(old_dir + turn, 4);
        }

        renderer_draw_pipe(ps->r, p, old_dir, new_dir);

        p->x = x;
        p->y = y;
        p->direction = new_dir;
    }
}

/* returns 0 when the animation should stop */
static int pipes_update(PipesScreen *ps)
{
    if (_kbhit()) {
        int key = _getch();
        if (key == 0 || key == 224) {        /* extended key: eat the 2nd byte */
            (void)_getch();
            key = -1;
        }
        if (key != -1 && !pipes_handle_key(ps, key)) return 0;
    }

    if (!renderer_update_size(ps->r)) return 0;

    if (ps->r->width != ps->width || ps->r->height != ps->height) {
        ps->width  = ps->r->width;
        ps->height = ps->r->height;
        renderer_clear(ps->r);
    }

    pipes_move(ps);

    ps->count += ps->n_pipes;
    if (ps->cfg->limit > 0 && ps->count >= ps->cfg->limit) {
        renderer_clear(ps->r);
        ps->count = 0;
    }

    Sleep(ps->delay_ms);
    return 1;
}

/* ------------------------------------------------------------------ */
/* __main__.py                                                         */
/* ------------------------------------------------------------------ */

static void usage(void)
{
    printf(
"usage: pipes [-h] [-p PIPES] [-f FPS] [-s STEADY] [-r LIMIT] [-R] [-B] [-C]\n"
"             [-P {0..9}] [-K] [-S] [-v]\n"
"\n"
"Basically pipes.sh but rewritten in C\n"
"\n"
"options:\n"
"  -h, --help          show this help message and exit\n"
"  -p, --pipes N       number of pipes\n"
"  -f, --fps N         frames per second (20-100)\n"
"  -s, --steady N      steadiness (5-15)\n"
"  -r, --limit N       character limit before reset\n"
"  -R, --random        random start\n"
"  -B, --no-bold       disable bold\n"
"  -C, --no-color      disable color\n"
"  -P, --pipe-style N  change pipe style (0-9)\n"
"  -K, --keep-style    keep style on wrap\n"
"  -S, --save-config   save current settings as default\n"
"  -v, --version       show program's version number and exit\n"
"\n"
"runtime keys: p/o steadiness, f/d fps, b bold, c color, k keep-style,\n"
"              ESC or ? to quit\n");
}

/* pulls the value for an option, supporting "-p 5", "--pipes 5", "--pipes=5" */
static int arg_value(int argc, char **argv, int *i, const char *eq, int *out)
{
    const char *s;
    char *end;
    long v;

    if (eq != NULL) {
        s = eq;
    } else {
        if (*i + 1 >= argc) {
            fprintf(stderr, "error: %s expects a value\n", argv[*i]);
            return 0;
        }
        (*i)++;
        s = argv[*i];
    }
    v = strtol(s, &end, 10);
    if (end == s || *end != '\0') {
        fprintf(stderr, "error: '%s' is not an integer\n", s);
        return 0;
    }
    *out = (int)v;
    return 1;
}

/* 1 = run, 0 = exit cleanly, -1 = exit with error */
static int parse_args(int argc, char **argv, PipeConfig *cfg, int *do_save)
{
    int i;

    for (i = 1; i < argc; i++) {
        char *a = argv[i];
        char *eq = NULL;
        int v;

        if (strncmp(a, "--", 2) == 0) {
            eq = strchr(a, '=');
            if (eq != NULL) { *eq = '\0'; eq++; }
        }

        if (!strcmp(a, "-h") || !strcmp(a, "--help")) {
            usage();
            return 0;
        } else if (!strcmp(a, "-v") || !strcmp(a, "--version")) {
            printf("pipes-c v%s\n", APP_VERSION);
            return 0;
        } else if (!strcmp(a, "-p") || !strcmp(a, "--pipes")) {
            if (!arg_value(argc, argv, &i, eq, &v)) return -1;
            cfg->pipes = clampi(v, 1, MAX_PIPES);
        } else if (!strcmp(a, "-f") || !strcmp(a, "--fps")) {
            if (!arg_value(argc, argv, &i, eq, &v)) return -1;
            cfg->fps = clampi(v, 20, 100);
        } else if (!strcmp(a, "-s") || !strcmp(a, "--steady")) {
            if (!arg_value(argc, argv, &i, eq, &v)) return -1;
            cfg->steady = clampi(v, 5, 15);
        } else if (!strcmp(a, "-r") || !strcmp(a, "--limit")) {
            if (!arg_value(argc, argv, &i, eq, &v)) return -1;
            cfg->limit = v < 0 ? 0 : v;
        } else if (!strcmp(a, "-P") || !strcmp(a, "--pipe-style")) {
            if (!arg_value(argc, argv, &i, eq, &v)) return -1;
            if (v < 0 || v > 9) {
                fprintf(stderr, "error: --pipe-style must be 0..9\n");
                return -1;
            }
            cfg->pipe_types[0] = v;
            cfg->n_pipe_types  = 1;
        } else if (!strcmp(a, "-R") || !strcmp(a, "--random")) {
            cfg->random_start = 1;
        } else if (!strcmp(a, "-B") || !strcmp(a, "--no-bold")) {
            cfg->bold = 0;
        } else if (!strcmp(a, "-C") || !strcmp(a, "--no-color")) {
            cfg->color = 0;
        } else if (!strcmp(a, "-K") || !strcmp(a, "--keep-style")) {
            cfg->keep_style = 1;
        } else if (!strcmp(a, "-S") || !strcmp(a, "--save-config")) {
            *do_save = 1;
        } else {
            fprintf(stderr, "error: unrecognized argument: %s\n", a);
            usage();
            return -1;
        }
    }
    return 1;
}

static BOOL WINAPI ctrl_handler(DWORD type)
{
    (void)type;
    renderer_restore(g_renderer);            /* leave the console usable */
    ExitProcess(0);
    return TRUE;
}

int main(int argc, char **argv)
{
    PipeConfig cfg;
    Renderer   renderer;
    PipesScreen screen;
    int do_save = 0;
    int rc;

    cfg = default_config();
    load_config(&cfg);

    rc = parse_args(argc, argv, &cfg, &do_save);
    if (rc == 0)  return 0;
    if (rc < 0)   return 2;

    if (do_save) save_config(&cfg);

    srand((unsigned)(GetTickCount() ^ (DWORD)time(NULL)));

    if (!renderer_init(&renderer, &cfg)) return 1;
    g_renderer = &renderer;

    if (!SetConsoleCtrlHandler(ctrl_handler, TRUE))
        fprintf(stderr, "warning: Ctrl+C will not restore the console\n");

    timeBeginPeriod(1);                      /* Sleep() accurate to ~1 ms */

    if (!pipes_init(&screen, &renderer, &cfg)) {
        timeEndPeriod(1);
        renderer_restore(&renderer);
        return 1;
    }

    while (pipes_update(&screen)) {
        /* loop until ESC / ? / Ctrl+C */
    }

    timeEndPeriod(1);
    free(screen.pipes);
    renderer_restore(&renderer);
    g_renderer = NULL;
    return 0;
}
