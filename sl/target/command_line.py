#!/usr/bin/env python3
import os
import sys
import time
from .pure_python import sl

def main():
    try:
        rows, columns = os.get_terminal_size().lines, os.get_terminal_size().columns
    except OSError:
        rows, columns = 24, 80
        
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    for frame in sl(columns, rows, arg):
        print(frame)
        time.sleep(0.04)

if __name__ == '__main__':
    main()
