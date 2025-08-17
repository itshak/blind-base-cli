import pygame
import os

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), 'sounds')
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sound_debug.log')

def _log(message):
    with open(LOG_FILE, 'a') as f:
        f.write(message + '\n')

pygame.mixer.init()

def play_sound(sound_name):
    """Plays a sound from the sounds directory."""
    _log(f"Attempting to play sound: {sound_name}")
    try:
        sound_path = os.path.join(SOUNDS_DIR, sound_name)
        _log(f"Full sound path: {sound_path}")
        pygame.mixer.Sound(sound_path).play()
        _log(f"Successfully called playsound for: {sound_name}")
    except Exception as e:
        _log(f"Error playing sound: {e}")