#!/usr/bin/env python3
"""
asciiquarium.py - a Python port of the Perl `asciiquarium` (Term::Animation) program.

Displays an animated ASCII-art aquarium in the terminal:
fish, seaweed, bubbles, a castle, plus random visitors (ship, whale,
sea monster, big fish, shark that eats small fish).

Controls (same as the Perl version):
    q  quit
    r  redraw / rebuild the scene
    p  pause / unpause

Run:            python3 asciiquarium.py
Classic mode:   python3 asciiquarium.py -c      (only the original art)
Self-test:      python3 asciiquarium.py --selftest   (headless sanity checks)

This is a self-contained reimplementation of the small slice of
Term::Animation the original relied on: entities with a shape (one or more
frames of ASCII art), a colour mask, an (x, y, z) position where lower z is
drawn on top, per-frame movement, transparency, death conditions
(off-screen / timed / after N frames) with a respawn callback, and 2-D
collision detection between "physical" entities.
"""

import curses
import random
import time
import argparse

# ----------------------------------------------------------------------------
# Colour handling
# ----------------------------------------------------------------------------
# Single-letter colour codes used in the art masks. Lower-case = normal,
# upper-case = bold/bright (bold black usually renders as grey).
_CURSES_COLORS = {
    'k': curses.COLOR_BLACK,
    'r': curses.COLOR_RED,
    'g': curses.COLOR_GREEN,
    'y': curses.COLOR_YELLOW,
    'b': curses.COLOR_BLUE,
    'm': curses.COLOR_MAGENTA,
    'c': curses.COLOR_CYAN,
    'w': curses.COLOR_WHITE,
}
_COLOR_LETTERS = set('krgybmcwKRGYBMCW')
_NAME_TO_LETTER = {
    'black': 'k', 'red': 'r', 'green': 'g', 'yellow': 'y',
    'blue': 'b', 'magenta': 'm', 'cyan': 'c', 'white': 'w',
}

_pairs = {}         # colour letter -> curses colour-pair number
_HEADLESS = False   # True during --selftest so we never touch real curses


def setup_colors():
    """Allocate one curses colour pair per base colour on the default bg."""
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    i = 1
    for letter, col in _CURSES_COLORS.items():
        try:
            curses.init_pair(i, col, bg)
        except curses.error:
            pass
        _pairs[letter] = i
        i += 1


def _norm_color(spec):
    """Normalise a default_color spec ('CYAN', 'cyan', 'c', 'C') to a code."""
    if not spec:
        return 'w'
    if len(spec) == 1:
        return spec
    letter = _NAME_TO_LETTER.get(spec.lower(), 'w')
    return letter.upper() if spec.isupper() else letter


def attr_for(code):
    """Return the curses attribute (colour pair + bold) for a colour code."""
    if _HEADLESS:
        return 0
    p = _pairs.get(code.lower())
    if p is None:
        return 0
    a = curses.color_pair(p)
    if code.isupper():
        a |= curses.A_BOLD
    return a


def rand_color(mask):
    """Replace each digit 1-9 in a mask with a randomly chosen colour code.

    All occurrences of a given digit get the same colour, matching the Perl
    behaviour where every "body" cell (digit 1) shares one colour, etc.
    """
    colors = ['c', 'C', 'r', 'R', 'y', 'Y', 'b', 'B', 'g', 'G', 'm', 'M']
    for i in range(1, 10):
        mask = mask.replace(str(i), random.choice(colors))
    return mask


# ----------------------------------------------------------------------------
# Entity: one drawable, movable thing on screen
# ----------------------------------------------------------------------------
def _to_frames(shape):
    """Normalise a shape (str or list of str) into a list of line-lists.

    Matches Perl's split(/\\n/): trailing empty lines are dropped, a leading
    empty line (from art that starts with a newline) is kept.
    """
    frames = [shape] if isinstance(shape, str) else list(shape)
    out = []
    for f in frames:
        lines = f.split('\n')
        while lines and lines[-1] == '':
            lines.pop()
        out.append(lines)
    return out


