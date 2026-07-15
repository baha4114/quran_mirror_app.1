# -*- coding: utf-8 -*-
"""
ابزار شکل‌دهی متن راست‌به‌چپ (عربی/فارسی) برای Kivy.
Kivy به صورت پیش‌فرض حروف عربی را متصل نمی‌کند؛ این ماژول
با arabic_reshaper و python-bidi متن را درست می‌کند.
"""
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _OK = True
except Exception:
    _OK = False

_cache = {}


def rtl(text):
    """متن فارسی/عربی را برای نمایش درست در Kivy آماده می‌کند."""
    if text is None:
        return ""
    text = str(text)
    if not _OK or not text.strip():
        return text
    if text in _cache:
        return _cache[text]
    try:
        reshaped = arabic_reshaper.reshape(text)
        out = get_display(reshaped)
    except Exception:
        out = text
    if len(_cache) < 5000:
        _cache[text] = out
    return out


def rtl_multiline(text):
    """شکل‌دهی متن چندخطی (هر خط جداگانه)."""
    if text is None:
        return ""
    return "\n".join(rtl(line) for line in str(text).split("\n"))
