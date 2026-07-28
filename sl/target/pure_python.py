import random

# D51 Constants
D51HEIGHT = 10
D51FUNNEL = 7
D51LENGTH = 83
D51PATTERNS = 6

D51STR1 = "      ====        ________                ___________ "
D51STR2 = "  _D _|  |_______/        \\__I_I_____===__|_________| "
D51STR3 = "   |(_)---  |   H\\________/ |   |        =|___ ___|   "
D51STR4 = "   /     |  |   H  |  |     |   |         ||_| |_||   "
D51STR5 = "  |      |  |   H  |__--------------------| [___] |   "
D51STR6 = "  | ________|___H__/__|_____/[][]~\\_______|       |   "
D51STR7 = "  |/ |   |-----------I_____I [][] []  D   |=======|__ "

D51WHL11 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL12 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL13 = "  \\_/      \\O=====O=====O=====O_/      \\_/            "

D51WHL21 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL22 = " |/-=|___|=O=====O=====O=====O   |_____/~\\___/        "
D51WHL23 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL31 = "__/ =| o |=-O=====O=====O=====O \\ ____Y___________|__ "
D51WHL32 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL33 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL41 = "__/ =| o |=-~O=====O=====O=====O\\ ____Y___________|__ "
D51WHL42 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL43 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL51 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL52 = " |/-=|___|=   O=====O=====O=====O|_____/~\\___/        "
D51WHL53 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL61 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL62 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL63 = "  \\_/      \\_O=====O=====O=====O/      \\_/            "

D51DEL = "                                                      "

COAL01 = "                              "
COAL02 = "                              "
COAL03 = "    _________________         "
COAL04 = "   _|                \\_____A  "
COAL05 = " =|                        |  "
COAL06 = " -|                        |  "
COAL07 = "__|________________________|_ "
COAL08 = "|__________________________|_ "
COAL09 = "   |_D__D__D_|  |_D__D__D_|   "
COAL10 = "    \\_/   \\_/    \\_/   \\_/    "

COALDEL = "                              "

# LOGO Constants
LOGOHEIGHT = 6
LOGOFUNNEL = 4
LOGOLENGTH = 84
LOGOPATTERNS = 6

LOGO1 = "     ++      +------ "
LOGO2 = "     ||      |+-+ |  "
LOGO3 = "   /---------|| | |  "
LOGO4 = "  + ========  +-+ |  "

LWHL11 = " _|--O========O~\\-+  "
LWHL12 = "//// \\_/      \\_/    "

LWHL21 = " _|--/O========O\\-+  "
LWHL22 = "//// \\_/      \\_/    "

LWHL31 = " _|--/~O========O-+  "
LWHL32 = "//// \\_/      \\_/    "

LWHL41 = " _|--/~\\------/~\\-+  "
LWHL42 = "//// \\_O========O    "

LWHL51 = " _|--/~\\------/~\\-+  "
LWHL52 = "//// \\O========O/    "

LWHL61 = " _|--/~\\------/~\\-+  "
LWHL62 = "//// O========O_/    "

LCOAL1 = "____                 "
LCOAL2 = "|   \\@@@@@@@@@@@     "
LCOAL3 = "|    \\@@@@@@@@@@@@@_ "
LCOAL4 = "|                  | "
LCOAL5 = "|__________________| "
LCOAL6 = "   (O)       (O)     "

LCAR1 = "____________________ "
LCAR2 = "|  ___ ___ ___ ___ | "
LCAR3 = "|  |_| |_| |_| |_| | "
LCAR4 = "|__________________| "
LCAR5 = "|__________________| "
LCAR6 = "   (O)        (O)    "

DELLN = "                     "

# C51 Constants
C51HEIGHT = 11
C51FUNNEL = 7
C51LENGTH = 87
C51PATTERNS = 6

C51DEL = "                                                       "

