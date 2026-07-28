import sys
import time
import math
import argparse
import os
import signal

# Bignum representation (5x4 per digit)
NUMBERS = """
 ━━ 
┃  ┃
    
┃  ┃
 ━━ 

    
   ┃
    
   ┃
    

 ━━ 
   ┃
 ━━ 
┃   
 ━━ 

 ━━ 
   ┃
 ━━ 
   ┃
 ━━ 

    
┃  ┃
 ━━ 
   ┃
    

 ━━ 
┃   
 ━━ 
   ┃
 ━━ 

 ━━ 
┃   
 ━━ 
┃  ┃
 ━━ 

 ━━ 
   ┃
    
   ┃
    

 ━━ 
┃  ┃
 ━━ 
┃  ┃
 ━━ 

 ━━ 
┃  ┃
 ━━ 
   ┃
 ━━ 

    
    
 :: 
    
    

    
    
 .. 
    
    
"""

def get_digit_lines():
    blocks = [b.strip('\n') for b in NUMBERS.strip('\n').split('\n\n')]
    digits = []
    for block in blocks:
        lines = [line.ljust(4) for line in block.split('\n')]
        while len(lines) < 5:
            lines.append("    ")
        digits.append(lines)
    return digits

DIGITS = get_digit_lines()

def get_time_string(time_str, blink=False):
    res = ["", "", "", "", ""]
    for char in time_str:
        if char == ':':
            idx = 11 if blink else 10
        elif '0' <= char <= '9':
            idx = int(char)
        else:
            idx = 10 # fallback space or colon
        
        for i in range(5):
            res[i] += DIGITS[idx][i] + " "
    return res

def clear_screen():
    sys.stdout.write("\033[2J\033[H")

def move_cursor(x, y):
    sys.stdout.write(f"\033[{int(y)};{int(x)}H")

def draw_digital(now_str, blink):
    lines = get_time_string(now_str, blink)
    # Get terminal size
    try:
        cols, rows = os.get_terminal_size()
    except OSError:
        cols, rows = 80, 24
    
    w = len(lines[0])
    h = 5
    
    start_x = max(1, (cols - w) // 2 + 1)
    start_y = max(1, (rows - h) // 2 + 1)
    
    sys.stdout.write("\033[31m") # Red text default
    for i, line in enumerate(lines):
        move_cursor(start_x, start_y + i)
        sys.stdout.write(line)

def angle_coords(max_v, val, radius):
    theta = 2.0 * math.pi * (max_v - val) / max_v
    x = -math.sin(theta) * radius
    y = -math.cos(theta) * radius
    return x, y

def draw_analog(now, show_seconds):
    try:
        cols, rows = os.get_terminal_size()
    except OSError:
        cols, rows = 80, 24
    
    cx = cols // 2
    cy = rows // 2
    radius = min(cx // 2, cy) - 2 # // 2 for cx because chars are taller than wide

    # Draw face
    sys.stdout.write("\033[38;2;255;255;255m")
    for n in range(1, 61):
        nx, ny = angle_coords(60, n % 60, radius)
        move_cursor(cx + nx * 2, cy + ny) # *2 for font aspect ratio
        if n % 5 == 0:
            sys.stdout.write(f"{n // 5}")
        elif show_seconds:
            sys.stdout.write("·")
            
    # Hands
    sec = now.tm_sec
    minute = now.tm_min
    hour = now.tm_hour
    
    m_val = minute + sec / 60.0
    h_val = (hour % 12) + m_val / 60.0
    
    def draw_line(val, max_v, r, color_code):
        sys.stdout.write(color_code)
        steps = max(1, int(r))
        for i in range(steps):
            nx, ny = angle_coords(max_v, val, i)
            move_cursor(cx + nx * 2, cy + ny)
            sys.stdout.write("█")

    if show_seconds:
        draw_line(sec, 60, radius * 0.9, "\033[38;2;80;128;80m") # Green-ish
    
    draw_line(m_val, 60, radius * 0.8, "\033[38;2;44;89;212m") # Blue-ish
    draw_line(h_val, 12, radius * 0.5, "\033[38;2;255;167;10m") # Orange-ish

def parse_duration(dur_str):
    if dur_str.endswith('s'):
        return int(dur_str[:-1])
    if dur_str.endswith('m'):
        return int(dur_str[:-1]) * 60
    if dur_str.endswith('h'):
        return int(dur_str[:-1]) * 3600
    return int(dur_str)

def format_duration(seconds):
    s = int(seconds)
    m = s // 60
    s = s % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def main():
    parser = argparse.ArgumentParser(description="Terminal clock")
    parser.add_argument("-analog", action="store_true", help="Analog clock mode")
    parser.add_argument("-aa", action="store_true", help="Analog mode alias")
    parser.add_argument("-24", dest="h24", action="store_true", help="24-hour format")
    parser.add_argument("-countdown", type=str, help="Countdown mode (e.g. 5m, 10s)")
    args, unknown = parser.parse_known_args()

    analog_mode = args.analog or args.aa
    countdown_seconds = 0
    if args.countdown:
        countdown_seconds = parse_duration(args.countdown)

    end_time = time.time() + countdown_seconds

    def signal_handler(sig, frame):
        sys.stdout.write("\033[0m\033[?25h") # Reset colors and show cursor
        clear_screen()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    sys.stdout.write("\033[?25l") # Hide cursor

    blink = False
    last_sec = -1

    try:
        while True:
            now = time.time()
            now_dt = time.localtime(now)
            
            if now_dt.tm_sec != last_sec:
                last_sec = now_dt.tm_sec
                blink = not blink
            
            clear_screen()
            
            if args.countdown:
                remaining = end_time - now
                if remaining <= 0:
                    clear_screen()
                    move_cursor(1, 1)
                    print("Time's up!")
                    break
                
                time_str = format_duration(remaining)
                draw_digital(time_str, blink)
            else:
                if analog_mode:
                    draw_analog(now_dt, True)
                else:
                    fmt = "%H:%M:%S" if args.h24 else "%I:%M:%S"
                    time_str = time.strftime(fmt, now_dt)
                    if not args.h24 and time_str.startswith("0"):
                        time_str = " " + time_str[1:] # strip leading zero for 12h
                    draw_digital(time_str, blink)
            
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[0m\033[?25h") # Reset colors and show cursor
        clear_screen()

if __name__ == "__main__":
    main()