class Entity:
    def __init__(self, shape, name=None, type=None, color=None,
                 position=(0, 0, 0), callback=None, callback_args=None,
                 death_cb=None, coll_handler=None, default_color='w',
                 auto_trans=False, transparent=None, physical=False,
                 die_offscreen=False, die_time=None, die_frame=None,
                 depth=None):
        self.name = name
        self.type = type
        self.frames = _to_frames(shape)

        if color is None:
            self.mask_frames = None
        elif isinstance(color, str):
            self.mask_frames = _to_frames(color)
        else:
            self.mask_frames = _to_frames(color)

        self.x = float(position[0])
        self.y = float(position[1])
        self.z = float(position[2]) if len(position) > 2 else 0.0

        self.callback = callback
        self.callback_args = list(callback_args) if callback_args else [0, 0, 0]
        self.death_cb = death_cb
        self.coll_handler = coll_handler
        self.default_code = _norm_color(default_color)

        # Space and '?' are always transparent; a caller-supplied char adds one.
        self.transparent = {' ', '?'}
        if transparent:
            self.transparent.add(transparent)

        self.physical = physical
        self.die_offscreen = die_offscreen
        self.die_time = die_time
        self.die_frame = die_frame

        self.frame_pos = 0.0
        self.frames_alive = 0
        self._dead = False
        self._was_onscreen = False
        self._collisions = []

        self.width = max((max((len(l) for l in fr), default=0)
                          for fr in self.frames), default=0)
        self.height = max((len(fr) for fr in self.frames), default=0)

    # --- small accessors (mirror the Perl method names) ---
    def position(self):
        return (int(self.x), int(self.y), int(self.z))

    def size(self):
        return (self.width, self.height)

    def collisions(self):
        return self._collisions

    def kill(self):
        self._dead = True

    def frame_index(self):
        n = len(self.frames)
        return int(self.frame_pos) % n if n else 0

    # --- movement ---
    def _default_move(self):
        a = self.callback_args
        if len(a) > 0:
            self.x += a[0]
        if len(a) > 1:
            self.y += a[1]
        if len(a) > 2:
            self.z += a[2]
        self.frame_pos += a[3] if len(a) > 3 else 1

    # --- rendering / geometry ---
    def _current_lines(self):
        fi = self.frame_index()
        return self.frames[fi] if fi < len(self.frames) else self.frames[-1]

    def bbox(self):
        ox, oy = int(self.x), int(self.y)
        return (ox, oy, ox + self.width, oy + self.height)

    def cells(self):
        """Absolute (x, y) of every non-transparent cell in the current frame."""
        lines = self._current_lines()
        ox, oy = int(self.x), int(self.y)
        s = set()
        for r, line in enumerate(lines):
            for c, ch in enumerate(line):
                if ch not in self.transparent:
                    s.add((ox + c, oy + r))
        return s

    def blit(self, scr, sw, sh):
        lines = self._current_lines()
        mlines = None
        if self.mask_frames:
            mlines = self.mask_frames[self.frame_index() % len(self.mask_frames)]
        ox, oy = int(self.x), int(self.y)
        default_attr = attr_for(self.default_code)
        for r, line in enumerate(lines):
            sy = oy + r
            if sy < 0 or sy >= sh:
                continue
            for c, ch in enumerate(line):
                if ch in self.transparent:
                    continue
                sx = ox + c
                if sx < 0 or sx >= sw:
                    continue
                attr = default_attr
                if mlines is not None and r < len(mlines):
                    ml = mlines[r]
                    if c < len(ml) and ml[c] in _COLOR_LETTERS:
                        attr = attr_for(ml[c])
                try:
                    scr.addch(sy, sx, ch, attr)
                except curses.error:
                    # curses raises on the very last cell; safe to ignore.
                    pass


# ----------------------------------------------------------------------------
# Animation: owns the screen and the list of entities
# ----------------------------------------------------------------------------
class Animation:
    def __init__(self, scr):
        self.scr = scr
        self.entities = []
        self.paused = False
        self.update_size()

    def update_size(self):
        self.height, self.width = self.scr.getmaxyx()

    # entity management
    def add_entity(self, e):
        self.entities.append(e)
        return e

    def new_entity(self, **kw):
        return self.add_entity(Entity(**kw))

    def del_entity(self, e):
        if e in self.entities:
            self.entities.remove(e)

    def clear_entities(self):
        self.entities = []

    def get_entities_of_type(self, t):
        return [e for e in self.entities if e.type == t]

    # geometry helpers
    def _offscreen(self, e):
        x0, y0, x1, y1 = e.bbox()
        return x1 <= 0 or x0 >= self.width or y1 <= 0 or y0 >= self.height

    @staticmethod
    def _bbox_overlap(a, b):
        ax0, ay0, ax1, ay1 = a.bbox()
        bx0, by0, bx1, by1 = b.bbox()
        return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)

    # one animation tick
    def animate(self):
        for e in list(self.entities):
            if e.callback:
                e.callback(e, self)
            else:
                e._default_move()
            e.frames_alive += 1
            if not self._offscreen(e):
                e._was_onscreen = True
        self._handle_collisions()
        self._reap()

    def _handle_collisions(self):
        phys = [e for e in self.entities if e.physical]
        for e in phys:
            e._collisions = []
        cellmap = {e: e.cells() for e in phys}
        for i in range(len(phys)):
            for j in range(i + 1, len(phys)):
                a, b = phys[i], phys[j]
                if not self._bbox_overlap(a, b):
                    continue
                if cellmap[a] & cellmap[b]:
                    a._collisions.append(b)
                    b._collisions.append(a)
        for e in phys:
            if e.coll_handler and e._collisions:
                e.coll_handler(e, self)

    def _reap(self):
        now = time.time()
        snapshot = list(self.entities)
        orig_len = len(self.entities)
        survivors = []
        for e in snapshot:
            dead = e._dead
            if not dead and e.die_offscreen and e._was_onscreen and self._offscreen(e):
                dead = True
            if not dead and e.die_time is not None and now >= e.die_time:
                dead = True
            if not dead and e.die_frame is not None and e.frames_alive >= e.die_frame:
                dead = True
            if dead:
                if e.death_cb:
                    e.death_cb(e, self)   # may append replacements to self.entities
            else:
                survivors.append(e)
        spawned = self.entities[orig_len:]
        self.entities = survivors + spawned

    def draw(self):
        self.scr.erase()
        for e in sorted(self.entities, key=lambda e: e.z, reverse=True):
            e.blit(self.scr, self.width, self.height)
        self.scr.refresh()


# ----------------------------------------------------------------------------
# Depths (lower z = drawn on top / closer to viewer)
# ----------------------------------------------------------------------------
DEPTH = {
    'shark': 2, 'fish_start': 3, 'fish_end': 20, 'seaweed': 21, 'castle': 22,
    'water_line3': 2, 'water_gap3': 3, 'water_line2': 4, 'water_gap2': 5,
    'water_line1': 6, 'water_gap1': 7, 'water_line0': 8, 'water_gap0': 9,
}

