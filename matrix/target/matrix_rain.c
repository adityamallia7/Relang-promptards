/*
 * matrix_rain.c - C port of dant89/matrix-digital-rain-python (rain.py).
 *
 * Faithful reimplementation of the Python `Matrix` class: a console
 * "Matrix digital rain" printed one row at a time. Each column is a small
 * state machine:
 *      state 1 : active  -> print a random green character
 *      state 2 : "head"  -> print a random WHITE character, then drop to 1
 *      state 0 : blank   -> print a space
 * Per row, an active column has a 1/30 chance to die (->0), and a blank
 * column has a 1/60 chance to spawn a new head (->2). Exactly mirrors the
 * original startMatrix() loop.
 *
 * Customisations (same defaults as the Python version), given as optional
 * positional args:
 *      matrix_rain [screen_width=150] [line_count=750] [line_speed=0.1]
 *
 * Build:
 *      Linux/macOS/WSL : gcc -O2 -o matrix_rain matrix_rain.c
 *      Windows (MinGW) : gcc -O2 -o matrix_rain.exe matrix_rain.c
 *      Windows (MSVC)  : cl matrix_rain.c
 *
 * Quit early with Ctrl-C; the terminal colour is restored on exit.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>

/* ---- character set + colours, extracted verbatim from rain.py ---- */
static const char *MATRIX_CHARS[] = {
    "- ", "* ", "% ", "& ", "# ", "@ ", "1 ", "2 ",
    "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ", "0 ",
    "\xe3\x82\xa2", "\xe3\x82\xa3", "\xe3\x82\xa4", "\xe3\x82\xa5", "\xe3\x82\xa6", "\xe3\x82\xa7", "\xe3\x82\xa8", "\xe3\x82\xa9",
    "\xe3\x82\xaa", "\xe3\x82\xab", "\xe3\x82\xac", "\xe3\x82\xad", "\xe3\x82\xae", "\xe3\x82\xaf", "\xe3\x82\xb0", "\xe3\x82\xb1",
    "\xe3\x82\xb2", "\xe3\x82\xb3", "\xe3\x82\xb4", "\xe3\x82\xb5", "\xe3\x82\xb6", "\xe3\x82\xb7", "\xe3\x82\xb8", "\xe3\x82\xb9",
    "\xe3\x82\xba", "\xe3\x82\xbb", "\xe3\x82\xbc", "\xe3\x82\xbd", "\xe3\x82\xbe", "\xe3\x82\xbf", "\xe3\x83\x80", "\xe3\x83\x81",
    "\xe3\x83\x82", "\xe3\x83\x83", "\xe3\x83\x84", "\xe3\x83\x85", "\xe3\x83\x86",
};
static const int MATRIX_CHARS_COUNT = 53;

/* 256-colour green shades used for the trailing characters. */
static const char *GREEN[] = { "\033[38;5;22m", "\033[38;5;28m" };
static const int   GREEN_COUNT = 2;
/* Colour 15 = bright white: the leading "head" character. */
static const char *WHITE = "\033[38;5;15m";
static const char *RESET = "\033[0m";

/* Longest thing written per column: colour prefix (<=10) + char (<=3). */
#define PER_COL_MAX 16

/* ---- platform: UTF-8 + ANSI setup, and sub-second sleep ---- */
#ifdef _WIN32
#include <windows.h>
static void platform_init(void) {
    SetConsoleOutputCP(CP_UTF8);                 /* so katakana render */
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD mode = 0;
    if (h != INVALID_HANDLE_VALUE && GetConsoleMode(h, &mode))
        SetConsoleMode(h, mode | 0x0004);        /* ENABLE_VIRTUAL_TERMINAL_PROCESSING */
}
static void sleep_seconds(double s) {
    if (s > 0.0) Sleep((DWORD)(s * 1000.0 + 0.5));
}
#else
static void platform_init(void) { /* nothing needed on POSIX */ }
static void sleep_seconds(double s) {
    if (s <= 0.0) return;
    struct timespec ts;
    ts.tv_sec  = (time_t)s;
    ts.tv_nsec = (long)((s - (double)ts.tv_sec) * 1e9);
    if (ts.tv_nsec < 0) ts.tv_nsec = 0;
    if (ts.tv_nsec > 999999999L) ts.tv_nsec = 999999999L;
    nanosleep(&ts, NULL);
}
#endif

/* ---- clean exit: restore colour so the shell isn't left green ---- */
static void restore_terminal(void) {
    fputs(RESET, stdout);
    fflush(stdout);
}
static volatile sig_atomic_t g_stop = 0;
static void on_sigint(int sig) {
    (void)sig;
    g_stop = 1;               /* checked by the main loop; cleanup runs there */
}