C51STR1 = "        ___                                            "
C51STR2 = "       _|_|_  _     __       __             ___________"
C51STR3 = "    D__/   \\_(_)___|  |__H__|  |_____I_Ii_()|_________|"
C51STR4 = "     | `---'   |:: `--'  H  `--'         |  |___ ___|  "
C51STR5 = "    +|~~~~~~~~++::~~~~~~~H~~+=====+~~~~~~|~~||_| |_||  "
C51STR6 = "    ||        | ::       H  +=====+      |  |::  ...|  "
C51STR7 = "|    | _______|_::-----------------[][]-----|       |  "

C51WH11 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH12 = "------'|oOo|=[]=-      ||      ||      |  ||=======_|__"
C51WH13 = "/~\\____|___|/~\\_|  O=======O=======O   |__|+-/~\\_|     "
C51WH14 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH21 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH22 = "------'|oOo|=[]=- O=======O=======O    |  ||=======_|__"
C51WH23 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH24 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH31 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH32 = "------'|oOo|==[]=- O=======O=======O   |  ||=======_|__"
C51WH33 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH34 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH41 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH42 = "------'|oOo|===[]=- O=======O=======O  |  ||=======_|__"
C51WH43 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH44 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH51 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH52 = "------'|oOo|===[]=-    ||      ||      |  ||=======_|__"
C51WH53 = "/~\\____|___|/~\\_|    O=======O=======O |__|+-/~\\_|     "
C51WH54 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH61 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH62 = "------'|oOo|==[]=-     ||      ||      |  ||=======_|__"
C51WH63 = "/~\\____|___|/~\\_|   O=======O=======O  |__|+-/~\\_|     "
C51WH64 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