# Toggled by the -c flag: when False the "new" (extra) art is disabled.
NEW_FISH = True
NEW_MONSTER = True

# ----------------------------------------------------------------------------
# Environment: water line + castle + seaweed
# ----------------------------------------------------------------------------
WATER_SEGMENTS = [
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    "^^^^ ^^^  ^^^   ^^^    ^^^^      ",
    "^^^^      ^^^^     ^^^    ^^     ",
    "^^      ^^^^      ^^^    ^^^^^^  ",
]


def add_environment(anim):
    seg_len = len(WATER_SEGMENTS[0])
    repeat = int(anim.width / seg_len) + 1
    for i, seg in enumerate(WATER_SEGMENTS):
        anim.new_entity(
            name="water_seg_%d" % i,
            type="waterline",
            shape=seg * repeat,
            position=[0, i + 5, DEPTH['water_line%d' % i]],
            default_color='cyan',
            physical=True,
        )


CASTLE_IMAGE = r"""
               T~~
               |
              /^\
             /   \
 _   _   _  /     \  _   _   _
[ ]_[ ]_[ ]/ _   _ \[ ]_[ ]_[ ]
|_=__-_ =_|_[ ]_[ ]_|_=-___-__|
 | _- =  | =_ = _    |= _=   |
 |= -[]  |- = _ =    |_-=_[] |
 | =_    |= - ___    | =_ =  |
 |=  []- |-  /| |\   |=_ =[] |
 |- =_   | =| | | |  |- = -  |
 |_______|__|_|_|_|__|_______|
"""

CASTLE_MASK = r"""
                RR

              yyy
             y   y
            y     y
           y       y



              yyy
             yy yy
            y y y y
            yyyyyyy
"""


def add_castle(anim):
    anim.new_entity(
        name="castle",
        shape=CASTLE_IMAGE,
        color=CASTLE_MASK,
        position=[anim.width - 32, anim.height - 13, DEPTH['castle']],
        default_color='BLACK',
    )


def add_all_seaweed(anim):
    count = int(anim.width / 15)
    for _ in range(max(count, 1)):
        add_seaweed(None, anim)


def add_seaweed(old, anim):
    frames = ['', '']
    height = random.randint(3, 6)
    for i in range(1, height + 1):
        left = i % 2
        right = 1 - left
        frames[left] += "(\n"
        frames[right] += " )\n"
    x = random.randint(1, max(anim.width - 2, 1))
    y = anim.height - height
    anim_speed = random.random() * 0.05 + 0.25
    anim.new_entity(
        name="seaweed%f" % random.random(),
        shape=frames,
        position=[x, y, DEPTH['seaweed']],
        callback_args=[0, 0, 0, anim_speed],
        die_time=time.time() + random.randint(0, 4 * 60) + 8 * 60,
        death_cb=add_seaweed,
        default_color='green',
    )


# ----------------------------------------------------------------------------
# Bubbles
# ----------------------------------------------------------------------------
def add_bubble(fish, anim):
    a = fish.callback_args
    fw, fh = fish.width, fish.height
    fx, fy, fz = int(fish.x), int(fish.y), int(fish.z)
    bx = fx + fw if a[0] > 0 else fx
    by = fy + fh // 2
    bz = fz - 1
    anim.new_entity(
        shape=['.', 'o', 'O', 'O', 'O'],
        type='bubble',
        position=[bx, by, bz],
        callback_args=[0, -1, 0, 0.1],
        die_offscreen=True,
        physical=True,
        coll_handler=bubble_collision,
        default_color='CYAN',
    )


def bubble_collision(bubble, anim):
    for obj in bubble.collisions():
        if obj.type == 'waterline':
            bubble.kill()
            break


# ----------------------------------------------------------------------------
# Fish.  Each entry is (shape, colour-mask).  In the mask, digits 1-9 are
# placeholders that get replaced with a random colour at spawn time; 4 is the
# eye (forced white).  Fish come in mirrored pairs: even index faces/moves
# right, odd index faces/moves left.
#
#   1 body   2 dorsal fin   3 flippers   4 eye   5 mouth   6 tailfin   7 gills
# ----------------------------------------------------------------------------

OLD_FISH = [
    (r"""
       \
     ...\..,
\  /'       \
 >=     (  ' >
/  \      / /
    `"'"'/''
""", r"""
       2
     1112111
6  11       1
 66     7  4 5
6  1      3 1
    11111311
"""),
    (r"""
      /
  ,../...
 /       '\  /
< '  )     =<
 \ \      /  \
  `'\'"'"'
""", r"""
      2
  1112111
 1       11  6
5 4  7     66
 1 3      1  6
  11311111
"""),
    (r"""
    \
\ /--\
>=  (o>
/ \__/
    /
""", r"""
    2
6 1111
66  745
6 1111
    3
"""),
    (r"""
  /
 /--\ /
<o)  =<
 \__/ \
  \
""", r"""
  2
 1111 6
547  66
 1111 6
  3
"""),
    (r"""
       \:.
\;,   ,;\\,,
  \\;;:::::::o
  ///;;::::::::<
 /;` ``/////``
""", r"""
       222
666   1122211
  6661111111114
  66611111111115
 666 113333311
"""),
    (r"""
      .:/
   ,,///;,   ,;/
 o:::::::;;///
>::::::::;;\\
  ''\\\'' ';\
""", r"""
      222
   1122211   666
 4111111111666
51111111111666
  113333311 666
"""),
    (r"""
  __
><_'>
   '
""", r"""
  11
61145
   3
"""),
    (r"""
 __
<'_><
 `
""", r"""
 11
54116
 3
"""),
    (r"""
   ..\,
>='   ('>
  '''/''
""", r"""
   1121
661   745
  111311
"""),
    (r"""
  ,/..
<')   `=<
 ``\```
""", r"""
  1211
547   166
 113111
"""),
    (r"""
   \
  / \
>=_('>
  \_/
   /
""", r"""
   2
  1 1
661745
  111
   3
"""),
    (r"""
  /
 / \
<')_=<
 \_/
  \
""", r"""
  2
 1 1
547166
 111
  3
"""),
    (r"""
  ,\
>=('>
  '/
""", r"""
  12
66745
  13
"""),
    (r"""
 /,
<')=<
 \`
""", r"""
 21
54766
 31
"""),
    (r"""
  __
\/ o\
/\__/
""", r"""
  11
61 41
61111
"""),
    (r"""
 __
/o \/
\__/\
""", r"""
 11
14 16
11116
"""),
]


