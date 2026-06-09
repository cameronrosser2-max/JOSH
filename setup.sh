#!/bin/bash
echo ""
echo " ================================================"
echo "   JOSH Instagram Bot — First Time Setup"
echo " ================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo " ERROR: Python not found. Install it from https://python.org/downloads"
    exit 1
fi

echo " Installing packages..."
pip3 install -r requirements.txt --quiet

echo ""
echo " Setup complete! Run:  python3 instagram_dm.py"
echo ""
