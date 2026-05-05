#!/usr/bin/env python3
"""
Josh — AI Sales Representative
Sells websites to HVAC, Plumbing, Electrician, and Repair shops
"""

import os
import sys
from agent import JoshAgent


BANNER = """
╔══════════════════════════════════════════════╗
║         JOSH — AI Sales Representative       ║
║   Websites for Trades: HVAC · Plumb · Elec   ║
╚══════════════════════════════════════════════╝

Commands:
  Type your response and press Enter
  /reset   — Start a new call
  /quit    — Exit
  /debug   — Show detected industry
"""


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("Enter your Anthropic API key (or set ANTHROPIC_API_KEY env var):")
        key = input("> ").strip()
    if not key:
        print("ERROR: API key required.")
        sys.exit(1)
    return key


def run():
    api_key = get_api_key()
    agent = JoshAgent(api_key=api_key)

    print(BANNER)
    print("Starting call simulation...\n")

    # Josh opens the call
    opening = agent.opening_line()
    print(f"Josh: {opening}\n")

    while True:
        try:
            user_input = input("You:  ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCall ended.")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("Exiting.")
            break

        if user_input == "/reset":
            agent.reset()
            print("\n--- New call started ---\n")
            opening = agent.opening_line()
            print(f"Josh: {opening}\n")
            continue

        if user_input == "/debug":
            industry = agent.industry
            name = agent.prospect_name
            print(f"[DEBUG] Industry: {industry['name'] if industry else 'Not detected'}")
            print(f"[DEBUG] Prospect name: {name or 'Unknown'}\n")
            continue

        response = agent.chat(user_input)
        print(f"\nJosh: {response}\n")


if __name__ == "__main__":
    run()