NEW_FISH_ART = [
    (r"""
   \
  / \
>=_('>
  \_/
   /
""", r"""
   1
  1 1
663745
  111
   3
"""),
    (r"""
  /
 / \
<')_=<
 \_/
  \
""", r"""
  2
 111
547366
 111
  3
"""),
    (r"""
     ,
     }\
\  .'  `\
}}<   ( 6>
/  `,  .'
     }/
     '
""", r"""
     2
     22
6  11  11
661   7 45
6  11  11
     33
     3
"""),
    (r"""
    ,
   /{
 /'  `.  /
<6 )   >{{
 `.  ,'  \
   \{
    `
""", r"""
    2
   22
 11  11  6
54 7   166
 11  11  6
   33
    3
"""),
    (r"""
            \'`.
             )  \
(`.??????_.-`' ' '`-.
 \ `.??.`        (o) \_
  >  ><     (((       (
 / .`??`._      /_|  /'
(.`???????`-. _  _.-`
            /__/'

""", r"""
            1111
             1  1
111      11111 1 1111
 1 11  11        141 11
  1  11     777       5
 1 11  111      333  11
111       111 1  1111
            11111

"""),
    (r"""
       .'`/
      /  (
  .-'` ` `'-._??????.')
_/ (o)        '.??.' /
)       )))     ><  <
`\  |_\      _.'??'. \
  '-._  _ .-'???????'.)
      `\__\
""", r"""
       1111
      1  1
  1111 1 11111      111
11 141        11  11 1
5       777     11  1
11  333      111  11 1
  1111  1 111       111
      11111
"""),
    (r"""
       ,--,_
__    _\.---'-.
\ '.-"     // o\
/_.'-._    \\  /
       `"--(/"`
""", r"""
       22222
66    121111211
6 6111     77 41
6661111    77  1
       11113311
"""),
    (r"""
    _,--,
 .-'---./_    __
/o \\     "-.' /
\  //    _.-'._\
 `"\)--"`
""", r"""
    22222
 112111121    66
14 77     1116 6
1  77    1111666
 11331111
"""),
]


def add_all_fish(anim):
    screen_size = (anim.height - 9) * anim.width
    count = int(screen_size / 350)
    for _ in range(max(count, 1)):
        add_fish(None, anim)


def add_fish(old, anim):
    if NEW_FISH and random.randrange(12) > 8:
        add_fish_entity(anim, NEW_FISH_ART)
    else:
        add_fish_entity(anim, OLD_FISH)


def add_fish_entity(anim, pairs):
    n = len(pairs)
    fish_num = random.randrange(n)
    shape, mask = pairs[fish_num]

    speed = random.random() * 2 + 0.25
    depth = random.randrange(DEPTH['fish_end'] - DEPTH['fish_start']) + DEPTH['fish_start']
    color_mask = rand_color(mask.replace('4', 'W'))
    if fish_num % 2:
        speed = -speed

    fish = Entity(
        type='fish',
        shape=shape,
        color=color_mask,
        auto_trans=True,
        position=[0, 0, depth],
        callback=fish_callback,
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=add_fish,
        physical=True,
        coll_handler=fish_collision,
    )

    max_h = 9
    min_h = anim.height - fish.height
    span = min_h - max_h
    fish.y = float(random.randrange(span) + max_h) if span > 0 else float(max_h)
    fish.x = float(anim.width - 2) if fish_num % 2 else float(1 - fish.width)
    anim.add_entity(fish)


def fish_callback(fish, anim):
    if random.randrange(100) > 97:
        add_bubble(fish, anim)
    fish._default_move()


def fish_collision(fish, anim):
    for obj in fish.collisions():
        if obj.type == 'teeth' and fish.height <= 5:
            add_splat(anim, *obj.position())
            fish.kill()
            break


SPLAT_FRAMES = [
    r"""

   .
  ***
   '

""",
    r"""

 ",*;`
 "*,**
 *"'~'

""",
    r"""
  , ,
 " ","'
 *" *'"
  " ; .

""",
    r"""
* ' , ' `
' ` * . '
 ' `' ",'
* ' " * .
" * ', '
""",
]


def add_splat(anim, x, y, z):
    anim.new_entity(
        shape=SPLAT_FRAMES,
        position=[x - 4, y - 2, z - 2],
        default_color='RED',
        callback_args=[0, 0, 0, 0.25],
        transparent=' ',
        die_frame=15,
    )


