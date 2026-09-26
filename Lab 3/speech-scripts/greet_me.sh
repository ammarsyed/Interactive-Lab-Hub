#!/usr/bin/env bash
# Greets me by name with Piper. Usage: ./greet_me.sh [name]

python3 -m piper --model en_US-lessac-medium --data-dir "$(dirname "$0")/../voices" --output-raw \
  -- "Hi ${1:-Ammar}, welcome back. I hope you've been well." | aplay -q -r 22050 -f S16_LE -t raw -