SMOKEPTNS = 16
Smoke = [
    ["(   )", "(    )", "(    )", "(   )", "(  )", "(  )", "( )", "( )", "()", "()", "O", "O", "O", "O", "O", " "],
    ["(@@@)", "(@@@@)", "(@@@@)", "(@@@)", "(@@)", "(@@)", "(@)", "(@)", "@@", "@@", "@", "@", "@", "@", "@", " "]
]
Eraser = ["     ", "      ", "      ", "     ", "    ", "    ", "   ", "   ", "  ", "  ", " ", " ", " ", " ", " ", " "]
SMOKE_DY = [2, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SMOKE_DX = [-2, -1, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3]


class SLEngine:
    def __init__(self, cols, lines, arg=''):
        self.cols = cols
        self.lines = lines
        self.ACCIDENT = 0
        self.LOGO = 0
        self.FLY = 0
        self.C51 = 0
        self.DANCE = 0
        self.RAND = 0
        
        self.parse_arg(arg)
        
        if self.RAND == 1:
            self.ACCIDENT |= random.randint(0, 1)
            self.LOGO |= random.randint(0, 1)
            self.FLY |= random.randint(0, 1)
            self.C51 |= random.randint(0, 1)
            self.DANCE |= random.randint(0, 1)
            
        self.min_offset = self.count_min()
        self.N = -self.min_offset + self.cols - 1
        
        self.smoke_S = []
        self.smoke_sum = 0

    def parse_arg(self, arg):
        i = 0
        while i < len(arg):
            if arg[i] == '-':
                i += 1
                while i < len(arg) and arg[i] != '-':
                    c = arg[i]
                    if c == 'l': self.LOGO += 1
                    elif c == 'a': self.ACCIDENT = 1
                    elif c == 'F': self.FLY = 1
                    elif c == 'c': self.C51 = 1
                    elif c == 'd': self.DANCE = 1
                    elif c == 'r': self.RAND = 1
                    i += 1
            else:
                i += 1

    def count_min(self):
        offset = 21
        if self.LOGO >= 1:
            return -LOGOLENGTH - 1 - offset * (self.LOGO - 1)
        elif self.C51 == 1:
            return -C51LENGTH - 1
        else:
            return -D51LENGTH - 1

    def my_mvaddstr(self, canvas, y, x, s):
        if y < 0 or y >= self.lines:
            return
        idx = 0
        slen = len(s)
        while idx < slen and x < 0:
            idx += 1
            x += 1
        while idx < slen and x < self.cols:
            canvas[y][x] = s[idx]
            idx += 1
            x += 1

    def add_man(self, canvas, y, x):
        man = [["", "(O)"], ["Help!", "\\O/"]]
        for i in range(2):
            idx = (LOGOLENGTH + x) // 12 % 2
            self.my_mvaddstr(canvas, y + i, x, man[idx][i])

    def add_fdancer(self, canvas, y, x):
        fdancer = [["\\\\0", "/\\", "|\\"], ["0//", "/\\", "/|"]]
        Efdancer = [["   ", "  ", "  "], ["   ", "  ", "  "]]
        for i in range(3):
            idx = (LOGOLENGTH + x) // 12 % 2
            self.my_mvaddstr(canvas, y + i, x + 1, Efdancer[idx][i])
            self.my_mvaddstr(canvas, y + i, x, fdancer[idx][i])

    def add_mdancer(self, canvas, y, x):
        mdancer = [["_O_", " #", "/\\"], ["(0)", " #", "/\\"], ["(O_", " #", "/\\"]]
        Emdancer = [["   ", "  ", "  "], ["   ", "  ", "  "], ["   ", "  ", "  "]]
        for i in range(3):
            idx = (LOGOLENGTH + x) // 12 % 3
            self.my_mvaddstr(canvas, y + i, x + 1, Emdancer[idx][i])
            self.my_mvaddstr(canvas, y + i, x, mdancer[idx][i])

    def add_smoke(self, canvas, y, x):
        if x % 4 == 0:
            for s in self.smoke_S:
                self.my_mvaddstr(canvas, s['y'], s['x'], Eraser[s['ptrn']])
                s['y'] -= SMOKE_DY[s['ptrn']]
                s['x'] += SMOKE_DX[s['ptrn']]
                if s['ptrn'] < SMOKEPTNS - 1:
                    s['ptrn'] += 1
                self.my_mvaddstr(canvas, s['y'], s['x'], Smoke[s['kind']][s['ptrn']])
            self.my_mvaddstr(canvas, y, x, Smoke[self.smoke_sum % 2][0])
            self.smoke_S.append({'y': y, 'x': x, 'ptrn': 0, 'kind': self.smoke_sum % 2})
            self.smoke_sum += 1

    def add_sl(self, canvas, x):
        sl_patterns = [
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL11, LWHL12, DELLN],
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL21, LWHL22, DELLN],
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL31, LWHL32, DELLN],
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL41, LWHL42, DELLN],
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL51, LWHL52, DELLN],
            [LOGO1, LOGO2, LOGO3, LOGO4, LWHL61, LWHL62, DELLN],
        ]
        coal = [LCOAL1, LCOAL2, LCOAL3, LCOAL4, LCOAL5, LCOAL6, DELLN]
        car = [LCAR1, LCAR2, LCAR3, LCAR4, LCAR5, LCAR6, DELLN]

        py1 = py2 = py3 = 0
        offset = 21
        y = self.lines // 2 - 3

        if self.FLY == 1:
            y = (x // 6) + self.lines - (self.cols // 6) - LOGOHEIGHT
            py1, py2, py3 = 2, 4, 6

        for i in range(LOGOHEIGHT + 1):
            pat_idx = (LOGOLENGTH + offset * (self.LOGO - 1) + x) // 3 % LOGOPATTERNS
            self.my_mvaddstr(canvas, y + i, x, sl_patterns[pat_idx][i])
            self.my_mvaddstr(canvas, y + i + py1, x + 21, coal[i])
            for j in range(self.LOGO + 1):
                yoffset = 2 * j * self.FLY
                self.my_mvaddstr(canvas, y + i + py3 + yoffset, x + 42 + offset * j, car[i])

        if self.ACCIDENT == 1:
            self.add_man(canvas, y + 1, x + 14)
            for j in range(self.LOGO + 1):
                yoffset = self.FLY * (2 + 2 * j)
                self.add_man(canvas, y + 1 + py2 + yoffset, x + 45 + offset * j)
                self.add_man(canvas, y + 1 + py2 + yoffset, x + 53 + offset * j)

        if self.DANCE == 1 and self.ACCIDENT == 0 and self.FLY == 0:
            self.add_mdancer(canvas, y - 2, x + 21)
            for j in range(self.LOGO + 1):
                self.add_mdancer(canvas, y + py2 - 2, x + 45 + offset * j)
                self.add_mdancer(canvas, y + py2 - 2, x + 50 + offset * j)
                self.add_mdancer(canvas, y + py2 - 2, x + 55 + offset * j)

        self.add_smoke(canvas, y - 1, x + LOGOFUNNEL)

    def add_D51(self, canvas, x):
        d51 = [
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL11, D51WHL12, D51WHL13, D51DEL],
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL21, D51WHL22, D51WHL23, D51DEL],
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL31, D51WHL32, D51WHL33, D51DEL],
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL41, D51WHL42, D51WHL43, D51DEL],
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL51, D51WHL52, D51WHL53, D51DEL],
            [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7, D51WHL61, D51WHL62, D51WHL63, D51DEL],
        ]
        coal = [COAL01, COAL02, COAL03, COAL04, COAL05, COAL06, COAL07, COAL08, COAL09, COAL10, COALDEL]

        dy = 0
        y = self.lines // 2 - 5
        if self.FLY == 1:
            y = (x // 7) + self.lines - (self.cols // 7) - D51HEIGHT
            dy = 1

        for i in range(D51HEIGHT + 1):
            pat_idx = (D51LENGTH + x) % D51PATTERNS
            self.my_mvaddstr(canvas, y + i, x, d51[pat_idx][i])
            self.my_mvaddstr(canvas, y + i + dy, x + 53, coal[i])

        if self.ACCIDENT == 1:
            self.add_man(canvas, y + 2, x + 43)
            self.add_man(canvas, y + 2, x + 47)

        if self.DANCE == 1 and self.ACCIDENT == 0 and self.FLY == 0:
            self.add_mdancer(canvas, y - 2, x + 43)
            self.add_fdancer(canvas, y - 2, x + 48)

        self.add_smoke(canvas, y - 1, x + D51FUNNEL)

    def add_C51(self, canvas, x):
        c51 = [
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH11, C51WH12, C51WH13, C51WH14, C51DEL],
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH21, C51WH22, C51WH23, C51WH24, C51DEL],
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH31, C51WH32, C51WH33, C51WH34, C51DEL],
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH41, C51WH42, C51WH43, C51WH44, C51DEL],
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH51, C51WH52, C51WH53, C51WH54, C51DEL],
            [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7, C51WH61, C51WH62, C51WH63, C51WH64, C51DEL],
        ]
        coal = [COALDEL, COAL01, COAL02, COAL03, COAL04, COAL05, COAL06, COAL07, COAL08, COAL09, COAL10, COALDEL]

        dy = 0
        y = self.lines // 2 - 5
        if self.FLY == 1:
            y = (x // 7) + self.lines - (self.cols // 7) - C51HEIGHT
            dy = 1

        for i in range(C51HEIGHT + 1):
            pat_idx = (C51LENGTH + x) % C51PATTERNS
            self.my_mvaddstr(canvas, y + i, x, c51[pat_idx][i])
            self.my_mvaddstr(canvas, y + i + dy, x + 55, coal[i])

        if self.ACCIDENT == 1:
            self.add_man(canvas, y + 3, x + 45)
            self.add_man(canvas, y + 3, x + 49)

        if self.DANCE == 1 and self.ACCIDENT == 0 and self.FLY == 0:
            self.add_mdancer(canvas, y - 1, x + 45)
            self.add_fdancer(canvas, y - 1, x + 50)

        self.add_smoke(canvas, y - 1, x + C51FUNNEL)

    def step(self, mod):
        x = -mod + self.cols - 1
        canvas = [[' '] * self.cols for _ in range(self.lines)]
        
        if self.LOGO >= 1:
            self.add_sl(canvas, x)
        elif self.C51 == 1:
            self.add_C51(canvas, x)
        else:
            self.add_D51(canvas, x)
            
        return "\n".join("".join(row) for row in canvas)

    def generate(self):
        for mod in range(self.N):
            yield self.step(mod)


def sl(cols, lines, arg=''):
    engine = SLEngine(cols, lines, arg)
    return engine.generate()