# ----------------------------------------------------------------------------
# Random big objects: shark, ship, whale, sea-monster, big fish
# ----------------------------------------------------------------------------
SHARK_IMAGE = [
    r"""
                              __
                             ( `\
  ,??????????????????????????)   `\
;' `.????????????????????????(     `\__
 ;   `.?????????????__..---''          `~~~~-._
  `.   `.____...--''                       (b  `--._
    >                     _.-'      .((      ._     )
  .`.-`--...__         .-'     -.___.....-(|/|/|/|/'
 ;.'?????????`. ...----`.___.',,,_______......---'
 '???????????'-'
""",
    r"""
                     __
                    /' )
                  /'   (??????????????????????????,
              __/'     )????????????????????????.' `;
      _.-~~~~'          ``---..__?????????????.'   ;
 _.--'  b)                       ``--...____.'   .'
(     _.      )).      `-._                     <
 `\|\|\|\|)-.....___.-     `-.         __...--'-.'.
   `---......_______,,,`.___.'----... .'?????????`.;
                                     `-`???????????`
""",
]

SHARK_MASK = [
    r"""




                                           cR
 
                                          cWWWWWWWW

""",
    r"""




        Rc

  WWWWWWWWc

""",
]


def add_shark(old, anim):
    direction = random.randint(0, 1)
    x = -53
    y = random.randrange(max(anim.height - 19, 1)) + 9
    teeth_x = -9
    teeth_y = y + 7
    speed = 2
    if direction:
        speed = -speed
        x = anim.width - 2
        teeth_x = x + 9

    anim.new_entity(
        type='teeth',
        shape="*",
        position=[teeth_x, teeth_y, DEPTH['shark'] + 1],
        callback_args=[speed, 0, 0],
        physical=True,
    )
    anim.new_entity(
        type="shark",
        color=SHARK_MASK[direction],
        shape=SHARK_IMAGE[direction],
        auto_trans=True,
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=shark_death,
        default_color='CYAN',
    )


def shark_death(shark, anim):
    for obj in anim.get_entities_of_type('teeth'):
        anim.del_entity(obj)
    random_object(shark, anim)


SHIP_IMAGE = [
    r"""
     |    |    |
    )_)  )_)  )_)
   )___))___))___)\
  )____)____)_____)\\
_____|____|____|____\\\__
\                   /
""",
    r"""
         |    |    |
        (_(  (_(  (_(
      /(___((___((___(
    //(_____(____(____(
__///____|____|____|_____
    \                   /
""",
]

SHIP_MASK = [
    r"""
     y    y    y

                  w
                   ww
yyyyyyyyyyyyyyyyyyyywwwyy
y                   y
""",
    r"""
         y    y    y

      w
    ww
yywwwyyyyyyyyyyyyyyyyyyyy
    y                   y
""",
]


def add_ship(old, anim):
    direction = random.randint(0, 1)
    x = -24
    speed = 1
    if direction:
        speed = -speed
        x = anim.width - 2
    anim.new_entity(
        color=SHIP_MASK[direction],
        shape=SHIP_IMAGE[direction],
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap1']],
        default_color='WHITE',
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=random_object,
    )


WHALE_IMAGE = [
    r"""
        .-----:
      .'       `.
,????/       (o) \
\`._/          ,__)
""",
    r"""
    :-----.
  .'       `.
 / (o)       \????,
(__,          \_.'/
""",
]

WHALE_MASK = [
    r"""
             C C
           CCCCCCC
           C  C  C
        BBBBBBB
      BB       BB
B    B       BWB B
BBBBB          BBBB
""",
    r"""
   C C
 CCCCCCC
 C  C  C
    BBBBBBB
  BB       BB
 B BWB       B    B
BBBB          BBBBB
""",
]

WATER_SPOUT = [
    "\n\n\n   :",
    "\n\n   :\n   :",
    "\n  . .\n  -:-\n   :",
    "\n  . .\n .-:-.\n   :",
    "\n  . .\n'.-:-.`\n'  :  '",
    "\n\n .- -.\n;  :  ;",
    "\n\n\n;     ;",
]


def add_whale(old, anim):
    direction = random.randint(0, 1)
    speed = 1
    if direction:
        speed = -speed
        x = anim.width - 2
        spout_align = 1
    else:
        x = -18
        spout_align = 11

    frames = []
    masks = []
    for _ in range(5):
        frames.append("\n\n\n" + WHALE_IMAGE[direction])
        masks.append(WHALE_MASK[direction])
    for spout in WATER_SPOUT:
        aligned = ("\n" + " " * spout_align).join(spout.split("\n"))
        frames.append(aligned + WHALE_IMAGE[direction])
        masks.append(WHALE_MASK[direction])

    anim.new_entity(
        color=masks,
        shape=frames,
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap2']],
        default_color='WHITE',
        callback_args=[speed, 0, 0, 1],
        die_offscreen=True,
        death_cb=random_object,
    )


def add_monster(old, anim):
    if NEW_MONSTER:
        add_new_monster(old, anim)
    else:
        add_old_monster(old, anim)


