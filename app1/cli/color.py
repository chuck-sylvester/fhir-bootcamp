# ---------------------------------------------------------------------
# app1/cli/color.py
# ---------------------------------------------------------------------
# ANSI color codes as constants
# -----------------------------------------------------------------------

"""
# Method 1: Combine codes
print(f"{YELLOW}{BG_BLUE}This is yellow text on blue background{RESET}")

# Method 2: Single escape sequence (more efficient)
YELLOW_ON_BLUE = "\033[33;44m"
print(f"{YELLOW_ON_BLUE}This is yellow text on blue background{RESET}")

The pattern for combining is \033[<foreground>;<background>m
You can chain multiple codes with semicolons in a single escape sequence.
"""

# ANSI foreground/text color codes
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"
GRAY    = "\033[90m"
RESET   = "\033[0m"

# Standard backgrounds (40-47)
BG_BLACK   = "\033[40m"
BG_RED     = "\033[41m"
BG_GREEN   = "\033[42m"
BG_YELLOW  = "\033[43m"
BG_BLUE    = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN    = "\033[46m"
BG_WHITE   = "\033[47m"
