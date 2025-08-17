import pygame
import os

from blindbase.core.settings import settings

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), 'sounds')
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sound_debug.log')

def _log(message):
    with open(LOG_FILE, 'a') as f:
        f.write(message + '\n')

if settings.ui.sound_enabled:
    try:
        pygame.mixer.init()
    except pygame.error:
        settings.ui.sound_enabled = False

def play_sound(sound_name):
    """Plays a sound from the sounds directory."""
    if not settings.ui.sound_enabled:
        return
    _log(f"Attempting to play sound: {sound_name}")
    try:
        sound_path = os.path.join(SOUNDS_DIR, sound_name)
        _log(f"Full sound path: {sound_path}")
        pygame.mixer.Sound(sound_path).play()
        _log(f"Successfully called playsound for: {sound_name}")
    except Exception as e:
        _log(f"Error playing sound: {e}")