NEW_MONSTER_IMAGE = [
    [
        r"""
         _???_?????????????????????_???_???????_a_a
       _{.`=`.}_??????_???_??????_{.`=`.}_????{/ ''\_
 _????{.'  _  '.}????{.`'`.}????{.'  _  '.}??{|  ._oo)
{ \????{/  .'?'.  \}??{/ .-. \}??{/  .'?'.  \}?{/  |
""",
        r"""
                      _???_????????????????????_a_a
  _??????_???_??????_{.`=`.}_??????_???_??????{/ ''\_
 { \????{.`'`.}????{.'  _  '.}????{.`'`.}????{|  ._oo)
  \ \??{/ .-. \}??{/  .'?'.  \}??{/ .-. \}???{/  |
""",
    ],
    [
        r"""
   a_a_???????_???_?????????????????????_???_
 _/'' \}????_{.`=`.}_??????_???_??????_{.`=`.}_
(oo_.  |}??{.'  _  '.}????{.`'`.}????{.'  _  '.}????_
    |  \}?{/  .'?'.  \}??{/ .-. \}??{/  .'?'.  \}??/ }
""",
        r"""
   a_a_????????????????????_   _
 _/'' \}??????_???_??????_{.`=`.}_??????_???_??????_
(oo_.  |}????{.`'`.}????{.'  _  '.}????{.`'`.}????/ }
    |  \}???{/ .-. \}??{/  .'?'.  \}??{/ .-. \}??/ /
""",
    ],
]

NEW_MONSTER_MASK = [
    r"""                                                W W



""",
    r"""
   W W



""",
]


def add_new_monster(old, anim):
    direction = random.randint(0, 1)
    speed = 2
    if direction:
        speed = -speed
        x = anim.width - 2
    else:
        x = -54
    masks = [NEW_MONSTER_MASK[direction], NEW_MONSTER_MASK[direction]]
    anim.new_entity(
        shape=NEW_MONSTER_IMAGE[direction],
        auto_trans=True,
        color=masks,
        position=[x, 2, DEPTH['water_gap2']],
        callback_args=[speed, 0, 0, 0.25],
        death_cb=random_object,
        die_offscreen=True,
        default_color='GREEN',
    )


OLD_MONSTER_IMAGE = [
    [
        r"""
                                                          ____
            __??????????????????????????????????????????/   o  \
          /    \????????_?????????????????????_???????/     ____ >
  _??????|  __  |?????/   \????????_????????/   \????|     |
 | \?????|  ||  |????|     |?????/   \?????|     |???|     |
""",
        r"""
                                                          ____
                                             __?????????/   o  \
             _?????????????????????_???????/    \?????/     ____ >
   _???????/   \????????_????????/   \????|  __  |???|     |
  | \?????|     |?????/   \?????|     |???|  ||  |???|     |
""",
        r"""
                                                          ____
                                  __????????????????????/   o  \
 _??????????????????????_???????/    \????????_???????/     ____ >
| \??????????_????????/   \????|  __  |?????/   \????|     |
 \ \???????/   \?????|     |???|  ||  |????|     |???|     |
""",
        r"""
                                                          ____
                       __???????????????????????????????/   o  \
  _??????????_???????/    \????????_??????????????????/     ____ >
 | \???????/   \????|  __  |?????/   \????????_??????|     |
  \ \?????|     |???|  ||  |????|     |?????/   \????|     |
""",
    ],
    [
        r"""
    ____
  /  o   \??????????????????????????????????????????__
< ____     \???????_?????????????????????_????????/    \
      |     |????/   \????????_????????/   \?????|  __  |??????_
      |     |???|     |?????/   \?????|     |????|  ||  |?????/ |
""",
        r"""
    ____
  /  o   \?????????__
< ____     \?????/    \???????_?????????????????????_
      |     |???|  __  |????/   \????????_????????/   \???????_
      |     |???|  ||  |???|     |?????/   \?????|     |?????/ |
""",
        r"""
    ____
  /  o   \????????????????????__
< ____     \???????_????????/    \???????_??????????????????????_
      |     |????/   \?????|  __  |????/   \????????_??????????/ |
      |     |???|     |????|  ||  |???|     |?????/   \???????/ /
""",
        r"""
    ____
  /  o   \???????????????????????????????__
< ____     \??????????????????_????????/    \???????_??????????_
      |     |??????_????????/   \?????|  __  |????/   \???????/ |
      |     |????/   \?????|     |????|  ||  |???|     |?????/ /
""",
    ],
]

OLD_MONSTER_MASK = [
    r"""

                                                            W



""",
    r"""

     W



""",
]


def add_old_monster(old, anim):
    direction = random.randint(0, 1)
    speed = 2
    if direction:
        speed = -speed
        x = anim.width - 2
    else:
        x = -64
    masks = [OLD_MONSTER_MASK[direction] for _ in range(4)]
    anim.new_entity(
        shape=OLD_MONSTER_IMAGE[direction],
        auto_trans=True,
        color=masks,
        position=[x, 2, DEPTH['water_gap2']],
        callback_args=[speed, 0, 0, 0.25],
        death_cb=random_object,
        die_offscreen=True,
        default_color='GREEN',
    )


def add_big_fish(old, anim):
    if NEW_FISH and random.randrange(3) > 1:
        add_big_fish_2(old, anim)
    else:
        add_big_fish_1(old, anim)


BIG_FISH_1_IMAGE = [
    r"""
 ______
`""-.  `````-----.....__
     `.  .      .       `-.
       :     .     .       `.
 ,?????:   .    .          _ :
: `.???:                  (@) `._
 `. `..'     .     =`-.       .__)
   ;     .        =  ~  :     .-"
 .' .'`.   .    .  =.-'  `._ .'
: .'???:               .   .'
 '???.'  .    .     .   .-'
   .'____....----''.'=.'
   ""?????????????.'.'
               ''"'`
""",
    r"""
                           ______
          __.....-----'''''  .-""'
       .-'       .      .  .'
     .'       .     .     :
    : _          .    .   :?????,
 _.' (@)                  :???.' :
(__.       .-'=     .     `..' .'
 "-.     :  ~  =        .     ;
   `. _.'  `-.=  .    .   .'`. `.
     `.   .               :???`. :
       `-.   .     .    .  `.???`
          `.=`.``----....____`.
            `.`.?????????????""
              '`"``
""",
]

