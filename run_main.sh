#!/bin/bash

uv run python main.py build "/Users/mromano/research/schedule_maker/Schedule Creation (2026-2027).xlsm" "/Users/mromano/research/schedule_maker/Schedule, Call, and GAD Combined Request Form, 2026-2027 (Responses).xlsx" --dry-run
# uv run python main.py build "/Users/mromano/research/schedule_maker/Schedule Creation (2026-2027).xlsm" "/Users/mromano/research/schedule_maker/Schedule, Call, and GAD Combined Request Form, 2026-2027 (Responses).xlsx" -o output.xlsm
# uv run python main.py stats "output.xlsm" -o report.txt
# uv run python main.py validate "output.xlsm"