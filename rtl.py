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

# یک reshaper سفارشی که «چسبِ کلمه‌ایِ الله» (تبدیلِ «الله» به یک نویسهٔ واحد) را خاموش می‌کند.
# بعضی فونت‌ها (مثل A Ali) گلیفِ آن نویسه را بدونِ الفِ ابتدایی می‌کشند و «الله» به شکلِ «لله» دیده می‌شود.
# با خاموش‌کردنِ این چسب، «الله» با حروفِ عادی و الفِ سالم نوشته می‌شود؛
# چسبِ لازمِ «لا» (لام‌الف) دست‌نخورده می‌ماند.
_reshaper = None
if _OK:
    try:
        _reshaper = arabic_reshaper.ArabicReshaper(configuration={
            'support_ligatures': 'yes',
            'ARABIC LIGATURE ALLAH': 'no',
        })
    except Exception:
        _reshaper = None


def _reshape(text):
    if _reshaper is not None:
        return _reshaper.reshape(text)
    return arabic_reshaper.reshape(text)


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
        reshaped = _reshape(text)
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