BIG_FISH_1_MASK = [
    r"""
 111111
11111  11111111111111111
     11  2      2       111
       1     2     2       11
 1     1   2    2          1 1
1 11   1                  1W1 111
 11 1111     2     1111       1111
   1     2        1  1  1     111
 11 1111   2    2  1111  111 11
1 11   1               2   11
 1   11  2    2     2   111
   111111111111111111111
   11             1111
               11111
""",
    r"""
                           111111
          111111111111111111  11111
       111       2      2  11
     11       2     2     1
    1 1          2    2   1     1
 111 1W1                  1   11 1
1111       1111     2     1111 11
 111     1  1  1        2     1
   11 111  1111  2    2   1111 11
     11   2               1   11 1
       111   2     2    2  11   1
          111111111111111111111
            1111             11
              11111
""",
]


def add_big_fish_1(old, anim):
    direction = random.randint(0, 1)
    speed = 3
    if direction:
        x = anim.width - 1
        speed = -speed
    else:
        x = -34
    max_h = 9
    min_h = anim.height - 15
    span = min_h - max_h
    y = random.randrange(span) + max_h if span > 0 else max_h
    anim.new_entity(
        shape=BIG_FISH_1_IMAGE[direction],
        auto_trans=True,
        color=rand_color(BIG_FISH_1_MASK[direction]),
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW',
    )


BIG_FISH_2_IMAGE = [
    r"""
                _ _ _
             .='\ \ \`"=,
           .'\ \ \ \ \ \ \
\'=._?????/ \ \ \_\_\_\_\_\
\'=._'.??/\ \,-"`- _ - _ - '-.
  \`=._\|'.\/- _ - _ - _ - _- \
  ;"= ._\=./_ -_ -_ {`"=_    @ \
   ;="_-_=- _ -  _ - {"=_"-     \
   ;_=_--_.,          {_.='   .-/
  ;.="` / ';\        _.     _.-`
  /_.='/ \/ /;._ _ _{.-;`/"`
/._=_.'???'/ / / / /{.= /
/.=' ??????`'./_/_.=`{_/
""",
    r"""
            _ _ _
        ,="`/ / /'=.
       / / / / / / /'.
      /_/_/_/_/_/ / / \?????_.='/
   .-' - _ - _ -`"-,/ /\??.'_.='/
  / -_ - _ - _ - _ -\/.'|/_.=`/
 / @    _="`} _- _- _\.=/_. =";
/     -"_="} - _  - _ -=_-_"=;
\-.   '=._}          ,._--_=_;
 `-._     ._        /;' \ `"=.;
     `"\`;-.}_ _ _.;\ \/ \'=._\
        \ =.}\ \ \ \ \'???'._=_.\
         \_}`=._\_\.'`???????'=.\
""",
]

BIG_FISH_2_MASK = [
    r"""
                1 1 1
             1111 1 11111
           111 1 1 1 1 1 1
11111     1 1 1 11111111111
1111111  11 111112 2 2 2 2 111
  111111111112 2 2 2 2 2 2 22 1
  111 1111 12 22 22 11111    W 1
   11111112 2 2  2 2 111111     1
   111111111          11111   111
  11111 11111        11     1111
  111111 11 1111 1 111111111
1111111   11 1 1 1 1111 1
1111       1111111111111
""",
    r"""
            1 1 1
        11111 1 1111
       1 1 1 1 1 1 111
      11111111111 1 1 1     11111
   111 2 2 2 2 211111 11  1111111
  1 22 2 2 2 2 2 2 211111111111
 1 W    11111 22 22 2111111 111
1     111111 2 2  2 2 21111111
111   11111          111111111
 1111     11        111 1 11111
     111111111 1 1111 11 111111
        1 1111 1 1 1 11   1111111
         1111111111111       1111
""",
]


def add_big_fish_2(old, anim):
    direction = random.randint(0, 1)
    speed = 2.5
    if direction:
        x = anim.width - 1
        speed = -speed
    else:
        x = -33
    max_h = 9
    min_h = anim.height - 14
    span = min_h - max_h
    y = random.randrange(span) + max_h if span > 0 else max_h
    anim.new_entity(
        shape=BIG_FISH_2_IMAGE[direction],
        auto_trans=True,
        color=rand_color(BIG_FISH_2_MASK[direction]),
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW',
    )


RANDOM_OBJECTS = [add_ship, add_whale, add_monster, add_big_fish, add_shark]


def random_object(dead, anim):
    random.choice(RANDOM_OBJECTS)(dead, anim)


def build_scene(anim):
    add_environment(anim)
    add_castle(anim)
    add_all_seaweed(anim)
    add_all_fish(anim)
    random_object(None, anim)


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------
MIN_W, MIN_H = 40, 15


def _too_small(anim):
    return anim.width < MIN_W or anim.height < MIN_H