/* Inclusive random int in [lo, hi], matching Python's random.randint. */
static int randint(int lo, int hi) {
    return lo + rand() % (hi - lo + 1);
}

/* Parse a positive-ish long from argv with full validation. */
static int parse_long(const char *s, long lo, long hi, long *out) {
    char *end = NULL;
    errno = 0;
    long v = strtol(s, &end, 10);
    if (end == s || *end != '\0') return -1;      /* not a number */
    if (errno == ERANGE || v < lo || v > hi) return -1;
    *out = v;
    return 0;
}
static int parse_double(const char *s, double lo, double hi, double *out) {
    char *end = NULL;
    errno = 0;
    double v = strtod(s, &end);
    if (end == s || *end != '\0') return -1;
    if (errno == ERANGE || v < lo || v > hi) return -1;
    *out = v;
    return 0;
}

int main(int argc, char **argv) {
    long   screen_width = 150;
    long   line_count   = 750;
    double line_speed   = 0.1;

    /* --- argument handling with clear error messages --- */
    if (argc > 1 && (strcmp(argv[1], "-h") == 0 || strcmp(argv[1], "--help") == 0)) {
        fprintf(stderr,
            "Usage: %s [screen_width] [line_count] [line_speed]\n"
            "  screen_width  columns of rain      (default 150, range 1-100000)\n"
            "  line_count    rows to print        (default 750, 0 = a lot)\n"
            "  line_speed    seconds between rows  (default 0.1, range 0-3600)\n",
            argv[0]);
        return 0;
    }
    if (argc > 1 && parse_long(argv[1], 1, 100000, &screen_width) != 0) {
        fprintf(stderr, "error: screen_width must be an integer in 1..100000\n");
        return 1;
    }
    if (argc > 2 && parse_long(argv[2], 0, INT_MAX, &line_count) != 0) {
        fprintf(stderr, "error: line_count must be an integer in 0..%d\n", INT_MAX);
        return 1;
    }
    if (argc > 3 && parse_double(argv[3], 0.0, 3600.0, &line_speed) != 0) {
        fprintf(stderr, "error: line_speed must be a number in 0..3600 (seconds)\n");
        return 1;
    }
    if (argc > 4) {
        fprintf(stderr, "error: too many arguments (see --help)\n");
        return 1;
    }

    /* --- allocate the per-column state and the line buffer --- */
    /* overflow guard on the buffer size before multiplying */
    if ((size_t)screen_width > (SIZE_MAX - 2) / PER_COL_MAX) {
        fprintf(stderr, "error: screen_width too large\n");
        return 1;
    }
    int *state = malloc((size_t)screen_width * sizeof(int));
    size_t buf_cap = (size_t)screen_width * PER_COL_MAX + 2;   /* + '\n' + '\0' */
    char *line = malloc(buf_cap);
    if (!state || !line) {
        fprintf(stderr, "error: out of memory\n");
        free(state); free(line);
        return 1;
    }

    platform_init();
    signal(SIGINT, on_sigint);
    srand((unsigned)time(NULL));

    for (long i = 0; i < screen_width; i++) state[i] = 1;   /* _setScreenLineArray */

    /* --- the main loop: one printed row per iteration --- */
    for (long l = 0; l < line_count && !g_stop; l++) {
        size_t pos = 0;

        for (long m = 0; m < screen_width; m++) {
            int n = state[m];
            const char *color;
            const char *glyph;

            if (n == 1 || n == 2) {
                if (n == 2) {
                    color = WHITE;                            /* bright head */
                    state[m] = 1;
                } else {
                    color = GREEN[randint(0, GREEN_COUNT - 1)];
                }
                glyph = MATRIX_CHARS[randint(0, MATRIX_CHARS_COUNT - 1)];
                if (randint(1, 30) == 1) state[m] = 0;        /* column dies */
            } else {                                          /* n == 0: blank */
                color = GREEN[randint(0, GREEN_COUNT - 1)];
                glyph = " ";
                if (randint(1, 60) == 1) state[m] = 2;        /* new head */
            }

            /* append colour + glyph; guaranteed to fit in PER_COL_MAX */
            size_t cl = strlen(color), gl = strlen(glyph);
            if (pos + cl + gl + 2 > buf_cap) break;           /* defensive */
            memcpy(line + pos, color, cl); pos += cl;
            memcpy(line + pos, glyph, gl); pos += gl;
        }

        line[pos++] = '\n';
        line[pos]   = '\0';
        fputs(line, stdout);
        fflush(stdout);                                       /* show before sleeping */
        sleep_seconds(line_speed);
    }

    restore_terminal();
    free(state);
    free(line);
    return 0;
}
