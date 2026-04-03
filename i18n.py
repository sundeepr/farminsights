"""
i18n.py — Translation loader and language helpers.
Translations live in translations/<lang>.json.
Language is stored in Flask session under 'lang'.
"""

import json
import os
from flask import session

SUPPORTED_LANGS = ['en', 'hi', 'te', 'mr']
DEFAULT_LANG = 'en'

_cache = {}

def _load(lang):
    path = os.path.join('translations', f'{lang}.json')
    with open(path, 'r', encoding='utf-8') as f:
        _cache[lang] = json.load(f)
    return _cache[lang]

def get_lang():
    """Return the active language code from session, defaulting to 'en'."""
    lang = session.get('lang', DEFAULT_LANG)
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG

def get_translations(lang=None):
    """Return the full translation dict for the given (or session) language.
    Falls back to English for any missing keys."""
    if lang is None:
        lang = get_lang()
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    t = _load(DEFAULT_LANG).copy()
    if lang != DEFAULT_LANG:
        t.update(_load(lang))
    return t