def run(scr):
    curses.curs_set(0)
    scr.nodelay(False)
    scr.timeout(100)          # ~10 fps, like the Perl halfdelay(1)
    setup_colors()

    anim = Animation(scr)
    if _too_small(anim):
        _show_too_small(scr, anim)
    else:
        build_scene(anim)

    while True:
        ch = scr.getch()

        if ch != -1:
            if ch == curses.KEY_RESIZE:
                anim.update_size()
                anim.clear_entities()
                if _too_small(anim):
                    _show_too_small(scr, anim)
                    continue
                build_scene(anim)
                continue
            c = chr(ch).lower() if 0 <= ch < 256 else ''
            if c == 'q':
                return
            elif c == 'r':
                anim.update_size()
                anim.clear_entities()
                if _too_small(anim):
                    _show_too_small(scr, anim)
                    continue
                build_scene(anim)
                continue
            elif c == 'p':
                anim.paused = not anim.paused

        if _too_small(anim):
            continue

        if not anim.paused:
            anim.animate()
        anim.draw()


def _show_too_small(scr, anim):
    scr.erase()
    msg = "Terminal too small (need %dx%d). Resize, or press q." % (MIN_W, MIN_H)
    try:
        scr.addstr(0, 0, msg[:max(anim.width - 1, 0)])
    except curses.error:
        pass
    scr.refresh()


def main():
    parser = argparse.ArgumentParser(description="ASCII-art aquarium animation.")
    parser.add_argument('-c', '--classic', action='store_true',
                        help="classic mode: only the original art")
    parser.add_argument('--selftest', action='store_true',
                        help="run headless sanity checks and exit")
    args = parser.parse_args()

    global NEW_FISH, NEW_MONSTER
    if args.classic:
        NEW_FISH = False
        NEW_MONSTER = False

    if args.selftest:
        selftest()
        return

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass


# ----------------------------------------------------------------------------
# Headless self-test (no terminal needed)
# ----------------------------------------------------------------------------
class _FakeScreen:
    """Minimal stand-in for a curses window, records draw calls."""
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.calls = 0

    def getmaxyx(self):
        return (self.h, self.w)

    def erase(self):
        pass

    def refresh(self):
        pass

    def addch(self, y, x, ch, attr=0):
        if not (0 <= y < self.h and 0 <= x < self.w):
            raise curses.error("out of bounds")
        self.calls += 1


def selftest():
    global _HEADLESS
    _HEADLESS = True
    print("Running self-test...")

    # 1. Every art shape/mask parses and mask dims are not wildly off.
    def check_pair(label, shape, mask):
        e = Entity(shape=shape, color=mask)
        sh = len(e.frames[0])
        mh = len(e.mask_frames[0]) if e.mask_frames else 0
        assert sh > 0, "%s: empty shape" % label
        # A mask may be shorter than the shape (accent-only colouring); it must
        # not be meaningfully taller, which would signal a transcription slip.
        assert mh <= sh + 1, "%s: mask %d rows taller than shape %d rows" % (label, mh, sh)

    for i, (s, m) in enumerate(OLD_FISH):
        check_pair("old_fish[%d]" % i, s, rand_color(m.replace('4', 'W')))
    for i, (s, m) in enumerate(NEW_FISH_ART):
        check_pair("new_fish[%d]" % i, s, rand_color(m.replace('4', 'W')))
    for i in range(2):
        check_pair("shark[%d]" % i, SHARK_IMAGE[i], SHARK_MASK[i])
        check_pair("ship[%d]" % i, SHIP_IMAGE[i], SHIP_MASK[i])
        # Whale masks are sized for the composed (spout + body) frame.
        check_pair("whale[%d]" % i, "\n\n\n" + WHALE_IMAGE[i], WHALE_MASK[i])
        check_pair("bigfish1[%d]" % i, BIG_FISH_1_IMAGE[i], rand_color(BIG_FISH_1_MASK[i]))
        check_pair("bigfish2[%d]" % i, BIG_FISH_2_IMAGE[i], rand_color(BIG_FISH_2_MASK[i]))
    print("  [ok] all %d fish + creatures parse, shape/mask dims aligned"
          % (len(OLD_FISH) + len(NEW_FISH_ART)))

    # 2. Build a scene and run many frames on a fake screen; must not crash.
    for w, h in [(80, 24), (200, 50), (40, 15)]:
        scr = _FakeScreen(h, w)
        anim = Animation(scr)
        build_scene(anim)
        n0 = len(anim.entities)
        for _ in range(300):
            anim.animate()
            anim.draw()
        assert len(anim.entities) > 0, "scene emptied out"
        print("  [ok] %dx%d: %d entities at start, %d after 300 frames, %d cells drawn"
              % (w, h, n0, len(anim.entities), scr.calls))

    # 3. Collision: a shark's teeth must be able to kill a small fish.
    scr = _FakeScreen(24, 80)
    anim = Animation(scr)
    fish = Entity(type='fish', shape="><(('>", position=[10, 10, 5],
                  physical=True, coll_handler=fish_collision, auto_trans=True)
    anim.add_entity(fish)
    anim.new_entity(type='teeth', shape="*", position=[12, 10, 3], physical=True)
    anim.animate()
    assert fish not in anim.entities, "teeth failed to eat the fish"
    print("  [ok] collision: shark teeth eat a small fish")

    # 4. Bubble pops on the water line.
    scr = _FakeScreen(24, 80)
    anim = Animation(scr)
    add_environment(anim)
    bubble = Entity(type='bubble', shape="O", position=[10, 6, 7],
                    physical=True, coll_handler=bubble_collision)
    anim.add_entity(bubble)
    anim.animate()
    assert bubble not in anim.entities, "bubble failed to pop at surface"
    print("  [ok] collision: bubble pops at the water line")

    print("Self-test passed.")
    _HEADLESS = False


if __name__ == "__main__":
    main()
