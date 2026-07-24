# -*- coding: utf-8 -*-
"""
قطب‌نمای قرآنی — پردازش آینه‌ای (نسخهٔ موبایل / اندروید)
بازنویسی‌شده با Kivy — همهٔ قابلیت‌های نسخهٔ دسکتاپ، بدون وابستگی به PyQt.
روی ویندوز با پایتون اجرا می‌شود و با GitHub Actions به APK تبدیل می‌شود.
"""
import os
import json
import shutil
import zipfile
import threading
import base64
from datetime import datetime

# --- شکل‌دهیِ بومیِ متنِ عربی/فارسی با Pango (فقط اندروید) ---
# اگر ارائه‌دهندهٔ Pango در بیلد موجود باشد، Kivy حروف را «متصل» و راست‌به‌چپ شکل می‌دهد
# و ویرایش/انتخاب/حذف در کادرهای متن کاملاً طبیعی می‌شود. مقدار 'pango,sdl2' یعنی اگر
# Pango نبود، خودکار به sdl2 برمی‌گردد تا برنامه هرگز کرش نکند. باید پیش از importهای kivy تنظیم شود.
if 'ANDROID_ARGUMENT' in os.environ:
    os.environ.setdefault('KIVY_TEXT', 'pango,sdl2')

from kivy.utils import platform as _kivy_platform
# روی اندروید/iOS تنظیماتِ ماوس اعمال نشود تا لمسِ انگشت به‌صورت استاندارد و روان مدیریت شود
# (فعال‌بودنِ ارائه‌دهندهٔ ماوس روی موبایل باعث تداخل با اسکرول و لمسِ دکمه‌ها می‌شود)
if _kivy_platform not in ('android', 'ios'):
    from kivy.config import Config
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition, FadeTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform

import core
import features
import ai_manager
import qref
from rtl import rtl, rtl_multiline


def _native_text_shaping():
    """True اگر ارائه‌دهندهٔ متنِ فعالِ Kivy از نوع Pango باشد (شکل‌دهیِ بومیِ عربی/فارسی)."""
    try:
        from kivy.core.text import Label as _CoreTextLabel
        return 'pango' in (getattr(_CoreTextLabel, '__module__', '') or '').lower()
    except Exception:
        return False
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# اگر پوشهٔ assets وجود داشته باشد از آن استفاده می‌کنیم؛ وگرنه فایل‌ها را از همین پوشهٔ اصلی می‌خوانیم
# (روی گیت‌هاب فایل‌ها در ریشه هستند، روی ویندوز داخل assets)
ASSET_DIR = os.path.join(BASE_DIR, 'assets')
if not os.path.isdir(ASSET_DIR):
    ASSET_DIR = BASE_DIR


def asset(name):
    return os.path.join(ASSET_DIR, name)


def _atomic_write_json(path, data, indent=2):
    """ذخیرهٔ امن (اتمیک) JSON.
    اول روی یک فایل موقت نوشته می‌شود و فقط پس از نوشتنِ کاملِ آن، با یک عملیاتِ
    جایگزینیِ اتمیک روی فایل اصلی می‌نشیند. یک نسخهٔ پشتیبان (.bak) از فایلِ سالمِ
    قبلی هم نگه داشته می‌شود تا قطع‌شدنِ ناگهانی وسطِ ذخیره، داده را خراب نکند."""
    import os as _os, json as _json, shutil as _shutil, tempfile as _tempfile
    directory = _os.path.dirname(_os.path.abspath(path)) or '.'
    try:
        if _os.path.exists(path) and _os.path.getsize(path) > 0:
            _shutil.copy2(path, path + '.bak')
    except Exception:
        pass
    fd, tmp = _tempfile.mkstemp(prefix='.tmp_', suffix='.json', dir=directory)
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8') as f:
            _json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(tmp, path)
    except Exception:
        try:
            _os.remove(tmp)
        except Exception:
            pass
        raise


def normalize_mode(mode_value):
    """یکسان‌سازی نام عملگر با فرم استانداردِ کوتاه (سازگار با نسخهٔ ویندوز)."""
    mapping = {
        "تقارن درجا فقط آیه (سوره ثابت، آیه آینه می‌شود)": "تقارن درجا فقط آیه",
        "تقارن درجا فقط سوره (آیه ثابت، سوره آینه می‌شود)": "تقارن درجا فقط سوره",
        "تقارن درجا کامل (آینه‌ی کامل)": "تقارن درجا کامل",
        "جابجایی کامل (تعویض جای سوره و آیه)": "جابجایی کامل",
    }
    return mapping.get(mode_value, mode_value)


def _normalize_item_modes(item):
    """مبدّلِ خودکار: نام عملگرِ یک کشف (و مقصدهای گروهی‌اش) را به فرم استانداردِ کوتاه تبدیل می‌کند، تا فایل‌های قدیمی یا واردشده از ویندوز دقیقاً هم‌راستا شوند."""
    if not isinstance(item, dict):
        return item
    if 'mode' in item:
        item['mode'] = normalize_mode(item.get('mode', ''))
    tgts = item.get('all_targets')
    if isinstance(tgts, list):
        for t in tgts:
            if isinstance(t, dict) and 'operator' in t:
                t['operator'] = normalize_mode(t.get('operator', ''))
    return item


# ---- ثبت فونت‌ها ----
LabelBase.register(name='arabic', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))
LabelBase.register(name='ui', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))
# فونتِ مخصوصِ جملهٔ «به نام الله برای الله» (فایلِ A Ali.ttf کنارِ main.py)
LabelBase.register(name='besmele', fn_regular=asset('A Ali.ttf'), fn_bold=asset('A Ali.ttf'))
# فونت پیش‌فرض kivy (Roboto) را هم به font.ttf تغییر می‌دهیم تا
# همهٔ ویجت‌ها (منوی کشویی Spinner، عنوان Popup، دکمه‌های ساده، فایل‌یاب) فارسی را درست نشان دهند.
LabelBase.register(name='Roboto', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))

# ---- پالت رنگ ----
C_BG = (0.05, 0.08, 0.14, 1)
C_PANEL = (1, 1, 1, 0.10)
C_PANEL_SOLID = (0.10, 0.14, 0.22, 1)
# نسخه و نشانهٔ بیلد (روی صفحهٔ خانه نشان داده می‌شود) — هر بار کد را عوض کردی این را هم بالا ببر
BUILD_VERSION = '4.1'

def _tag_multiselect(container, tags, current_str, title_text):
    """کنترلِ چندانتخابیِ برچسب‌ها (رفتار شبکه). خروجی: تابعی که رشتهٔ پیوسته برمی‌گرداند."""
    sep = chr(1548) + ' '  # ، و فاصله
    sel = set()
    for _p in str(current_str or '').replace(chr(1548), sep.strip()).split(sep.strip()):
        _p = _p.strip()
        if _p and _p != 'نامشخص':
            sel.add(_p)
    all_tags = list(tags)
    for _t in sel:
        if _t not in all_tags:
            all_tags.append(_t)
    container.add_widget(RLabel(title_text, font_size='14sp', color=C_GOLD,
                               halign='right', size_hint_y=None, height=dp(30)))
    _sv = ScrollView(size_hint_y=None, height=dp(150), bar_width=dp(4))
    _grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(6), padding=(dp(2), dp(2)))
    _grid.bind(minimum_height=_grid.setter('height'))
    _sv.add_widget(_grid)
    _btns = {}
    def _refresh():
        for _tt, _b in _btns.items():
            _on = (_tt in sel)
            _b._bg = list(C_GOLD if _on else (1, 1, 1, 0.10))
            _b.color = (0.05, 0.08, 0.14, 1) if _on else HOME_FG
            _b._state()
    def _toggle(_tt):
        if _tt in sel:
            sel.discard(_tt)
        else:
            sel.add(_tt)
        _refresh()
    for _t in all_tags:
        _cb = PillButton(_t, bg=(1, 1, 1, 0.10), fg=HOME_FG, size_hint_y=None,
                         height=dp(42), font_size='13sp', radius=14)
        _cb.bind(on_release=lambda _inst, _x=_t: _toggle(_x))
        _btns[_t] = _cb
        _grid.add_widget(_cb)
    container.add_widget(_sv)
    _refresh()
    def _get():
        return sep.join([t for t in all_tags if t in sel]) or 'نامشخص'
    return _get

BUILD_TAG = '2026-07-19'

C_GOLD = (0.95, 0.77, 0.36, 1)
C_BLUE = (0.15, 0.55, 0.92, 1)
C_PURPLE = (0.61, 0.28, 0.80, 1)
C_TEAL = (0.16, 0.70, 0.72, 1)    # turquoise for search
C_BURG = (0.45, 0.11, 0.19, 1)    # deep burgundy for the number button
C_GRAPHITE = (0.17, 0.19, 0.23, 1)  # unified refined dark graphite
C_INDIGO = (0.40, 0.36, 0.78, 1)  # calm indigo for AI section
C_NAVY = (0.13, 0.20, 0.42, 1)    # deep navy (sormeh-ei)
C_OLIVE = (0.24, 0.30, 0.13, 1)   # dark murky olive-green
C_ORANGE = (1.0, 0.60, 0.10, 1)
C_GREEN = (0.20, 0.72, 0.45, 1)
C_RED = (0.90, 0.28, 0.28, 1)
C_TEXT = (0.96, 0.97, 1, 1)
C_MUTED = (0.72, 0.78, 0.88, 1)
HOME_BTN = (0.13, 0.13, 0.16, 1)
HOME_FG = (0.97, 0.98, 1, 1)


# --- کمک‌تابع‌های گرافیکی (گرادیان پس‌زمینه و قاب نئون) ---
_BG_GRAD_CACHE = {}


def _bg_gradient():
    tex = _BG_GRAD_CACHE.get('bg')
    if tex is not None:
        return tex
    from kivy.graphics.texture import Texture
    h = 256
    top = (16, 26, 52)
    bot = (5, 8, 16)
    buf = bytearray()
    for i in range(h):
        t = i / (h - 1)
        buf += bytes((
            int(bot[0] + (top[0] - bot[0]) * t),
            int(bot[1] + (top[1] - bot[1]) * t),
            int(bot[2] + (top[2] - bot[2]) * t),
        ))
    tex = Texture.create(size=(1, h), colorfmt='rgb')
    tex.blit_buffer(bytes(buf), colorfmt='rgb', bufferfmt='ubyte')
    tex.wrap = 'clamp_to_edge'
    _BG_GRAD_CACHE['bg'] = tex
    return tex


def _neon_border(widget, color, width=1.6, alpha=0.85):
    from kivy.graphics import Color as _Color, Line as _Line
    with widget.canvas.after:
        _Color(color[0], color[1], color[2], alpha)
        ln = _Line(width=width)

    def _u(*a):
        try:
            ln.rounded_rectangle = (widget.x + dp(1), widget.y + dp(1),
                                    widget.width - dp(2), widget.height - dp(2), dp(14))
        except Exception:
            pass
    widget.bind(pos=_u, size=_u)
    Clock.schedule_once(_u, 0)


def P(text):
    """متن فارسی/عربی آمادهٔ نمایش."""
    return rtl_multiline(text)


# ==================================================================
# ویدجت‌های پایه
# ==================================================================
_MEASURE_CACHE = {}
_CORE_LABELS = {}


def _text_width(s, font_name, font_size):
    """عرض رندرشدهٔ یک رشته با همان فونت/اندازه."""
    key = (font_name, round(float(font_size), 1), s)
    v = _MEASURE_CACHE.get(key)
    if v is not None:
        return v
    try:
        from kivy.core.text import Label as CoreLabel
        ck = (font_name, round(float(font_size), 1))
        cl = _CORE_LABELS.get(ck)
        if cl is None:
            cl = CoreLabel(text='', font_name=font_name, font_size=font_size)
            _CORE_LABELS[ck] = cl
        cl.text = s
        cl.refresh()
        w = cl.content_width
    except Exception:
        w = len(s) * float(font_size) * 0.6
    if len(_MEASURE_CACHE) < 20000:
        _MEASURE_CACHE[key] = w
    return w


class RLabel(Label):
    """لیبل فارسی با شکل‌دهی راست‌به‌چپ و شکستن صحیح خطوط (رفع مشکل آینه‌ای)."""
    def __init__(self, text='', arabic=False, **kw):
        kw.setdefault('font_name', 'arabic' if arabic else 'ui')
        kw.setdefault('color', C_TEXT)
        kw.setdefault('halign', 'right')
        kw.setdefault('valign', 'middle')
        kw.setdefault('markup', False)
        self._fit_single = bool(kw.pop('fit_single', False))
        self._syncing = False
        self._base_fs = None
        self._raw = '' if text is None else str(text)
        super().__init__(**kw)
        self.bind(size=self._sync, font_size=self._sync)
        self._sync()

    def _wrap_para(self, para, max_w):
        words = para.split(' ')
        lines = []
        cur = ''
        for wd in words:
            trial = wd if not cur else cur + ' ' + wd
            if not cur or _text_width(rtl(trial), self.font_name, self.font_size) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def _sync(self, *a):
        if getattr(self, '_syncing', False):
            return
        w = self.width
        if getattr(self, '_fit_single', False):
            self._fit_single_line(w)
            return
        self.text_size = (w, None)
        raw = self._raw
        if not raw:
            self.text = ''
            return
        try:
            if w and w > 8:
                max_w = max(1.0, w - dp(6))
                out = []
                for para in raw.split('\n'):
                    if para == '':
                        out.append('')
                        continue
                    for ln in self._wrap_para(para, max_w):
                        out.append(rtl(ln))
                self.text = '\n'.join(out)
            else:
                self.text = P(raw)
        except Exception:
            self.text = P(raw)

    def _fit_single_line(self, w):
        raw = self._raw or ''
        disp = rtl(raw) if raw else ''
        self.text_size = (None, None)
        if not disp:
            self.text = ''
            return
        if w and w > 8:
            if self._base_fs is None:
                self._base_fs = self.font_size
            avail = max(1.0, w - dp(10))
            fs = self._base_fs
            guard = 0
            while fs > dp(9) and _text_width(disp, self.font_name, fs) > avail and guard < 60:
                fs -= dp(1)
                guard += 1
            if abs(fs - self.font_size) > 0.5:
                self._syncing = True
                try:
                    self.font_size = fs
                finally:
                    self._syncing = False
        self.text = disp

    def set_text(self, text):
        self._raw = '' if text is None else str(text)
        self._sync()


class RoundBox(BoxLayout):
    """جعبهٔ گوشه‌گرد با پس‌زمینه، سایهٔ نرمِ شناور و لبهٔ شیشه‌ای."""
    def __init__(self, bg=C_PANEL_SOLID, radius=18, border=None, shadow=None, **kw):
        super().__init__(**kw)
        from kivy.graphics import Line as _Line
        self._bg = bg
        self._radius = radius
        self._border = border
        # سایه فقط برای کارت‌های تقریباً مات (تا از پشتِ پنل‌های خیلی شفاف تیره دیده نشود)
        _opaque = (len(bg) < 4) or (bg[3] >= 0.5)
        self._shadow = _opaque if shadow is None else shadow
        # لبهٔ روشنِ شیشه‌ای فقط برای پنل‌های نیمه‌شفاف (حسِ glassmorphism)
        self._glass = (not _opaque) and (shadow is None)
        with self.canvas.before:
            # ۱) سایهٔ نرمِ چندلایه (هرچه دورتر، بزرگ‌تر و محوتر) → حسِ شناوربودن
            self._shadows = []
            if self._shadow:
                for k in range(4):
                    Color(0, 0, 0, 0.08)
                    sr = RoundedRectangle(radius=[radius + dp(2) * k])
                    self._shadows.append((sr, k))
            # ۲) قابِ دورِ کارت
            if border:
                self._bcol = Color(*border)
                self._brect = RoundedRectangle(radius=[radius])
            # ۳) پس‌زمینه
            self._col = Color(*bg)
            self._rect = RoundedRectangle(radius=[radius])
            # ۴) لبهٔ روشنِ شیشه‌ای (بازتابِ نور روی شیشه)
            self._rim = None
            if self._glass:
                Color(1, 1, 1, 0.10)
                self._rim = _Line(width=1.2)
            # top rim-light for every card (light-from-above glass highlight)
            Color(1, 1, 1, 0.20)
            self._toprim = _Line(width=1.3)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        for sr, k in getattr(self, '_shadows', []):
            ex = dp(1) + dp(2.5) * k
            dy = dp(2) + dp(2) * k
            sr.pos = (self.x - ex, self.y - ex - dy)
            sr.size = (self.width + 2 * ex, self.height + 2 * ex)
        if self._border:
            self._brect.pos = (self.x - dp(1.5), self.y - dp(1.5))
            self._brect.size = (self.width + dp(3), self.height + dp(3))
        if getattr(self, '_rim', None) is not None:
            try:
                self._rim.rounded_rectangle = (self.x + dp(1), self.y + dp(1),
                                               self.width - dp(2), self.height - dp(2), self._radius)
            except Exception:
                pass
        if getattr(self, '_toprim', None) is not None:
            _r = self._radius
            self._toprim.points = [self.x + _r + dp(2), self.y + self.height - dp(1.5),
                                   self.x + self.width - _r - dp(2), self.y + self.height - dp(1.5)]

    def set_bg(self, color):
        self._col.rgba = color


class ClickCard(ButtonBehavior, RoundBox):
    """کارت شیشه‌ایِ کلیک‌پذیر (برای ردیف‌های فهرست نتایج)."""
    pass


class PillButton(Button):
    """دکمهٔ گوشه‌گرد رنگی با انیمیشن فشردن."""
    def __init__(self, text='', bg=C_BLUE, fg=(1, 1, 1, 1), radius=16, font_size='16sp', **kw):
        super().__init__(**kw)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.font_name = 'ui'
        self.color = fg
        self.font_size = font_size
        self.text = P(text)
        self._bg = list(bg)
        self._radius = radius
        self._press_ins = 0
        self._grad = False
        with self.canvas.before:
            self._col = Color(1, 1, 1, 1)
            self._rect = RoundedRectangle(radius=[radius])
        self._refresh_bg()
        self.halign = 'center'
        self.valign = 'middle'
        self._base_fs = None
        self.bind(pos=self._upd, size=self._upd, state=self._state)
        self.bind(size=self._fit_text)
        self._fit_text()

    def _refresh_bg(self):
        bg = self._bg
        opaque = (len(bg) < 4) or (bg[3] >= 0.5)
        if opaque:
            self._grad = True
            top, bot = _grad_pair(bg)
            self._rect.texture = _get_grad_tex(top, bot)
            self._col.rgba = (1, 1, 1, 1)
        else:
            self._grad = False
            self._rect.texture = None
            self._col.rgba = list(bg)

    def _apply_rect(self):
        ins = getattr(self, '_press_ins', 0)
        self._rect.pos = (self.x + ins, self.y + ins)
        self._rect.size = (max(0, self.width - 2 * ins), max(0, self.height - 2 * ins))

    def _upd(self, *a):
        self._apply_rect()

    def _state(self, *a):
        # بازخوردِ لمسی: دکمه هنگامِ فشار کمی روشن‌تر و کمی فرورفته می‌شود
        self._refresh_bg()
        if self.state == 'down':
            if self._grad:
                self._col.rgba = (0.82, 0.82, 0.82, 1)
            else:
                self._col.rgba = [min(1, c * 1.25) for c in self._bg[:3]] + [self._bg[3]]
            self._press_ins = dp(2.5)
        else:
            self._press_ins = 0
        self._apply_rect()

    def _fit_text(self, *a):
        """فونت را خودکار کوچک می‌کند تا متن در عرضِ دکمه جا شود (رفعِ سرریز)."""
        disp = self.text or ''
        if not disp or not self.width or self.width < 8:
            return
        if self._base_fs is None:
            self._base_fs = self.font_size
        avail = max(1.0, self.width - dp(18))
        fs = self._base_fs
        guard = 0
        while fs > dp(8) and _text_width(disp, self.font_name, fs) > avail and guard < 80:
            fs -= dp(1)
            guard += 1
        if abs(fs - self.font_size) > 0.5:
            self.font_size = fs

    def set_text(self, text):
        self.text = P(text)
        self._fit_text()


def _html_to_lines(raw_html):
    """تبدیل HTML به متن خوانا برای نمایش داخل خودِ برنامه (بدون نیاز به مرورگر)."""
    from html.parser import HTMLParser
    import html as _htmlmod

    class _Extract(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style'):
                self._skip += 1
            elif tag == 'li':
                self.parts.append('\n• ')
            elif tag == 'br':
                self.parts.append('\n')
            elif tag in ('p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'table'):
                self.parts.append('\n')
            elif tag in ('td', 'th'):
                self.parts.append('   ')

        def handle_endtag(self, tag):
            if tag in ('script', 'style'):
                self._skip = max(0, self._skip - 1)
            elif tag in ('p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'li'):
                self.parts.append('\n')

        def handle_data(self, data):
            if not self._skip:
                self.parts.append(data)

    parser = _Extract()
    try:
        parser.feed(raw_html)
    except Exception:
        pass
    text = _htmlmod.unescape(''.join(parser.parts))
    out = []
    blank = False
    for ln in text.split('\n'):
        ln = ln.strip()
        if ln:
            out.append(ln)
            blank = False
        elif out and not blank:
            out.append('')
            blank = True
    return '\n'.join(out).strip()


def show_html_in_app(raw_html):
    """گزارش HTML را داخل خودِ برنامه (پنجرهٔ اسکرول‌شونده) نمایش می‌دهد."""
    text = _html_to_lines(raw_html)
    if not text.strip():
        toast('محتوایی برای نمایش یافت نشد.', 'گزارش')
        return
    # متن را به قطعه‌های کوچک می‌شکنیم و هر قطعه را در یک برچسبِ جدا می‌گذاریم.
    # دلیل: روی اندروید یک برچسبِ بسیار بلند، یک بافتِ (texture) گرافیکیِ غول‌آسا می‌سازد
    # که از حداکثرِ مجازِ GPU بزرگ‌تر می‌شود و «صفحهٔ سیاه/خالی» می‌دهد (روی ویندوز مشکلی ندارد).
    _lines = text.split('\n')
    _chunks = []
    _buf, _buf_len = [], 0
    for _ln in _lines:
        _buf.append(_ln)
        _buf_len += len(_ln) + 1
        if len(_buf) >= 25 or _buf_len >= 1200:
            _chunks.append('\n'.join(_buf))
            _buf, _buf_len = [], 0
    if _buf:
        _chunks.append('\n'.join(_buf))
    if not _chunks:
        _chunks = [text]

    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    sv = ScrollView(do_scroll_x=False, bar_width=dp(8), scroll_type=['bars', 'content'])
    box = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(12), spacing=dp(4))
    box.bind(minimum_height=box.setter('height'))
    # پس‌زمینهٔ تیرهٔ صریح تا متنِ روشن حتماً دیده شود
    from kivy.graphics import Color as _Clr, Rectangle as _Rect
    with box.canvas.before:
        _Clr(0.06, 0.09, 0.16, 1)
        _bg = _Rect(pos=box.pos, size=box.size)
    box.bind(pos=lambda _i, _v: setattr(_bg, 'pos', _v),
             size=lambda _i, _v: setattr(_bg, 'size', _v))
    for _ch in _chunks:
        _lbl = RLabel(_ch, font_size='15sp', halign='right', color=(1, 1, 1, 1), size_hint_y=None)
        _lbl.bind(texture_size=lambda _i, _v: setattr(_i, 'height', _v[1] + dp(8)))
        box.add_widget(_lbl)
    sv.add_widget(box)
    root.add_widget(sv)
    pop = Popup(title=P('گزارش'), content=root, size_hint=(0.96, 0.92),
                title_font='ui', title_align='center', separator_color=C_GOLD)
    close = PillButton('بستن', bg=C_RED, size_hint_y=None, height=dp(46))
    close.bind(on_release=lambda *a: pop.dismiss())
    root.add_widget(close)
    pop.open()


class _KbFocusMixin:
    """رفع مشکل کیبورد اندروید: آوردنِ خودکارِ باکس به بالای کیبورد."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(focus=self._kb_on_focus)

    def _kb_on_focus(self, _inst, val):
        # وقتی باکس با لمسِ انگشت فوکوس می‌گیرد، خودکار بالای کیبورد می‌آید
        # (فقط روی موبایل؛ روی ویندوز/دسکتاپ هیچ کاری لازم نیست و باعثِ جلوگیری از هنگ)
        if False:  # غیرفعال شد: جابه‌جاییِ صفحه هنگامِ فوکوس روی اندروید باعثِ هنگ و سیاه‌شدنِ صفحه می‌شد
            Clock.schedule_once(self._kb_ensure_visible, 0.35)
            Clock.schedule_once(self._kb_ensure_visible, 0.6)

    def _kb_ensure_visible(self, _dt):
        try:
            w = self.parent
            sv = None
            while w is not None:
                if isinstance(w, ScrollView):
                    sv = w
                    break
                w = w.parent
            if sv is None:
                return
            content = sv.children[0] if sv.children else None
            if content is None:
                return
            ch = content.height
            vh = sv.height
            if ch <= vh:
                return  # محتوا کوتاه‌تر از پنجره است؛ چیزی برای اسکرول نیست
            # ۱) گوشهٔ پایینِ ویجت در مختصاتِ پنجره (با دادنِ 0,0 دیگر دوبار جمع نمی‌شود)
            wx, wy = self.to_window(0, 0)
            # ۲) تبدیل به مختصاتِ محتوای داخلِ اسکرول
            cx, cy = content.to_local(wx, wy)
            # ۳) پایینِ باکس حدود ۵۵٪ ارتفاعِ صفحه بالاتر از لبهٔ پایینِ ویوپورت بایستد (بالای کیبورد)
            gap = vh * 0.55
            target_viewport_bottom = cy - gap
            # ۴) تبدیل به نسبتِ اسکرولِ Kivy (بین ۰ و ۱)
            s = target_viewport_bottom / float(ch - vh)
            s = max(0.0, min(1.0, s))
            Animation(scroll_y=s, d=0.25, t='out_quad').start(sv)
        except Exception:
            pass
    # توابع on_touch_down و on_touch_up قبلی حذف شدند (تداخل و کرش با کیبوردِ سیستم).


class PlainInput(_KbFocusMixin, TextInput):
    pass


class PersianTextInput(_KbFocusMixin, TextInput):
    # فیلد متنی راست‌به‌چپ که هنگام تایپ، فارسی را درست (بدون آینه‌ای) نشان می‌دهد
    def __init__(self, on_change=None, **kw):
        kw.setdefault('font_name', 'ui')
        kw.setdefault('halign', 'right')
        kw.setdefault('multiline', False)
        super().__init__(**kw)
        self._logical = ''
        self._guard = False
        self.on_change = on_change
        # با تغییرِ عرضِ باکسِ چندخطی، شکستِ خطوطِ فارسی دوباره محاسبه می‌شود
        if self.multiline:
            self.bind(width=lambda *a: self._render())

    def _wrap_para(self, para, max_w):
        """شکستنِ یک بند به خطوطِ جداگانه بر اساسِ عرضِ در دسترس (در فضای منطقی)."""
        words = para.split(' ')
        lines = []
        cur = ''
        for wd in words:
            trial = wd if not cur else cur + ' ' + wd
            if not cur or _text_width(rtl(trial), self.font_name, self.font_size) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def _display_multiline(self):
        """متنِ چندخطی را بندبند و کلمه‌به‌کلمه پیش‌شکست می‌دهد و هر خط را جداگانه
        راست‌به‌چپ می‌کند تا نه آینه‌ای شود و نه بخشی از خطِ اول به خطِ بعد بپرد."""
        logical = self._logical or ''
        if not logical:
            return ''
        try:
            pad = self.padding
            pl = pad[0] if isinstance(pad, (list, tuple)) and len(pad) >= 1 else dp(6)
            pr = pad[2] if isinstance(pad, (list, tuple)) and len(pad) >= 3 else pl
        except Exception:
            pl = pr = dp(6)
        avail = self.width - pl - pr - dp(6)
        out = []
        for para in logical.split('\n'):
            if para == '':
                out.append('')
                continue
            if avail and avail > 8:
                for ln in self._wrap_para(para, avail):
                    out.append(rtl(ln))
            else:
                out.append(rtl(para))
        return '\n'.join(out)

    def _render(self):
        self._guard = True
        try:
            if self.multiline:
                self.text = self._display_multiline()
                try:
                    self.cursor = self.get_cursor_from_index(len(self.text))
                except Exception:
                    pass
            else:
                disp = rtl(self._logical) if self._logical else ''
                self.text = disp
                if disp and disp != self._logical:
                    # متنِ نمایشی وارونه شده (SDL2): تازه‌ترین حرف در ابتدای رشتهٔ نمایشی (چپ) می‌نشیند
                    self.cursor = (0, 0)
                    Clock.schedule_once(lambda *a: setattr(self, 'scroll_x', 0), 0)
                else:
                    # بدونِ وارونگی (شکل‌دهیِ بومی یا متنِ لاتین/عددی): تازه‌ترین حرف در انتهاست
                    self.cursor = (len(disp), 0)
        finally:
            self._guard = False
        if self.on_change:
            self.on_change(self._logical)

    def insert_text(self, substring, from_undo=False):
        if self._guard or from_undo:
            return super().insert_text(substring, from_undo=from_undo)
        # رفع کرش: اگر کیبوردِ اندروید متنِ خالی فرستاد، رندر و جستجو را بی‌دلیل اجرا نکن
        if not substring:
            return None
        self._logical += substring
        self._render()
        return None

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self._guard or from_undo:
            return super().do_backspace(from_undo=from_undo, mode=mode)
        if self._logical:
            self._logical = self._logical[:-1]
            self._render()
        return None

    @property
    def query(self):
        return self._logical

    def set_logical(self, value):
        self._logical = value or ''
        self._render()

    def clear_logical(self):
        self._logical = ''
        self._guard = True
        try:
            self.text = ''
        finally:
            self._guard = False


# ---------------------------------------------------------------------------
# زیرساختِ ویرایشگرِ RTLِ درجا (نمایشِ همیشه‌شکل‌داده‌شده + ویرایشِ وسطِ متن)
# شکل‌دهیِ ۱:۱ (با حفظِ اعراب و نرمال‌سازیِ همزه) تا نگاشتِ دقیقِ مکان‌نما ممکن شود.
try:
    import arabic_reshaper as _pe_ar
    _edit_reshaper = _pe_ar.ArabicReshaper(configuration={
        'support_ligatures': 'no', 'delete_harakat': False,
        'delete_tatweel': False, 'shift_harakat_position': False})
    _EDIT_OK = True
except Exception:
    _edit_reshaper = None
    _EDIT_OK = False


def _pe_norm(s):
    if not s:
        return s
    s = s.replace('\u0648\u0654', '\u0624').replace('\u0627\u0654', '\u0623').replace('\u0627\u0655', '\u0625')
    s = s.replace('\u06cc\u0654', '\u0626').replace('\u064a\u0654', '\u0626').replace('\u0649\u0654', '\u0626')
    s = s.replace('\u0647\u0654', '\u06c0')
    return s


def _pe_cls(c):
    o = ord(c)
    if 0x0660 <= o <= 0x0669 or 0x06F0 <= o <= 0x06F9:
        return 'AN'
    if 0x0030 <= o <= 0x0039:
        return 'EN'
    if (0x0041 <= o <= 0x005A) or (0x0061 <= o <= 0x007A):
        return 'L'
    if (0x0600 <= o <= 0x06FF) or (0x0750 <= o <= 0x077F) or (0xFB50 <= o <= 0xFDFF) or (0xFE70 <= o <= 0xFEFF) or o in (0x200C, 0x200F):
        return 'R'
    return 'N'


_PE_LTRISH = ('L', 'EN', 'AN')


def _pe_reorder(R):
    """خطِ شکل‌داده‌شده (پایه RTL) را به ترتیبِ نمایشی درمی‌آورد.
    خروجی: (disp, src) که src[j] اندیسِ منطقیِ کاراکترِ جایگاهِ j است."""
    n = len(R)
    rev = list(range(n))[::-1]
    out = rev[:]
    j = 0
    while j < n:
        c = R[rev[j]]
        if _pe_cls(c) in _PE_LTRISH:
            k = j
            while k < n and (_pe_cls(R[rev[k]]) in _PE_LTRISH or (_pe_cls(R[rev[k]]) == 'N' and k + 1 < n and _pe_cls(R[rev[k + 1]]) in _PE_LTRISH)):
                k += 1
                if k < n and _pe_cls(R[rev[k - 1]]) == 'N' and _pe_cls(R[rev[k]]) not in _PE_LTRISH:
                    break
            out[j:k] = rev[j:k][::-1]
            j = k
        else:
            j += 1
    disp = ''.join(R[i] for i in out)
    return disp, out


def _pe_pure(R):
    for c in R:
        if _pe_cls(c) in ('L', 'EN', 'AN'):
            return False
    return True


class PersianEditor(_KbFocusMixin, TextInput):
    """ویرایشگرِ فارسی/عربی با نمایشِ همیشه‌درستِ راست‌به‌چپ و ویرایشِ کاملِ وسطِ متن.

    زیرِ sdl2 (بدونِ شکل‌دهیِ بومی) متنِ داخلِ کادر همیشه «شکل‌داده‌شده و متصل» است و
    هرگز آینه‌ای/بریده نمی‌شود؛ درعین‌حال کاربر می‌تواند مکان‌نما را هرجای متن ببرد و
    از وسط درج/حذف کند. متنِ منطقی جداگانه نگه داشته می‌شود؛ هر ویرایش روی آن انجام و
    دوباره شکل داده می‌شود، و مکان‌نما با نگاشتِ دقیقِ منطقی↔نمایشی همگام می‌ماند.
    زیرِ Pango (اگر روزی در بیلد فعال شود) خودِ Kivy متن را شکل می‌دهد.
    API سازگار: query / set_logical / clear_logical / attach_preview.
    """

    def __init__(self, on_change=None, **kw):
        kw.setdefault('font_name', 'ui')
        kw.setdefault('halign', 'right')
        kw.setdefault('multiline', True)
        super().__init__(**kw)
        # base_direction عمداً تنظیم نمی‌شود: زیرِ sdl2 متن را خودم از قبل
        # به ترتیبِ بصریِ راست‌به‌چپ می‌چینم؛ اگر جهتِ پایه را rtl کنیم Kivy ممکن
        # است دوباره روی متنِ ازقبل‌چیده‌شده bidi اعمال کند و خطوط را وارونه/جابه‌جا کند.
        self._logical = _pe_norm(kw.get('text', '') or '')
        self._guard = False
        self._degraded = False
        self._lines = []
        self._disp = ''
        self.on_change = on_change
        self._native = _native_text_shaping()
        self._can_map = _EDIT_OK and not self._native
        if self._native:
            if self._logical and not self.text:
                self.text = self._logical
            self.bind(text=self._on_text_native)
        else:
            self.bind(width=lambda *a: self._render(self._caret_logical()))
            self._render(len(self._logical))

    def _emit(self):
        self._update_preview()
        if self.on_change:
            try:
                self.on_change(self.query)
            except Exception:
                pass

    def _on_text_native(self, *a):
        self._logical = self.text
        self._emit()

    # ---------- شکل‌دهیِ یک خط ----------
    def _shape(self, seg):
        if not seg:
            return {'disp': '', 'src': [], 'n': 0, 'pure': True, 'log2disp': [], 'exact': True}
        if not self._can_map:
            d = rtl(seg)
            return {'disp': d, 'src': [], 'n': len(d), 'pure': True, 'log2disp': [], 'exact': False}
        try:
            R = _edit_reshaper.reshape(seg)
        except Exception:
            R = seg
        if len(R) != len(seg):
            d = rtl(seg)
            return {'disp': d, 'src': [], 'n': len(d), 'pure': True, 'log2disp': [], 'exact': False}
        disp, src = _pe_reorder(R)
        n = len(R)
        log2disp = [0] * n
        for j, li in enumerate(src):
            log2disp[li] = j
        return {'disp': disp, 'src': src, 'n': n, 'pure': _pe_pure(R), 'log2disp': log2disp, 'exact': True}

    def _line_l2d(self, sh, li):
        n = sh['n']
        if n == 0:
            return 0
        li = max(0, min(li, n))
        if not sh['exact']:
            return n - li
        if li <= 0:
            return n if sh['pure'] else sh['log2disp'][0]
        if li >= n:
            return 0 if sh['pure'] else (sh['log2disp'][n - 1] + 1)
        if sh['pure']:
            return n - li
        return sh['log2disp'][li]

    def _line_d2l(self, sh, dj):
        n = sh['n']
        if n == 0:
            return 0
        dj = max(0, min(dj, n))
        if not sh['exact']:
            return n - dj
        if dj <= 0:
            return n if sh['pure'] else sh['src'][0]
        if dj >= n:
            return 0 if sh['pure'] else (sh['src'][n - 1] + 1)
        if sh['pure']:
            return n - dj
        return sh['src'][dj]

    # ---------- ساختِ خطوط + wrap ----------
    def _avail_width(self):
        try:
            pad = self.padding
            pl = pad[0] if isinstance(pad, (list, tuple)) else dp(6)
            pr = pad[2] if isinstance(pad, (list, tuple)) and len(pad) >= 3 else pl
        except Exception:
            pl = pr = dp(6)
        # حاشیهٔ امنِ بزرگ‌تر: خطوط را کمی باریک‌تر از عرضِ واقعیِ کادر می‌شکنیم تا
        # موتورِ متنِ Kivy هرگز خطِ ازقبل‌شکسته‌شدهٔ من را دوباره نشکند (همین «شکستنِ
        # دوباره» بود که خطوط را وارونه/جابه‌جا می‌کرد).
        w = self.width - pl - pr - dp(18)
        return w if (w and w > 8) else 0

    def _tokenize(self, para):
        toks = []
        j = 0
        n = len(para)
        while j < n:
            k = j
            while k < n and para[k] != ' ':
                k += 1
            while k < n and para[k] == ' ':
                k += 1
            toks.append(para[j:k])
            j = k
        return toks

    def _wrap_para(self, para, avail):
        if para == '':
            return [(0, '')]
        if not avail:
            return [(0, para)]
        segs = []
        cur = ''
        cur_start = 0
        for tok in self._tokenize(para):
            trial = cur + tok
            if cur and _text_width(self._shape(trial)['disp'], self.font_name, self.font_size) > avail:
                segs.append((cur_start, cur))
                cur_start += len(cur)
                cur = tok
            else:
                cur = trial
        segs.append((cur_start, cur))
        return segs

    def _build(self):
        self._lines = []
        avail = self._avail_width()
        parts = self._logical.split(chr(10))
        pos = 0
        for pi, para in enumerate(parts):
            for (soff, seg) in self._wrap_para(para, avail):
                s = pos + soff
                self._lines.append((s, s + len(seg), self._shape(seg)))
            pos += len(para)
            if pi < len(parts) - 1:
                pos += 1
        self._disp = chr(10).join(l[2]['disp'] for l in self._lines)

    # ---------- نگاشتِ منطقی ↔ اندیسِ تختِ نمایش ----------
    def _log2flat(self, ci):
        ci = max(0, min(ci, len(self._logical)))
        off = 0
        for (s, e, sh) in self._lines:
            if s <= ci <= e:
                return off + self._line_l2d(sh, ci - s)
            off += len(sh['disp']) + 1
        return max(0, len(self._disp))

    def _flat2log(self, F):
        off = 0
        for (s, e, sh) in self._lines:
            L = len(sh['disp'])
            if F <= off + L:
                ci = s + self._line_d2l(sh, max(0, F - off))
                return max(0, min(ci, len(self._logical)))
            off += L + 1
        if self._lines:
            return self._lines[-1][1]
        return 0

    def _caret_logical(self):
        if getattr(self, '_degraded', False):
            return len(self._logical)
        try:
            return self._flat2log(self.cursor_index())
        except Exception:
            return len(self._logical)

    def _render(self, caret_ci=None):
        if self._native:
            return
        # ۱) ساختِ نمایشِ شکل‌گرفتهٔ من (با نگاشتِ دقیقِ مکان‌نما)
        built = True
        try:
            self._build()
            disp = self._disp
        except Exception:
            built = False
            disp = None
        # ۲) ست‌کردنِ متن در کادر؛ اگر متنِ من داخلِ Kivy خطا داد،
        #    به نمایشِ اثبات‌شدهٔ rtl_multiline برمی‌گردیم تا پنجره حتماً باز شود و هرگز کرش نکند.
        self._guard = True
        try:
            if built and disp is not None:
                try:
                    self.text = disp
                    self._degraded = False
                except Exception:
                    built = False
            if not built:
                try:
                    self.text = rtl_multiline(self._logical)
                except Exception:
                    try:
                        self.text = self._logical
                    except Exception:
                        pass
                self._degraded = True
        finally:
            self._guard = False
        # ۳) پاک‌کردنِ هرگونه انتخابِ قدیمی تا اشاره‌گرهای انتخابِ Kivy پس از
        #    بازچینشِ خطوط بی‌اعتبار/خارج‌ازمحدوده نشوند (منشأِ کرشِ پاک‌کردن+تایپ).
        try:
            self.cancel_selection()
        except Exception:
            pass
        # ۴) همگام‌سازیِ مکان‌نما با محافظتِ کامل؛ اگر هر چیزی خطا داد مکان‌نما را
        #    به (0,0) می‌بریم تا هرگز به سطرِ ناموجود اشاره نکند.
        if caret_ci is None:
            caret_ci = len(self._logical)
        caret_ci = max(0, min(caret_ci, len(self._logical)))
        try:
            if self._degraded:
                target = len(self.text)
            else:
                target = self._log2flat(caret_ci)
            self.cursor = self.get_cursor_from_index(target)
        except Exception:
            try:
                self.cursor = (0, 0)
            except Exception:
                pass

    # ---------- ویرایش ----------
    def _sel_range_logical(self):
        if getattr(self, '_degraded', False):
            return None
        try:
            if self.selection_text:
                a = self.selection_from
                b = self.selection_to
                fa, fb = (a, b) if a <= b else (b, a)
                la = self._flat2log(fa)
                lb = self._flat2log(fb)
                return (min(la, lb), max(la, lb))
        except Exception:
            pass
        return None

    def insert_text(self, substring, from_undo=False):
        if self._native:
            return super().insert_text(substring, from_undo=from_undo)
        if self._guard:
            return None
        try:
            sub = _pe_norm(substring or '')
            if not sub:
                return None
            sel = self._sel_range_logical()
            # پاک‌کردنِ انتخابِ داخلیِ Kivy پیش از تغییرِ متن، تا اشاره‌گرهای
            # قدیمیِ انتخاب به خطوطِ حذف‌شده اشاره نکنند.
            try:
                self.cancel_selection()
            except Exception:
                pass
            if sel and sel[0] != sel[1]:
                a, b = sel
                self._logical = self._logical[:a] + self._logical[b:]
                ci = a
            else:
                ci = self._caret_logical()
            ci = max(0, min(ci, len(self._logical)))
            self._logical = self._logical[:ci] + sub + self._logical[ci:]
            self._render(ci + len(sub))
            self._emit()
        except Exception:
            pass
        return None

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self._native:
            return super().do_backspace(from_undo=from_undo, mode=mode)
        if self._guard:
            return None
        try:
            sel = self._sel_range_logical()
            try:
                self.cancel_selection()
            except Exception:
                pass
            if sel and sel[0] != sel[1]:
                a, b = sel
                self._logical = self._logical[:a] + self._logical[b:]
                self._render(a)
                self._emit()
                return None
            ci = self._caret_logical()
            ci = max(0, min(ci, len(self._logical)))
            if ci <= 0:
                return None
            self._logical = self._logical[:ci - 1] + self._logical[ci:]
            self._render(ci - 1)
            self._emit()
        except Exception:
            pass
        return None

    def delete_selection(self, from_undo=False):
        # مسیرهایی مثل بریدن/جایگذاری که Kivy خودش حذفِ انتخاب را صدا می‌زند
        # را از مدلِ منطقیِ من عبور می‌دهیم تا دو مدل از هم نیفتند.
        if self._native:
            return super().delete_selection(from_undo=from_undo)
        if self._guard:
            return None
        try:
            sel = self._sel_range_logical()
            try:
                self.cancel_selection()
            except Exception:
                pass
            if sel and sel[0] != sel[1]:
                a, b = sel
                self._logical = self._logical[:a] + self._logical[b:]
                self._render(a)
                self._emit()
        except Exception:
            pass
        return None

    @property
    def query(self):
        if self._native:
            return self.text
        return self._logical

    def set_logical(self, value):
        self._logical = _pe_norm(value or '')
        self._update_preview()
        if self._native:
            if self.text != self._logical:
                self.text = self._logical
            return
        self._render(len(self._logical))

    def clear_logical(self):
        self._logical = ''
        self._update_preview()
        if self._native:
            self.text = ''
            return
        self._render(0)

    def attach_preview(self, label):
        self._preview = label
        self._update_preview()

    def _update_preview(self):
        p = getattr(self, '_preview', None)
        if p is None:
            return
        try:
            p.set_text(self._logical or '')
        except Exception:
            pass


class SeedInput(_KbFocusMixin, TextInput):
    """ورودی عددی بذر که با یک تاچ ساده فوکوس می‌گیرد و کیبورد را بالا می‌آورد
    (رفع مشکل بالا نیامدنِ کیبورد داخل ScrollView)."""
    pass


def toast(message, title='پیام', kind=None):
    # تشخیصِ خودکارِ نوعِ پیام از روی عنوان/متن (تا صدها فراخوانیِ موجود بدونِ تغییر، رنگ و نشانهٔ درست بگیرند)
    if kind is None:
        _t = (title or '') + ' ' + (message or '')
        if 'خطا' in _t:
            kind = 'error'
        elif ('✓' in _t) or ('ذخیره' in _t) or ('ثبت شد' in _t) or ('موفقیت' in _t) \
                or ('اضافه شد' in _t) or ('کپی شد' in _t):
            kind = 'success'
        elif ('یافت نشد' in _t) or ('خالی' in _t) or ('نمانده' in _t):
            kind = 'warn'
        else:
            kind = 'info'
    _styles = {
        'success': (C_GREEN, '✓'),
        'error': (C_RED, '×'),
        'warn': (C_ORANGE, '!'),
        'info': (C_GOLD, '●'),
    }
    accent, icon = _styles.get(kind, (C_GOLD, '●'))
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10))
    content.add_widget(RLabel(icon, font_size='36sp', halign='center', color=accent,
                              size_hint_y=None, height=dp(46)))
    content.add_widget(RLabel(message, font_size='16sp', halign='center'))
    p = Popup(title=P(title), content=content, size_hint=(0.85, 0.44),
              title_font='ui', title_align='center', separator_color=accent)
    btn = PillButton('باشه', bg=(C_BLUE if kind == 'info' else accent),
                     size_hint_y=None, height=dp(46))
    btn.bind(on_release=p.dismiss)
    content.add_widget(btn)
    p.open()
    _fade_in(content, 0.18)
    # پیام‌های موفقیت پس از چند لحظه خودکار و نرم محو می‌شوند
    if kind == 'success':
        def _auto(_dt):
            try:
                _a = Animation(opacity=0, d=0.35)
                _a.bind(on_complete=lambda *x: p.dismiss())
                _a.start(content)
            except Exception:
                try:
                    p.dismiss()
                except Exception:
                    pass
        Clock.schedule_once(_auto, 2.2)
    return p


def confirm(message, on_yes, title='تأیید'):
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
    content.add_widget(RLabel(message, font_size='16sp', halign='center'))
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    p = Popup(title=P(title), content=content, size_hint=(0.85, 0.42),
              title_font='ui', title_align='center', separator_color=C_GOLD)
    yes = PillButton('بله', bg=C_GREEN)
    no = PillButton('انصراف', bg=C_RED)
    def _yes(*a):
        p.dismiss()
        on_yes()
    yes.bind(on_release=_yes)
    no.bind(on_release=p.dismiss)
    row.add_widget(yes)
    row.add_widget(no)
    content.add_widget(row)
    p.open()
    return p


def prompt_text(message, initial, on_ok, title='ویرایش', ok_label='ذخیره'):
    """دیالوگِ دریافتِ یک متنِ کوتاه (برای ویرایشِ نامِ برچسب)."""
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
    content.add_widget(RLabel(message, font_size='15sp', halign='right',
                              size_hint_y=None, height=dp(30)))
    ti = PersianTextInput(multiline=False, font_name='ui', font_size='15sp',
                          background_color=(1, 1, 1, 0.95),
                          foreground_color=(0.05, 0.08, 0.14, 1),
                          padding=[dp(8), dp(14)], size_hint_y=None, height=dp(48))
    content.add_widget(ti)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    p = Popup(title=P(title), content=content, size_hint=(0.88, 0.46),
              title_font='ui', title_align='center', separator_color=C_GOLD)
    ok = PillButton(ok_label, bg=C_GREEN)
    no = PillButton('انصراف', bg=C_RED)
    def _ok(*a):
        val = ti.query.strip()
        p.dismiss()
        on_ok(val)
    ok.bind(on_release=_ok)
    no.bind(on_release=p.dismiss)
    row.add_widget(ok)
    row.add_widget(no)
    content.add_widget(row)
    p.open()
    try:
        ti.set_logical(initial or '')
    except Exception:
        pass
    return p


def _fade_in(widget, d=0.28):
    """ظاهرشدنِ نرمِ یک ویجت (محو ← نمایان) برای ورودِ روانِ کارت‌ها و پیام‌ها."""
    try:
        widget.opacity = 0
        Animation(opacity=1, d=d, t='out_quad').start(widget)
    except Exception:
        pass


def empty_state(text, hint=None, icon='۝', height=dp(160)):
    """حالتِ خالیِ دلنشین: یک نشانهٔ محو + پیامِ اصلی + یک راهنماییِ تشویقی."""
    box = BoxLayout(orientation='vertical', size_hint_y=None, height=height,
                    padding=dp(16), spacing=dp(8))
    box.add_widget(Widget(size_hint_y=1))
    box.add_widget(RLabel(icon, arabic=True, font_size='52sp', halign='center',
                          color=(C_MUTED[0], C_MUTED[1], C_MUTED[2], 0.45),
                          size_hint_y=None, height=dp(64)))
    box.add_widget(RLabel(text, font_size='16sp', bold=True, halign='center',
                          color=C_TEXT, size_hint_y=None, height=dp(30)))
    if hint:
        box.add_widget(RLabel(hint, font_size='13sp', halign='center',
                              color=C_MUTED, size_hint_y=None, height=dp(44)))
    box.add_widget(Widget(size_hint_y=1))
    _fade_in(box, 0.4)
    return box


# ==================================================================
# صفحهٔ پایه (پس‌زمینه + هدر)
# ==================================================================
# ==================================================================
# اطلاعاتِ عددیِ سوره — دکمهٔ نیلی + پاپ‌آپِ فشرده، و چیپِ تبدیلِ برچسب‌دار
# ==================================================================
C_INFO = (0.18, 0.20, 0.52, 1)   # نیلیِ تیره — دکمهٔ اطلاعات (اوپَک ← گرادیانِ خودکار)


def _info_row(label, value, color):
    # عدد دقیقاً کنارِ برچسب (در سمتِ راست) تا خواندنِ آسان
    row = RoundBox(bg=(1, 1, 1, 0.05), radius=10, shadow=False, orientation='horizontal',
                   size_hint_y=None, height=dp(36), padding=[dp(10), 0], spacing=dp(10))
    row.add_widget(Widget())
    chip = RoundBox(bg=color, radius=8, shadow=False, size_hint=(None, None),
                    size=(dp(56), dp(24)), pos_hint={'center_y': 0.5})
    chip.add_widget(RLabel(str(value), bold=True, font_size='14sp', halign='center', color=(1, 1, 1, 1)))
    lab = RLabel(str(label), font_size='14sp', halign='right', color=C_TEXT,
                 size_hint_x=None, width=dp(150))
    row.add_widget(chip)
    row.add_widget(lab)
    return row


def _ayah_ratio_bar(a, tot):
    try:
        frac = max(0.02, min(1.0, float(a) / float(tot))) if tot else 0.02
        pct = int(round(100.0 * float(a) / float(tot))) if tot else 0
    except Exception:
        frac, pct = 0.02, 0
    wrap = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(40), spacing=dp(4))
    cap = RLabel('آیهٔ %s از %s  (٪%d)' % (a, tot, pct), font_size='12sp', halign='center',
                 color=C_MUTED, size_hint_y=None, height=dp(16))
    track = RoundBox(bg=(1, 1, 1, 0.09), radius=7, shadow=False, orientation='horizontal',
                     size_hint_y=None, height=dp(14), padding=dp(2))
    track.add_widget(RoundBox(bg=C_GREEN, radius=6, shadow=False, size_hint_x=frac))
    track.add_widget(Widget(size_hint_x=max(0.0, 1.0 - frac)))
    wrap.add_widget(cap)
    wrap.add_widget(track)
    return wrap


def show_surah_info(entries):
    root = BoxLayout(orientation='vertical', padding=dp(6), spacing=dp(8))
    sv = ScrollView(do_scroll_x=False, bar_width=dp(4))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=[dp(2), dp(2)])
    box.bind(minimum_height=box.setter('height'))
    for ent in entries:
        try:
            title, s, a = ent
            s = int(s or 0)
            a = int(a or 0)
        except Exception:
            continue
        sec = RoundBox(bg=(1, 1, 1, 0.05), radius=16, shadow=False, orientation='vertical',
                       size_hint_y=None, padding=dp(9), spacing=dp(6))
        sec.bind(minimum_height=lambda i, v: setattr(i, 'height', v + dp(18)))
        nm = qref.name(s)
        htxt = ('%s — %s' % (title, nm)) if title else nm
        th = RLabel(htxt, bold=True, font_size='16sp', halign='center', color=C_GOLD,
                    size_hint_y=None, height=dp(26))
        sec.add_widget(th)
        sec.add_widget(_info_row('شمارهٔ سوره', s, C_BLUE))
        sec.add_widget(_info_row('شمارهٔ نزول', qref.nuzul(s), C_PURPLE))
        sec.add_widget(_info_row('شمارهٔ آیه', a, C_GREEN))
        sec.add_widget(_info_row('تعداد کل آیات', qref.total_ayahs(s), C_ORANGE))
        sec.add_widget(_ayah_ratio_bar(a, qref.total_ayahs(s)))
        box.add_widget(sec)
    sv.add_widget(box)
    root.add_widget(sv)
    close = PillButton('بستن', bg=C_RED, radius=14, size_hint_y=None, height=dp(44), font_size='15sp')
    root.add_widget(close)
    pop = Popup(title=P('اطلاعاتِ عددیِ سوره'), content=root, size_hint=(0.9, 0.78),
                title_font='ui', title_size='18sp', title_color=C_GOLD,
                separator_color=C_GOLD, background_color=(0.05, 0.07, 0.12, 1))
    close.bind(on_release=lambda *a: pop.dismiss())
    root.opacity = 0
    pop.open()
    Animation(opacity=1, duration=0.28).start(root)
    return pop


def info_button(entries, width=dp(108), font_size='11sp', height=None, full=False):
    b = PillButton('اطلاعات عددی', bg=C_INFO, font_size=font_size)
    if full:
        b.size_hint_x = 1
    else:
        b.size_hint_x = None
        b.width = width
    if height is not None:
        b.size_hint_y = None
        b.height = height
    b.bind(on_release=lambda *a: show_surah_info(entries() if callable(entries) else entries))
    return b


def _info_btn_row(entries, height=dp(34)):
    r = BoxLayout(size_hint_y=None, height=height, spacing=dp(6))
    r.add_widget(Widget())
    r.add_widget(info_button(entries))
    return r


def _disc_info_btn(item):
    ents = [('بذر', item.get('seed_s'), item.get('seed_a'))]
    if item.get('target_s'):
        ents.append(('مقصد', item.get('target_s'), item.get('target_a')))
    return _info_btn_row(ents)


class TransformChip(BoxLayout):
    # چیپِ ریز: سوره سمتِ راست ، آیه سمتِ چپ (هماهنگ با عنوان).
    # اول رویِ اعدادِ بذر (به رنگِ طلاییِ عنوان) مکث می‌کند، بعد شروع به تغییر.
    def __init__(self, seed_s, seed_a, tgt_s, tgt_a, **kw):
        super().__init__(orientation='horizontal', size_hint=(None, None), **kw)
        self.height = dp(30)
        self.width = dp(96)
        self.spacing = dp(4)
        self._pairs = [(str(seed_s), str(seed_a)), (str(tgt_s), str(tgt_a))]
        self._i = 0
        # ترتیبِ چیدمان (چپ→راست): اول «آیه» (چپ)، بعد «سوره» (راست)
        self.a_num = self._slot('آیه', self._pairs[0][1])
        self.s_num = self._slot('سوره', self._pairs[0][0])
        if self._pairs[0] != self._pairs[1]:
            Clock.schedule_once(self._start, 1.5 + (id(self) % 9) * 0.13)

    def _slot(self, cap, val):
        col = BoxLayout(orientation='vertical', size_hint=(None, 1), width=dp(44))
        c = RLabel(cap, font_size='9sp', halign='center', color=C_MUTED, size_hint_y=None, height=dp(12))
        n = RLabel(val, bold=True, font_size='13sp', halign='center', color=C_GOLD)
        col.add_widget(c)
        col.add_widget(n)
        self.add_widget(col)
        return n

    def _start(self, *a):
        Clock.schedule_interval(self._flip, 1.8)

    def _flip(self, *a):
        if self.get_root_window() is None:
            return False
        nxt = 1 - self._i
        ns, na = self._pairs[nxt]

        def _swap(*_):
            self.s_num.set_text(ns)
            self.a_num.set_text(na)
            self._i = nxt
            Animation(opacity=1, duration=0.55).start(self.s_num)
            Animation(opacity=1, duration=0.55).start(self.a_num)
        a1 = Animation(opacity=0.12, duration=0.55)
        a1.bind(on_complete=lambda *x: _swap())
        a1.start(self.s_num)
        Animation(opacity=0.12, duration=0.55).start(self.a_num)


class BaseScreen(Screen):
    def __init__(self, title='', show_back=True, **kw):
        super().__init__(**kw)
        self.root_layout = FloatLayout()
        add = self.root_layout.add_widget
        # پس‌زمینه
        with self.root_layout.canvas.before:
            Color(1, 1, 1, 1)
            self._bgrect = Rectangle(pos=(0, 0), size=Window.size, texture=_bg_gradient())
        Window.bind(size=lambda *a: setattr(self._bgrect, 'size', Window.size))
        try:
            self.bg_image = Image(source=asset('bg.jpg'), allow_stretch=True,
                                  keep_ratio=False, color=(1, 1, 1, 0.5),
                                  size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
            add(self.bg_image)
        except Exception:
            pass
        # ستون اصلی
        self.container = BoxLayout(orientation='vertical', size_hint=(1, 1),
                                   padding=dp(10), spacing=dp(8))
        add(self.container)
        # هدر
        header = RoundBox(bg=(1, 1, 1, 0.06), orientation='horizontal',
                          size_hint_y=None, height=dp(56), padding=dp(8), spacing=dp(6))
        if show_back:
            back = PillButton('بازگشت', bg=(1, 1, 1, 0.14), size_hint_x=None, width=dp(90),
                              font_size='14sp')
            back.bind(on_release=self.go_back)
            header.add_widget(back)
        else:
            header.add_widget(Widget(size_hint_x=None, width=dp(4)))
        self.title_label = RLabel(title, font_name='ui', bold=True, font_size='20sp',
                                  halign='center', color=C_GOLD)
        # عنوان‌ها همیشه یک‌خطی، وسط‌چین و متناسب با فضا (نه زیرِ هم، نه داخلِ دکمهٔ بازگشت)
        self.title_label._fit_single = True
        header.add_widget(self.title_label)
        header.add_widget(Widget(size_hint_x=None, width=dp(90) if show_back else dp(4)))
        self.header = header
        self.container.add_widget(header)
        self.add_widget(self.root_layout)

    def go_back(self, *a):
        self.manager.transition = SlideTransition(direction='right')
        self.manager.current = 'home'

    def body(self, widget):
        self.container.add_widget(widget)


# ==================================================================
# خانه
# ==================================================================
class HomeScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='', show_back=False, **kw)
        app = App.get_running_app()
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(4))
        content = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(6), spacing=dp(12))
        content.bind(minimum_height=content.setter('height'))

        # آیهٔ محوری متحرک در نوار بالای صفحه (خاموش‌روشن)
        try:
            self.header.height = dp(106)
            self.title_label._fit_single = False
            self.title_label.font_name = 'besmele'
            self.title_label.color = C_GOLD
            self.title_label.font_size = '45sp'
            self.title_label.set_text('به نام الله برای الله')
            # کادر شیشه‌ای بماند (بدونِ قابِ زرد)؛ فقط شهابِ نورانی دورش بچرخد
            orbit_dot(self.header, C_GOLD)
            # جملهٔ «به نام الله برای الله» نرم خاموش/روشن می‌شود
            _va = (Animation(opacity=0.4, duration=1.6) + Animation(opacity=1, duration=1.6))
            _va.repeat = True
            _va.start(self.title_label)
        except Exception:
            pass

        title = RLabel('قطب‌نمای قرآنی', bold=True, font_size='33sp', halign='center',
                       color=C_TEXT, size_hint_y=None, height=dp(46))
        subtitle = RLabel('پردازش آینه‌ای (هولوگرافیک)', font_size='14sp', halign='center',
                          color=C_MUTED, size_hint_y=None, height=dp(28))
        content.add_widget(title)
        content.add_widget(subtitle)
        content.add_widget(Widget(size_hint_y=None, height=dp(10)))
        # نشانهٔ نسخه/بیلد — برای اطمینان از اینکه دقیقاً همین کد روی گوشی اجرا می‌شود
        build_tag = RLabel('﴿ إِنَّا نَحْنُ نَزَّلْنَا الذِّکْرَ وَإِنَّا لَهُ لَحَافِظُونَ ﴾',
                           arabic=True, bold=True, font_size='18sp', halign='center', color=C_GOLD,
                           size_hint_y=1)
        # --- kateebe: glass banner framing the ayah (bigger, ornate, softly glowing) ---
        ayah_box = RoundBox(bg=(0.05, 0.08, 0.14, 0.45), orientation='vertical',
                            size_hint=(None, None), height=dp(54), radius=16,
                            padding=[dp(14), dp(6)], pos_hint={'center_x': 0.5})
        ayah_box.add_widget(build_tag)
        content.add_widget(ayah_box)
        pulse_aura(ayah_box, C_GOLD, alpha=0.6, thickness=0.8)
        def _fit_ayah(*_a):
            try:
                _tw = _text_width(rtl(build_tag._raw), build_tag.font_name, build_tag.font_size)
            except Exception:
                _tw = 0
            if _tw and _tw > 8:
                ayah_box.width = _tw + dp(52)
            else:
                Clock.schedule_once(_fit_ayah, 0.05)
        Clock.schedule_once(_fit_ayah, 0)

        # پنل شیشه‌ایِ جستجوی متن آیه یا ترجمه (بدون نیاز به اعراب دقیق)
        vsbox = RoundBox(bg=(0.05, 0.08, 0.14, 0.62), orientation='vertical',
                         size_hint_y=None, height=dp(172), padding=dp(12), spacing=dp(8))
        vsbox.add_widget(RLabel('جستجوی متن آیه یا ترجمه', bold=True, font_size='16sp',
                                halign='center', color=C_TEXT, size_hint_y=None, height=dp(26)))
        self.vs_in = PersianTextInput(hint_text=P('جستجوی متن یا شمارهٔ آیه'),
                                      font_name='arabic', halign='right', font_size='16sp',
                                      multiline=False, size_hint_y=None, height=dp(48),
                                      background_color=(1, 1, 1, 0.92),
                                      foreground_color=(0.05, 0.08, 0.14, 1))
        self.vs_in.bind(on_text_validate=lambda *a: self.search_verse())
        vsbox.add_widget(self.vs_in)
        vbtnrow = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        vbtn = PillButton('انتخاب خودکار', bg=(1, 1, 1, 0.10), fg=C_TEXT)
        vbtn.bind(on_release=lambda *a: self.search_verse())
        vbtn_all = PillButton('نمایش لیست جستجو', bg=(1, 1, 1, 0.10), fg=C_TEXT)
        vbtn_all.bind(on_release=lambda *a: self.show_all_results())
        vbtnrow.add_widget(vbtn)
        vbtnrow.add_widget(vbtn_all)
        vsbox.add_widget(vbtnrow)
        content.add_widget(vsbox)
        # شهابِ نورانی مثلِ کادرِ بالا، اما کوچک‌تر، کم‌رنگ‌تر و سبک‌تر (دنبالهٔ کوتاه‌تر)
        self._vs_orbit = pulse_aura(vsbox, C_TEAL, alpha=0.7)
        # هنگامِ تایپ در کادرِ جستجو، شهابِ آن پررنگ می‌شود (المانِ فعال = روشن‌تر)
        self.vs_in.bind(focus=lambda _i, f: self._vs_orbit['set_alpha'](1.0 if f else 0.6))

        # کارت شیشه‌ایِ نتیجهٔ جستجو (زیر کادر جستجو؛ متن طلایی/نارنجی)
        self.verse_box = RoundBox(bg=(0.05, 0.08, 0.14, 0.62), orientation='vertical',
                                  size_hint_y=None, padding=dp(14), spacing=dp(6))
        self.verse_box.bind(minimum_height=self.verse_box.setter('height'))
        self.verse_meta = RLabel('', font_size='13sp', halign='center', color=C_ORANGE,
                                 size_hint_y=None, height=dp(0))
        self.verse = RLabel('نتیجهٔ جستجوی آیه در اینجا نمایش داده می‌شود',
                            arabic=True, font_size='18sp', halign='center', color=C_MUTED,
                            size_hint_y=None, height=dp(40))
        self.verse.bind(texture_size=lambda i, v: setattr(i, 'height', max(dp(40), v[1] + dp(10))))
        self.verse_box.add_widget(self.verse_meta)
        self.verse_box.add_widget(self.verse)
        content.add_widget(self.verse_box)
        pulse_aura(self.verse_box, C_GOLD)

        # پنل ورودی بذر
        seedbox = RoundBox(bg=(1, 1, 1, 0.09), orientation='vertical', size_hint_y=None,
                           height=dp(300), padding=dp(14), spacing=dp(10))
        seedbox.add_widget(RLabel('انتخاب بذر', bold=True, font_size='17sp',
                                  halign='center', color=C_GOLD, size_hint_y=None, height=dp(28)))
        inrow = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        self.in_s = SeedInput(hint_text=P('سوره'), multiline=False, font_name='ui',
                              halign='center', font_size='18sp', input_filter='int',
                              background_color=(1, 1, 1, 0.92), foreground_color=(0.05, 0.08, 0.14, 1),
                              padding=[dp(8), dp(12)])
        self.in_a = SeedInput(hint_text=P('آیه'), multiline=False, font_name='ui',
                              halign='center', font_size='18sp', input_filter='int',
                              background_color=(1, 1, 1, 0.92), foreground_color=(0.05, 0.08, 0.14, 1),
                              padding=[dp(8), dp(12)])
        inrow.add_widget(self.in_s)
        inrow.add_widget(self.in_a)
        seedbox.add_widget(inrow)

        brow = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        b_matrix = PillButton('پردازش ماتریس', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), font_size='16sp')
        b_matrix.bind(on_release=lambda *a: self.run('matrix'))
        brow.add_widget(b_matrix)
        seedbox.add_widget(brow)

        prow = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        b_sem = PillButton('پیش‌بینی (معنا)', bg=C_GRAPHITE, fg=HOME_FG)
        b_sem.bind(on_release=lambda *a: self.run('semantic'))
        b_num = PillButton('پیش‌بینی (اعداد)', bg=C_GRAPHITE, fg=HOME_FG)
        b_num.bind(on_release=lambda *a: self.run('numeric'))
        prow.add_widget(b_sem)
        prow.add_widget(b_num)
        seedbox.add_widget(prow)
        drow = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(0))
        drow.add_widget(Widget(size_hint_x=0.25))
        b_exp = PillButton('دفترِ پژوهش', bg=C_GRAPHITE, fg=HOME_FG, font_size='15sp', size_hint_x=0.5)
        b_exp.bind(on_release=lambda *a: self.nav('experiment'))
        drow.add_widget(b_exp)
        drow.add_widget(Widget(size_hint_x=0.25))
        seedbox.add_widget(drow)
        content.add_widget(seedbox)
        pulse_aura(seedbox, C_GREEN)

        # پنل دستیار هوش مصنوعی: ورود به گفتگو + تنظیمات کلید API
        aibox = RoundBox(bg=(0.05, 0.08, 0.14, 0.62), orientation='vertical', size_hint_y=None,
                         height=dp(118), padding=dp(12), spacing=dp(8))
        aibox.add_widget(RLabel('دستیار هوش مصنوعی', bold=True, font_size='16sp',
                                halign='center', color=C_GOLD, size_hint_y=None, height=dp(26)))
        airow = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        b_chat = PillButton('گفتگو با هوش مصنوعی', bg=C_GRAPHITE, fg=HOME_FG, font_size='15sp')
        b_chat.bind(on_release=lambda *a: open_chat_chooser())
        b_set = PillButton('تنظیمات', bg=(0.20, 0.24, 0.32, 1), fg=C_TEXT, size_hint_x=None,
                           width=dp(110), font_size='14sp')
        b_set.bind(on_release=lambda *a: open_ai_settings())
        airow.add_widget(b_chat)
        airow.add_widget(b_set)
        aibox.add_widget(airow)
        content.add_widget(aibox)
        pulse_aura(aibox, C_INDIGO)

        # کاشی‌های ناوبری
        grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(10))
        grid.bind(minimum_height=grid.setter('height'))
        nav = [
            ('لابراتوار کشفیات', C_GREEN, 'lab'),
            ('گلچین برگزیده', C_GOLD, 'featured'),
            ('جستجوی کشفیات', C_BLUE, 'search'),
            ('مدیریت برچسب‌ها', C_PURPLE, 'tags'),
            ('رسانه و معرفی', C_ORANGE, 'media'),
            ('راهنما', (0.3, 0.4, 0.55, 1), 'guide'),
            ('پشتیبان و بازیابی', (0.25, 0.5, 0.6, 1), 'backup'),
            ('درباره', (0.4, 0.35, 0.5, 1), 'about'),
        ]
        def _tint(col, f=0.30):
            return [c * f for c in col[:3]] + [1]
        for label, color, target in nav:
            b = PillButton(label, bg=_tint(color), fg=HOME_FG, size_hint_y=None,
                           height=dp(72), font_size='15sp', radius=16)
            # شهابِ کوچک‌ترِ کم‌رنگ‌تر با دنبالهٔ کوتاه دورِ هر دکمه (سبک‌تر برای CPU چون تعدادشان زیاد است)
            pulse_aura(b, color, alpha=0.7, thickness=0.85)
            b.bind(on_release=lambda inst, t=target: self.nav(t))
            grid.add_widget(b)
        content.add_widget(grid)
        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        scroll.add_widget(content)
        self.body(scroll)

    def _seed(self):
        try:
            s = int(core.conv(self.in_s.text.strip()))
            a = int(core.conv(self.in_a.text.strip()))
            return s, a
        except Exception:
            toast('لطفاً شمارهٔ سوره و آیهٔ معتبر وارد کنید.', 'خطا')
            return None

    def run(self, kind):
        seed = self._seed()
        if not seed:
            return
        app = App.get_running_app()
        s, a = seed
        if kind == 'matrix':
            fs, fa, is_fb, msg = app.data.apply_circular(s, a)
            if fs is None:
                toast('آیهٔ معتبر یافت نشد.', 'خطا')
                return
            scr = self.manager.get_screen('matrix')
            scr.show(fs, fa)
            self.manager.transition = SlideTransition(direction='left')
            self.manager.current = 'matrix'
        else:
            found = app.data.find_seed(s, a)
            if not found:
                toast('آیهٔ مورد نظر در دیتابیس یافت نشد.', 'خطا')
                return
            fs, fa = found
            scr = self.manager.get_screen('predict')
            scr.show(fs, fa, kind)
            self.manager.transition = SlideTransition(direction='left')
            self.manager.current = 'predict'

    def nav(self, target):
        scr = self.manager.get_screen(target)
        if hasattr(scr, 'refresh'):
            scr.refresh()
        self.manager.transition = SlideTransition(direction='left')
        self.manager.current = target

    def _verse_arb(self, s, a):
        try:
            v = App.get_running_app().data.get(s, a)
        except Exception:
            v = None
        if isinstance(v, dict):
            return v.get('arb', '') or ''
        return ''

    def _show_verse_result(self, s, a):
        arb = self._verse_arb(s, a)
        self.verse.color = C_GOLD
        self.verse.set_text(('« %s »' % arb) if arb else '« آیه یافت شد »')
        self.verse_meta.color = C_ORANGE
        self.verse_meta.set_text('سوره %s ، آیه %s' % (s, a))
        self.verse_meta.height = dp(24)
        try:
            self.in_s.text = str(s)
            self.in_a.text = str(a)
        except Exception:
            pass

    def search_verse(self):
        app = App.get_running_app()
        q = (self.vs_in.query or '').strip()
        if not q:
            toast('لطفاً بخشی از متن آیه یا ترجمه را وارد کنید.', 'جستجو')
            return
        if getattr(self, '_searching', False):
            return
        self._searching = True

        def _work():
            try:
                res = app.data.find_by_text(q)
                err = None
            except Exception as ex:
                res, err = None, str(ex)

            def _done(dt):
                self._searching = False
                if err:
                    toast('خطا در جستجو: %s' % err, 'خطا')
                    return
                if not res:
                    self.verse_meta.set_text('')
                    self.verse_meta.height = dp(0)
                    self.verse.color = C_RED
                    self.verse.set_text('آیه‌ای مطابق این متن یافت نشد')
                    toast('آیه‌ای با این متن پیدا نشد؛ دکمهٔ «نمایش همه» را امتحان کنید.', 'یافت نشد')
                    return
                s, a = res
                self._show_verse_result(s, a)

            Clock.schedule_once(_done, 0)

        threading.Thread(target=_work, daemon=True).start()

    def _pick_result(self, s, a, popup=None):
        self._show_verse_result(s, a)
        if popup is not None:
            try:
                popup.dismiss()
            except Exception:
                pass

    def show_all_results(self):
        app = App.get_running_app()
        q = (self.vs_in.query or '').strip()
        if not q:
            toast('ابتدا واژه یا بخشی از متن را وارد کنید.', 'جستجو')
            return
        if getattr(self, '_searching', False):
            return
        self._searching = True
        # پیامِ «لطفاً صبر کنید» فقط تا زمانِ آماده‌شدنِ نتایج نمایش داده می‌شود و سپس بسته می‌شود
        self._wait_popup = toast('در حال جستجو…', 'لطفاً صبر کنید')

        def _work():
            try:
                results = app.data.search_all(q, limit=2000)
                err = None
            except Exception as ex:
                results, err = None, str(ex)

            def _done(dt):
                self._searching = False
                _wp = getattr(self, '_wait_popup', None)
                if _wp is not None:
                    try:
                        _wp.dismiss()
                    except Exception:
                        pass
                    self._wait_popup = None
                if err:
                    toast('خطا در جستجو: %s' % err, 'خطا')
                    return
                if not results:
                    toast('هیچ آیه‌ای برای این عبارت پیدا نشد.', 'یافت نشد')
                    return
                self._build_results_popup(q, results)

            Clock.schedule_once(_done, 0)

        threading.Thread(target=_work, daemon=True).start()

    def _build_results_popup(self, q, results):
        # --- اسکرول بی‌پایان: دستهٔ نخست فوری نمایش، بقیه هنگام اسکرول بارگذاری ---
        is_num = q and core.conv(q).strip().isdigit()
        head_txt = ('%d آیه با شمارهٔ «%s»' % (len(results), q)) if is_num \
            else ('%d نتیجه برای «%s» (از بیشترین تطابق)' % (len(results), q))

        popup = Popup(title=P('نتایج جستجو'), size_hint=(0.96, 0.92))
        root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        header = RLabel(head_txt, bold=True, font_size='15sp', halign='center', color=C_GOLD,
                        size_hint_y=None, height=dp(30))
        root.add_widget(header)

        sv = ScrollView(do_scroll_x=False, bar_width=dp(6), scroll_type=['bars', 'content'])
        grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(2))
        grid.bind(minimum_height=grid.setter('height'))
        sv.add_widget(grid)
        root.add_widget(sv)

        BATCH = 40
        state = {'shown': 0, 'loading': False}

        def _make_row(r):
            s, a = r['s'], r['a']
            arb = r.get('arb', '') or ''
            pers = r.get('pers', '') or ''
            arb_s = (arb[:75] + '…') if len(arb) > 75 else arb
            pers_s = (pers[:80] + '…') if len(pers) > 80 else pers
            card = ClickCard(bg=(0.11, 0.14, 0.22, 0.98), border=C_GOLD, orientation='vertical',
                             size_hint_y=None, height=dp(140), padding=dp(8), spacing=dp(2))
            card.add_widget(_rev_badge(s, halign='left', height=dp(14)))
            card.add_widget(RLabel('سوره %s ، آیه %s' % (s, a), font_size='12sp',
                                   halign='right', color=C_ORANGE, size_hint_y=None, height=dp(20)))
            card.add_widget(RLabel(arb_s, arabic=True, font_size='15sp', halign='right',
                                   color=C_TEXT, size_hint_y=None, height=dp(46)))
            card.add_widget(RLabel(pers_s, font_size='13sp', halign='right',
                                   color=C_MUTED, size_hint_y=None, height=dp(36)))
            card.bind(on_release=lambda inst, ss=s, aa=a: self._pick_result(ss, aa, popup))
            _fade_in(card)
            return card

        def _load_batch(*a):
            start = state['shown']
            chunk = results[start:start + BATCH]

            # رندرِ تکه‌تکهٔ کارت‌ها (هر فریم ۳ کارت) تا پاپ‌آپ هنگام باز شدن گیر نکند
            def _add_incremental_rows(items):
                if not items:
                    state['shown'] = min(len(results), start + BATCH)
                    header.set_text('%s — %d از %d' % (head_txt, state['shown'], len(results)))
                    state['loading'] = False
                    return
                for r in items[:3]:
                    grid.add_widget(_make_row(r))
                Clock.schedule_once(lambda dt: _add_incremental_rows(items[3:]), 0.01)

            _add_incremental_rows(chunk)

        def _on_scroll(inst, val):
            # scroll_y=0 یعنی انتهای فهرست؛ نزدیک انتها که رسیدیم دستهٔ بعدی را بیاور
            if state['loading'] or state['shown'] >= len(results):
                return
            if val <= 0.15:
                state['loading'] = True
                Clock.schedule_once(_load_batch, 0)

        sv.bind(scroll_y=_on_scroll)

        close = PillButton('بستن', bg=(1, 1, 1, 0.12), fg=C_TEXT, size_hint_y=None, height=dp(46))
        close.bind(on_release=lambda *a: popup.dismiss())
        root.add_widget(close)
        popup.content = root
        popup.open()
        _load_batch()   # دستهٔ نخست بلافاصله نمایش داده می‌شود


# ==================================================================
# کارت آیه (مشترک)
# ==================================================================
# ------------------------------------------------------------------
# مدیریت چرخهٔ عمر انیمیشن‌های نوری (رفع نشت انیمیشن و آزادسازی ترد اصلی)
# ------------------------------------------------------------------
_LIVE_GLOWS = []   # [(anim, target_color, widget)]


def _register_glow(anim, target, widget):
    """هر انیمیشن تکرارشونده را ثبت می‌کند تا بعداً بتوان متوقف‌ش‌ کرد."""
    _LIVE_GLOWS.append((anim, target, widget))
    if len(_LIVE_GLOWS) > 80:
        _prune_glows()


def _prune_glows():
    """انیمیشن ویجت‌هایی که دیگر روی صفحه نیستند را لغو می‌کند (جلوگیری از اشباع ترد UI)."""
    alive = []
    for anim, target, widget in _LIVE_GLOWS:
        try:
            if widget is not None and widget.get_root_window() is None:
                anim.cancel(target)
            else:
                alive.append((anim, target, widget))
        except Exception:
            pass
    _LIVE_GLOWS[:] = alive


def apply_glow(widget, color=None, speed=1.4, width=1.6, hi=0.85, lo=0.12):
    """نور افکتی نرم که دور یک کارت می‌تپد/می‌چرخد.
    width = ضخامتِ خط، hi/lo = بیشینه/کمینهٔ شفافیتِ چشمک."""
    from kivy.graphics import Color as _Color, Line as _Line
    col = color or C_GOLD
    with widget.canvas.after:
        gc = _Color(col[0], col[1], col[2], lo)
        gl = _Line(width=width)

    def _upd(*a):
        try:
            gl.rounded_rectangle = (widget.x + dp(1), widget.y + dp(1),
                                    widget.width - dp(2), widget.height - dp(2), dp(14))
        except Exception:
            pass
    widget.bind(pos=_upd, size=_upd)
    Clock.schedule_once(_upd, 0)
    anim = Animation(a=hi, duration=speed) + Animation(a=lo, duration=speed)
    anim.repeat = True
    anim.start(gc)
    _register_glow(anim, gc, widget)
    return gl


def _make_glow_texture(size=64):
    """یک بافتِ نرمِ نورانی (محو به سمتِ لبه‌ها) برای شهاب می‌سازد."""
    from kivy.graphics.texture import Texture
    import math as _m
    tex = Texture.create(size=(size, size), colorfmt='rgba')
    c = (size - 1) / 2.0
    buf = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            dx = (x - c) / c
            dy = (y - c) / c
            d2 = dx * dx + dy * dy
            a = _m.exp(-4.5 * d2) if d2 <= 1.0 else 0.0
            j = (y * size + x) * 4
            buf[j] = 255
            buf[j + 1] = 255
            buf[j + 2] = 255
            buf[j + 3] = int(255 * a)
    tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
    tex.mag_filter = 'linear'
    tex.min_filter = 'linear'
    return tex


_GLOW_TEX = None


def _get_glow_tex():
    global _GLOW_TEX
    if _GLOW_TEX is None:
        try:
            _GLOW_TEX = _make_glow_texture()
        except Exception:
            _GLOW_TEX = None
    return _GLOW_TEX


def orbit_dot(widget, color=None, period=5.5, scale=1.0, fps=60, alpha=1.0, trail=30):
    """شهابِ نورانیِ نرم: همهٔ نورها با بافتِ محوشونده (fade) کشیده می‌شوند تا لبهٔ تیز نداشته باشند؛ سرِ درخشان + دنبالهٔ گرادیانی که دورِ لبهٔ کادر می‌چرخد.
    alpha = شدتِ روشناییِ کلی (برای کم‌رنگ‌کردنِ المان‌های غیرفعال)، trail = تعدادِ قطعاتِ دنباله (کمتر = سبک‌تر برای CPU)."""
    import math
    from kivy.graphics import Color as _Color, Ellipse as _Ellipse
    col = color or C_GOLD
    r, g, b = col[0], col[1], col[2]
    base = dp(14) * scale
    TRAIL = max(4, int(trail))
    tex = _get_glow_tex()
    segs = []
    cols = []   # (Color, base_alpha) — برای تنظیمِ زندهٔ شدتِ روشنایی
    with widget.canvas.after:
        # دنبالهٔ گرادیانی: frac=0 نوکِ دم (طلایی/محو)، frac=1 نزدیکِ سر (سفیدِ داغ)
        for i in range(TRAIL):
            frac = i / float(TRAIL - 1)
            mix = frac ** 2
            cr = r + (1.0 - r) * mix
            cg = g + (1.0 - g) * mix
            cb = b + (1.0 - b) * mix
            a = 0.9 * (frac ** 1.5)
            _ci = _Color(cr, cg, cb, a * alpha)
            cols.append((_ci, a))
            e = _Ellipse(texture=tex)
            segs.append((e, frac))
        # بلومِ بزرگِ نرمِ دورِ سر
        _cbloom = _Color(r, g, b, 0.5 * alpha)
        cols.append((_cbloom, 0.5))
        bloom = _Ellipse(texture=tex)
        # مغزِ درخشانِ سفیدتاب
        _ccore = _Color(1.0, 0.97, 0.85, 0.95 * alpha)
        cols.append((_ccore, 0.95))
        core = _Ellipse(texture=tex)
        # جرقهٔ سفیدِ داغِ نوکِ سر
        _cspark = _Color(1, 1, 1, 1 * alpha)
        cols.append((_cspark, 1.0))
        spark = _Ellipse(texture=tex)
    state = {'t': 0.0, 'mul': alpha}

    def _pos(tt, w, h, x0, y0):
        per = 2.0 * (w + h)
        d = (tt % 1.0) * per
        if d < w:
            return x0 + d, y0
        d -= w
        if d < h:
            return x0 + w, y0 + d
        d -= h
        if d < w:
            return x0 + w - d, y0 + h
        d -= w
        return x0, y0 + h - d

    def _put(e, cx, cy, sz):
        e.pos = (cx - sz / 2.0, cy - sz / 2.0)
        e.size = (sz, sz)

    def _tick(dt):
        try:
            w, h = widget.width, widget.height
            x0, y0 = widget.x, widget.y
            if w <= 0 or h <= 0:
                return
            state['t'] = (state['t'] + dt / max(0.1, period)) % 1.0
            t = state['t']
            per = 2.0 * (w + h)
            tail_len = (base * 12.0) / per
            for e, frac in segs:
                tt = t - tail_len * (1.0 - frac)
                px, py = _pos(tt, w, h, x0, y0)
                sz = base * (0.5 + 1.7 * (frac ** 1.3))
                _put(e, px, py, sz)
            hx, hy = _pos(t, w, h, x0, y0)
            twinkle = 1.0 + 0.12 * math.sin(t * 6.2832 * 5)
            _put(bloom, hx, hy, base * 4.2 * twinkle)
            _put(core, hx, hy, base * 1.7)
            _put(spark, hx, hy, base * 0.9)
        except Exception:
            pass

    Clock.schedule_interval(_tick, 1.0 / max(1, fps))

    def _set_alpha(m):
        state['mul'] = m
        for _ci, _ba in cols:
            try:
                _ci.a = _ba * m
            except Exception:
                pass

    return {'tick': _tick, 'set_alpha': _set_alpha}



# ==================================================================
# طراحیِ تازهٔ نورها: هالهٔ تشعشعیِ تپنده + گرادیانِ دکمه‌ها + نورِ چرخانِ دایره‌ای
# (نرم، تپنده، و سبک برای CPU/GPU؛ جنسِ نور مثلِ دنبالهٔ نرمِ شهاب)
# ==================================================================

_GRAD_TEX_CACHE = {}


def _make_grad_texture(c_top, c_bottom, size=64):
    # بافتِ گرادیانِ عمودی؛ ردیفِ پایین = c_bottom و ردیفِ بالا = c_top
    from kivy.graphics.texture import Texture
    h = size
    buf = bytearray()
    for i in range(h):
        t = i / float(h - 1)
        r = int(255 * (c_bottom[0] + (c_top[0] - c_bottom[0]) * t))
        g = int(255 * (c_bottom[1] + (c_top[1] - c_bottom[1]) * t))
        b = int(255 * (c_bottom[2] + (c_top[2] - c_bottom[2]) * t))
        a0 = c_bottom[3] if len(c_bottom) > 3 else 1.0
        a1 = c_top[3] if len(c_top) > 3 else 1.0
        a = int(255 * (a0 + (a1 - a0) * t))
        buf += bytes((max(0, min(255, r)), max(0, min(255, g)),
                      max(0, min(255, b)), max(0, min(255, a))))
    tex = Texture.create(size=(1, h), colorfmt='rgba')
    tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
    tex.wrap = 'clamp_to_edge'
    return tex


def _grad_pair(bg):
    # از یک رنگِ پایه، جفت‌رنگِ گرادیانِ چشم‌نواز می‌سازد (بالا روشن‌تر و کمی چرخشِ فام)
    import colorsys
    r, g, b = bg[0], bg[1], bg[2]
    a = bg[3] if len(bg) > 3 else 1.0
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    l_top = max(0.0, min(1.0, ll * 0.82 + 0.02))
    s_top = min(1.0, ss * 1.10 + 0.05)
    h_top = (hh + 0.02) % 1.0
    top = colorsys.hls_to_rgb(h_top, l_top, s_top)
    l_bot = max(0.0, ll * 0.42)
    s_bot = min(1.0, ss * 1.14 + 0.05)
    h_bot = (hh - 0.015) % 1.0
    bot = colorsys.hls_to_rgb(h_bot, l_bot, s_bot)
    return (top[0], top[1], top[2], a), (bot[0], bot[1], bot[2], a)


def _get_grad_tex(top, bot):
    key = (tuple(round(c, 3) for c in top), tuple(round(c, 3) for c in bot))
    tex = _GRAD_TEX_CACHE.get(key)
    if tex is None:
        try:
            tex = _make_grad_texture(top, bot)
        except Exception:
            tex = None
        _GRAD_TEX_CACHE[key] = tex
    return tex


def _aura_perim_point(f, w, h, x0, y0):
    # نقطه‌ای روی محیطِ مستطیل، متناسب با f از 0 تا 1
    per = 2.0 * (w + h)
    d = (f % 1.0) * per
    if d < w:
        return x0 + d, y0
    d -= w
    if d < h:
        return x0 + w, y0 + d
    d -= h
    if d < w:
        return x0 + w - d, y0 + h
    d -= w
    return x0, y0 + h - d


def pulse_aura(widget, color=None, speed=2.2, thickness=1.0, hi=0.12, lo=0.03,
               alpha=1.0, radius=None, thin=None):
    # حاشیهٔ نورانیِ «بهم‌پیوسته» که دورِ کلِ کادر خاموش/روشن می‌تپد.
    # همان جنسِ نرمِ دنبالهٔ نور است: چند خطِ گوشه‌گردِ هم‌مرکز با شفافیتِ کم
    # روی هم می‌نشینند و یک نوارِ نرمِ پیوسته می‌سازند (نه نقطه‌های جدا).
    # رنگ‌ها تیره‌تر و کم‌نورترند و فقط شفافیت انیمیت می‌شود (بسیار سبک).
    from kivy.graphics import Color as _Color, Line as _Line
    col = color or C_GOLD
    r, g, b = col[0] * 0.78, col[1] * 0.78, col[2] * 0.78
    LAYERS = 5
    st = {'built': False, 'lines': [], 'toplines': [], 'col': None, 'core': None, 'top': None,
          'anim': None, 'anim2': None, 'animt': None, 'rad': radius}

    def _rad():
        if st['rad'] is not None:
            return st['rad']
        return getattr(widget, '_radius', None) or dp(16)

    def _start(mult):
        c = st.get('col')
        cc = st.get('core')
        _h = max(0.0, min(1.0, hi * mult))
        _l = max(0.0, min(1.0, lo * mult))
        if c is not None:
            if st.get('anim') is not None:
                try:
                    st['anim'].cancel(c)
                except Exception:
                    pass
            an = (Animation(a=_h, duration=speed, t='in_out_sine')
                  + Animation(a=_l, duration=speed, t='in_out_sine'))
            an.repeat = True
            st['anim'] = an
            an.start(c)
            _register_glow(an, c, widget)
        if cc is not None:
            if st.get('anim2') is not None:
                try:
                    st['anim2'].cancel(cc)
                except Exception:
                    pass
            _hc = max(0.0, min(1.0, _h * 0.9))
            _lc = max(0.0, min(1.0, _l * 0.9))
            an2 = (Animation(a=_hc, duration=speed, t='in_out_sine')
                   + Animation(a=_lc, duration=speed, t='in_out_sine'))
            an2.repeat = True
            st['anim2'] = an2
            an2.start(cc)
            _register_glow(an2, cc, widget)
        ct = st.get('top')
        if ct is not None:
            if st.get('animt') is not None:
                try:
                    st['animt'].cancel(ct)
                except Exception:
                    pass
            _ht = max(0.0, min(1.0, hi * mult * 1.9))
            _lt = max(0.0, min(1.0, lo * mult * 1.9))
            ant = (Animation(a=_ht, duration=speed, t='in_out_sine')
                   + Animation(a=_lt, duration=speed, t='in_out_sine'))
            ant.repeat = True
            st['animt'] = ant
            ant.start(ct)
            _register_glow(ant, ct, widget)

    def _reposition(*a):
        if not st['built']:
            return
        w, h = widget.width, widget.height
        if w <= 1 or h <= 1:
            return
        rad = _rad()
        for ln in st['lines']:
            ln.rounded_rectangle = (widget.x, widget.y, w, h, rad)
        for ln in st['toplines']:
            ln.points = [widget.x + rad, widget.y + h,
                         widget.x + w - rad, widget.y + h]

    def _build(*a):
        if st['built']:
            return
        w, h = widget.width, widget.height
        if w <= 1 or h <= 1:
            return
        rad = _rad()
        base = dp(0.8)
        step = dp(1.6) * thickness
        with widget.canvas.after:
            st['col'] = _Color(r, g, b, lo * alpha)
            for _i in range(LAYERS):
                lw = base + (LAYERS - 1 - _i) * step
                st['lines'].append(_Line(
                    rounded_rectangle=(widget.x, widget.y, w, h, rad), width=lw))
            # neon core line removed: keep the aura soft, dim and thin
            st['top'] = _Color(min(1.0, r + 0.06), min(1.0, g + 0.06),
                               min(1.0, b + 0.06), lo * alpha)
            for _i in range(3):
                lw = base + (3 - 1 - _i) * step * 1.2
                st['toplines'].append(_Line(
                    points=[widget.x + rad, widget.y + h,
                            widget.x + w - rad, widget.y + h], width=lw))
        st['built'] = True
        _reposition()
        _start(alpha)

    widget.bind(pos=_reposition, size=lambda *a: (_build(), _reposition()))
    Clock.schedule_once(lambda *a: (_build(), _reposition()), 0)

    return {'set_alpha': lambda m: _start(m), 'state': st}


def orbit_ring(widget, color=None, period=3.8, fps=45, trail=20):
    # نورِ شهابیِ نرم که روی مسیرِ «دایره‌ای» دورِ یک دکمه می‌چرخد،
    # همراه با هالهٔ مشکیِ نرم دورِ محیطِ دکمه (به‌جای کادرِ مستطیلی).
    import math
    from kivy.graphics import Color as _Color, Ellipse as _Ellipse
    col = color or C_GOLD
    r, g, b = col[0], col[1], col[2]
    tex = _get_glow_tex()
    base = dp(12)
    TRAIL = max(4, int(trail))
    segs = []
    with widget.canvas.after:
        _Color(0, 0, 0, 0.55)
        halo = _Ellipse(texture=tex)
        for i in range(TRAIL):
            frac = i / float(TRAIL - 1)
            mix = frac ** 2
            cr = r + (1.0 - r) * mix
            cg = g + (1.0 - g) * mix
            cb = b + (1.0 - b) * mix
            _Color(cr, cg, cb, 0.9 * (frac ** 1.5))
            segs.append((_Ellipse(texture=tex), frac))
        _Color(r, g, b, 0.5)
        bloom = _Ellipse(texture=tex)
        _Color(1.0, 0.97, 0.85, 0.95)
        core = _Ellipse(texture=tex)
        _Color(1, 1, 1, 1)
        spark = _Ellipse(texture=tex)
    state = {'t': 0.0}

    def _put(e, cx, cy, sz):
        e.pos = (cx - sz / 2.0, cy - sz / 2.0)
        e.size = (sz, sz)

    def _cpos(f, cx, cy, rad):
        ang = 2.0 * math.pi * (f % 1.0) - math.pi / 2.0
        return cx + rad * math.cos(ang), cy + rad * math.sin(ang)

    def _tick(dt):
        try:
            w, h = widget.width, widget.height
            if w <= 0 or h <= 0:
                return
            cx, cy = widget.center_x, widget.center_y
            rad = max(w, h) / 2.0 + dp(7)
            _put(halo, cx, cy, max(w, h) + dp(34))
            state['t'] = (state['t'] + dt / max(0.1, period)) % 1.0
            t = state['t']
            tail = 0.16
            for e, frac in segs:
                tt = t - tail * (1.0 - frac)
                px, py = _cpos(tt, cx, cy, rad)
                sz = base * (0.5 + 1.5 * (frac ** 1.3))
                _put(e, px, py, sz)
            hx, hy = _cpos(t, cx, cy, rad)
            _put(bloom, hx, hy, base * 3.4)
            _put(core, hx, hy, base * 1.6)
            _put(spark, hx, hy, base * 0.9)
        except Exception:
            pass

    Clock.schedule_interval(_tick, 1.0 / max(1, fps))
    return {'tick': _tick}


def verse_card(mode, s, a, arb, pers, is_seed=False, is_fallback=False, reason='',
               on_save=None, score_text='', on_select=None, selected=False):
    bg = (0.16, 0.13, 0.05, 1) if is_seed else ((0.22, 0.08, 0.08, 1) if is_fallback else (0.10, 0.14, 0.22, 1))
    border = C_GOLD if is_seed else (C_RED if is_fallback else None)
    card = RoundBox(bg=bg, border=border, orientation='vertical', size_hint_y=None,
                    padding=dp(12), spacing=dp(6))
    card.add_widget(_rev_badge(s, halign='left'))
    head = RLabel(f'{mode}   سوره {s} ، آیه {a}', bold=True, font_size='15sp',
                  color=(C_GOLD if is_seed else C_ORANGE), halign='right', size_hint_y=None)
    head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
    card.add_widget(head)
    try:
        card.add_widget(_info_btn_row([('', s, a)]))
    except Exception:
        pass
    if score_text:
        sc = RLabel(score_text, font_size='13sp', color=C_MUTED, halign='right', size_hint_y=None)
        sc.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(sc)
    arb_l = RLabel(f'« {arb} »', arabic=True, font_size='20sp', halign='center',
                   color=C_TEXT, size_hint_y=None)
    arb_l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
    card.add_widget(arb_l)
    pers_l = RLabel(pers, font_size='14sp', halign='center', color=C_MUTED, size_hint_y=None)
    pers_l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
    card.add_widget(pers_l)
    if is_fallback and reason:
        warn = RLabel('' + reason, font_size='12sp', halign='right', color=C_RED, size_hint_y=None)
        warn.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(warn)
    if on_select is not None:
        _sb = PillButton('انتخاب شد ✓' if selected else 'انتخاب این مقصد',
                         bg=C_GREEN if selected else C_BLUE, size_hint_y=None, height=dp(42), font_size='14sp')
        _sb.bind(on_release=lambda *x: on_select())
        card.add_widget(_sb)
    elif on_save:
        btn = PillButton('ثبت این کشف', bg=C_GREEN, size_hint_y=None, height=dp(42), font_size='14sp')
        btn.bind(on_release=lambda *x: on_save())
        card.add_widget(btn)

    apply_glow(card, C_GREEN if selected else (C_GOLD if is_seed else (C_RED if is_fallback else C_BLUE)))
    _fade_in(card)

    def _h(*a):
        total = sum(c.height for c in card.children) + dp(24) + dp(6) * (len(card.children) - 1)
        card.height = total
    Clock.schedule_once(_h, 0)
    card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
    return card


# ==================================================================
# صفحهٔ ماتریس
# ==================================================================
class MatrixScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='پردازش ماتریس آینه‌ای', **kw)
        self.mode = 'normal'          # normal = هفت‌عملگر | rotation = دورانی
        self._seed = (1, 1)
        self._seed_card = None
        self._cards = []
        self._view_a = {}             # idx -> آیهٔ نمایش‌داده‌شده (ناوبری مستقل کارت)
        self._hidden = set()          # idx کارت‌های موقتاً حذف‌شده (ضربدر)
        self._select_mode = None      # None | 'pair' | 'group'
        self._selected = []           # idx کارت‌های انتخاب‌شده (جفت)

        # هدر پردازش در یک خط و با اندازهٔ پویا نمایش داده شود (بدون بهم‌ریختگی)
        self.title_label._fit_single = True

        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.mode_btn = PillButton('حالت: ماتریس هفت‌عملگر', bg=C_PURPLE, font_size='13sp')
        self.mode_btn.bind(on_release=lambda *a: self.toggle_mode())
        top.add_widget(self.mode_btn)
        self.body(top)

        selrow = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.group_btn = PillButton('انتخاب گروهی', bg=C_BLUE, font_size='13sp')
        self.group_btn.bind(on_release=lambda *a: self.toggle_select('group'))
        self.pair_btn = PillButton('انتخاب جفتی', bg=C_BLUE, font_size='13sp')
        self.pair_btn.bind(on_release=lambda *a: self.toggle_select('pair'))
        selrow.add_widget(self.group_btn)
        selrow.add_widget(self.pair_btn)
        self.body(selrow)

        self.reg_bar = BoxLayout(size_hint_y=None, height=dp(0), spacing=dp(8))
        self.body(self.reg_bar)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)

        # دکمهٔ شناورِ هوش مصنوعی (شیشه‌ای/نئونی) — گوشهٔ پایین‌راست؛ پس از ساختِ کارت‌ها ظاهر می‌شود
        self.ai_fab = PillButton('AI', bg=(0.10, 0.16, 0.28, 0.75), fg=(1, 1, 1, 1),
                                 radius=dp(30), font_size='18sp',
                                 size_hint=(None, None), size=(dp(60), dp(60)),
                                 pos_hint={'right': 0.95, 'y': 0.06})
        self.ai_fab.bind(on_release=lambda *a: self._ai_analyze())
        self.ai_fab.opacity = 0
        self.ai_fab.disabled = True
        self.root_layout.add_widget(self.ai_fab)
        orbit_ring(self.ai_fab, C_BLUE, period=3.6, fps=45, trail=20)

    # ---------- حالت پردازش ----------
    def toggle_mode(self):
        self.mode = 'rotation' if self.mode == 'normal' else 'normal'
        self.mode_btn.set_text('حالت: پردازش دورانی ارقام بذر' if self.mode == 'rotation'
                               else 'حالت: ماتریس هفت‌عملگر')
        self.show(*self._seed)
        _n = len(self._cards) if getattr(self, '_cards', None) else 0
        toast('حالت پردازش: %s\n(%d کارت ساخته شد)' % (('دورانی ارقام بذر' if self.mode == 'rotation'
                                    else 'ماتریس هفت‌عملگر'), _n), 'حالت')

    def toggle_select(self, kind):
        self._select_mode = None if self._select_mode == kind else kind
        self._selected = []
        self.group_btn.set_text('★ انتخاب گروهی' if self._select_mode == 'group' else 'انتخاب گروهی')
        self.pair_btn.set_text('★ انتخاب جفتی' if self._select_mode == 'pair' else 'انتخاب جفتی')
        self._render()
        _names = {'group': 'انتخاب گروهی', 'pair': 'انتخاب جفتی'}
        _nt = len(self._visible_target_indices())
        if self._select_mode:
            toast('حالت «%s» فعال شد؛ روی %d کارتِ مقصد بزنید.' % (_names[kind], _nt), 'انتخاب')
        else:
            toast('حالت انتخاب خاموش شد.', 'انتخاب')

    def _reset_state(self):
        self._view_a = {}
        self._hidden = set()
        self._selected = []
        self._select_mode = None
        self.group_btn.set_text('انتخاب گروهی')
        self.pair_btn.set_text('انتخاب جفتی')

    # ---------- ناوبری ----------
    def _seed_nav(self, delta):
        app = App.get_running_app()
        s, a = self._seed
        na = a + delta
        if na < 1:
            toast('به ابتدای سوره رسیدید.', 'ناوبری')
            return
        maxa = app.data.max_a.get(s)
        if maxa and na > maxa:
            toast('به انتهای سوره رسیدید.', 'ناوبری')
            return
        if app.data.get(s, na) is None:
            toast('آیه یافت نشد.', 'ناوبری')
            return
        self.show(s, na)

    def _card_nav(self, idx, delta):
        app = App.get_running_app()
        c = self._cards[idx]
        cur = self._view_a.get(idx, c['a'])
        na = cur + delta
        if na < 1:
            toast('به ابتدای سوره رسیدید.', 'ناوبری')
            return
        maxa = app.data.max_a.get(c['s'])
        if maxa and na > maxa:
            toast('به انتهای سوره رسیدید.', 'ناوبری')
            return
        if app.data.get(c['s'], na) is None:
            toast('آیه یافت نشد.', 'ناوبری')
            return
        self._view_a[idx] = na
        self._render()

    # ---------- ساخت/نمایش ----------
    def show(self, s, a):
        app = App.get_running_app()
        self._reset_state()
        self._seed = (s, a)
        self.title_label._base_fs = None
        self.title_label.font_size = '21sp'
        self.title_label.set_text('پردازش : سوره %s و آیه %s' % (s, a))
        if self.mode == 'rotation':
            self._cards = features.generate_rotation_cards(app.data, s, a)
        else:
            self._cards = core.process_matrix(app.data, s, a)
        self._render()

    def _resolved(self, idx):
        """کارت با اعمال ناوبری مستقل (آیهٔ جایگزین) برگردانده می‌شود."""
        app = App.get_running_app()
        c = dict(self._cards[idx])
        if idx in self._view_a:
            na = self._view_a[idx]
            v = app.data.get(c['s'], na) or {}
            c['a'] = na
            c['arb'] = v.get('arb', '')
            c['pers'] = v.get('pers', '')
        return c

    def _visible_target_indices(self):
        return [i for i, c in enumerate(self._cards)
                if c.get('kind') == 'target' and i not in self._hidden]

    def _render(self):
        self.list.clear_widgets()
        _prune_glows()   # لغو انیمیشن‌های کارت‌های حذف‌شده تا ترد UI آزاد بماند
        self._update_reg_bar()
        if not self._cards:
            self.list.add_widget(empty_state('داده‌ای برای این بذر یافت نشد',
                                             hint='شمارهٔ سوره و آیه را بررسی کن و دوباره تلاش کن'))
            self._set_fab(False)
            return
        self._seed_card = self._cards[0]
        self.list.add_widget(self._make_card(0, is_seed=True))
        for i in range(1, len(self._cards)):
            if self._cards[i].get('kind') != 'target':
                continue
            if i in self._hidden:
                continue
            self.list.add_widget(self._make_card(i, is_seed=False))
        self._set_fab(len(self._visible_target_indices()) > 0)

    def _set_fab(self, show):
        fab = getattr(self, 'ai_fab', None)
        if fab is None:
            return
        fab.disabled = not show
        Animation(opacity=1 if show else 0, d=0.25).start(fab)

    def _ai_analyze(self):
        if not self._cards:
            toast('اول یک بذر را پردازش کن.', 'هوش مصنوعی')
            return
        seed = self._resolved(0)
        targets = []
        for i in range(1, len(self._cards)):
            if self._cards[i].get('kind') != 'target':
                continue
            if i in self._hidden:
                continue
            targets.append(self._resolved(i))
        if not targets:
            toast('کارتی برای تحلیل نیست.', 'هوش مصنوعی')
            return
        msgs = ai_manager.build_matrix_messages(seed, targets)
        show_ai_result_popup('تحلیل یکپارچهٔ ماتریس', msgs,
                             subtitle='بذر: سوره %s ، آیه %s  —  %d مقصد' % (seed['s'], seed['a'], len(targets)))

    def _make_card(self, idx, is_seed=False):
        c = self._resolved(idx)
        is_fb = c.get('is_fallback', False)
        # ظاهرِ شیشه‌ایِ هماهنگ با باکس‌های صفحهٔ هوم: پس‌زمینهٔ نیمه‌شفافِ شناور + هالهٔ نورانیِ رنگی.
        # تفکیکِ رنگی حفظ می‌شود: بذر=کهربایی/طلایی ، مقصدِ عادی=سرمه‌ایِ آبی ، جایگزین=زرشکی/قرمز.
        if is_seed:
            bg = (0.16, 0.13, 0.05, 0.55)
        elif is_fb:
            bg = (0.24, 0.09, 0.09, 0.52)
        else:
            bg = (0.05, 0.08, 0.14, 0.62)
        card = RoundBox(bg=bg, orientation='vertical', size_hint_y=None,
                        padding=dp(12), spacing=dp(6))

        # ردیف بالای کارت: نشان عملگر (چپ) + ضربدر حذف (راست)
        toprow = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        if is_seed:
            badge = _neon_badge('بذر', C_GOLD, size=(dp(48), dp(26)))
        elif self.mode == 'rotation':
            _rot = (c.get('mode', '').split('←')[0].split('(')[0].strip() or 'چرخش')
            badge = _neon_badge(_rot, C_PURPLE, size=(dp(104), dp(26)))
        else:
            badge = _neon_badge(op_of({'mode': c.get('mode', '')}), C_BLUE, size=(dp(42), dp(26)))
        toprow.add_widget(badge)
        if not is_seed:
            try:
                _sd = self._seed
                toprow.add_widget(TransformChip(_sd[0], _sd[1], c['s'], c['a']))
            except Exception:
                pass
        toprow.add_widget(Widget())
        try:
            toprow.add_widget(_rev_pulse_badge(c['s']))
        except Exception:
            pass
        try:
            toprow.add_widget(info_button([('', c['s'], c['a'])]))
        except Exception:
            pass
        if not is_seed:
            xb = PillButton('حذف موقت', bg=C_RED, fg=(1, 1, 1, 1), size_hint_x=None, width=dp(100), font_size='12sp')
            xb.bind(on_release=lambda *a, i=idx: self._hide_card(i))
            toprow.add_widget(xb)
        card.add_widget(toprow)

        # متنِ مختصات از رویِ کارت حذف شد؛ داخلِ «اطلاعات عددی» دیده می‌شود
        # دکمه‌های اطلاعات عددی و حذف موقت به ردیفِ بالا (کنارِ چیپ) منتقل شدند
        arb_l = RLabel('« %s »' % c.get('arb', ''), arabic=True, font_size='20sp', halign='center',
                       color=C_TEXT, size_hint_y=None)
        arb_l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
        card.add_widget(arb_l)
        pers_l = RLabel(c.get('pers', ''), font_size='14sp', halign='center', color=C_MUTED, size_hint_y=None)
        pers_l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(pers_l)
        if is_fb and c.get('reason'):
            warn = RLabel(c.get('reason', ''), font_size='12sp', halign='right', color=C_RED, size_hint_y=None)
            warn.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
            card.add_widget(warn)

        # ردیف آیهٔ قبل/بعد (برای همهٔ کارت‌ها)
        nav = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        b_next = PillButton('آیهٔ بعد ▶', bg=(1, 1, 1, 0.14), font_size='13sp')
        b_prev = PillButton('◀ آیهٔ قبل', bg=(1, 1, 1, 0.14), font_size='13sp')
        if is_seed:
            b_next.bind(on_release=lambda *a: self._seed_nav(+1))
            b_prev.bind(on_release=lambda *a: self._seed_nav(-1))
        else:
            b_next.bind(on_release=lambda *a, i=idx: self._card_nav(i, +1))
            b_prev.bind(on_release=lambda *a, i=idx: self._card_nav(i, -1))
        nav.add_widget(b_next)
        nav.add_widget(b_prev)
        card.add_widget(nav)

        # دکمهٔ کنش (فقط کارت‌های مقصد)
        if not is_seed:
            if self._select_mode == 'pair':
                picked = idx in self._selected
                order = (self._selected.index(idx) + 1) if picked else None
                lbl = ('انتخاب‌شده (%d)' % order) if picked else 'انتخاب برای جفت'
                sb = PillButton(lbl, bg=C_GREEN if picked else C_BLUE, size_hint_y=None, height=dp(42), font_size='14sp')
                sb.bind(on_release=lambda *a, i=idx: self._pick_pair(i))
                card.add_widget(sb)
            elif self._select_mode == 'group':
                info = RLabel('در انتخاب گروهی ★ (با «حذف موقت» بردارید)', font_size='12sp',
                              halign='center', color=C_GREEN, size_hint_y=None)
                info.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
                card.add_widget(info)
            else:
                rb = PillButton('ثبت این کشف با بذر', bg=C_GREEN, size_hint_y=None, height=dp(42), font_size='14sp')
                rb.bind(on_release=lambda *a, i=idx: self._register_single(i))
                card.add_widget(rb)

        # هالهٔ نورانیِ نرمِ دورِ کارت — همان جنسِ «شهابِ» باکس‌های صفحهٔ هوم (pulse_aura)
        # رنگِ هاله، تفکیکِ نوعِ کارت را نشان می‌دهد (طلایی=بذر، سبز=انتخابِ گروهی، قرمز=جایگزین، آبی=مقصد).
        gcol = C_GOLD if is_seed else (C_GREEN if (self.mode != 'rotation' and self._select_mode == 'group')
                                       else (C_RED if is_fb else C_BLUE))
        pulse_aura(card, gcol)

        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
        return card

    def _hide_card(self, idx):
        self._hidden.add(idx)
        self._selected = [i for i in self._selected if i != idx]
        self._render()

    def _restore_hidden(self):
        self._hidden = set()
        self._render()

    def _pick_pair(self, idx):
        if idx in self._selected:
            self._selected = [i for i in self._selected if i != idx]
        else:
            if len(self._selected) >= 2:
                toast('برای جفت فقط دو مقصد انتخاب کنید.', 'جفت')
                return
            self._selected.append(idx)
        self._render()

    def _update_reg_bar(self):
        self.reg_bar.clear_widgets()
        widgets = []
        if self._select_mode == 'group':
            n = len(self._visible_target_indices())
            b = PillButton('ثبت کشف گروهی (%d مقصد)' % n, bg=C_GREEN, font_size='14sp')
            b.bind(on_release=lambda *a: self._register_group())
            widgets.append(b)
        elif self._select_mode == 'pair':
            n = len(self._selected)
            b = PillButton('ثبت جفت عملگری (%d از ۲)' % n, bg=C_GREEN, font_size='14sp')
            b.bind(on_release=lambda *a: self._register_pair())
            widgets.append(b)
        if self._hidden:
            rb = PillButton('بازگردانی حذف‌شده‌ها (%d)' % len(self._hidden), bg=C_ORANGE, font_size='13sp')
            rb.bind(on_release=lambda *a: self._restore_hidden())
            widgets.append(rb)
        if not widgets:
            self.reg_bar.height = dp(0)
            return
        self.reg_bar.height = dp(48)
        for w in widgets:
            self.reg_bar.add_widget(w)

    # ---------- ثبت کشف ----------
    def _register_single(self, idx):
        app = App.get_running_app()
        app.add_discovery(self._seed_card, self._resolved(idx))

    def _register_group(self):
        app = App.get_running_app()
        idxs = self._visible_target_indices()
        if not idxs:
            toast('هیچ کارتی برای ثبت گروهی نمانده است.', 'گروهی')
            return
        targets = [self._resolved(i) for i in idxs]
        app.add_group_discovery(self._seed_card, targets)
        self._reset_state()
        self._render()

    def _register_pair(self):
        app = App.get_running_app()
        if len(self._selected) != 2:
            toast('برای جفت دقیقاً دو مقصد انتخاب کنید.', 'جفت')
            return
        ta = self._resolved(self._selected[0])
        tb = self._resolved(self._selected[1])
        app.add_pair_discovery(self._seed_card, ta, tb)
        self._reset_state()
        self._render()


# ==================================================================
# صفحهٔ پیش‌بینی (معنا / اعداد)
# ==================================================================
class PredictScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='پیش‌بینی آینه', **kw)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)

    def show(self, s, a, kind):
        app = App.get_running_app()
        self.list.clear_widgets()
        seed = app.data.get(s, a)
        self.title_label.set_text('پیش‌بینی ' + ('معنایی' if kind == 'semantic' else 'عددی'))
        # کارت بذر
        self.list.add_widget(verse_card('بذر ساختاری', s, a, seed['arb'], seed['pers'], is_seed=True))
        if kind == 'semantic':
            preds = core.predict_mirror(app.data, s, a, seed['arb'])
            ctx = {'s': s, 'a': a, 'seed_arb': seed['arb'], 'seed_pers': seed['pers'], 'preds': []}
            for _r, (op, ts, ta, score, status, is_fb, msg) in enumerate(preds, 1):
                d = app.data.get(ts, ta) or {}
                ctx['preds'].append({'rank': _r, 'op_code': op_of({'mode': op}), 's': ts, 'a': ta,
                                     'arb': d.get('arb', ''), 'pers': d.get('pers', ''), 'is_fallback': is_fb})
            self._pred_ctx = ctx
            actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
            pbtn = PillButton('کپی پرامپت هوش مصنوعی (۷ قانونی)', bg=C_PURPLE, font_size='12sp')
            pbtn.bind(on_release=lambda *a: self._copy_pred_prompt())
            hbtn = PillButton('نمایش گزارش HTML', bg=C_GREEN, font_size='12sp')
            hbtn.bind(on_release=lambda *a: self._open_html())
            actions.add_widget(pbtn)
            actions.add_widget(hbtn)
            self.list.add_widget(actions)
            for rank, (op, ts, ta, score, status, is_fb, msg) in enumerate(preds, 1):
                d = app.data.get(ts, ta) or {}
                sc = 'رتبه %d | امتیاز: %.0f٪ | %s' % (rank, score, status)
                if rank <= 3:
                    sc += '  •  نیازمند تحلیل هوش مصنوعی یا انسانی'
                seed_card = {'mode': op, 's': s, 'a': a, 'arb': seed['arb'], 'pers': seed['pers']}
                tgt = {'mode': op, 's': ts, 'a': ta, 'arb': d.get('arb', ''), 'pers': d.get('pers', ''),
                       'is_fallback': is_fb, 'reason': msg}
                w = verse_card(op, ts, ta, d.get('arb', ''), d.get('pers', ''),
                               is_fallback=is_fb, reason=(msg if is_fb else ''),
                               score_text=sc,
                               on_save=(lambda sd=seed_card, cc=tgt: app.add_discovery(sd, cc)))
                w.opacity = 0
                self.list.add_widget(w)
                Animation(opacity=1, duration=0.3).start(w)
        else:
            preds = core.predict_mirror_numeric(app.data, s, a)
            if not preds:
                self.list.add_widget(empty_state('مقصد معتبری با الگوریتمِ عددی یافت نشد',
                                                 hint='این بذر با روشِ عددی نتیجه نداد؛ روشِ معنایی را امتحان کن'))
                return
            for (op, ts, ta, prio, detail, is_fb, msg) in preds:
                d = app.data.get(ts, ta) or {}
                sc = f'اولویت {prio} | {detail}'
                seed_card = {'mode': op, 's': s, 'a': a, 'arb': seed['arb'], 'pers': seed['pers']}
                tgt = {'mode': op, 's': ts, 'a': ta, 'arb': d.get('arb', ''), 'pers': d.get('pers', ''),
                       'is_fallback': is_fb, 'reason': msg}
                w = verse_card(op, ts, ta, d.get('arb', ''), d.get('pers', ''),
                               is_fallback=is_fb, reason=(msg if is_fb else ''), score_text=sc,
                               on_save=(lambda sd=seed_card, cc=tgt: app.add_discovery(sd, cc)))
                w.opacity = 0
                self.list.add_widget(w)
                Animation(opacity=1, duration=0.3).start(w)

    def _copy_pred_prompt(self):
        ctx = getattr(self, '_pred_ctx', None)
        if not ctx:
            toast('ابتدا یک پیش‌بینی معنایی اجرا کنید.', 'هوش مصنوعی')
            return
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(features.build_prediction_prompt(
                ctx['s'], ctx['a'], ctx['seed_arb'], ctx['seed_pers'], ctx['preds']))
            toast('پرامپت پیش‌بینی معنایی کپی شد؛ آن را در چت هوش مصنوعی بچسبانید.', 'هوش مصنوعی')
        except Exception:
            toast('کپی ممکن نشد.', 'خطا')

    def _open_html(self):
        app = App.get_running_app()
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        content.add_widget(RLabel('کد HTML گزارش هوش مصنوعی را اینجا بچسبانید:',
                                  font_size='14sp', color=C_GOLD, halign='center', size_hint_y=None, height=dp(50)))
        ti = PlainInput(multiline=True, font_size='12sp', size_hint_y=1,
                       background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
        content.add_widget(ti)
        pop = Popup(title=P('نمایش گزارش HTML'), content=content, size_hint=(0.96, 0.85),
                    title_font='ui', title_align='center', separator_color=C_GOLD)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        bshow = PillButton('نمایش گزارش', bg=C_GREEN)

        def _show(*a):
            html = ti.text or ''
            if not html.strip():
                toast('متن HTML خالی است.', 'خطا')
                return
            show_html_in_app(html)   # نمایش داخل خودِ برنامه (بدون نیاز به مرورگر)
        bshow.bind(on_release=_show)
        bclose = PillButton('بستن', bg=C_RED)
        bclose.bind(on_release=pop.dismiss)
        row.add_widget(bshow)
        row.add_widget(bclose)
        content.add_widget(row)
        pop.open()


# ==================================================================
# لابراتوار کشفیات
# ==================================================================
OPERATORS = [
    ('T1', 'جابجایی خالص بذر'),
    ('T2', 'تقارن درجا کامل'),
    ('T3', 'تقارن درجا فقط سوره'),
    ('T4', 'تقارن درجا فقط آیه'),
    ('T5', 'جابجایی + تقارن کامل'),
    ('T6', 'جابجایی + تقارن فقط سوره'),
    ('T7', 'جابجایی + تقارن فقط آیه'),
    ('OTHER', 'گروهی و سایر'),
]


def op_of(item):
    if item.get('op_key'):
        return item['op_key']
    m = str(item.get('mode', ''))
    if 'خالص' in m:
        return 'T1'
    if 'ضربدری' in m:
        return 'T5'
    if 'جابجایی' in m and 'کامل' in m:
        return 'T5'
    if 'تقارن درجا کامل' in m:
        return 'T2'
    if 'جابجایی' in m and 'فقط سوره' in m:
        return 'T6'
    if 'جابجایی' in m and 'فقط آیه' in m:
        return 'T7'
    if 'فقط سوره' in m:
        return 'T3'
    if 'فقط آیه' in m:
        return 'T4'
    return 'OTHER'


def discovery_key(item):
    """کلید یکتای یک کشف برای تطبیق نئون/آخرین کشف."""
    if 'all_targets' in item:
        return ('G', item.get('seed_s'), item.get('seed_a'), item.get('mode'),
                tuple((t.get('s'), t.get('a')) for t in item.get('all_targets', [])))
    return (item.get('seed_s'), item.get('seed_a'), item.get('target_s'),
            item.get('target_a'), item.get('mode'))


def lab_section_of(item):
    """بخش لابراتوار: تردیدی‌ها جدا، گروهی‌ها جدا، بقیه زیر عملگر خودشان."""
    if item.get('is_doubtful'):
        return 'DOUBT'
    if item.get('mode') == 'گروهی':
        return 'GROUP'
    return op_of(item)


LAB_SECTIONS = [(k, t) for k, t in OPERATORS if k != 'OTHER'] + [
    ('GROUP', 'کشفیات گروهی'),
    ('DOUBT', 'کشفیات تردیدی'),
]


def _neon_badge(text, color=None, size=None):
    """نشان کوچک نئونی چشمک‌زن (مثلاً T1..T7) برای گوشهٔ کارت."""
    from kivy.graphics import Color as _C, RoundedRectangle as _RR, Line as _L
    if color is None:
        color = C_BLUE
    if size is None:
        size = (dp(42), dp(26))
    lbl = Label(text=rtl(text), font_name='ui', bold=True, font_size='13sp',
                size_hint=(None, None), size=size, color=(1, 1, 1, 1))
    with lbl.canvas.before:
        _C(color[0], color[1], color[2], 0.20)
        bg = _RR(radius=[dp(8)])
        lc = _C(color[0], color[1], color[2], 0.95)
        ln = _L(width=1.5)

    def _u(*a):
        bg.pos = lbl.pos
        bg.size = lbl.size
        ln.rounded_rectangle = (lbl.x, lbl.y, lbl.width, lbl.height, dp(8))
    lbl.bind(pos=_u, size=_u)
    anim = Animation(a=1.0, duration=0.6) + Animation(a=0.12, duration=0.6)
    anim.repeat = True
    anim.start(lc)
    _register_glow(anim, lc, lbl)
    return lbl


def _auto_label(text, arabic=False, **kw):
    kw.setdefault('size_hint_y', None)
    lbl = RLabel(text, arabic=arabic, **kw)
    lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
    return lbl


# برچسبِ ریزِ مکی/مدنی برای کارتهای آیه (همه‌جای اپ)
C_MAKKI = (0.98, 0.80, 0.42, 1)
C_MADANI = (0.50, 0.84, 0.66, 1)
C_REVPAIR = (0.80, 0.84, 0.96, 1)


def _rev_tag(s):
    try:
        r = qref.revelation(s)
    except Exception:
        r = ''
    return 'مکّی' if r == 'مکی' else ('مدنی' if r == 'مدنی' else '')


def _rev_color(s):
    try:
        return C_MAKKI if qref.is_makki(s) else C_MADANI
    except Exception:
        return C_MUTED


def _rev_badge(s, halign='left', font_size='10sp', height=None):
    return RLabel(_rev_tag(s), font_size=font_size, bold=True, halign=halign,
                  color=_rev_color(s), size_hint_y=None, height=(height or dp(15)))


def _rev_pair_text(seed_s, target_s):
    st = _rev_tag(seed_s)
    tt = _rev_tag(target_s)
    if st and tt:
        return 'بذر: %s · مقصد: %s' % (st, tt)
    return st or tt or ''


def _rev_pair_badge(seed_s, target_s, halign='left', font_size='10sp', height=None):
    return RLabel(_rev_pair_text(seed_s, target_s), font_size=font_size, bold=True,
                  halign=halign, color=C_REVPAIR, size_hint_y=None, height=(height or dp(15)))


def _rev_pulse_badge(s, width=None, font_size='11sp'):
    """برچسبِ ریزِ مکی/مدنی با چشمک‌زدنِ نرم — برای ردیفِ بالایِ کارت‌هایِ پردازش."""
    tag = _rev_tag(s)
    lbl = RLabel(tag, font_size=font_size, bold=True, halign='center', valign='middle',
                 color=_rev_color(s), size_hint_y=None, height=dp(26))
    lbl.size_hint_x = None
    lbl.width = width or dp(46)
    if tag:
        try:
            anim = Animation(opacity=0.35, d=0.85) + Animation(opacity=1.0, d=0.85)
            anim.repeat = True
            anim.start(lbl)
        except Exception:
            pass
    return lbl


def _verse_block(border, s, a, arb, pers):
    c = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=border, orientation='vertical',
                 size_hint_y=None, padding=dp(10), spacing=dp(4))
    c.add_widget(_rev_badge(s, halign='left'))
    c.add_widget(_auto_label('سوره %s ، آیه %s' % (s, a), font_size='12sp', color=C_MUTED, halign='right'))
    try:
        c.add_widget(_info_btn_row([('', s, a)]))
    except Exception:
        pass
    c.add_widget(_auto_label('« %s »' % (arb or ''), arabic=True, font_size='18sp', color=C_TEXT, halign='center'))
    c.add_widget(_auto_label('ترجمه: ' + (pers or ''), font_size='13sp', color=C_MUTED, halign='right'))
    c.bind(minimum_height=lambda i, v: setattr(c, 'height', v + dp(24)))
    return c


def generate_default_analysis(e):
    """متن تحلیل پیش‌فرض یک کشف (هم‌راستا با نسخهٔ ویندوز):
    فقط نام عملگر و یک یادآوری کوتاه؛ بدون متن آیه و ترجمه، تا باکس تحلیل
    فقط چیزی باشد که خودِ کاربر می‌نویسد."""
    return (
        'این کشف بر اساس عملگر «%s» پیشنهاد شده است.\n\n'
        '(لطفاً تحلیل دقیق خود را از رابطهٔ معنایی این دو آیه یادداشت کنید…)'
        % (e.get('mode', '') or '—'))


class AnalysisRawInput(_KbFocusMixin, TextInput):
    """کادرِ نوشتنِ پایدار برای پنجرهٔ بزرگِ ویرایش.
    ویرایش کاملاً بومیِ Kivy است (هرگز کرش نمی‌کند و مکان‌نما دقیق است)؛ نمایشِ
    درستِ متصلِ راست‌به‌چپ را نمایشگرِ زندهٔ کنارِ آن نشان می‌دهد."""
    def __init__(self, on_change=None, **kw):
        kw.setdefault('font_name', 'ui')
        kw.setdefault('halign', 'right')
        kw.setdefault('multiline', True)
        super().__init__(**kw)
        try:
            self.base_direction = 'rtl'
        except Exception:
            pass
        self._on_change = on_change
        self.bind(text=self._changed)

    def _changed(self, *a):
        cb = self._on_change
        if cb:
            try:
                cb(self.text)
            except Exception:
                pass

    @property
    def query(self):
        return _pe_norm(self.text or '')

    def set_logical(self, value):
        v = _pe_norm(value or '')
        if self.text != v:
            self.text = v


def open_big_analysis_editor(initial_text, on_save):
    """پنجرهٔ بزرگِ ویرایشِ تحلیل: نمایشگرِ زندهٔ درست (بالا) + کادرِ نوشتنِ پایدار (پایین).
    کاربر در کادرِ پایین می‌نویسد و همان لحظه نمایشِ درستِ متصل را بالا می‌بیند."""
    initial_text = initial_text or ''
    root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
    root.add_widget(RLabel('در کادرِ پایین بنویس؛ نمایشِ درست و متصل را بالا زنده می‌بینی.',
                           font_size='13sp', color=C_GOLD, halign='center',
                           size_hint_y=None, height=dp(32)))
    root.add_widget(RLabel('نمایشِ درست:', font_size='13sp', color=C_MUTED, halign='right',
                           size_hint_y=None, height=dp(24)))
    vbox = RoundBox(bg=(1, 1, 1, 0.06), border=(1, 1, 1, 0.15), orientation='vertical',
                    size_hint_y=0.46, padding=dp(10))
    vscroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    viewer = RLabel('', font_size='17sp', halign='right', valign='top',
                    color=C_TEXT, size_hint_y=None)
    viewer.bind(texture_size=lambda i, v: setattr(viewer, 'height', v[1] + dp(6)))
    vscroll.add_widget(viewer)
    vbox.add_widget(vscroll)
    root.add_widget(vbox)
    root.add_widget(RLabel('متنِ قابلِ ویرایش:', font_size='13sp', color=C_MUTED, halign='right',
                           size_hint_y=None, height=dp(24)))

    def _live(txt):
        viewer.set_text(txt or '')

    editor = AnalysisRawInput(on_change=_live, size_hint_y=0.46,
                              background_color=(1, 1, 1, 0.98),
                              foreground_color=(0.05, 0.08, 0.14, 1),
                              font_size='16sp')
    editor.set_logical(initial_text)
    _live(initial_text)
    root.add_widget(editor)
    ep = Popup(title=P('ویرایش تحلیل'), content=root, size_hint=(0.98, 0.96),
               title_font='ui', title_align='center', separator_color=C_GOLD)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    sv = PillButton('ذخیره', bg=C_GREEN)
    cn = PillButton('انصراف', bg=C_RED)

    def _do_save(*a):
        try:
            on_save(editor.query)
        except Exception:
            pass
        ep.dismiss()

    sv.bind(on_release=_do_save)
    cn.bind(on_release=lambda *a: ep.dismiss())
    row.add_widget(sv)
    row.add_widget(cn)
    root.add_widget(row)
    ep.open()
    Clock.schedule_once(lambda *a: setattr(editor, 'focus', True), 0.3)


def _add_analysis_field(content, initial_text=''):
    """در پنجرهٔ تحلیل: نمایشِ درستِ فقط‌خواندنیِ تحلیل + دکمهٔ «ویرایش تحلیل».
    ویرایش در یک پنجرهٔ بزرگِ جدا (نمایشگرِ زنده + کادرِ پایدار) انجام می‌شود تا نمایش
    همیشه درست و متصل بماند و هرگز آینه‌ای/به‌هم‌ریخته/کرش نشود."""
    content.add_widget(RLabel('تحلیل شما:', font_size='15sp', size_hint_y=None, height=dp(26)))
    holder = {'text': _pe_norm(initial_text or '')}
    placeholder = '— هنوز تحلیلی ننوشته‌اید. روی «ویرایش تحلیل» بزنید تا بنویسید. —'
    vbox = RoundBox(bg=(1, 1, 1, 0.05), border=(1, 1, 1, 0.14), orientation='vertical',
                    size_hint_y=1, padding=dp(10))
    vscroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    viewer = RLabel(holder['text'] or placeholder, font_size='16sp', halign='right',
                    valign='top', color=C_TEXT, size_hint_y=None)
    viewer.bind(texture_size=lambda i, v: setattr(viewer, 'height', v[1] + dp(6)))
    vscroll.add_widget(viewer)
    vbox.add_widget(vscroll)
    content.add_widget(vbox)
    edit_btn = PillButton('✏️ ویرایش تحلیل', bg=C_BLUE, size_hint_y=None, height=dp(46),
                          font_size='15sp')
    content.add_widget(edit_btn)

    class _Ctl:
        @property
        def query(self):
            return holder['text']

        def set_logical(self, value):
            holder['text'] = _pe_norm(value or '')
            viewer.set_text(holder['text'] or placeholder)

    ctl = _Ctl()

    def _open(*a):
        open_big_analysis_editor(holder['text'], ctl.set_logical)

    edit_btn.bind(on_release=_open)
    return ctl


def open_note_editor(item, source='lab', title='ویرایش تحلیل', intro=None, on_saved=None, saved_msg='ذخیره شد ✓', on_cancel=None):
    """پنجرهٔ ثبت/ویرایش تحلیل یک کشف (با برچسب و وضعیت تردید)."""
    app = App.get_running_app()
    content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
    if intro:
        content.add_widget(RLabel(intro, font_size='14sp', color=C_GOLD, halign='center',
                                  size_hint_y=None, height=dp(50)))
    # فیلد متن + پیش‌نمایشِ زندهٔ درست (سازگار با موتورِ sdl2)
    ti = _add_analysis_field(content, item.get('note', ''))
    # دکمهٔ دستیارِ هوش مصنوعی: تولیدِ متنِ تحلیلیِ کوتاه و تزریق در فیلد (کاربر بعداً ویرایش می‌کند)
    ai_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
    ai_btn = PillButton('✦ کمکِ هوش مصنوعی در تحلیل', bg=C_PURPLE, fg=HOME_FG, font_size='14sp')

    def _ai_fill(*a):
        seed = {'s': item.get('seed_s'), 'a': item.get('seed_a'),
                'arb': item.get('seed_arb', ''), 'pers': item.get('seed_pers', '')}
        target = {'s': item.get('target_s'), 'a': item.get('target_a'),
                  'arb': item.get('target_arb', ''), 'pers': item.get('target_pers', '')}
        operator = item.get('mode', '') or 'نامشخص'
        msgs = ai_manager.build_note_messages(seed, target, operator)
        ai_btn.disabled = True
        ai_btn.set_text('در حال نوشتن تحلیل...')

        def _done(full):
            ai_btn.disabled = False
            ai_btn.set_text('✦ بازنویسی با هوش مصنوعی')
            txt = (full or '').strip()
            if txt:
                ti.set_logical(txt)
            else:
                toast('پاسخی دریافت نشد.', 'هوش مصنوعی', kind='warn')

        def _err(msg):
            ai_btn.disabled = False
            ai_btn.set_text('✦ کمکِ هوش مصنوعی در تحلیل')
            toast(msg, 'هوش مصنوعی', kind='error')

        ai_manager.chat(msgs, on_done=_done, on_error=_err,
                        stream=False, temperature=0.5, max_tokens=600)

    ai_btn.bind(on_release=_ai_fill)
    ai_row.add_widget(ai_btn)
    content.add_widget(ai_row)
    tags = list(app.get_all_tags())
    _get_tags = _tag_multiselect(content, list(app.get_all_tags()), item.get('relation_type'), 'برچسب تحلیلی (رفتار شبکه) — هر تعداد که خواستی انتخاب کن:')
    state = {'d': bool(item.get('is_doubtful', False))}
    btog = PillButton('وضعیت: تردیدی' if state['d'] else 'وضعیت: مطمئن',
                      bg=C_ORANGE if state['d'] else C_GREEN, size_hint_y=None, height=dp(44), font_size='14sp')
    def _tog(*a):
        state['d'] = not state['d']
        btog.set_text('وضعیت: تردیدی' if state['d'] else 'وضعیت: مطمئن')
        # رنگ پس‌زمینه هم همگام شود تا تغییر وضعیت کاملاً دیده شود
        btog._bg = list(C_ORANGE if state['d'] else C_GREEN)
        btog._state()
    btog.bind(on_release=_tog)
    content.add_widget(btog)
    ep = Popup(title=P(title), content=content, size_hint=(0.96, 0.94),
               title_font='ui', title_align='center', separator_color=C_GOLD)
    row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
    saved = {'v': False}
    sv = PillButton('ذخیره', bg=C_GREEN)
    def _sv(*a):
        saved['v'] = True
        item['note'] = ti.query
        item['relation_type'] = _get_tags()
        item['is_doubtful'] = state['d']
        if source == 'lab':
            app.save_favs()
        else:
            app.save_featured()
        ep.dismiss()
        if on_saved:
            on_saved()
        toast(saved_msg, 'ذخیره')
    sv.bind(on_release=_sv)
    cn = PillButton('انصراف', bg=C_RED)
    cn.bind(on_release=lambda *a: ep.dismiss())
    # اگر پنجره بدونِ «ذخیره» بسته شود (انصراف، کلیکِ بیرون، بازگشت) و on_cancel
    # داده شده باشد، آن را صدا می‌زنیم تا کشفی که موقتاً ثبت شده از لابراتوار حذف شود.
    def _on_dismiss(*a):
        if on_cancel and not saved['v']:
            try:
                on_cancel()
            except Exception:
                pass
    ep.bind(on_dismiss=_on_dismiss)
    row2.add_widget(sv)
    row2.add_widget(cn)
    content.add_widget(row2)
    ep.open()


def show_group_discovery(item, source='lab', screen=None):
    app = App.get_running_app()
    root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
    box.bind(minimum_height=box.setter('height'))
    p = Popup(title=P('جزئیات کشف گروهی'), content=root, size_hint=(0.96, 0.92),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _refresh_parent():
        if screen is not None and hasattr(screen, 'refresh'):
            screen.refresh()

    def _render():
        box.clear_widgets()
        box.add_widget(_auto_label('نوع: ' + str(item.get('mode', '')), bold=True,
                                   font_size='15sp', color=C_GOLD, halign='right'))
        box.add_widget(_auto_label('آیهٔ مبدأ (بذر)', bold=True, font_size='14sp', color=C_GOLD, halign='right'))
        box.add_widget(_verse_block(C_PURPLE, item.get('seed_s'), item.get('seed_a'),
                                    item.get('seed_arb', ''), item.get('seed_pers', '')))
        targets = item.get('all_targets', [])
        box.add_widget(_auto_label('مقصدها (%d):' % len(targets), bold=True,
                                   font_size='14sp', color=C_ORANGE, halign='right'))
        for idx, t in enumerate(targets):
            box.add_widget(_verse_block(C_GOLD, t.get('s'), t.get('a'), t.get('arb', ''), t.get('pers', '')))
            if t.get('operator'):
                box.add_widget(_auto_label('عملگر: ' + str(t.get('operator')), font_size='12sp',
                                           color=C_MUTED, halign='right'))
            if source == 'lab':
                rmb = PillButton('حذف این مقصد از گروه', bg=C_RED, size_hint_y=None, height=dp(38), font_size='12sp')

                def _rm(*a, i=idx):
                    def _do():
                        ok, msg = app.remove_target_from_group(item, i)
                        toast(msg, 'گروهی' if ok else 'خطا')
                        if ok:
                            if not item.get('all_targets'):
                                p.dismiss()
                                _refresh_parent()
                            else:
                                _render()
                    confirm('این مقصد از گروه حذف شود؟', _do, 'حذف مقصد')
                rmb.bind(on_release=_rm)
                box.add_widget(rmb)
        box.add_widget(_auto_label('رفتار شبکه: ' + str(item.get('relation_type', 'نامشخص')),
                                   font_size='14sp', color=C_ORANGE, halign='right'))
        _note = item.get('note', '')
        box.add_widget(_auto_label('تحلیل شما: ' + (_note if _note else '—'),
                                   font_size='14sp', color=C_TEXT, halign='right'))

    _render()
    scroll.add_widget(box)
    root.add_widget(scroll)

    def _edit(*a):
        open_note_editor(item, source, title='ویرایش تحلیل', on_saved=_render)

    def _delete(*a):
        def _do():
            lst = app.favs if source == 'lab' else app.featured
            if item in lst:
                lst.remove(item)
            if source == 'lab':
                app.save_favs()
            else:
                app.save_featured()
            p.dismiss()
            _refresh_parent()
        confirm('کل این کشف گروهی حذف شود؟', _do, 'حذف کشف')

    def _to_featured(*a):
        app.featured.append(dict(item))
        app.save_featured()
        toast('به گلچین افزوده شد.', 'گلچین')

    grid = GridLayout(cols=2, size_hint_y=None, height=dp(104), spacing=dp(8))
    if source == 'lab':
        bb = PillButton('افزودن به گلچین', bg=C_GOLD, font_size='14sp')
        bb.bind(on_release=_to_featured)
        grid.add_widget(bb)
    be = PillButton('ویرایش تحلیل', bg=C_BLUE, font_size='14sp')
    be.bind(on_release=_edit)
    grid.add_widget(be)
    bd = PillButton('حذف کشف' if source == 'lab' else 'حذف از گلچین', bg=C_RED, font_size='14sp')
    bd.bind(on_release=_delete)
    grid.add_widget(bd)
    root.add_widget(grid)
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def show_discovery(item, source='lab', screen=None):
    if 'all_targets' in item:
        return show_group_discovery(item, source, screen)
    app = App.get_running_app()
    root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
    box.bind(minimum_height=box.setter('height'))
    box.add_widget(_auto_label('آیهٔ مبدأ (بذر)', bold=True, font_size='15sp', color=C_GOLD, halign='right'))
    box.add_widget(_verse_block(C_PURPLE, item.get('seed_s'), item.get('seed_a'),
                                item.get('seed_arb', ''), item.get('seed_pers', '')))
    box.add_widget(_auto_label('گرهٔ کشف‌شده: ' + str(item.get('mode', '')), bold=True,
                               font_size='14sp', color=C_GOLD, halign='right'))
    box.add_widget(_verse_block(C_GOLD, item.get('target_s'), item.get('target_a'),
                                item.get('target_arb', ''), item.get('target_pers', '')))
    box.add_widget(_auto_label('رفتار شبکه: ' + str(item.get('relation_type', 'نامشخص')),
                               font_size='14sp', color=C_ORANGE, halign='right'))
    _note = item.get('note', '')
    box.add_widget(_auto_label('تحلیل شما: ' + (_note if _note else '—'),
                               font_size='14sp', color=C_TEXT, halign='right'))
    scroll.add_widget(box)
    root.add_widget(scroll)
    p = Popup(title=P('جزئیات کشف'), content=root, size_hint=(0.96, 0.9),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _refresh_parent():
        if screen is not None and hasattr(screen, 'refresh'):
            screen.refresh()

    def _copy(*a):
        try:
            from kivy.core.clipboard import Clipboard
            txt = ('[%s] رفتار: %s\n' % (item.get('mode', ''), item.get('relation_type', ''))
                   + 'مبدأ (سوره %s آیه %s): %s\n%s\n' % (item.get('seed_s'), item.get('seed_a'),
                     item.get('seed_arb', ''), item.get('seed_pers', ''))
                   + 'مقصد (سوره %s آیه %s): %s\n%s\n' % (item.get('target_s'), item.get('target_a'),
                     item.get('target_arb', ''), item.get('target_pers', ''))
                   + ('تحلیل: ' + _note if _note else ''))
            Clipboard.copy(txt)
            toast('اطلاعات کشف کپی شد.', 'کپی')
        except Exception:
            toast('کپی ممکن نشد.', 'خطا')

    def _delete(*a):
        def _do():
            lst = app.favs if source == 'lab' else app.featured
            key = (item.get('seed_s'), item.get('seed_a'), item.get('target_s'),
                   item.get('target_a'), item.get('mode'))
            for i, it in enumerate(lst):
                if (it.get('seed_s'), it.get('seed_a'), it.get('target_s'),
                        it.get('target_a'), it.get('mode')) == key:
                    del lst[i]
                    break
            if source == 'lab':
                app.save_favs()
            else:
                app.save_featured()
            p.dismiss()
            _refresh_parent()
        confirm('این کشف حذف شود؟', _do, 'حذف کشف')

    def _to_featured(*a):
        app.add_featured(item)

    def _edit(*a):
        content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
        # فیلد متن + پیش‌نمایشِ زندهٔ درست (سازگار با موتورِ sdl2)
        ti = _add_analysis_field(content, item.get('note', ''))
        _ai_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        _ai_btn = PillButton('✦ کمکِ هوش مصنوعی در تحلیل', bg=C_PURPLE, fg=HOME_FG, font_size='14sp')

        def _ai_fill(*a):
            seed = {'s': item.get('seed_s'), 'a': item.get('seed_a'),
                    'arb': item.get('seed_arb', ''), 'pers': item.get('seed_pers', '')}
            target = {'s': item.get('target_s'), 'a': item.get('target_a'),
                      'arb': item.get('target_arb', ''), 'pers': item.get('target_pers', '')}
            operator = item.get('mode', '') or 'نامشخص'
            msgs = ai_manager.build_note_messages(seed, target, operator)
            _ai_btn.disabled = True
            _ai_btn.set_text('در حال نوشتن تحلیل...')

            def _done(full):
                _ai_btn.disabled = False
                _ai_btn.set_text('✦ بازنویسی با هوش مصنوعی')
                txt = (full or '').strip()
                if txt:
                    ti.set_logical(txt)
                else:
                    toast('پاسخی دریافت نشد.', 'هوش مصنوعی', kind='warn')

            def _err(msg):
                _ai_btn.disabled = False
                _ai_btn.set_text('✦ کمکِ هوش مصنوعی در تحلیل')
                toast(msg, 'هوش مصنوعی', kind='error')

            ai_manager.chat(msgs, on_done=_done, on_error=_err,
                            stream=False, temperature=0.5, max_tokens=600)

        _ai_btn.bind(on_release=_ai_fill)
        _ai_row.add_widget(_ai_btn)
        content.add_widget(_ai_row)
        _get_tags2 = _tag_multiselect(content, list(app.get_all_tags()), item.get('relation_type'), 'برچسب (رفتار شبکه) — چند انتخابی:')
        # امکان تغییر وضعیت (تردیدی ↔ مطمئن) برای همین کشف — مخصوصاً برای خارج‌کردنِ کشف از بخشِ تردیدی‌ها
        _st = {'d': bool(item.get('is_doubtful', False))}
        b_status = PillButton('وضعیت: تردیدی' if _st['d'] else 'وضعیت: مطمئن',
                              bg=C_ORANGE if _st['d'] else C_GREEN, size_hint_y=None, height=dp(44), font_size='14sp')

        def _tog_status(*a):
            _st['d'] = not _st['d']
            b_status.set_text('وضعیت: تردیدی' if _st['d'] else 'وضعیت: مطمئن')
            b_status._bg = list(C_ORANGE if _st['d'] else C_GREEN)
            b_status._state()
        b_status.bind(on_release=_tog_status)
        content.add_widget(b_status)
        ep = Popup(title=P('ویرایش تحلیل'), content=content, size_hint=(0.96, 0.94),
                   title_font='ui', title_align='center', separator_color=C_GOLD)
        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        sv = PillButton('ذخیره', bg=C_GREEN)

        def _sv(*a):
            item['note'] = ti.query
            item['relation_type'] = _get_tags2()
            item['is_doubtful'] = _st['d']
            if source == 'lab':
                app.save_favs()
            else:
                app.save_featured()
            ep.dismiss()
            p.dismiss()
            _refresh_parent()
            toast('تغییرات ذخیره شد ✓', 'ذخیره')
        sv.bind(on_release=_sv)
        cn = PillButton('انصراف', bg=C_RED)
        cn.bind(on_release=ep.dismiss)
        row2.add_widget(sv)
        row2.add_widget(cn)
        content.add_widget(row2)
        ep.open()

    grid = GridLayout(cols=2, size_hint_y=None, height=dp(104), spacing=dp(8))
    if source == 'lab':
        bb = PillButton('افزودن به گلچین', bg=C_GOLD, font_size='14sp')
        bb.bind(on_release=_to_featured)
        grid.add_widget(bb)
    be = PillButton('ویرایش تحلیل', bg=C_BLUE, font_size='14sp')
    be.bind(on_release=_edit)
    grid.add_widget(be)
    bd = PillButton('حذف کشف' if source == 'lab' else 'حذف از گلچین', bg=C_RED, font_size='14sp')
    bd.bind(on_release=_delete)
    grid.add_widget(bd)
    bc = PillButton('کپی اطلاعات', bg=C_GREEN, font_size='14sp')
    bc.bind(on_release=_copy)
    grid.add_widget(bc)
    root.add_widget(grid)
    b_exp = PillButton('افزودن به آزمایش', bg=C_INDIGO, fg=HOME_FG, size_hint_y=None, height=dp(46))
    b_exp.bind(on_release=lambda *a: _exp_attach_dialog(_exp_item_from_discovery(dict(item, source=source)), 'افزودن این کشف به یک آزمایش'))
    root.add_widget(b_exp)
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


# ==================================================================
# دفترِ پژوهش (Experiment notebook)
# لایه‌ی ساختاریافته برای ثبت فرضیه، روش، نتیجه و موردهای مرتبط
# ==================================================================
EXP_STATUS = [
    ('open', '⏳ باز', C_ORANGE),
    ('confirmed', '✅ تأییدشده', C_GREEN),
    ('rejected', '❌ رد شده', C_RED),
]


def _exp_status_meta(status):
    for k, lbl, col in EXP_STATUS:
        if k == status:
            return lbl, col
    return EXP_STATUS[0][1], EXP_STATUS[0][2]


def _exp_item_key(it):
    if not isinstance(it, dict):
        return None
    if it.get('kind') == 'verse':
        return ('verse', it.get('s'), it.get('a'))
    return ('pair', it.get('seed_s'), it.get('seed_a'),
            it.get('target_s'), it.get('target_a'), it.get('mode'))


def _exp_item_from_discovery(item):
    d = dict(item)
    d['kind'] = 'pair'
    return d


def _exp_sep():
    return RoundBox(bg=(1, 1, 1, 0.10), size_hint_y=None, height=dp(2), radius=1, shadow=False)


def _exp_create_dialog(first_item=None, on_created=None):
    def _ok(val):
        title = (val or '').strip()
        if not title:
            toast('عنوان نمی‌تواند خالی باشد.', 'دفتر پژوهش', kind='warn')
            return
        app = App.get_running_app()
        exp = app.exp_create(title)
        if first_item is not None:
            app.exp_add_item(exp, first_item)
        toast('آزمایش ساخته شد ✓', 'دفتر پژوهش')
        try:
            app.sm.get_screen('experiment').refresh()
        except Exception:
            pass
        if on_created:
            on_created(exp)
    prompt_text('عنوان یا فرضیهٔ کوتاهِ آزمایش:', '', _ok,
                title='آزمایشِ جدید', ok_label='بساز')


def _exp_attach_dialog(new_item, desc=''):
    """انتخابِ آزمایش برای پیوستِ یک مورد (جفت یا آیهٔ تکی)."""
    app = App.get_running_app()
    exps = getattr(app, 'experiments', []) or []
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    if desc:
        root.add_widget(RLabel(desc, font_size='13sp', halign='center', color=C_GOLD,
                               size_hint_y=None, height=dp(30)))
    b_new = PillButton('+ آزمایشِ جدید با این مورد', bg=C_GREEN, size_hint_y=None, height=dp(48))
    root.add_widget(b_new)
    root.add_widget(RLabel('یا افزودن به آزمایشِ موجود:', font_size='13sp', halign='right',
                           color=C_MUTED, size_hint_y=None, height=dp(24)))
    sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(2))
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    root.add_widget(sv)
    p = Popup(title=P('افزودن به آزمایش'), content=root, size_hint=(0.94, 0.86),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _attach(exp):
        ok = app.exp_add_item(exp, new_item)
        p.dismiss()
        toast('به آزمایش افزوده شد ✓' if ok else 'این مورد از قبل در آزمایش هست.',
              'دفتر پژوهش', kind=None if ok else 'warn')
        try:
            app.sm.get_screen('experiment').refresh()
        except Exception:
            pass

    def _new(*a):
        p.dismiss()
        _exp_create_dialog(first_item=new_item)
    b_new.bind(on_release=_new)

    if not exps:
        grid.add_widget(RLabel('هنوز آزمایشی نساخته‌ای.', font_size='13sp', halign='center',
                               color=C_MUTED, size_hint_y=None, height=dp(30)))
    else:
        for exp in exps:
            txt = '%s  •  %d مورد' % (exp.get('title') or 'بی‌عنوان', len(exp.get('items') or []))
            b = PillButton(txt, bg=(0.16, 0.13, 0.05, 1), size_hint_y=None, height=dp(54), font_size='14sp')
            b.bind(on_release=lambda inst, e=exp: _attach(e))
            grid.add_widget(b)
    p.open()


def _exp_pick_verse_dialog(on_pick):
    """جست‌وجوی تک‌آیه در کلّ آیات (همان موتورِ جستجوی خانه) و انتخاب برای پیوست."""
    app = App.get_running_app()
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    ti = PersianTextInput(hint_text=P('جستجوی متن یا شمارهٔ آیه'),
                          font_name='arabic', halign='right', font_size='15sp',
                          multiline=False, size_hint_y=None, height=dp(48),
                          background_color=(1, 1, 1, 0.92),
                          foreground_color=(0.05, 0.08, 0.14, 1))
    root.add_widget(ti)
    b_go = PillButton('جستجو', bg=C_TEAL, fg=(0.05, 0.08, 0.14, 1), size_hint_y=None, height=dp(46))
    root.add_widget(b_go)
    head = RLabel('متن یا شمارهٔ آیه را جستجو کن و روی نتیجه بزن', font_size='13sp',
                  halign='center', color=C_MUTED, size_hint_y=None, height=dp(26))
    root.add_widget(head)
    sv = ScrollView(do_scroll_x=False, bar_width=dp(6), scroll_type=['bars', 'content'])
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(2))
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    root.add_widget(sv)
    p = Popup(title=P('افزودن آیه از جستجو'), content=root, size_hint=(0.96, 0.92),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _row(r):
        s, a = r['s'], r['a']
        arb = (r.get('arb', '') or '')
        pers = (r.get('pers', '') or '')
        arb_s = (arb[:70] + '…') if len(arb) > 70 else arb
        pers_s = (pers[:80] + '…') if len(pers) > 80 else pers
        card = ClickCard(bg=(0.11, 0.14, 0.22, 0.98), border=C_TEAL, orientation='vertical',
                         size_hint_y=None, height=dp(136), padding=dp(8), spacing=dp(2))
        card.add_widget(_rev_badge(s, halign='left', height=dp(14)))
        card.add_widget(RLabel('سوره %s ، آیه %s' % (s, a), font_size='12sp', halign='right',
                               color=C_ORANGE, size_hint_y=None, height=dp(20)))
        card.add_widget(RLabel(arb_s, arabic=True, font_size='15sp', halign='right',
                               color=C_TEXT, size_hint_y=None, height=dp(46)))
        card.add_widget(RLabel(pers_s, font_size='13sp', halign='right', color=C_MUTED,
                               size_hint_y=None, height=dp(34)))

        def _pick(*a, ss=s, aa=a):
            p.dismiss()
            on_pick(ss, aa)
        card.bind(on_release=_pick)
        return card

    def _run(*a):
        q = (ti.query or '').strip() if hasattr(ti, 'query') else ''
        if not q:
            toast('عبارت یا شمارهٔ آیه را وارد کن.', 'جستجو', kind='warn')
            return
        head.set_text('در حال جستجو…')
        grid.clear_widgets()

        def _work():
            try:
                res = app.data.search_all(q, limit=300)
                err = None
            except Exception as ex:
                res, err = None, str(ex)

            def _done(dt):
                if err:
                    head.set_text('خطا در جستجو: %s' % err)
                    return
                if not res:
                    head.set_text('آیه‌ای پیدا نشد.')
                    return
                head.set_text('%d نتیجه — روی آیه بزن تا وصل شود' % len(res))
                for r in res[:80]:
                    grid.add_widget(_row(r))
            Clock.schedule_once(_done, 0)
        threading.Thread(target=_work, daemon=True).start()

    b_go.bind(on_release=_run)
    ti.bind(on_text_validate=_run)
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def _exp_disc_pick_card(it, src, on_pick):
    tag = 'گلچین' if src == 'featured' else 'لابراتوار'
    card = ClickCard(bg=(0.11, 0.14, 0.22, 0.98), border=C_GOLD, orientation='vertical',
                     size_hint_y=None, height=dp(114), padding=dp(8), spacing=dp(2))
    card.add_widget(_rev_pair_badge(it.get('seed_s'), it.get('target_s'), halign='left', height=dp(14)))
    card.add_widget(RLabel('[%s] سوره %s:%s ↔ سوره %s:%s  %s' % (tag, it.get('seed_s'),
                    it.get('seed_a'), it.get('target_s'), it.get('target_a'), it.get('mode', '') or ''),
                    font_size='12sp', halign='right', color=C_ORANGE, size_hint_y=None, height=dp(22)))
    arb = (it.get('target_arb', '') or it.get('seed_arb', '') or '')
    arb_s = (arb[:60] + '…') if len(arb) > 60 else arb
    card.add_widget(RLabel('« %s »' % arb_s, arabic=True, font_size='14sp', halign='right',
                    color=C_TEXT, size_hint_y=None, height=dp(50)))
    card.bind(on_release=lambda *a: on_pick(it, src))
    return card


def _exp_pick_discovery_dialog(exp, on_added=None):
    """انتخاب از کشفیاتِ ذخیره‌شده (لابراتوار + گلچین) برای پیوست به آزمایش."""
    app = App.get_running_app()
    allitems = [(it, 'lab') for it in getattr(app, 'favs', []) if isinstance(it, dict)]
    allitems += [(it, 'featured') for it in getattr(app, 'featured', []) if isinstance(it, dict)]
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    ti = PersianTextInput(hint_text=P('فیلترِ متن/سوره'), font_name='ui', halign='right',
                          font_size='14sp', multiline=False, size_hint_y=None, height=dp(44),
                          background_color=(1, 1, 1, 0.92), foreground_color=(0.05, 0.08, 0.14, 1))
    root.add_widget(ti)
    head = RLabel('روی یک کشف بزن تا به آزمایش وصل شود', font_size='13sp', halign='center',
                  color=C_MUTED, size_hint_y=None, height=dp(24))
    root.add_widget(head)
    sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(6), padding=dp(2))
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    root.add_widget(sv)
    p = Popup(title=P('افزودن از کشفیات'), content=root, size_hint=(0.96, 0.92),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _add(it, src):
        d = _exp_item_from_discovery(it)
        d['source'] = src
        ok = app.exp_add_item(exp, d)
        p.dismiss()
        if on_added:
            on_added()
        toast('کشف به آزمایش وصل شد ✓' if ok else 'این کشف از قبل در آزمایش هست.',
              'دفتر پژوهش', kind=None if ok else 'warn')

    def _hay(it):
        try:
            sn = qref.name(int(it.get('seed_s'))) if it.get('seed_s') else ''
        except Exception:
            sn = ''
        try:
            tn = qref.name(int(it.get('target_s'))) if it.get('target_s') else ''
        except Exception:
            tn = ''
        return _norm_search(' '.join([str(it.get('seed_arb', '')), str(it.get('target_arb', '')),
                                      str(it.get('seed_pers', '')), str(it.get('target_pers', '')),
                                      str(it.get('mode', '')), str(sn), str(tn),
                                      '%s %s %s %s %s:%s %s:%s' % (it.get('seed_s'), it.get('seed_a'),
                                       it.get('target_s'), it.get('target_a'),
                                       it.get('seed_s'), it.get('seed_a'),
                                       it.get('target_s'), it.get('target_a'))]))

    def _match(it, toks):
        if not toks:
            return True
        hay = _hay(it)
        return all(t in hay for t in toks)

    def _section(title, color):
        grid.add_widget(RLabel(title, font_size='13sp', bold=True, halign='right', color=color,
                               size_hint_y=None, height=dp(28)))

    def _build(*a):
        grid.clear_widgets()
        raw = (ti.query or '').strip() if hasattr(ti, 'query') else ''
        qn = _norm_search(raw) if raw else ''
        toks = [t for t in qn.split(' ') if t] if qn else []
        shown = 0
        for gsrc, gtitle, gcolor in (('lab', 'کشفیاتِ لابراتوار', C_TEAL),
                                     ('featured', 'گلچین', C_GOLD)):
            g_items = [it for (it, src) in allitems if src == gsrc and _match(it, toks)]
            if not g_items:
                continue
            _section('%s (%d)' % (gtitle, len(g_items)), gcolor)
            for it in g_items:
                grid.add_widget(_exp_disc_pick_card(it, gsrc, _add))
                shown += 1
                if shown >= 200:
                    break
            if shown >= 200:
                break
        if shown == 0:
            head.set_text('کشفی مطابقِ فیلتر پیدا نشد.')
        else:
            head.set_text('%d کشف — روی یکی بزن' % shown)

    ti.on_change = lambda *a: _build()
    ti.bind(on_text_validate=_build)
    if not allitems:
        head.set_text('هنوز کشفی ذخیره نکرده‌ای.')
    else:
        _build()
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def _exp_show_verse(it):
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))
    root.add_widget(_verse_block(C_TEAL, it.get('s'), it.get('a'),
                                 it.get('arb', ''), it.get('pers', '')))
    p = Popup(title=P('آیهٔ تکی'), content=root, size_hint=(0.94, 0.6),
              title_font='ui', title_align='center', separator_color=C_GOLD)
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def _exp_item_row(it, on_open, on_remove):
    row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60), spacing=dp(6))
    is_verse = it.get('kind') == 'verse'
    card = ClickCard(bg=(0.11, 0.14, 0.22, 1), border=(C_TEAL if is_verse else C_GOLD),
                     orientation='vertical', size_hint_y=None, height=dp(60),
                     padding=dp(8), spacing=dp(2))
    if is_verse:
        top = 'سوره %s : آیه %s  —  آیهٔ تکی  ·  %s' % (it.get('s'), it.get('a'), _rev_tag(it.get('s')))
        arb = (it.get('arb', '') or '')
    else:
        top = 'سوره %s:%s ↔ سوره %s:%s  —  %s  ·  %s' % (it.get('seed_s'), it.get('seed_a'),
              it.get('target_s'), it.get('target_a'), it.get('mode', '') or 'جفت',
              _rev_pair_text(it.get('seed_s'), it.get('target_s')))
        arb = (it.get('target_arb', '') or it.get('seed_arb', '') or '')
    arb_s = (arb[:44] + '…') if len(arb) > 44 else arb
    card.add_widget(RLabel(top, font_size='12sp', halign='right', color=C_ORANGE,
                           size_hint_y=None, height=dp(20)))
    card.add_widget(RLabel('« %s »' % arb_s, arabic=True, font_size='14sp', halign='right',
                           color=C_TEXT, size_hint_y=None, height=dp(28)))
    card.bind(on_release=lambda *a: on_open(it))
    rm_wrap = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(52),
                        padding=[dp(3), dp(0)], spacing=dp(2))
    rm_wrap.add_widget(Widget(size_hint_y=1))
    b_rm = PillButton('🗑 حذف', bg=C_RED, fg=(1, 1, 1, 1),
                      size_hint=(None, None), size=(dp(46), dp(30)), radius=8,
                      font_size='11sp')
    b_rm.bind(on_release=lambda *a: on_remove(it))
    rm_wrap.add_widget(b_rm)
    rm_wrap.add_widget(RLabel('این آیه', font_size='9sp', halign='center', color=C_MUTED,
                              size_hint_y=None, height=dp(13)))
    rm_wrap.add_widget(Widget(size_hint_y=1))
    row.add_widget(card)
    row.add_widget(rm_wrap)
    return row


def _exp_detail_dialog(exp, screen=None):
    app = App.get_running_app()
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
    box.bind(minimum_height=box.setter('height'))
    scroll.add_widget(box)
    root.add_widget(scroll)
    p = Popup(title=P('آزمایش'), content=root, size_hint=(0.97, 0.94),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _touch():
        exp['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        app.save_experiments()

    def _refresh_screen():
        if screen is not None and hasattr(screen, 'refresh'):
            screen.refresh()

    def _open_edit(label, field, multiline):
        cur = str(exp.get(field, '') or '')
        if not multiline:
            def _ok(v):
                exp[field] = (v or '').strip()
                _touch(); _rebuild(); _refresh_screen()
            prompt_text(label + ':', cur, _ok, title=label, ok_label='ذخیره')
            return

        def _save(val):
            exp[field] = (val or '').strip()
            _touch(); _rebuild(); _refresh_screen()
        open_big_analysis_editor(cur, _save)

    def _field_row(label, field, color=C_TEXT, multiline=True):
        val = str(exp.get(field, '') or '').strip()
        box.add_widget(_auto_label(label, bold=True, font_size='14sp', color=C_GOLD, halign='right'))
        box.add_widget(_auto_label(val if val else '—', font_size='14sp', color=color, halign='right'))
        b = PillButton('✏️ ویرایش', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        b.bind(on_release=lambda *a, lb=label, fl=field, ml=multiline: _open_edit(lb, fl, ml))
        box.add_widget(b)

    def _cycle_status(*a):
        order = [k for k, _l, _c in EXP_STATUS]
        cur = exp.get('status', 'open')
        try:
            nxt = order[(order.index(cur) + 1) % len(order)]
        except Exception:
            nxt = 'open'
        exp['status'] = nxt
        _touch(); _rebuild(); _refresh_screen()

    def _add_from_disc(*a):
        _exp_pick_discovery_dialog(exp, on_added=lambda: (_rebuild(), _refresh_screen()))

    def _add_from_search(*a):
        def _pick(s, aa):
            v = app.data.get(s, aa)
            v = v if isinstance(v, dict) else {}
            it = {'kind': 'verse', 's': s, 'a': aa,
                  'arb': v.get('arb', ''), 'pers': v.get('pers', '')}
            ok = app.exp_add_item(exp, it)
            _rebuild(); _refresh_screen()
            toast('آیه افزوده شد ✓' if ok else 'این آیه از قبل در آزمایش هست.',
                  'دفتر پژوهش', kind=None if ok else 'warn')
        _exp_pick_verse_dialog(_pick)

    def _remove_item(it):
        def _do():
            app.exp_remove_item(exp, it)
            _rebuild(); _refresh_screen()
        confirm('این مورد از آزمایش برداشته شود؟', _do, 'برداشتن مورد')

    def _open_item(it):
        if it.get('kind') == 'verse':
            _exp_show_verse(it)
        else:
            show_discovery(it, source=it.get('source', 'lab'))

    def _delete_exp(*a):
        def _do():
            app.exp_delete(exp.get('id'))
            p.dismiss(); _refresh_screen()
        confirm('کلِ این آزمایش حذف شود؟', _do, 'حذف آزمایش')

    def _rebuild():
        box.clear_widgets()
        lbl, col = _exp_status_meta(exp.get('status', 'open'))
        box.add_widget(_auto_label(exp.get('title') or 'بی‌عنوان', bold=True, font_size='18sp',
                                   color=C_GOLD, halign='center'))
        b_title = PillButton('✏️ ویرایش عنوان', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        b_title.bind(on_release=lambda *a: _open_edit('عنوان', 'title', False))
        box.add_widget(b_title)
        b_status = PillButton('وضعیت: ' + lbl, bg=col, size_hint_y=None, height=dp(46), font_size='15sp')
        b_status.bind(on_release=_cycle_status)
        box.add_widget(b_status)
        box.add_widget(_exp_sep())
        _field_row('فرضیه', 'hypothesis')
        _field_row('نتیجه (یافته‌های من)', 'result')
        box.add_widget(_exp_sep())
        items = exp.get('items') or []
        box.add_widget(_auto_label('کشفیات و آیاتِ مرتبط (%d)' % len(items), bold=True,
                                   font_size='15sp', color=C_GOLD, halign='right'))
        addrow = GridLayout(cols=2, size_hint_y=None, height=dp(48), spacing=dp(8))
        b_disc = PillButton('افزودن از کشفیات', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), font_size='13sp')
        b_disc.bind(on_release=_add_from_disc)
        b_srch = PillButton('افزودن آیه از جستجو', bg=C_TEAL, fg=(0.05, 0.08, 0.14, 1), font_size='13sp')
        b_srch.bind(on_release=_add_from_search)
        addrow.add_widget(b_disc)
        addrow.add_widget(b_srch)
        box.add_widget(addrow)
        if not items:
            box.add_widget(_auto_label('هنوز موردی وصل نشده. از دو دکمهٔ بالا اضافه کن.',
                                       font_size='13sp', color=C_MUTED, halign='center'))
        else:
            for it in items:
                box.add_widget(_exp_item_row(it, on_open=_open_item, on_remove=_remove_item))
        box.add_widget(_exp_sep())
        b_ai_num = PillButton('گفت‌وگو با هوش مصنوعی — بُعد اعداد', bg=C_INDIGO, fg=HOME_FG,
                              size_hint_y=None, height=dp(52), font_size='14sp')
        b_ai_num.bind(on_release=lambda *a: open_experiment_ai(exp, screen, mode='numeric'))
        box.add_widget(b_ai_num)
        b_ai_sem = PillButton('گفت‌وگو با هوش مصنوعی — بُعد معنا', bg=C_TEAL, fg=(0.05, 0.08, 0.14, 1),
                              size_hint_y=None, height=dp(52), font_size='14sp')
        b_ai_sem.bind(on_release=lambda *a: open_experiment_ai(exp, screen, mode='semantic'))
        box.add_widget(b_ai_sem)
        b_del = PillButton('حذف آزمایش', bg=C_RED, size_hint_y=None, height=dp(46), font_size='14sp')
        b_del.bind(on_release=_delete_exp)
        box.add_widget(b_del)
        b_close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
        b_close.bind(on_release=p.dismiss)
        box.add_widget(b_close)

    _rebuild()
    p.open()


# ==================================================================
# دفترِ پژوهش — تحلیلِ عددی و گفت‌وگویِ اختصاصی با هوش مصنوعی
# ==================================================================
QURAN_TOTAL_AYAHS = 6236

# تسک‌های پیش‌فرض (کاربر بقیه را دستی اضافه می‌کند)
DEFAULT_MATH_TASKS = [
    'رجوع به جدول زوج و فرد',
    'مستطیلِ جادویی — از چهار متغیرِ هر آیه (شماره سوره، شماره آیه، '
    'تعداد کل آیاتِ سوره، شماره نزول) یک ماتریس/مستطیل بساز. چیدمانِ '
    'هر ردیف: راست=شماره سوره، چپ=شماره آیه؛ ردیفِ بعد همین دو برای آیهٔ دوم؛ '
    'سپس به همین ترتیب تعداد کل آیات و شماره نزول. با جبرِ خطی بررسی کن '
    'جمع و تفاضلِ اضلاعِ بالا و پایین، تفاضلِ اضلاعِ چپ و راست، و تفاضلِ قطرها '
    'با هم برابرند یا نه؛ نتیجه را روشن بگو.',
]

# تسک‌های پیش‌فرضِ بُعدِ معنا (کاربر بقیه را دستی اضافه می‌کند)
DEFAULT_SEMANTIC_TASKS = [
    'حروفِ مقطعه — بررسی کن آیا «حرفِ اول» و «حرفِ آخرِ» هر یک از دو آیه، '
    'جزوِ ۱۴ حرفِ مقطعه (نص حکیم قاطع له سر: ا،ل،م،ص،ر،ک،ه،ی،ع،ط،س،ح،ق،ن) هست یا نه. '
    'برای هر آیه حرفِ اول و آخر را مشخص کن، بگو کدام جزوِ این ۱۴ حرف است، و نتیجه را برای دو آیه کنار هم جمع‌بندی کن.',
    'هم‌آوایی و پیوندِ واژگانی — دو آیه را از نظرِ هم‌آواییِ واژه‌ای، اشتراکِ ریشهٔ کلمات، '
    'و تکرارِ واژه‌های مشترک بررسی کن. واژه‌ها یا ریشه‌های مشترک را فهرست کن و بگو پیوندِ لفظی چقدر قوی است.',
    'تحلیلِ مفهومی — دو آیه را از نظرِ معنا و پیام مقایسه کن: آیا مکمل‌اند، متقابل‌اند، '
    'علت و معلول‌اند، پرسش و پاسخ‌اند، یا زاویهٔ دیدِ متفاوت به یک موضوع؟ پیوندِ مفهومیِ اصلی را روشن توضیح بده.',
]


def _abs_ayah_index(s, a):
    """شمارهٔ ترتیبیِ آیه در کلِ قرآن (idx) و فاصله تا انتهای قرآن."""
    try:
        s = int(s); a = int(a)
    except Exception:
        return None, None
    if s < 1 or s > 114 or a < 1:
        return None, None
    before = 0
    for k in range(1, s):
        before += qref.total_ayahs(k)
    idx = before + a
    return idx, (QURAN_TOTAL_AYAHS - idx)


def _exp_numeric_verses(exp):
    """فهرستِ یکتا از آیاتِ آزمایش به‌صورتِ (label, s, a) — برای show_surah_info."""
    out = []
    seen = set()

    def _push(label, s, a):
        try:
            s = int(s); a = int(a)
        except Exception:
            return
        if (s, a) in seen:
            return
        seen.add((s, a))
        out.append((label, s, a))

    for it in (exp.get('items') or []):
        if not isinstance(it, dict):
            continue
        if it.get('kind') == 'verse':
            _push('آیهٔ تکی', it.get('s'), it.get('a'))
        else:
            _push('بذر', it.get('seed_s'), it.get('seed_a'))
            _push('مقصد', it.get('target_s'), it.get('target_a'))
    return out


def _exp_numeric_text(exp):
    """متنِ دادهٔ عددیِ آزمایش — برای تزریق در سیستم‌پرامت."""
    nl = chr(10)
    lines = ['=== دادهٔ عددیِ آیاتِ این آزمایش ===',
             'کلِ قرآن ۱۱۴ سوره و %d آیه است.' % QURAN_TOTAL_AYAHS]
    verses = _exp_numeric_verses(exp)
    if not verses:
        lines.append('(هنوز هیچ آیه/کشفی به آزمایش وصل نشده است.)')
    else:
        for i, (label, s, a) in enumerate(verses, 1):
            idx, dist = _abs_ayah_index(s, a)
            lines.append(
                '%d) %s — سوره %d («%s»)، آیه %d | شماره نزول=%d | تعداد کل آیاتِ سوره=%d | '
                'ترتیب در کل قرآن=%s | فاصله تا انتهای قرآن=%s آیه'
                % (i, label, s, qref.name(s), a, qref.nuzul(s), qref.total_ayahs(s),
                   ('؟' if idx is None else idx), ('؟' if dist is None else dist)))
    pairs = [it for it in (exp.get('items') or [])
             if isinstance(it, dict) and it.get('kind') != 'verse'
             and it.get('target_s') is not None]
    if pairs:
        lines.append('')
        lines.append('اثرانگشتِ ماتریسیِ جفت‌آیه‌ها (ماتریسِ ۲×۲ [[S,A],[s,a]]):')
        for i, it in enumerate(pairs, 1):
            try:
                fp = qref.fingerprint_text(it.get('seed_s'), it.get('seed_a'),
                                           it.get('target_s'), it.get('target_a'),
                                           qref.op_code(it.get('mode', '')))
                lines.append('%d) %s' % (i, fp.replace(nl, ' | ')))
            except Exception:
                pass
    return nl.join(lines)


def _exp_ai_system(exp):
    nl = chr(10)
    role = nl.join([
        'تو دستیارِ عددیِ اختصاصیِ بخشِ «دفترِ پژوهش» در اپلیکیشنِ «قطب‌نمای قرآنی» هستی.',
        'این گفت‌وگو کاملاً مخصوصِ همین آزمایش است و به هیچ بخش یا گفت‌وگوی دیگری ربطی ندارد.',
        'کاربر می‌خواهد فرضیه‌اش را در بُعدِ اعداد بیازماید. تو به دادهٔ عددیِ آیاتِ همین آزمایش دسترسی داری:',
        'برای هر آیه: شماره سوره، شماره آیه، تعداد کل آیاتِ سوره، شماره نزول، شمارهٔ ترتیبی در کل قرآن و فاصله تا انتهای قرآن.',
        'وقتی کاربر یک «تسکِ ریاضی/جبری» می‌دهد، دقیقاً همان را روی همین داده اجرا کن؛ محاسبات را گام‌به‌گام و شفاف نشان بده و در پایان نتیجه را روشن بگو.',
        'صادق باش: اگر تساوی/الگویی برقرار نیست، صریح بگو برقرار نیست. عدد از خودت نساز. فارسیِ روان و منظم بنویس.',
        'اگر کاربر تسکِ «رجوع به جدول زوج و فرد» را انتخاب کرد یا خواست به «جدولِ زوج و فرد» رجوع کنی، منظورش دقیقاً همان جدولی است که در پایین آمده: دسته‌بندیِ همگن/ناهمگنِ سوره‌ها بر پایهٔ زوج/فردبودنِ شمارهٔ سوره و تعدادِ آیات، به‌همراهِ مکی/مدنی و ۷۴ سورهٔ دارای قفلِ کریپتوگرافیک. از همان استفاده کن.',
        qref.ANALYSIS_GUIDE,
        qref.EVENODD_GUIDE,
    ])
    return role + nl + nl + _exp_numeric_text(exp)


def _exp_semantic_verses(exp):
    """فهرستِ یکتا از آیاتِ آزمایش به‌صورتِ (label, s, a, arb, pers) — برای بُعدِ معنا."""
    out = []
    seen = set()

    def _push(label, s, a, arb, pers):
        try:
            s = int(s); a = int(a)
        except Exception:
            return
        if (s, a) in seen:
            return
        seen.add((s, a))
        out.append((label, s, a, str(arb or ''), str(pers or '')))

    for it in (exp.get('items') or []):
        if not isinstance(it, dict):
            continue
        if it.get('kind') == 'verse':
            _push('آیهٔ تکی', it.get('s'), it.get('a'), it.get('arb'), it.get('pers'))
        else:
            _push('بذر', it.get('seed_s'), it.get('seed_a'), it.get('seed_arb'), it.get('seed_pers'))
            _push('مقصد', it.get('target_s'), it.get('target_a'), it.get('target_arb'), it.get('target_pers'))
    return out


def _exp_letter_mark(letter):
    if not letter:
        return '؟'
    tag = '✓ جزوِ حروف مقطعه' if qref.is_muqatta_letter(letter) else 'خارج از حروف مقطعه'
    return '«%s» %s' % (letter, tag)


def _exp_semantic_text(exp):
    """متنِ دادهٔ معناییِ آزمایش — برای تزریق در سیستم‌پرامت."""
    nl = chr(10)
    lines = ['=== متنِ آیاتِ این آزمایش (بُعدِ معنا) ===']
    verses = _exp_semantic_verses(exp)
    if not verses:
        lines.append('(هنوز هیچ آیه/کشفی به آزمایش وصل نشده است.)')
    else:
        for i, (label, s, a, arb, pers) in enumerate(verses, 1):
            first, last = qref.first_last_letters(arb)
            lines.append('%d) %s — سوره %d («%s») آیه %d' % (i, label, s, qref.name(s), a))
            lines.append('   عربی: %s' % (arb or '—'))
            lines.append('   ترجمه: %s' % (pers or '—'))
            lines.append('   حرفِ اول: %s | حرفِ آخر: %s' % (_exp_letter_mark(first), _exp_letter_mark(last)))
    return nl.join(lines)


def _exp_semantic_system(exp):
    nl = chr(10)
    role = nl.join([
        'تو دستیارِ معناییِ اختصاصیِ بخشِ «دفترِ پژوهش» در اپلیکیشنِ «قطب‌نمای قرآنی» هستی.',
        'این گفت‌وگو کاملاً مخصوصِ همین آزمایش است و به هیچ بخش یا گفت‌وگوی دیگری ربطی ندارد.',
        'کاربر می‌خواهد فرضیه‌اش را در بُعدِ معنا بیازماید. تو به متنِ عربی و ترجمهٔ آیاتِ همین آزمایش و نیز به جدولِ ۱۴ حرفِ مقطعه دسترسی داری.',
        'وقتی کاربر یک «تسک» می‌دهد، دقیقاً همان را روی همین آیات اجرا کن؛ تحلیل را شفاف و مستند بگو و در پایان نتیجه را روشن جمع‌بندی کن.',
        'صادق باش: اگر پیوند/الگویی نیست، صریح بگو نیست. از خودت آیه یا واژه نساز. فارسیِ روان و منظم بنویس.',
        qref.SEMANTIC_GUIDE,
        qref.MUQATTAAT_GUIDE,
    ])
    return role + nl + nl + _exp_semantic_text(exp)


def _exp_semantic_info(exp):
    """پنجرهٔ نمایشِ متنِ آیات + حرفِ اول/آخر و حروفِ مقطعه."""
    root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
    root.add_widget(RLabel('۱۴ حرفِ مقطعه (%s): %s' % (
        getattr(qref, 'MUQATTAAT_KEY', qref.MUQATTAAT_PHRASE), ''.join(qref.MUQATTAAT_LETTERS)),
        font_size='13sp', halign='center', color=C_GOLD, size_hint_y=None, height=dp(26)))
    sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(2))
    box.bind(minimum_height=box.setter('height'))
    verses = _exp_semantic_verses(exp)
    if not verses:
        box.add_widget(RLabel('هنوز آیه‌ای وصل نشده.', font_size='14sp', halign='center',
                              color=C_MUTED, size_hint_y=None, height=dp(30)))
    for (label, s, a, arb, pers) in verses:
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(4))
        card.add_widget(RLabel('%s — %s %d:%d' % (label, qref.name(s), s, a), font_size='13sp',
                               bold=True, color=C_GOLD, halign='right', size_hint_y=None, height=dp(24)))
        la = RLabel(arb or '—', arabic=True, font_size='16sp', halign='right', color=C_TEXT, size_hint_y=None)
        la.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(la)
        lp = RLabel(pers or '—', font_size='14sp', halign='right', color=C_MUTED, size_hint_y=None)
        lp.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(lp)
        first, last = qref.first_last_letters(arb)
        card.add_widget(RLabel('حرف اول: %s | حرف آخر: %s' % (_exp_letter_mark(first), _exp_letter_mark(last)),
                               font_size='12sp', halign='right', color=C_INFO, size_hint_y=None, height=dp(24)))
        card.bind(minimum_height=lambda i, v, c=card: setattr(c, 'height', v))
        box.add_widget(card)
    sv.add_widget(box)
    root.add_widget(sv)
    p = Popup(title=P('متنِ آیات و حروفِ مقطعه'), content=root, size_hint=(0.96, 0.92),
              title_font='ui', title_align='center', separator_color=C_GOLD)
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def open_experiment_tasks(on_pick=None, kind='numeric'):
    """پنجرهٔ تسک‌ها: انتخاب/افزودن/ویرایش/حذف. kind='numeric'|'semantic'. on_pick(text) متنِ تسک را برمی‌گرداند."""
    app = App.get_running_app()
    is_sem = (kind == 'semantic')
    tasks_attr = 'semantic_tasks' if is_sem else 'math_tasks'
    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    b_new = PillButton('+ تسکِ جدید', bg=C_GREEN, size_hint_y=None, height=dp(48), font_size='14sp')
    root.add_widget(b_new)
    root.add_widget(RLabel('روی «درج در چت» بزن تا تسک به گفت‌وگو برود' if on_pick else 'تسک‌های ریاضی را اینجا مدیریت کن',
                           font_size='12sp', halign='center', color=C_MUTED,
                           size_hint_y=None, height=dp(22)))
    sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(8), padding=dp(2))
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    root.add_widget(sv)
    p = Popup(title=P('تسک‌های معنا' if is_sem else 'تسک‌های ریاضی'), content=root, size_hint=(0.96, 0.92),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _task_card(t):
        text = str(t.get('text', '') or '')
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(6))
        lbl = RLabel(text, font_size='14sp', color=C_TEXT, halign='right', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(lbl)
        rowb = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        if on_pick:
            b_use = PillButton('درج در چت', bg=C_TEAL, fg=(0.05, 0.08, 0.14, 1), font_size='12sp')
            b_use.bind(on_release=lambda *a, tx=text: _use(tx))
            rowb.add_widget(b_use)
        b_edit = PillButton('ویرایش', bg=C_BLUE, font_size='12sp')
        b_edit.bind(on_release=lambda *a, tt=t: _edit(tt))
        b_del = PillButton('حذف', bg=(0.62, 0.17, 0.20, 1), fg=(1, 0.92, 0.92, 1), font_size='12sp')
        b_del.bind(on_release=lambda *a, tt=t: _del(tt))
        rowb.add_widget(b_edit)
        rowb.add_widget(b_del)
        card.add_widget(rowb)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
        return card

    def _rebuild():
        grid.clear_widgets()
        tasks = getattr(app, tasks_attr, []) or []
        if not tasks:
            grid.add_widget(RLabel('هنوز تسکی نساخته‌ای.', font_size='13sp', halign='center',
                                   color=C_MUTED, size_hint_y=None, height=dp(30)))
            return
        for t in tasks:
            grid.add_widget(_task_card(t))

    def _use(text):
        if on_pick:
            on_pick(text)
        p.dismiss()

    def _edit(t):
        def _save(val):
            app.task_update(t.get('id'), val, kind)
            _rebuild()
        open_big_analysis_editor(t.get('text', ''), _save)

    def _new(*a):
        def _save(val):
            if (val or '').strip():
                app.task_add(val, kind)
                _rebuild()
        open_big_analysis_editor('', _save)

    def _del(t):
        def _yes():
            app.task_delete(t.get('id'), kind)
            _rebuild()
        confirm('این تسک حذف شود؟', _yes, 'حذف تسک')

    b_new.bind(on_release=_new)
    _rebuild()
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


def open_experiment_ai(exp, screen=None, mode='numeric'):
    """پنجرهٔ تحلیل + چتِ اختصاصیِ هر آزمایش (جدا از بقیهٔ چت‌ها).
    mode='numeric' → بُعد اعداد | mode='semantic' → بُعد معنا."""
    app = App.get_running_app()
    is_sem = (mode == 'semantic')
    hist_key = 'ai_messages_semantic' if is_sem else 'ai_messages_numeric'
    # مهاجرتِ تاریخچهٔ نسخهٔ قبل (که فقط یک چتِ عددی داشت)
    if not is_sem and exp.get('ai_messages') and not exp.get(hist_key):
        exp[hist_key] = exp.get('ai_messages')
    if not isinstance(exp.get(hist_key), list):
        exp[hist_key] = []
    state = {'busy': False, 'acc': ''}

    root = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(6))
    topbar = GridLayout(cols=3, size_hint_y=None, height=dp(46), spacing=dp(6))
    b_num = PillButton('متن آیات' if is_sem else 'اطلاعات عددی', bg=C_INFO, font_size='12sp')
    if is_sem:
        b_num.bind(on_release=lambda *a: _exp_semantic_info(exp))
    else:
        b_num.bind(on_release=lambda *a: show_surah_info(_exp_numeric_verses(exp)))
    b_task = PillButton('تسک‌ها', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), font_size='12sp')
    b_conc = PillButton('نتیجه‌گیری', bg=C_GREEN, fg=(0.05, 0.08, 0.14, 1), font_size='12sp')
    topbar.add_widget(b_num)
    topbar.add_widget(b_task)
    topbar.add_widget(b_conc)
    root.add_widget(topbar)

    inrow = RoundBox(bg=(0.05, 0.08, 0.14, 0.62), orientation='horizontal', size_hint_y=None,
                     height=dp(60), padding=dp(6), spacing=dp(6))
    inp = PersianTextInput(hint_text=P('پیامت را بنویس یا یک تسک انتخاب کن...'), multiline=False,
                           font_size='15sp', background_color=(1, 1, 1, 0.95),
                           foreground_color=(0.05, 0.08, 0.14, 1))
    send = PillButton('ارسال', bg=C_GREEN, size_hint_x=None, width=dp(66), font_size='13sp')
    b_attach = PillButton('پیوست', bg=C_INDIGO, fg=HOME_FG, size_hint_x=None, width=dp(58), font_size='12sp')
    inrow.add_widget(inp)
    inrow.add_widget(b_attach)
    inrow.add_widget(send)
    root.add_widget(inrow)

    attach_state = {'file': None}
    attach_row = BoxLayout(size_hint_y=None, height=dp(0), spacing=dp(6), opacity=0)
    attach_lbl = RLabel('', font_size='12sp', halign='right', color=C_TEAL)
    b_attach_clear = PillButton('حذفِ پیوست', bg=C_RED, size_hint_x=None, width=dp(110), font_size='11sp')
    attach_row.add_widget(attach_lbl)
    attach_row.add_widget(b_attach_clear)
    root.add_widget(attach_row)

    def _update_attach_row():
        f = attach_state['file']
        if f:
            attach_lbl.set_text('پیوست: %s' % f['name'])
            attach_row.height = dp(34)
            attach_row.opacity = 1
        else:
            attach_lbl.set_text('')
            attach_row.height = dp(0)
            attach_row.opacity = 0

    def _clear_attach(*a):
        attach_state['file'] = None
        _update_attach_row()
    b_attach_clear.bind(on_release=_clear_attach)

    def _extract_pdf_text(path):
        for modname in ('pypdf', 'PyPDF2'):
            try:
                mod = __import__(modname)
                reader = mod.PdfReader(path)
                parts = []
                for pg in reader.pages:
                    try:
                        parts.append(pg.extract_text() or '')
                    except Exception:
                        pass
                txt = '\n'.join(parts).strip()
                if txt:
                    return txt
            except Exception:
                continue
        return ''

    def _load_attachment(path):
        try:
            name = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
        except Exception:
            toast('فایل نامعتبر است.', 'پیوست', kind='error')
            return
        img_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
        txt_ext = {'.txt', '.md', '.csv', '.json', '.py', '.log', '.html', '.xml',
                   '.js', '.ts', '.c', '.cpp', '.java', '.ini', '.yaml', '.yml'}
        try:
            if ext in img_ext:
                with open(path, 'rb') as f:
                    raw = f.read()
                if len(raw) > 6 * 1024 * 1024:
                    toast('تصویر خیلی بزرگ است (حداکثر ۶ مگابایت).', 'پیوست', kind='warn')
                    return
                mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else ('image/' + ext.lstrip('.'))
                data_url = 'data:%s;base64,%s' % (mime, base64.b64encode(raw).decode('ascii'))
                attach_state['file'] = {'name': name, 'kind': 'image', 'data_url': data_url}
            elif ext == '.pdf':
                txt = _extract_pdf_text(path)
                if not txt:
                    toast('استخراجِ متنِ این PDF روی این دستگاه ممکن نشد.', 'پیوست', kind='warn')
                    return
                attach_state['file'] = {'name': name, 'kind': 'text', 'text': txt[:12000]}
            elif ext in txt_ext:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    txt = f.read()
                attach_state['file'] = {'name': name, 'kind': 'text', 'text': txt[:12000]}
            else:
                toast('این نوع فایل پشتیبانی نمی‌شود (تصویر، متن یا PDF).', 'پیوست', kind='warn')
                return
        except Exception as ex:
            toast('خطا در خواندنِ فایل: %s' % ex, 'پیوست', kind='error')
            return
        _update_attach_row()
        toast('فایل پیوست شد ✓ — حالا پیامت را بنویس و بفرست.', 'پیوست')

    def _open_attach(*a):
        from kivy.uix.filechooser import FileChooserListView
        box = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        box.add_widget(RLabel('یک فایل انتخاب کن (تصویر، متن یا PDF)', font_size='13sp',
                              halign='center', color=C_MUTED, size_hint_y=None, height=dp(24)))
        start = '/'
        for cand in (os.path.expanduser('~'), '/sdcard', os.getcwd(), '/'):
            try:
                if cand and os.path.isdir(cand):
                    start = cand
                    break
            except Exception:
                continue
        fc = FileChooserListView(path=start,
                                 filters=['*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp', '*.bmp',
                                          '*.pdf', '*.txt', '*.md', '*.csv', '*.json', '*.py'])
        box.add_widget(fc)
        brow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_ok = PillButton('انتخاب', bg=C_GREEN)
        b_cancel = PillButton('انصراف', bg=C_RED)
        brow.add_widget(b_ok)
        brow.add_widget(b_cancel)
        box.add_widget(brow)
        fp = Popup(title=P('انتخابِ فایلِ پیوست'), content=box, size_hint=(0.97, 0.94),
                   title_font='ui', title_align='center', separator_color=C_GOLD)

        def _ok(*a):
            sel = fc.selection
            if not sel:
                toast('یک فایل را انتخاب کن.', 'پیوست', kind='warn')
                return
            fp.dismiss()
            _load_attachment(sel[0])
        b_ok.bind(on_release=_ok)
        b_cancel.bind(on_release=fp.dismiss)
        fp.open()
    b_attach.bind(on_release=_open_attach)

    mrow = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
    b_retest = PillButton('تست مجدد', bg=C_INDIGO, fg=HOME_FG, font_size='12sp')
    b_clear = PillButton('گفتگوی تازه', bg=(1, 1, 1, 0.14), font_size='12sp')
    mrow.add_widget(b_retest)
    mrow.add_widget(b_clear)
    root.add_widget(mrow)

    sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
    log = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(6))
    log.bind(minimum_height=log.setter('height'))
    sv.add_widget(log)
    root.add_widget(sv)

    p = Popup(title=P((('تحلیلِ معنا — ' if is_sem else 'تحلیلِ عددی — ') + (exp.get('title') or 'آزمایش'))), content=root,
              size_hint=(0.98, 0.96), title_font='ui', title_align='center', separator_color=C_GOLD)

    def _scroll_bottom(*a):
        sv.scroll_y = 0

    def _bubble(text, role='ai'):
        is_user = (role == 'user')
        bg = (0.10, 0.28, 0.16, 1) if is_user else (0.10, 0.14, 0.22, 1)
        card = RoundBox(bg=bg, orientation='vertical', size_hint_y=None, padding=dp(10), spacing=dp(4))
        who = RLabel('تو' if is_user else 'هوش مصنوعی', font_size='12sp', bold=True,
                     color=(C_GREEN if is_user else C_GOLD), halign='right',
                     size_hint_y=None, height=dp(20))
        card.add_widget(who)
        lbl = RLabel(text, font_size='15sp', color=C_TEXT, halign='right', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
        card.add_widget(lbl)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
        log.add_widget(card)
        try:
            _fade_in(card)
        except Exception:
            pass
        Clock.schedule_once(_scroll_bottom, 0.05)
        return lbl

    def _render_history():
        log.clear_widgets()
        if not exp[hist_key]:
            _bubble(('سلام! این گفت‌وگوی معنایی فقط برای همین آزمایش است. متنِ عربی و ترجمهٔ '
                     'آیاتِ افزوده‌شده و نیز جدولِ ۱۴ حرفِ مقطعه را در اختیار دارم. '
                     'یک تسک انتخاب کن یا سؤالت را بنویس.') if is_sem else
                    ('سلام! این گفت‌وگو فقط برای همین آزمایش است. اطلاعاتِ عددیِ آیاتِ '
                     'افزوده‌شده را دارم (سوره، آیه، نزول، تعداد آیات و فاصله تا انتهای قرآن). '
                     'یک تسک انتخاب کن یا سؤالت را بنویس تا محاسبه کنم.'), role='ai')
        else:
            for m in exp[hist_key]:
                _bubble(str(m.get('content') or ''),
                        role=('user' if m.get('role') == 'user' else 'ai'))

    def _persist():
        exp['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        try:
            app.save_experiments()
        except Exception:
            pass

    def _turn(user_text, to_result=False, attach=None):
        if state['busy']:
            toast('صبر کن تا پاسخِ قبلی کامل شود.', 'هوش مصنوعی')
            return
        user_text = (user_text or '').strip()
        if not user_text and not attach:
            return
        disp = user_text
        if attach:
            disp = (user_text + ('\n' if user_text else '') + '[پیوست: %s]' % attach.get('name', ''))
        _bubble(disp, role='user')
        store_text = user_text
        if attach and attach.get('kind') == 'text':
            store_text = (user_text + ('\n\n' if user_text else '') +
                          '[محتوای فایلِ پیوست «%s»]:\n%s' % (attach.get('name', ''), attach.get('text', '')))
        elif attach and attach.get('kind') == 'image':
            store_text = (user_text + ('\n' if user_text else '') +
                          '[تصویرِ پیوست: %s]' % attach.get('name', ''))
        exp[hist_key].append({'role': 'user', 'content': store_text})
        _persist()
        state['busy'] = True
        state['acc'] = ''
        target = _bubble('…', role='ai')
        msgs = [{'role': 'system', 'content': (_exp_semantic_system(exp) if is_sem else _exp_ai_system(exp))}] + \
               [{'role': m['role'], 'content': m['content']} for m in exp[hist_key][-12:]]
        if attach and attach.get('kind') == 'image':
            msgs[-1] = {'role': 'user', 'content': [
                {'type': 'text', 'text': (user_text or 'این تصویر را با توجه به موضوعِ آزمایش بررسی کن.')},
                {'type': 'image_url', 'image_url': {'url': attach.get('data_url', '')}},
            ]}

        def _delta(piece):
            state['acc'] += piece
            try:
                target.set_text(state['acc'])
            except Exception:
                target.text = state['acc']
            Clock.schedule_once(_scroll_bottom, 0)

        def _done(full=''):
            state['busy'] = False
            text = (full or state['acc'] or '').strip() or '(پاسخی دریافت نشد)'
            try:
                target.set_text(text)
            except Exception:
                target.text = text
            exp[hist_key].append({'role': 'assistant', 'content': text})
            if to_result:
                prev = (exp.get('result') or '').strip()
                stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                add = ('نتیجه‌گیریِ هوش مصنوعی (%s):' % stamp) + chr(10) + text
                exp['result'] = (prev + chr(10) + chr(10) + add) if prev else add
                toast('نتیجه‌گیری در بخشِ «نتیجه» ذخیره شد', 'دفتر پژوهش')
                try:
                    if screen is not None and hasattr(screen, 'refresh'):
                        screen.refresh()
                except Exception:
                    pass
            _persist()

        def _err(msg):
            state['busy'] = False
            try:
                target.set_text('⚠ ' + str(msg))
            except Exception:
                target.text = '⚠ ' + str(msg)
            toast(str(msg), 'هوش مصنوعی', kind='error')

        ai_manager.chat(msgs, on_delta=_delta, on_done=_done, on_error=_err,
                        stream=True, temperature=(0.5 if is_sem else 0.3), max_tokens=1600)

    def _send(*a):
        q = (inp.query or '').strip()
        attach = attach_state['file']
        if not q and not attach:
            return
        try:
            inp.clear_logical()
        except Exception:
            inp.text = ''
        _turn(q, attach=attach)
        if attach:
            attach_state['file'] = None
            _update_attach_row()

    def _pick_task(text):
        try:
            inp.set_logical(text)
        except Exception:
            inp.text = text

    def _conclude(*a):
        if state['busy']:
            toast('صبر کن تا پاسخِ قبلی کامل شود.', 'هوش مصنوعی')
            return
        if not exp[hist_key]:
            toast('اول کمی گفت‌وگو کن، بعد نتیجه‌گیری بگیر.', 'دفتر پژوهش')
            return
        _turn('بر اساسِ کلِ گفت‌وگوی بالا یک نتیجه‌گیریِ نهاییِ منسجم و کوتاه بنویس: '
              'آیا فرضیه در بُعدِ اعداد تأیید شد یا نه، و مهم‌ترین یافته‌های عددی چه بودند.',
              to_result=True)

    def _retest(*a):
        _turn('می‌خواهم همین فرضیه را دوباره و دقیق‌تر بیازماییم؛ خلاصه‌ای از وضعیتِ فعلی بده '
              'و گامِ بعدی را پیشنهاد بده.')

    def _clear(*a):
        def _yes():
            exp[hist_key] = []
            _persist()
            _render_history()
        confirm('کلِ گفت‌وگوی این آزمایش پاک شود؟', _yes, 'گفتگوی تازه')

    send.bind(on_release=_send)
    inp.bind(on_text_validate=_send)
    b_task.bind(on_release=lambda *a: open_experiment_tasks(on_pick=_pick_task, kind=mode))
    b_conc.bind(on_release=_conclude)
    b_retest.bind(on_release=_retest)
    b_clear.bind(on_release=_clear)

    b_close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(44), font_size='13sp')
    b_close.bind(on_release=p.dismiss)
    root.add_widget(b_close)

    _render_history()
    try:
        _neon_border(inrow, C_BLUE, width=1.4, alpha=0.9)
    except Exception:
        pass
    p.open()


class ExperimentScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='دفترِ پژوهش', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_new = PillButton('+ آزمایشِ جدید', bg=C_GREEN, font_size='14sp')
        b_new.bind(on_release=lambda *a: _exp_create_dialog())
        top.add_widget(b_new)
        self.body(top)
        srow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.search_in = PersianTextInput(hint_text=P('جستجو در فرضیه‌ها و یادداشت‌ها'),
                                          font_name='ui', halign='right', font_size='14sp',
                                          multiline=False,
                                          background_color=(1, 1, 1, 0.92),
                                          foreground_color=(0.05, 0.08, 0.14, 1))
        self.search_in.on_change = lambda *a: self.refresh()
        self.search_in.bind(on_text_validate=lambda *a: self.refresh())
        b_s = PillButton('جستجو', bg=C_BLUE, size_hint_x=None, width=dp(90), font_size='13sp')
        b_s.bind(on_release=lambda *a: self.refresh())
        srow.add_widget(self.search_in)
        srow.add_widget(b_s)
        self.body(srow)
        self.count_lbl = RLabel('', font_size='13sp', halign='center', color=C_MUTED,
                                size_hint_y=None, height=dp(24))
        self.body(self.count_lbl)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(4))
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        self.body(self.scroll)

    def refresh(self):
        app = App.get_running_app()
        allexps = getattr(app, 'experiments', []) or []
        try:
            raw = (self.search_in.query or '').strip()
        except Exception:
            raw = ''
        exps = allexps
        if raw:
            qn = _norm_search(raw)
            toks = [t for t in qn.split(' ') if t]

            def _match(e):
                hay = _norm_search(' '.join([str(e.get('title') or ''), str(e.get('hypothesis') or ''),
                                             str(e.get('method') or ''), str(e.get('result') or ''),
                                             str(e.get('control') or '')]))
                return all(t in hay for t in toks)
            exps = [e for e in allexps if isinstance(e, dict) and _match(e)]
        self.grid.clear_widgets()
        self.title_label.set_text('دفترِ پژوهش (%d)' % len(allexps))
        self.count_lbl.set_text('%d آزمایش' % len(exps))
        if not exps:
            self.grid.add_widget(empty_state('هنوز آزمایشی نداری',
                                             hint='با دکمهٔ + آزمایشِ جدید بساز، یا از کشفیات و جستجو مورد اضافه کن'))
            return
        for exp in exps:
            self.grid.add_widget(self._card(exp))

    def _card(self, exp):
        lbl, col = _exp_status_meta(exp.get('status', 'open'))
        card = ClickCard(bg=(0.10, 0.14, 0.22, 1), border=col, orientation='vertical',
                         size_hint_y=None, padding=dp(10), spacing=dp(4))
        card.bind(minimum_height=lambda i, v: setattr(i, 'height', v + dp(20)))
        card.add_widget(_auto_label(exp.get('title') or 'بی‌عنوان', bold=True, font_size='16sp',
                                    color=C_GOLD, halign='right'))
        meta = '%s   •   %d مورد   •   %s' % (lbl, len(exp.get('items') or []),
                                                  exp.get('updated') or exp.get('date') or '')
        card.add_widget(_auto_label(meta, font_size='12sp', color=C_MUTED, halign='right'))
        hyp = (exp.get('hypothesis') or '').strip()
        if hyp:
            hyp_s = (hyp[:90] + '…') if len(hyp) > 90 else hyp
            card.add_widget(_auto_label('فرضیه: ' + hyp_s, font_size='13sp', color=C_TEXT, halign='right'))
        card.bind(on_release=lambda *a, e=exp: _exp_detail_dialog(e, self))
        return card


class LabScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='لابراتوار کشفیات', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_all = PillButton('افزودن همه به گلچین', bg=C_GOLD, font_size='14sp')
        b_all.bind(on_release=lambda *a: self.add_all_featured())
        top.add_widget(b_all)
        self.count_lbl = RLabel('', font_size='14sp', halign='center', color=C_MUTED)
        top.add_widget(self.count_lbl)
        self.body(top)
        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        b_ai = PillButton('کپی پرامپت هوش مصنوعی', bg=C_PURPLE, font_size='13sp')
        b_ai.bind(on_release=lambda *a: self.copy_ai_prompt())
        b_html = PillButton('نمایش گزارش HTML', bg=C_BLUE, font_size='13sp')
        b_html.bind(on_release=lambda *a: self.open_html_viewer())
        row2.add_widget(b_ai)
        row2.add_widget(b_html)
        self.body(row2)
        row3 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        b_clear = PillButton('پاک کردن کل کشفیات', bg=C_RED, font_size='13sp')
        b_clear.bind(on_release=lambda *a: self.clear_all())
        row3.add_widget(b_clear)
        self.body(row3)
        self.body(RLabel('برای دیدن کشف‌های هر عملگر، روی آن بزنید.', font_size='13sp',
                         halign='center', color=C_MUTED, size_hint_y=None, height=dp(26)))
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(4))
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        self.body(self.scroll)

    def refresh(self):
        app = App.get_running_app()
        self.grid.clear_widgets()
        self.count_lbl.set_text('%d کشف' % len(app.favs))
        if not app.favs:
            self.grid.add_widget(empty_state('هنوز کشفی ثبت نشده است',
                                             hint='از صفحهٔ اصلی یک بذر انتخاب کن و اولین کشفت را ثبت کن'))
            return
        counts = {}
        for it in app.favs:
            k = lab_section_of(it)
            counts[k] = counts.get(k, 0) + 1
        last_sec = getattr(app, 'last_discovery_section', None)
        ordered = list(LAB_SECTIONS)
        if last_sec:
            ordered.sort(key=lambda kt: 0 if kt[0] == last_sec else 1)
        for key, title in ordered:
            n = counts.get(key, 0)
            if n == 0:
                continue
            if key == last_sec:
                label = '● %s  (%d کشف)  — جدید' % (title, n)
            else:
                label = '%s  (%d کشف)' % (title, n)
            b = PillButton(label, bg=(0.16, 0.13, 0.05, 1),
                           size_hint_y=None, height=dp(64), font_size='16sp')
            b.bind(on_release=lambda inst, k=key, t=title: self.open_op(k, t))
            self.grid.add_widget(b)
            if key == last_sec:
                apply_glow(b, C_GREEN, speed=0.6, width=5.0, hi=1.0, lo=0.25)

    def open_op(self, key, title):
        scr = self.manager.get_screen('operator')
        scr.load('lab', key, title)
        self.manager.transition = SlideTransition(direction='left')
        self.manager.current = 'operator'

    def add_all_featured(self):
        app = App.get_running_app()
        n = app.add_all_featured()
        toast('%d کشف به گلچین اضافه شد.' % n, 'گلچین')

    def clear_all(self):
        app = App.get_running_app()

        def _do():
            app.favs = []
            app.save_favs()
            self.refresh()
        confirm('کل کشفیات لابراتوار پاک شود؟', _do, 'پاک کردن کل')

    def copy_ai_prompt(self):
        app = App.get_running_app()
        if not app.favs:
            toast('ابتدا چند کشف ثبت کنید.', 'هوش مصنوعی')
            return
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(features.build_semantic_prompt(app.favs))
            toast('پرامپت تحلیل معنایی کپی شد؛ آن را در چت هوش مصنوعی بچسبانید.', 'هوش مصنوعی')
        except Exception:
            toast('کپی ممکن نشد.', 'خطا')

    def open_html_viewer(self):
        app = App.get_running_app()
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(10))
        content.add_widget(RLabel('کد HTML گزارش هوش مصنوعی را اینجا بچسبانید:',
                                  font_size='14sp', color=C_GOLD, halign='center', size_hint_y=None, height=dp(50)))
        ti = PlainInput(multiline=True, font_size='12sp', size_hint_y=1,
                       background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
        content.add_widget(ti)
        pop = Popup(title=P('نمایش گزارش HTML'), content=content, size_hint=(0.96, 0.85),
                    title_font='ui', title_align='center', separator_color=C_GOLD)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        bshow = PillButton('نمایش گزارش', bg=C_GREEN)

        def _show(*a):
            html = ti.text or ''
            if not html.strip():
                toast('متن HTML خالی است.', 'خطا')
                return
            show_html_in_app(html)   # نمایش داخل خودِ برنامه (بدون نیاز به مرورگر)
        bshow.bind(on_release=_show)
        bclose = PillButton('بستن', bg=C_RED)
        bclose.bind(on_release=pop.dismiss)
        row.add_widget(bshow)
        row.add_widget(bclose)
        content.add_widget(row)
        pop.open()


class OperatorScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='کشف‌های عملگر', **kw)
        self.title_label._fit_single = True
        self.source = 'lab'
        self.op_key = 'T1'
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)

    def load(self, source, op_key, title):
        self.source = source
        self.op_key = op_key
        src_name = 'لابراتوار' if source == 'lab' else 'گلچین'
        self.title_label.set_text('%s — %s' % (src_name, title))
        self.refresh()

    def refresh(self):
        app = App.get_running_app()
        self.list.clear_widgets()
        # هر بار که این بخش دوباره باز می‌شود، رندرِ قبلی (اگر در جریان بود) لغو شود
        self._op_gen = getattr(self, '_op_gen', 0) + 1
        gen = self._op_gen
        if getattr(self, '_op_render_ev', None) is not None:
            self._op_render_ev.cancel()
            self._op_render_ev = None
        items = app.favs if self.source == 'lab' else app.featured
        key_fn = lab_section_of if self.source == 'lab' else op_of
        matched = [it for it in items if key_fn(it) == self.op_key]
        # آخرین کشفِ ثبت‌شده باید اولِ لیست بیاید (favs به‌ترتیبِ افزوده‌شدن است)
        if self.source == 'lab':
            matched.reverse()
        if not matched:
            self.list.add_widget(empty_state('در این بخش هنوز کشفی نیست',
                                             hint='کشف‌های ثبت‌شدهٔ این عملگر اینجا نمایش داده می‌شوند'))
            return
        last_key = getattr(app, 'last_discovery_key', None)
        # رندرِ تکه‌تکه: هر فریم چند کارت، تا صفحه فوری باز شود و رابط کاربری قفل نشود
        queue = list(matched)

        def _add_batch(_dt):
            if gen != getattr(self, '_op_gen', 0):
                return  # این بخش دوباره باز شده؛ رندرِ قدیمی را رها کن
            for _ in range(6):
                if not queue:
                    self._op_render_ev = None
                    return
                it = queue.pop(0)
                card = self._group_card(it) if 'all_targets' in it else self._card(it)
                self.list.add_widget(card)
                if last_key is not None and discovery_key(it) == last_key:
                    apply_glow(card, C_GREEN, speed=0.6, width=5.0, hi=1.0, lo=0.25)
            if queue:
                self._op_render_ev = Clock.schedule_once(_add_batch, 0)
            else:
                self._op_render_ev = None

        self._op_render_ev = Clock.schedule_once(_add_batch, 0)

    def _card(self, item):
        border = C_GOLD if self.source == 'featured' else C_BLUE
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=border, orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(4))
        pair = RLabel('سوره %s:%s     سوره %s:%s' % (item.get('seed_s'), item.get('seed_a'),
                      item.get('target_s'), item.get('target_a')),
                      font_size='13sp', color=C_MUTED, halign='center', size_hint_y=None)
        pair.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(pair)
        card.add_widget(_rev_pair_badge(item.get('seed_s'), item.get('target_s'), halign='center', height=dp(14)))
        try:
            card.add_widget(_disc_info_btn(item))
        except Exception:
            pass
        a2 = RLabel('« %s »' % (item.get('target_arb', '')), arabic=True, font_size='16sp',
                    halign='center', color=C_TEXT, size_hint_y=None)
        a2.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(a2)
        _tp = (item.get('target_pers', '') or '').strip()
        if _tp:
            tr = RLabel(_tp, font_size='13sp', halign='center', color=C_MUTED, size_hint_y=None)
            tr.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
            card.add_widget(tr)
        extra = '  (تردیدی)' if item.get('is_doubtful') else ''
        rel = RLabel('رفتار: %s%s' % (item.get('relation_type', 'نامشخص'), extra), font_size='12sp',
                     color=C_ORANGE, halign='right', size_hint_y=None)
        rel.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(rel)
        btn = PillButton('مشاهده و ویرایش', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        btn.bind(on_release=lambda *a, it=item: show_discovery(it, self.source, self))
        card.add_widget(btn)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v + dp(20)))
        _fade_in(card)
        return card

    def _group_card(self, item):
        border = C_GOLD if self.source == 'featured' else C_PURPLE
        card = RoundBox(bg=(0.12, 0.10, 0.20, 1), border=border, orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(4))
        head = RLabel('%s — سوره %s:%s ← %d مقصد' % (item.get('mode', ''), item.get('seed_s'),
                      item.get('seed_a'), len(item.get('all_targets', []))),
                      font_size='13sp', color=C_ORANGE, halign='center', size_hint_y=None)
        head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(head)
        card.add_widget(_rev_badge(item.get('seed_s'), halign='center', height=dp(14)))
        try:
            card.add_widget(_disc_info_btn(item))
        except Exception:
            pass
        a1 = RLabel('« %s »' % item.get('seed_arb', ''), arabic=True, font_size='15sp',
                    halign='center', color=C_TEXT, size_hint_y=None)
        a1.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(a1)
        _sp = (item.get('seed_pers', '') or '').strip()
        if _sp:
            tr = RLabel(_sp, font_size='13sp', halign='center', color=C_MUTED, size_hint_y=None)
            tr.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
            card.add_widget(tr)
        extra = '  (تردیدی)' if item.get('is_doubtful') else ''
        rel = RLabel('رفتار: %s%s' % (item.get('relation_type', 'نامشخص'), extra), font_size='12sp',
                     color=C_ORANGE, halign='right', size_hint_y=None)
        rel.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(rel)
        btn = PillButton('مشاهده و ویرایش', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        btn.bind(on_release=lambda *a, it=item: show_discovery(it, self.source, self))
        card.add_widget(btn)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v + dp(20)))
        _fade_in(card)
        return card

    def go_back(self, *a):
        self.manager.transition = SlideTransition(direction='right')
        self.manager.current = 'lab' if self.source == 'lab' else 'featured'


# ==================================================================
# گلچین برگزیده
# ==================================================================
class FeaturedScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='گلچین برگزیده', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_word = PillButton('اشتراک‌گذاری فایل JSON', bg=C_BLUE, font_size='12sp')
        # متن داخلِ خودِ دکمه بشکند و جا بگیرد (به‌جای بیرون‌زدن)
        b_word.halign = 'center'
        b_word.valign = 'middle'
        b_word.bind(size=lambda i, v: setattr(i, 'text_size', (i.width - dp(10), v[1])))
        b_word.bind(on_release=lambda *a: self.share_json())
        b_save = PillButton('ذخیره در گوشی', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), font_size='13sp')
        b_save.bind(on_release=lambda *a: self.save_json_device())
        b_clear = PillButton('پاک کردن کل', bg=C_RED, font_size='13sp')
        b_clear.bind(on_release=lambda *a: self.clear_all())
        top.add_widget(b_word)
        top.add_widget(b_save)
        top.add_widget(b_clear)
        self.body(top)
        # —— خروجیِ زیبای گلچین: Word / PDF / Excel ——
        exp = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        b_pdf = PillButton('خروجی PDF', bg=C_RED, font_size='13sp')
        b_pdf.bind(on_release=lambda *a: self.export_doc('pdf'))
        b_docx = PillButton('خروجی Word', bg=C_BLUE, font_size='13sp')
        b_docx.bind(on_release=lambda *a: self.export_doc('docx'))
        b_xlsx = PillButton('خروجی Excel', bg=C_GREEN, font_size='13sp')
        b_xlsx.bind(on_release=lambda *a: self.export_doc('xlsx'))
        exp.add_widget(b_pdf)
        exp.add_widget(b_docx)
        exp.add_widget(b_xlsx)
        self.body(exp)
        b_ai = PillButton('گفتگو با هوش مصنوعی', bg=C_PURPLE, fg=HOME_FG, font_size='14sp',
                          size_hint_y=None, height=dp(46))
        b_ai.bind(on_release=lambda *a: self._go_chat())
        self.body(b_ai)
        self.body(RLabel('برای دیدن نمونه‌های هر عملگر، روی آن بزنید.', font_size='13sp',
                         halign='center', color=C_MUTED, size_hint_y=None, height=dp(26)))
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(4))
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        self.body(self.scroll)

    def refresh(self):
        app = App.get_running_app()
        self.grid.clear_widgets()
        self.title_label.set_text('گلچین برگزیده (%d)' % len(app.featured))
        if not app.featured:
            self.grid.add_widget(empty_state('گلچین برگزیده‌ات خالی است',
                                             hint='از لابراتوار، کشف‌های برگزیده را به گلچین اضافه کن'))
            return
        counts = {}
        for it in app.featured:
            k = op_of(it)
            counts[k] = counts.get(k, 0) + 1
        for key, title in OPERATORS:
            n = counts.get(key, 0)
            if n == 0:
                continue
            b = PillButton('%s  (%d نمونه)' % (title, n), bg=(0.16, 0.13, 0.05, 1),
                           size_hint_y=None, height=dp(64), font_size='16sp')
            b.bind(on_release=lambda inst, k=key, t=title: self.open_op(k, t))
            self.grid.add_widget(b)

    def _go_chat(self):
        self.manager.transition = SlideTransition(direction='left')
        self.manager.current = 'chat_disc'

    def open_op(self, key, title):
        scr = self.manager.get_screen('operator')
        scr.load('featured', key, title)
        self.manager.transition = SlideTransition(direction='left')
        self.manager.current = 'operator'

    def clear_all(self):
        app = App.get_running_app()

        def _do():
            app.featured = []
            app.save_featured()
            self.refresh()
        confirm('کل لیست گلچین پاک شود؟', _do, 'پاک کردن کل')

    def share_json(self):
        app = App.get_running_app()
        path = app.export_featured_json()
        if not path:
            toast('گلچین خالی است یا خطایی رخ داد.', 'خطا')
            return
        import share_util
        share_util.save_file_to_device(path, on_done=lambda ok, msg: toast(msg, 'گلچین' if ok else 'خطا'),
                                       mime='application/json', then_share=True)

    def save_json_device(self):
        app = App.get_running_app()
        path = app.export_featured_json()
        if not path:
            toast('گلچین خالی است یا خطایی رخ داد.', 'خطا')
            return
        import share_util
        share_util.save_file_to_device(path, on_done=lambda ok, msg: toast(msg, 'گلچین' if ok else 'خطا'),
                                       mime='application/json', then_share=False)

    def export_doc(self, kind):
        """ساختِ خروجیِ زیبای گلچین (Word/PDF/Excel) و باز کردنِ پنجرهٔ ذخیره/اشتراک."""
        app = App.get_running_app()
        if not app.featured:
            toast('گلچین خالی است.', 'خطا', kind='warn')
            return
        label = {'pdf': 'PDF', 'docx': 'Word', 'xlsx': 'Excel'}.get(kind, kind)
        toast('در حال ساختِ خروجیِ %s…' % label, 'گلچین')

        def _work(*a):
            path = app.export_featured_doc(kind)
            if not path:
                toast('ساختِ خروجی ممکن نشد.', 'خطا', kind='error')
                return
            import share_util
            mime = {
                'pdf': 'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }.get(kind, 'application/octet-stream')
            share_util.save_file_to_device(
                path, on_done=lambda ok, msg: toast(msg, 'گلچین' if ok else 'خطا'),
                mime=mime, then_share=True)

        Clock.schedule_once(_work, 0.05)


# ==================================================================
# جستجو
# ==================================================================
class SearchResultCard(RecycleDataViewBehavior, ClickCard):
    """ردیفِ فشرده و سبکِ نتیجهٔ جستجو. برای دیدنِ جزئیاتِ کامل روی ردیف لمس کنید."""
    def __init__(self, **kw):
        kw.setdefault('orientation', 'vertical')
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(62))
        kw.setdefault('padding', [dp(10), dp(6)])
        kw.setdefault('spacing', dp(2))
        kw.setdefault('bg', (0.10, 0.14, 0.22, 1))
        kw.setdefault('radius', 12)
        super().__init__(**kw)
        self._src = ''
        self._item = None
        self._top = RLabel('', font_size='12sp', halign='right',
                           size_hint_y=None, height=dp(20))
        self._arb = RLabel('', arabic=True, font_size='14sp', halign='right',
                           color=C_TEXT, size_hint_y=None, height=dp(28))
        self.add_widget(self._top)
        self.add_widget(self._arb)
        self.bind(on_release=self._open)

    def refresh_view_attrs(self, rv, index, data):
        # فقط متنِ دو لیبلِ موجود به‌روز می‌شود (بدون ساختِ ویدجتِ جدید)
        self._src = data.get('source', '')
        self._item = data.get('item')
        it = self._item or {}
        tag = 'گلچین' if self._src == 'featured' else 'لابراتوار'
        self._top.color = C_GOLD if self._src == 'featured' else C_MUTED
        self._top.set_text('[%s]  سوره %s:%s ↔ سوره %s:%s  %s  ·  %s' % (
            tag, it.get('seed_s'), it.get('seed_a'),
            it.get('target_s'), it.get('target_a'), it.get('mode', '') or '',
            _rev_pair_text(it.get('seed_s'), it.get('target_s'))))
        arb = (it.get('target_arb', '') or it.get('seed_arb', '') or '')
        arb_s = (arb[:45] + '…') if len(arb) > 45 else arb
        self._arb.set_text('« %s »' % arb_s)
        return super().refresh_view_attrs(rv, index, data)

    def _open(self, *a):
        if self._item is None:
            return
        try:
            screen = App.get_running_app().sm.get_screen('search')
        except Exception:
            screen = None
        show_discovery(self._item, self._src, screen)


class SearchScreen(BaseScreen):
    # حداکثر تعداد نتیجهٔ نمایشی (RecycleView فقط کارت‌های قابل‌مشاهده را می‌سازد)
    MAX_RESULTS = 200

    def __init__(self, **kw):
        super().__init__(title='جستجو در کشفیات', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        # با هر تغییرِ متن، جستجوی زنده (با کمی تأخیر) اجرا می‌شود؛ دکمه هم کار می‌کند
        self.q = PersianTextInput(hint_text=P('جستجو در لابراتوار و گلچین...'),
                                  on_change=lambda *a: self._schedule_search(),
                                  font_size='15sp',
                                  background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1),
                                  padding=[dp(8), dp(14)])
        self.q.bind(on_text_validate=lambda *a: self._run_search())
        b = PillButton('جستجو', bg=C_BLUE, size_hint_x=None, width=dp(96), font_size='14sp')
        b.bind(on_release=lambda *a: self._run_search())
        top.add_widget(self.q)
        top.add_widget(b)
        self.body(top)
        self.info = RLabel('', font_size='13sp', halign='center', color=C_MUTED,
                           size_hint_y=None, height=dp(24))
        self.body(self.info)
        # لیستِ نتایج: همان روشِ مطمئنِ لابراتوار (ScrollView + BoxLayout)؛ کارت‌ها فشرده و سبک‌اند
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(6), scroll_type=['bars', 'content'])
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)
        self._index = []          # ایندکسِ نرمال‌شدهٔ کشفیات: [(source, item, haystack)]
        self._index_sig = None    # امضای دیتاست برای کش: (len(favs), len(featured))
        self._search_ev = None    # نوبتِ زمان‌بندی‌شدهٔ جستجو (برای تأخیر و لغو)

    def refresh(self):
        # فهرست را اینجا (روی ترد اصلی) نمی‌سازیم؛ ساختِ سنگین در اولین جستجو و در ترد پس‌زمینه انجام می‌شود
        self.list.clear_widgets()
        self.info.set_text('واژهٔ عربی/فارسی یا شمارهٔ سوره/آیه را بنویسید؛ نتایج خودکار می‌آید.')

    def _build_index(self):
        app = App.get_running_app()
        idx = []
        for source, coll in (('lab', app.favs), ('featured', app.featured)):
            for it in coll:
                idx.append((source, it, self._make_hay(it)))
        self._index = idx

    def _make_hay(self, it):
        # متنِ جست‌وجوپذیرِ هر کشف: متنِ آیات، ترجمه‌ها، عملگر، برچسب، تحلیل و شماره‌ها
        parts = [it.get('seed_arb', ''), it.get('target_arb', ''),
                 it.get('seed_pers', ''), it.get('target_pers', ''),
                 it.get('mode', ''), it.get('relation_type', ''), it.get('note', '')]
        nums = 'سوره %s آیه %s سوره %s آیه %s %s:%s %s:%s' % (
            it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a'),
            it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a'))
        combined = ' '.join(str(x) for x in parts) + ' ' + nums
        # همان نرمال‌سازیِ جستجوی آیه: حذف اعراب + یکسان‌سازیِ حروف (ا/ی/ک/ه) + یکسان‌سازیِ ارقام
        return core.normalize_text(core.conv(combined))

    def _schedule_search(self, *a):
        # هم‌سبکِ جستجوی آیه: کارِ جستجو را بی‌درنگ اجرا نمی‌کنیم؛ با کمی تأخیر و لغوِ نوبتِ قبلی،
        # تا با تایپِ هر حرف، اپ سنگین/هنگ نشود.
        if self._search_ev is not None:
            self._search_ev.cancel()
        self._search_ev = Clock.schedule_once(self._run_search, 0.35)

    def _run_search(self, *a):
        # لغو زمان‌بندی‌های قبلی هنگام تایپِ سریع
        if self._search_ev is not None:
            self._search_ev.cancel()
            self._search_ev = None

        raw = (self.q.query or '').strip()
        term = core.normalize_text(core.conv(raw))

        if len(term) < 2:
            self.list.clear_widgets()
            self.info.set_text('حداقل ۲ حرف یا یک عدد وارد کنید.')
            return

        app = App.get_running_app()
        sig = (len(app.favs), len(app.featured))
        need_build = (getattr(self, '_index_sig', None) != sig) or (not self._index)
        self.info.set_text('در حال آماده‌سازی و جستجو...' if need_build else 'در حال جستجو...')

        # هر جستجو یک شمارهٔ نوبت می‌گیرد؛ نتیجهٔ نوبت‌های قدیمی (تایپِ سریع) نادیده گرفته می‌شود
        self._search_gen = getattr(self, '_search_gen', 0) + 1
        gen = self._search_gen

        # همهٔ کارِ سنگین (ساختِ فهرست + فیلتر) در ترد پس‌زمینه؛ نمایش با RecycleView آنی است
        def _do_search():
            try:
                if need_build:
                    idx = []
                    for source, coll in (('lab', app.favs), ('featured', app.featured)):
                        for it in coll:
                            idx.append((source, it, self._make_hay(it)))
                    self._index = idx
                    self._index_sig = sig
                matches = [(src, it) for src, it, hay in self._index if term in hay]
            except Exception:
                matches = []
            Clock.schedule_once(lambda dt: _on_search_done(matches), 0)

        def _on_search_done(matches):
            if gen != getattr(self, '_search_gen', 0):
                return  # نتیجهٔ یک جستجوی قدیمی‌ست؛ رهایش کن
            self.list.clear_widgets()
            if not matches:
                self.info.set_text('کشفی همخوان با «%s» یافت نشد.' % raw)
                return
            shown = matches[:self.MAX_RESULTS]
            if len(matches) > self.MAX_RESULTS:
                self.info.set_text('%d نتیجه — نمایشِ %d موردِ اول (برای کمتر شدن، عبارتِ دقیق‌تری بنویسید).'
                                   % (len(matches), self.MAX_RESULTS))
            else:
                self.info.set_text('%d نتیجه در لابراتوار و گلچین' % len(matches))

            # رندرِ تکه‌تکه: هر فریم چند کارت تا رابط کاربری روان بماند (بدون هنگ حتی با نتایج زیاد)
            queue = list(shown)

            def _add_batch(_dt):
                if gen != getattr(self, '_search_gen', 0):
                    return
                for _ in range(6):
                    if not queue:
                        return
                    src, it = queue.pop(0)
                    self.list.add_widget(self._result_row(src, it))
                if queue:
                    self._render_ev = Clock.schedule_once(_add_batch, 0)

            if getattr(self, '_render_ev', None) is not None:
                self._render_ev.cancel()
            self._render_ev = Clock.schedule_once(_add_batch, 0)

        threading.Thread(target=_do_search, daemon=True).start()

    def _result_row(self, src, it):
        # کارتِ فشرده و سبکِ نتیجه؛ با کلیک، همان پنجرهٔ ویرایشِ لابراتوار باز می‌شود
        card = ClickCard(bg=(0.10, 0.14, 0.22, 1),
                         border=(C_GOLD if src == 'featured' else C_BLUE),
                         orientation='vertical', size_hint_y=None, height=dp(66),
                         padding=[dp(10), dp(6)], spacing=dp(2), radius=12)
        tag = 'گلچین' if src == 'featured' else 'لابراتوار'
        top = RLabel('[%s]  سوره %s:%s ↔ سوره %s:%s  %s  ·  %s' % (
            tag, it.get('seed_s'), it.get('seed_a'),
            it.get('target_s'), it.get('target_a'), it.get('mode', '') or '',
            _rev_pair_text(it.get('seed_s'), it.get('target_s'))),
            font_size='12sp', halign='right',
            color=(C_GOLD if src == 'featured' else C_MUTED),
            size_hint_y=None, height=dp(20))
        card.add_widget(top)
        arb = (it.get('target_arb', '') or it.get('seed_arb', '') or '')
        arb_s = (arb[:45] + '…') if len(arb) > 45 else arb
        a = RLabel('« %s »' % arb_s, arabic=True, font_size='14sp', halign='right',
                   color=C_TEXT, size_hint_y=None, height=dp(30))
        card.add_widget(a)
        card.bind(on_release=lambda *_a, s=src, i=it: show_discovery(i, s, self))
        return card


# ==================================================================
# مدیریت برچسب‌ها
# ==================================================================
class TagsScreen(BaseScreen):
    DEFAULT = ["پژواک واژگانی", "تقارن ساختاری/نحوی", "هم‌آوایی صوتی", "تقابل کامل", "مکمل و بسط‌دهنده", "علت و معلول", "پرسش و پاسخ", "دیالوگ متقاطع", "گفت و گو", "وعده و تحقق وعده", "تمثیل موازی", "دادگاه و اعتراف", "تسبیح کائنات", "تکمیل پازل داستانی", "زاویه دید متفاوت"]

    def __init__(self, **kw):
        super().__init__(title='مدیریت برچسب‌ها', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.q = PersianTextInput(hint_text=P('برچسب جدید...'), multiline=False, font_name='ui',
                           font_size='15sp', background_color=(1, 1, 1, 0.95),
                           foreground_color=(0.05, 0.08, 0.14, 1), padding=[dp(8), dp(14)])
        b = PillButton('افزودن', bg=C_GREEN, size_hint_x=None, width=dp(110), font_size='14sp')
        b.bind(on_release=lambda *a: self.add_tag())
        top.add_widget(self.q)
        top.add_widget(b)
        self.body(top)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)

    def refresh(self):
        app = App.get_running_app()
        self.list.clear_widgets()
        for tag in app.get_all_tags():
            row = RoundBox(bg=(0.10, 0.14, 0.22, 1), orientation='horizontal', size_hint_y=None,
                           height=dp(50), padding=dp(10), spacing=dp(8))
            row.add_widget(RLabel(tag, font_size='15sp', halign='right'))
            if tag != 'نامشخص':
                b_edit = PillButton('ویرایش', bg=C_BLUE, size_hint_x=None, width=dp(92), font_size='13sp')
                b_edit.bind(on_release=lambda x, t=tag: self.edit_tag(t))
                row.add_widget(b_edit)
                b_del = PillButton('حذف', bg=C_RED, size_hint_x=None, width=dp(80), font_size='13sp')
                b_del.bind(on_release=lambda x, t=tag: self.del_tag(t))
                row.add_widget(b_del)
            self.list.add_widget(row)

    def add_tag(self):
        app = App.get_running_app()
        t = self.q.query.strip()
        if not t:
            return
        if t in app.get_all_tags():
            toast('این برچسب قبلاً وجود دارد.', 'تکرار')
            return
        if t in getattr(app, 'hidden_tags', []):
            app.hidden_tags.remove(t)
        if t not in TagsScreen.DEFAULT and t not in app.user_tags:
            app.user_tags.append(t)
        app.save_user_tags()
        self.q.clear_logical()
        self.refresh()

    def edit_tag(self, tag):
        app = App.get_running_app()
        def _ok(newname):
            ok, msg = app.rename_tag(tag, newname)
            if not ok:
                if msg:
                    toast(msg, 'ویرایش برچسب')
                return
            toast('برچسب ویرایش شد ✓', 'برچسب')
            self.refresh()
        prompt_text('نامِ جدید برای «' + tag + '»:', tag, _ok, title='ویرایش برچسب')

    def del_tag(self, tag):
        app = App.get_running_app()
        def _do():
            app.delete_tag(tag)
            self.refresh()
        confirm('برچسب «' + tag + '» حذف شود؟ (از همهٔ کشف‌های مرتبط هم برداشته می‌شود)', _do, 'حذف برچسب')


# ==================================================================
# رسانه و معرفی
# ==================================================================
class MediaScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='رسانه و معرفی', **kw)
        self.sound = None
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12), padding=dp(6))
        box.bind(minimum_height=box.setter('height'))

        box.add_widget(RLabel('چند کلام از طراح', bold=True, font_size='18sp', color=C_GOLD,
                              halign='center', size_hint_y=None, height=dp(34)))
        b_designer = PillButton('چند کلام از طراح در مورد اپلیکیشن', bg=C_ORANGE, size_hint_y=None, height=dp(52), font_size='14sp')
        b_designer.bind(on_release=lambda *a: self.play('designer.mp3'))
        box.add_widget(b_designer)
        b_stop = PillButton('توقف', bg=C_RED, size_hint_y=None, height=dp(52))
        b_stop.bind(on_release=lambda *a: self.stop())
        box.add_widget(b_stop)
        box.add_widget(Widget(size_hint_y=None, height=dp(20)))

        scroll.add_widget(box)
        self.body(scroll)

    def refresh(self):
        pass

    def play(self, name):
        try:
            from kivy.core.audio import SoundLoader
        except Exception as e:
            print('audio provider error:', e)
            toast('پخش صدا در این دستگاه در دسترس نیست.', 'خطا')
            return
        self.stop()
        path = asset(name)
        if not os.path.exists(path):
            toast('فایل صوتی یافت نشد.', 'خطا')
            return
        try:
            self.sound = SoundLoader.load(path)
        except Exception as e:
            print('audio load error:', e)
            self.sound = None
            toast('پخش این فایل صوتی ممکن نشد.', 'خطا')
            return
        if not self.sound:
            toast('پخش این فایل صوتی ممکن نشد.', 'خطا')
            return
        try:
            self.sound.play()
        except Exception as e:
            print('audio play error:', e)
            toast('پخش این فایل صوتی ممکن نشد.', 'خطا')

    def stop(self):
        if self.sound:
            self.sound.stop()
            self.sound = None

    def go_back(self, *a):
        self.stop()
        super().go_back()


# ==================================================================
# پشتیبان و بازیابی
# ==================================================================
class BackupScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='پشتیبان و بازیابی', **kw)
        box = BoxLayout(orientation='vertical', spacing=dp(14), padding=dp(16))
        box.add_widget(RLabel('از کشفیات، گلچین و برچسب‌های خود نسخهٔ پشتیبان بگیرید یا آن را بازیابی کنید.',
                              font_size='15sp', halign='center', color=C_MUTED, size_hint_y=None, height=dp(70)))
        b_backup = PillButton('پشتیبان‌گیری و اشتراک‌گذاری فایل JSON', bg=C_GREEN, size_hint_y=None, height=dp(56))
        b_backup.bind(on_release=lambda *a: self.backup(share=True))
        box.add_widget(b_backup)
        b_save = PillButton('ذخیرهٔ فایل پشتیبان در حافظهٔ گوشی', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), size_hint_y=None, height=dp(56))
        b_save.bind(on_release=lambda *a: self.backup(share=False))
        box.add_widget(b_save)
        b_import = PillButton('بارگذاری/بازیابی از فایل JSON', bg=C_BLUE, size_hint_y=None, height=dp(56))
        b_import.bind(on_release=lambda *a: self.open_import())
        box.add_widget(b_import)
        self.info = RLabel('', font_size='13sp', halign='center', color=C_GOLD, size_hint_y=None, height=dp(60))
        box.add_widget(self.info)
        box.add_widget(Widget())
        self.body(box)

    def refresh(self):
        self.info.set_text('')

    def backup(self, share=True):
        app = App.get_running_app()
        try:
            path = app.build_backup_zip()
        except Exception as e:
            self.info.set_text('خطا در ساخت پشتیبان:\n' + str(e))
            return
        if not path:
            self.info.set_text('هیچ داده‌ای برای پشتیبان‌گیری وجود ندارد.')
            toast('هنوز کشفی ثبت نشده است.', 'پشتیبان')
            return
        import share_util

        def _cb(ok, msg):
            self.info.set_text(msg)
            toast(msg, 'پشتیبان' if ok else 'خطا')
        share_util.save_file_to_device(path, on_done=_cb, mime='application/zip', then_share=share)

    def open_import(self):
        app = App.get_running_app()
        content = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        content.add_widget(RLabel('فایل پشتیبان ویندوز (ZIP) یا فایل JSON (favorites.json / featured.json) را انتخاب کنید، یا متن JSON را بچسبانید:',
                                  font_size='13sp', color=C_GOLD, halign='center', size_hint_y=None, height=dp(64)))
        bpick = PillButton('انتخاب فایل ZIP یا JSON از دستگاه', bg=C_BLUE, size_hint_y=None, height=dp(50), font_size='13sp')
        content.add_widget(bpick)
        picked = {'text': None, 'path': None}
        status = RLabel('', font_size='13sp', halign='center', color=C_GOLD,
                        size_hint_y=None, height=dp(30))
        content.add_widget(status)
        ti = PlainInput(multiline=True, font_size='12sp', size_hint_y=1,
                       hint_text=P('(اختیاری) در صورت تمایل، متن JSON را اینجا بچسبانید'),
                       background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
        content.add_widget(ti)

        def _on_file(path, msg):
            if not path:
                if msg:
                    toast(msg, 'انتخاب فایل')
                return
            picked['path'] = path
            picked['text'] = None
            name = ''
            try:
                import os as _os
                name = _os.path.basename(path)
            except Exception:
                pass
            status.set_text('فایل انتخاب شد%s. روی «بارگذاری» بزنید.' % ((' (%s)' % name) if name else ''))
            toast('فایل انتخاب شد؛ حالا روی «بارگذاری» بزنید.', 'بارگذاری')

        def _pick(*a):
            import share_util
            # هم فایل ZIP خروجی ویندوز و هم فایل JSON پذیرفته می‌شود
            share_util.pick_file(_on_file, mime='*/*')
        bpick.bind(on_release=_pick)

        opts = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        sp = Spinner(text=P('کشفیات لابراتوار'), values=[P('کشفیات لابراتوار'), P('گلچین')],
                     font_name='ui', size_hint_y=None, height=dp(44))
        state = {'mode': 'merge'}
        btog = PillButton('حالت: ادغام (افزودن جدیدها)', bg=C_GREEN, font_size='12sp')

        def _tog(*a):
            state['mode'] = 'replace' if state['mode'] == 'merge' else 'merge'
            btog.set_text('حالت: جایگزینی کامل' if state['mode'] == 'replace' else 'حالت: ادغام (افزودن جدیدها)')
            btog._bg = list(C_ORANGE if state['mode'] == 'replace' else C_GREEN)
            btog._state()
        btog.bind(on_release=_tog)
        opts.add_widget(sp)
        opts.add_widget(btog)
        content.add_widget(opts)

        pop = Popup(title=P('بارگذاری از فایل JSON'), content=content, size_hint=(0.96, 0.92),
                    title_font='ui', title_align='center', separator_color=C_GOLD)
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        bload = PillButton('بارگذاری', bg=C_GREEN)

        def _load(*a):
            target = 'lab' if sp.text == P('کشفیات لابراتوار') else 'featured'
            try:
                if picked['path']:
                    added, total, err = app.import_from_path(picked['path'], target, state['mode'])
                else:
                    txt = (ti.text or '')
                    if not txt.strip():
                        toast('ابتدا فایلی انتخاب کنید یا متن JSON را بچسبانید.', 'خطا')
                        return
                    added, total, err = app.import_items_json(txt, target, state['mode'])
            except Exception as e:
                added, total, err = 0, 0, 'خطای غیرمنتظره: %s' % str(e)[:100]
            if err:
                self.info.set_text('خطا: ' + err)
                toast('خطا: ' + err, 'خطا')
                return
            where = 'لابراتوار' if target == 'lab' else 'گلچین'
            msg = '%d مورد جدید به %s افزوده شد (مجموع: %d).' % (added, where, total)
            self.info.set_text(msg)
            toast(msg, 'بارگذاری')
            try:
                sm = self.manager
                sm.get_screen('lab' if target == 'lab' else 'featured').refresh()
            except Exception:
                pass
            pop.dismiss()
        bload.bind(on_release=_load)
        bcancel = PillButton('انصراف', bg=C_RED)
        bcancel.bind(on_release=pop.dismiss)
        row.add_widget(bload)
        row.add_widget(bcancel)
        content.add_widget(row)
        pop.open()


# ==================================================================
# درباره
# ==================================================================
class AboutScreen(BaseScreen):
    WEBSITE = 'https://6a304b9599e34.mywebzi.ir/'
    BALE_URL = 'https://ble.ir/dr_parsa114'

    def __init__(self, **kw):
        super().__init__(title='درباره', **kw)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        box = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(16), size_hint_y=None)
        box.bind(minimum_height=box.setter('height'))
        box.add_widget(self._lbl('قطب‌نمای قرآنی', bold=True, font_size='24sp', color=C_GOLD, halign='center'))
        box.add_widget(self._lbl('پردازش آینه‌ای (هولوگرافیک) — نسخهٔ موبایل', font_size='15sp', color=C_TEXT, halign='center'))
        box.add_widget(self._lbl('کاوش الگوهای عددی و معنایی میان آیات قرآن کریم. تمام ۶۲۳۶ آیه به صورت آفلاین در اپ گنجانده شده است.', font_size='13sp', color=C_MUTED, halign='center'))
        box.add_widget(Widget(size_hint_y=None, height=dp(8)))
        box.add_widget(self._lbl('راه ارتباطی با مؤلف:', bold=True, font_size='17sp', color=C_GOLD, halign='right'))
        b_site = PillButton('سایت مرجع قرآن ابر ماتریس', bg=C_BLUE, size_hint_y=None, height=dp(56), font_size='15sp')
        b_site.bind(on_release=lambda *a: self.open_url(self.WEBSITE))
        box.add_widget(b_site)
        box.add_widget(self._lbl(self.WEBSITE, font_size='12sp', color=C_MUTED, halign='center'))
        b_bale = PillButton('ارتباط در پیام‌رسان بله:  dr_parsa114', bg=C_GREEN, size_hint_y=None, height=dp(56), font_size='15sp')
        b_bale.bind(on_release=lambda *a: self.open_url(self.BALE_URL))
        box.add_widget(b_bale)
        box.add_widget(Widget(size_hint_y=None, height=dp(8)))
        box.add_widget(self._card_text('لطفاً کشفیات ویژهٔ خود را با مؤلف در میان بگذارید و به اشتراک بگذارید تا در نسخه‌های بعدی گنجانده شود.'))
        box.add_widget(self._card_text('این اپلیکیشن و سامانهٔ پردازش آن در حال توسعه و تکامل است؛ ان‌شاءالله به لطف خالق هستی و با کمک یکدیگر، با بزرگ‌تر کردن فهرست آیات آینه‌ای به این هدف مهم دست خواهیم یافت.'))
        box.add_widget(Widget(size_hint_y=None, height=dp(16)))
        scroll.add_widget(box)
        self.body(scroll)

    def _lbl(self, text, **kw):
        kw.setdefault('size_hint_y', None)
        l = RLabel(text, **kw)
        l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(12)))
        return l

    def _card_text(self, text):
        c = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=C_GOLD, orientation='vertical', size_hint_y=None, padding=dp(12))
        l = RLabel(text, font_size='14sp', color=C_TEXT, halign='right', size_hint_y=None)
        l.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        c.add_widget(l)
        c.bind(minimum_height=lambda i, v: setattr(c, 'height', v + dp(24)))
        return c

    def open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            toast('نشانی: ' + url, 'لینک')

    def refresh(self):
        pass


# ==================================================================
# راهنما
# ==================================================================
class GuideScreen(BaseScreen):
    # هر بخش: (عنوان، رنگ، توضیحِ کامل و خودآموز)
    SECTIONS = [
        ('۱) انتخاب بذر (سوره و آیه)', C_GOLD,
         'نقطهٔ شروعِ همه‌چیز اینجاست. در صفحهٔ اصلی شمارهٔ سوره و شمارهٔ آیه را وارد کنید؛ به این جفت «بذر» می‌گوییم و مبنای تمامِ پردازش‌هاست.\nاگر عددی خارج از محدوده وارد کنید، برنامه خودش آن را به نزدیک‌ترین آیهٔ معتبر اصلاح می‌کند تا خطا نگیرید.\nبرای تایپ کافی است روی کادرِ عدد یک‌بار لمس کنید تا کیبورد بالا بیاید.'),
        ('۲) جستجوی متنِ آیه (در صفحهٔ اصلی)', C_BLUE,
         'اگر شمارهٔ آیه را نمی‌دانید، از کادرِ «جستجوی متن آیه یا ترجمه» در همان صفحهٔ اصلی استفاده کنید.\nبخشی از متنِ عربی یا ترجمهٔ فارسی را بنویسید (نیازی به اعرابِ دقیق نیست) و «انتخاب خودکار» را بزنید تا نزدیک‌ترین آیه پیدا و به‌عنوان بذر انتخاب شود.\nبا دکمهٔ «نمایش لیست جستجو» همهٔ آیه‌های همخوان را در یک فهرست می‌بینید و یکی را برمی‌گزینید؛ اگر عدد بزنید، بر اساسِ شمارهٔ آیه می‌گردد.\nتوجه: این جستجو در متنِ قرآن است، نه در کشفیاتِ شما.'),
        ('۳) پردازش ماتریس', C_PURPLE,
         'قلبِ برنامه. هفت عملگرِ آینه‌ای (جابجایی و تقارنِ شماره‌های سوره و آیه) را روی بذر اجرا می‌کند و هفت آیهٔ «مقصد» به‌دست می‌آید.\nمتنِ کاملِ عربی و ترجمهٔ هر مقصد نمایش داده می‌شود.\nهر مقصدی که برایتان معنادار بود، با دکمهٔ «ثبت این کشف» در لابراتوار ذخیره کنید تا بعداً بررسی‌اش کنید.'),
        ('۴) پیش‌بینی (معنا)', C_GREEN,
         'کمک می‌کند از میانِ مقصدها، محتمل‌ترین‌ها را زودتر ببینید.\nمقصدهای آینه‌ای را بر اساسِ اشتراکِ واژه‌ها و نزدیکیِ معناییِ آن‌ها با بذر رتبه‌بندی می‌کند؛ هر چه بالاتر، ارتباطِ معناییِ قوی‌تر.'),
        ('۵) پیش‌بینی (اعداد)', C_ORANGE,
         'همان رتبه‌بندی، اما با معیارهای عددی.\nبا فیلترهایی مثلِ نیم‌کرهٔ سوره، اثرِانگشتِ رقمی و میزانِ تلورانس، نامزدهای عددی را غربال و اولویت‌بندی می‌کند تا الگوهای عددی راحت‌تر دیده شوند.'),
        ('۶) لابراتوار کشفیات', C_BLUE,
         'انبارِ همهٔ کشف‌های ثبت‌شدهٔ شما.\nکشف‌ها خودکار در این دسته‌ها مرتب می‌شوند: هفت عملگرِ آینه‌ای، به‌همراهِ «کشفیات گروهی» (ثبتِ گروهی) و «کشفیات تردیدی».\nروی هر دسته بزنید تا کشف‌های آن باز شود؛ فهرست به‌صورتِ تدریجی و روان بارگذاری می‌شود، پس حتی با هزاران کشف هم صفحه فوری باز می‌شود و معطل نمی‌مانید.\nروی هر کشف بزنید تا پنجرهٔ کامل باز شود: متنِ عربی و ترجمهٔ مبدأ و مقصد، همراه با گلچین‌کردن، ویرایشِ تحلیل و برچسب، حذف و کپی.'),
        ('۷) گلچین برگزیده', C_GOLD,
         'ویترینِ بهترین کشف‌های شما.\nکشف‌های مهم را از لابراتوار به گلچین می‌آورید. اینجا هم مثلِ لابراتوار بر اساسِ همان عملگرها و دسته‌ها (گروهی و تردیدی) مرتب شده و به‌صورتِ روان بارگذاری می‌شود.\nمی‌توانید از کلِ گلچین یک خروجیِ تمیزِ JSON بگیرید.'),
        ('۸) جستجوی کشفیات', C_PURPLE,
         'این جستجو با «جستجوی متن آیه» فرق دارد: اینجا فقط داخلِ کشف‌های خودتان (لابراتوار و گلچین) می‌گردد، نه کلِ قرآن.\nهر چیزی را می‌توانید بگردید: متنِ عربی، ترجمه، برچسب، تحلیلِ خودتان و شماره‌ها.\nنتیجه‌ها زنده و همزمان با تایپ نشان داده می‌شوند و حتی با هزاران کشف هم سریع می‌مانند.\nروی هر نتیجه بزنید تا همان پنجرهٔ کاملِ ویرایش باز شود.'),
        ('۹) مدیریت برچسب‌ها', C_GREEN,
         'برچسب‌های «رفتارِ آیه» را اینجا می‌سازید یا حذف می‌کنید؛ مثلاً «تقابلِ کامل»، «گفت‌وگو»، «علت و معلول».\nبعداً هنگامِ ثبتِ تحلیلِ یک کشف، این برچسب‌ها را به آن نسبت می‌دهید تا کشف‌هایتان منظم و قابلِ جستجو شوند.'),
        ('۱۰) رسانه و معرفی', C_ORANGE,
         'در این بخش «چند کلام از طراح» را می‌شنوید.\nیک معرفیِ صوتیِ کوتاه هنگامِ باز شدنِ برنامه یک‌بار پخش می‌شود و از اینجا هم می‌توانید دوباره آن را بشنوید.'),
        ('۱۱) پشتیبان و بازیابی', C_BLUE,
         'برای اینکه دادهٔ شما هیچ‌وقت گم نشود.\nاز کشفیات، گلچین و برچسب‌ها یک فایلِ پشتیبان بگیرید و هر وقت خواستید بازیابی کنید.\nهنگامِ بازیابی، مقصد را انتخاب می‌کنید (لابراتوار یا گلچین) و حالتِ «جایگزینی» یا «ادغام» را برمی‌گزینید؛ کشف‌های تکراری خودکار حذف می‌شوند.'),
        ('۱۲) درباره', C_PURPLE,
         'معرفیِ برنامه و راه‌های ارتباط با مؤلف (سایتِ مرجع و شناسهٔ پیام‌رسانِ بله).'),
    ]

    def __init__(self, **kw):
        super().__init__(title='راهنما', **kw)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(8))
        box.bind(minimum_height=box.setter('height'))
        box.add_widget(RLabel('روی هر بخش بزنید تا توضیحِ کاملِ آن باز شود.', font_size='14sp',
                              color=C_MUTED, halign='center', size_hint_y=None, height=dp(34)))

        def _tint(col, f=0.32):
            return [c * f for c in col[:3]] + [1]

        for title, color, body in self.SECTIONS:
            b = PillButton(title, bg=_tint(color), size_hint_y=None, height=dp(58), font_size='15sp')
            _neon_border(b, color, width=1.4, alpha=0.85)
            b.bind(on_release=lambda inst, t=title, d=body, c=color: self.show_help(t, d, c))
            box.add_widget(b)
        gt = asset('guide_table.png')
        if os.path.exists(gt):
            img = Image(source=gt, size_hint_y=None, height=dp(200), allow_stretch=True, keep_ratio=True)
            box.add_widget(img)
        scroll.add_widget(box)
        self.body(scroll)

    def show_help(self, title, body, color=None):
        if color is None:
            color = C_GOLD
        content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
        sc = ScrollView(do_scroll_x=False, bar_width=dp(4))
        inner = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        inner.bind(minimum_height=inner.setter('height'))
        head = RLabel(title, bold=True, font_size='18sp', color=color,
                      halign='center', size_hint_y=None)
        head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(10)))
        inner.add_widget(head)
        lbl = RLabel(body, font_size='15sp', color=C_TEXT,
                     halign='center', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(12)))
        inner.add_widget(lbl)
        sc.add_widget(inner)
        content.add_widget(sc)
        p = Popup(title=P(title), content=content, size_hint=(0.92, 0.72),
                  title_font='ui', title_align='center', separator_color=color)
        btn = PillButton('بستن', bg=color, size_hint_y=None, height=dp(46))
        btn.bind(on_release=p.dismiss)
        content.add_widget(btn)
        p.open()

    def refresh(self):
        pass


def _open_url(url):
    """باز کردنِ یک لینک در مرورگرِ سیستم (اندروید و دسکتاپ)."""
    try:
        if _kivy_platform == 'android':
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(url))
            PythonActivity.mActivity.startActivity(intent)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        toast('نشد سایت باز شود؛ این آدرس را دستی باز کن:\n' + url, 'راهنما')


def open_chat_chooser():
    """پنجرهٔ انتخابِ نوعِ گفت‌وگو: گفت‌وگو در موردِ کشفیات یا در موردِ قرآن کریم."""
    app = App.get_running_app()
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10))
    p = Popup(title=P('گفت‌وگو با هوش مصنوعی'), content=content, size_hint=(0.92, None),
              height=dp(360), title_font='ui', title_align='center', separator_color=C_GOLD)

    def _go(mode):
        p.dismiss()
        try:
            sm = app.root
            target = 'chat_quran' if mode == 'quran' else 'chat_disc'
            sm.transition = SlideTransition(direction='left')
            sm.current = target
        except Exception:
            toast('باز کردنِ گفت‌وگو ممکن نشد.', 'هوش مصنوعی', kind='error')

    b1 = PillButton('گفت‌وگو در موردِ کشفیات', bg=C_INDIGO, fg=HOME_FG,
                    size_hint_y=None, height=dp(72), font_size='16sp')
    b1.bind(on_release=lambda *a: _go('discoveries'))
    content.add_widget(b1)
    content.add_widget(RLabel('دسترسی به کشفیاتِ لابراتوار و گلچینِ تو', font_size='12sp',
                              halign='center', color=C_MUTED, size_hint_y=None, height=dp(22)))

    b2 = PillButton('گفت‌وگو در موردِ قرآن کریم', bg=C_GREEN, fg=(0.05, 0.08, 0.14, 1),
                    size_hint_y=None, height=dp(72), font_size='16sp')
    b2.bind(on_release=lambda *a: _go('quran'))
    content.add_widget(b2)
    content.add_widget(RLabel('دسترسی به کلِ آیاتِ دیتاکاوش و مرجعِ qref', font_size='12sp',
                              halign='center', color=C_MUTED, size_hint_y=None, height=dp(22)))

    close = PillButton('بستن', bg=C_RED, size_hint_y=None, height=dp(44))
    close.bind(on_release=lambda *a: p.dismiss())
    content.add_widget(close)
    p.open()


def open_ai_settings():
    """پنجرهٔ تنظیماتِ هوش مصنوعی: کلید API و آدرس سرور + تست اتصال."""
    app = App.get_running_app()
    cfg = getattr(app, 'ai_settings', None) or ai_manager.default_settings()
    content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(8))

    sv = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(4))
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6), padding=dp(2))
    box.bind(minimum_height=box.setter('height'))

    box.add_widget(RLabel('کلید API', bold=True, font_size='15sp', color=C_GOLD,
                          halign='right', size_hint_y=None, height=dp(26)))
    key_in = PlainInput(text=cfg.get('api_key', ''), multiline=False, font_name='ui',
                        font_size='14sp', size_hint_y=None, height=dp(46), hint_text='aa-...',
                        background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
    box.add_widget(key_in)

    box.add_widget(RLabel('آدرس سرور (Base URL)', bold=True, font_size='15sp', color=C_GOLD,
                          halign='right', size_hint_y=None, height=dp(26)))
    url_in = PlainInput(text=cfg.get('base_url', ai_manager.DEFAULT_BASE_URL), multiline=False,
                        font_name='ui', font_size='13sp', size_hint_y=None, height=dp(46),
                        background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
    box.add_widget(url_in)

    box.add_widget(RLabel('نام مدل (پیشرفته)', bold=True, font_size='15sp', color=C_GOLD,
                          halign='right', size_hint_y=None, height=dp(26)))
    model_in = PlainInput(text=cfg.get('model', ai_manager.DEFAULT_MODEL), multiline=False,
                          font_name='ui', font_size='13sp', size_hint_y=None, height=dp(46),
                          background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
    box.add_widget(model_in)
    guide = RLabel('''«دستیارِ هوشمند» چگونه فعال می‌شود؟

۱) این بخش برای تحلیلِ هوشمند به یک «کلیدِ API» نیاز دارد؛ کلید را در کادرِ بالا وارد و ذخیره کن.

۲) برای «شروع»، مؤلف یک «کدِ هدیه» به تو می‌دهد تا رایگان امتحان کنی.

۳) برای «ادامهٔ» استفاده، خودت از سایتِ اَوال اعتبار تهیه کن. آدرسِ سایت:
https://avalai.ir

۴) پیش‌فرض روی سرویسِ «اَوال» تنظیم است. برای اتصال به سرویسِ دیگر (مثلِ NVIDIA) فقط «آدرس سرور» و «نام مدل» را عوض کن. نمونهٔ نامِ مدل:
nvidia/llama-3.1-nemotron-70b-instruct

۵) برای دریافتِ کدِ هدیه یا هر پرسشی، از پیام‌رسانِ «بله» با مؤلف در تماس باش.''',
                   font_size='13sp', color=C_MUTED, halign='center', size_hint_y=None)
    guide.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(12)))
    box.add_widget(guide)
    b_link = PillButton('باز کردن سایتِ اَوال', bg=(1, 1, 1, 0.12), fg=C_TEXT,
                        size_hint_y=None, height=dp(44), font_size='13sp')
    b_link.bind(on_release=lambda *a: _open_url(ai_manager.MODELS_URL))
    box.add_widget(b_link)
    _note = RLabel('''توجه: برخی سرورها (مثلِ NVIDIA) ممکن است از داخلِ ایران بدونِ فیلترشکن پاسخ ندهند؛ در این صورت از همان سرویسِ پیش‌فرضِ اَوال استفاده کن.''', font_size='12sp', color=C_MUTED,
                   halign='center', size_hint_y=None)
    _note.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(10)))
    box.add_widget(_note)

    sv.add_widget(box)
    content.add_widget(sv)
    status = RLabel('', font_size='13sp', halign='center', color=C_MUTED,
                    size_hint_y=None, height=dp(26))
    content.add_widget(status)

    p = Popup(title=P('تنظیمات هوش مصنوعی'), content=content, size_hint=(0.94, 0.9),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _collect():
        return (key_in.text.strip(), url_in.text.strip(),
                model_in.text.strip() or ai_manager.DEFAULT_MODEL)

    def _save():
        k, u, m = _collect()
        app.save_ai_settings(api_key=k, base_url=u, model=m)

    def _test(*a):
        k, u, m = _collect()
        if not k:
            status.set_text('× ابتدا کلید API را وارد کن')
            toast('کلید API را وارد کن.', 'هوش مصنوعی', kind='warn')
            return
        app.save_ai_settings(api_key=k, base_url=u, model=m)
        status.set_text('در حال آزمایش اتصال...')
        b_test.disabled = True

        def _ok(msg):
            b_test.disabled = False
            status.set_text('✓ ' + msg)
            toast(msg, 'هوش مصنوعی', kind='success')

        def _fail(msg):
            b_test.disabled = False
            status.set_text('× ' + msg)
            toast(msg, 'هوش مصنوعی', kind='error')

        ai_manager.test_connection(on_ok=_ok, on_fail=_fail)

    btnrow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    b_test = PillButton('تست اتصال', bg=C_BLUE, font_size='14sp')
    b_test.bind(on_release=_test)
    b_save = PillButton('ذخیره و اتصال', bg=C_GREEN, font_size='14sp')
    b_save.bind(on_release=lambda *a: (_save(), toast('تنظیمات ذخیره شد ✓', 'هوش مصنوعی'), p.dismiss()))
    btnrow.add_widget(b_test)
    btnrow.add_widget(b_save)
    content.add_widget(btnrow)
    close = PillButton('بستن', bg=C_RED, size_hint_y=None, height=dp(44))
    close.bind(on_release=lambda *a: p.dismiss())
    content.add_widget(close)
    p.open()


def show_ai_result_popup(title, messages, subtitle=None, temperature=0.5, max_tokens=None):
    """پاپ‌آپِ گفتگویی: نخست تحلیل را زنده نشان می‌دهد و سپس می‌توان دربارهٔ همان تحلیل گفتگو کرد."""
    convo = list(messages)
    state = {'busy': True}

    root = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
    if subtitle:
        root.add_widget(RLabel(subtitle, font_size='13sp', color=C_GOLD, halign='center',
                               size_hint_y=None, height=dp(28)))

    sv = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(8))
    log = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(4), spacing=dp(10))
    log.bind(minimum_height=log.setter('height'))
    sv.add_widget(log)
    root.add_widget(sv)

    p = Popup(title=P(title), content=root, size_hint=(0.96, 0.94),
              title_font='ui', title_align='center', separator_color=C_GOLD)

    def _scroll_bottom(*a):
        sv.scroll_y = 0

    def _bubble(text, role='ai'):
        is_user = (role == 'user')
        bg = (0.10, 0.30, 0.18, 1) if is_user else (0.10, 0.14, 0.22, 1)
        card = RoundBox(bg=bg, orientation='vertical', size_hint_y=None, padding=dp(10), spacing=dp(4))
        card.bind(minimum_height=card.setter('height'))
        who = RLabel('تو' if is_user else 'هوش مصنوعی', font_size='12sp', bold=True,
                     color=(C_GREEN if is_user else C_GOLD), halign='right',
                     size_hint_y=None, height=dp(20))
        card.add_widget(who)
        lbl = RLabel(text, font_size='15sp', color=C_TEXT, halign='right', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
        card.add_widget(lbl)
        log.add_widget(card)
        _fade_in(card)
        Clock.schedule_once(_scroll_bottom, 0.05)
        return lbl

    def _stream_into(target_lbl):
        acc = {'t': ''}

        def _delta(piece):
            acc['t'] += piece
            target_lbl.set_text(acc['t'])
            Clock.schedule_once(_scroll_bottom, 0)

        def _done(full):
            text = (full or acc['t'] or '').strip() or '(پاسخی دریافت نشد)'
            target_lbl.set_text(text)
            convo.append({'role': 'assistant', 'content': text})
            state['busy'] = False

        def _err(msg):
            target_lbl.set_text('⚠ ' + msg)
            toast(msg, 'هوش مصنوعی', kind='error')
            state['busy'] = False

        ai_manager.chat(convo, on_delta=_delta, on_done=_done, on_error=_err,
                        stream=True, temperature=temperature, max_tokens=max_tokens)

    def _send(*a):
        if state['busy']:
            toast('صبر کن تا پاسخِ قبلی کامل شود.', 'هوش مصنوعی')
            return
        q = (inp.query or '').strip()
        if not q:
            return
        inp.clear_logical()
        convo.append({'role': 'user', 'content': q})
        _bubble(q, role='user')
        state['busy'] = True
        _stream_into(_bubble('...', role='ai'))

    inrow = RoundBox(bg=(0.05, 0.08, 0.14, 0.55), orientation='horizontal', size_hint_y=None,
                     height=dp(60), padding=dp(6), spacing=dp(6))
    inp = PersianTextInput(hint_text=P('دربارهٔ این تحلیل بپرس...'), multiline=False,
                           font_size='15sp', size_hint_y=None, height=dp(48),
                           background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
    inp.bind(on_text_validate=_send)
    b_send = PillButton('ارسال', bg=C_GREEN, size_hint_x=None, width=dp(88), font_size='14sp')
    b_send.bind(on_release=_send)
    inrow.add_widget(inp)
    inrow.add_widget(b_send)
    root.add_widget(inrow, index=len(root.children))

    close = PillButton('بستن', bg=C_RED, size_hint_y=None, height=dp(44))
    close.bind(on_release=lambda *a: p.dismiss())
    root.add_widget(close)

    p.open()
    _stream_into(_bubble('در حال دریافت تحلیل...', role='ai'))
    return p


# ==================================================================
# صفحهٔ گفتگو با هوش مصنوعی
# ==================================================================
class ChatScreen(BaseScreen):
    def __init__(self, mode='discoveries', **kw):
        super().__init__(title='گفت‌وگو با هوش مصنوعی', **kw)
        self._messages = []      # تاریخچهٔ گفتگو (بدون system)
        self._busy = False
        self._cur_label = None
        self._acc = ''
        self._attach = None      # پیوستِ در انتظارِ ارسال
        self.mode = 'quran' if mode == 'quran' else 'discoveries'
        self._chat_id = None       # شناسهٔ گفت‌وگوی ذخیره‌شدهٔ جاری
        self._dirty = False        # پیامِ ذخیره‌نشده‌ای هست؟
        self._idle_ev = None       # زمان‌سنجِ ذخیرهٔ خودکار
        try:
            self.title_label._fit_single = True
            self.title_label.font_size = '17sp'
            # اسپیسرِ راستِ پیش‌فرض را با دکمهٔ «تنظیمات»ِ هم‌عرضِ «بازگشت» جایگزین کن تا برچسب دقیقاً وسط بنشیند
            if self.header.children:
                self.header.remove_widget(self.header.children[0])
            gear = PillButton('تنظیمات', bg=(1, 1, 1, 0.14), size_hint_x=None,
                              width=dp(90), font_size='13sp')
            gear.bind(on_release=lambda *a: open_ai_settings())
            self.header.add_widget(gear)
        except Exception:
            pass

        # کادرِ نوشتن در بالای صفحه (نه پایین) تا کیبورد آن را نپوشاند
        inrow = RoundBox(bg=(0.05, 0.08, 0.14, 0.62), orientation='horizontal', size_hint_y=None,
                         height=dp(60), padding=dp(6), spacing=dp(6))
        b_attach = PillButton('پیوست', bg=(1, 1, 1, 0.12), fg=C_TEXT, size_hint_x=None,
                              width=dp(76), font_size='13sp')
        b_attach.bind(on_release=lambda *a: self._pick_file())
        self.inp = PersianTextInput(hint_text=P('پیامت را بنویس...'), multiline=False,
                                    font_size='15sp', size_hint_y=None, height=dp(48),
                                    background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1))
        self.inp.bind(on_text_validate=lambda *a: self._send())
        send = PillButton('ارسال', bg=C_GREEN, size_hint_x=None, width=dp(84), font_size='14sp')
        send.bind(on_release=lambda *a: self._send())
        inrow.add_widget(b_attach)
        inrow.add_widget(self.inp)
        inrow.add_widget(send)
        self.body(inrow)

        # نوارِ نمایشِ پیوستِ انتخاب‌شده (پیش‌فرض پنهان)
        self.attach_bar = BoxLayout(size_hint_y=None, height=0, spacing=dp(6), opacity=0)
        self.attach_lbl = RLabel('', font_size='12sp', color=C_GOLD, halign='right')
        b_clr = PillButton('حذف پیوست', bg=C_RED, size_hint_x=None, width=dp(104), font_size='12sp')
        b_clr.bind(on_release=lambda *a: self._clear_attach())
        self.attach_bar.add_widget(self.attach_lbl)
        self.attach_bar.add_widget(b_clr)
        self.body(self.attach_bar)

        # نوارِ مدیریتِ گفت‌وگو: چت جدید / ذخیره / ذخیره‌شده‌ها
        chat_bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_new = PillButton('چت جدید', bg=C_INDIGO, font_size='13sp')
        b_new.bind(on_release=lambda *a: self._new_chat())
        b_save = PillButton('ذخیره', bg=C_TEAL, font_size='13sp')
        b_save.bind(on_release=lambda *a: self._save_current())
        b_saved = PillButton('ذخیره‌شده‌ها', bg=(1, 1, 1, 0.14), font_size='13sp')
        b_saved.bind(on_release=lambda *a: self._open_saved())
        chat_bar.add_widget(b_new)
        chat_bar.add_widget(b_save)
        chat_bar.add_widget(b_saved)
        self.body(chat_bar)

        # تاریخچهٔ گفت‌وگو زیرِ کادرِ نوشتن، فضای باقی‌مانده را پر می‌کند
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.log = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(6))
        self.log.bind(minimum_height=self.log.setter('height'))
        self.scroll.add_widget(self.log)
        self.body(self.scroll)
        _neon_border(inrow, C_BLUE, width=1.4, alpha=0.9)

    def set_mode(self, mode):
        """تعیینِ حالتِ گفت‌وگو (کشفیات یا قرآن کریم). با تغییرِ حالت، گفتگو از نو آغاز می‌شود؛
        امّا خودِ صفحهٔ چت و چیدمانش هیچ تغییری نمی‌کند."""
        mode = 'quran' if mode == 'quran' else 'discoveries'
        changed = (getattr(self, 'mode', None) != mode)
        self.mode = mode
        if changed or not self.log.children:
            self._messages = []
            self.log.clear_widgets()
            self._clear_attach()
        self.refresh()

    def refresh(self):
        if self.log.children:
            return
        if getattr(self, 'mode', 'discoveries') == 'quran':
            self._add_bubble('سلام! این گفت‌وگو دربارهٔ «قرآن کریم» است. من به کلِ آیاتِ منبعِ '
                             '«دیتاکاوش» (متنِ عربی و ترجمهٔ فارسی) و مرجعِ qref دسترسی دارم. هر پرسشی '
                             'از قرآن داری بپرس؛ مثلاً «همهٔ آیاتی که مستقیم یا غیرمستقیم به اعداد اشاره '
                             'می‌کنند» یا «آیاتِ مربوط به اراده و اختیار». در سراسرِ آیات می‌گردم و '
                             'بی‌کم‌وکاست می‌آورم تا با هم بررسی کنیم.', role='ai')
        else:
            self._add_bubble('سلام! من به همهٔ کشفیاتِ لابراتوار و گلچینِ تو دسترسی دارم. '
                             'دربارهٔ الگوها، شباهت‌ها یا هر تحلیلی که بخواهی بپرس. '
                             'با دکمهٔ «پیوست» هم می‌توانی عکس، فایلِ متنی یا PDF بفرستی.', role='ai')

    # ---------- پیوستِ فایل / تصویر ----------
    def _pick_file(self):
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=self._on_file, multiple=False)
        except Exception:
            toast('انتخاب فایل روی این دستگاه ممکن نشد.', 'پیوست', kind='error')

    def _on_file(self, selection):
        if not selection:
            return
        path = selection[0]
        Clock.schedule_once(lambda *a: self._process_file(path), 0)

    def _process_file(self, path):
        try:
            ext = os.path.splitext(path)[1].lower()
            name = os.path.basename(path)
            if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'):
                with open(path, 'rb') as f:
                    raw = f.read()
                if len(raw) > 6 * 1024 * 1024:
                    toast('حجمِ تصویر خیلی زیاد است (بیش از ۶ مگابایت).', 'پیوست', kind='warn')
                    return
                mime = 'image/jpeg' if ext in ('.jpg', '.jpeg') else 'image/' + ext.lstrip('.')
                b64 = base64.b64encode(raw).decode('ascii')
                self._attach = {'kind': 'image', 'name': name,
                                'data_url': 'data:%s;base64,%s' % (mime, b64)}
                self._show_attach('تصویر: ' + name)
            elif ext == '.pdf':
                txt = self._extract_pdf(path)
                if txt is None:
                    return
                self._attach = {'kind': 'text', 'name': name, 'text': txt}
                self._show_attach('PDF: ' + name)
            elif ext in ('.txt', '.md', '.csv', '.json', '.log'):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    txt = f.read()
                self._attach = {'kind': 'text', 'name': name, 'text': txt[:8000]}
                self._show_attach('فایل: ' + name)
            else:
                toast('این نوع فایل پشتیبانی نمی‌شود (عکس، PDF یا فایلِ متنی بفرست).', 'پیوست', kind='warn')
        except Exception:
            toast('خواندنِ فایل ممکن نشد.', 'پیوست', kind='error')

    def _extract_pdf(self, path):
        try:
            from pypdf import PdfReader
        except Exception:
            try:
                from PyPDF2 import PdfReader
            except Exception:
                toast('کتابخانهٔ خواندنِ PDF در دسترس نیست.', 'پیوست', kind='error')
                return None
        try:
            reader = PdfReader(path)
            parts = []
            for pg in reader.pages[:30]:
                parts.append(pg.extract_text() or '')
            txt = (chr(10).join(parts)).strip()
            if not txt:
                toast('متنی از این PDF استخراج نشد (شاید اسکن‌شده باشد).', 'پیوست', kind='warn')
                return None
            return txt[:8000]
        except Exception:
            toast('خواندنِ PDF ممکن نشد.', 'پیوست', kind='error')
            return None

    def _show_attach(self, label):
        self.attach_lbl.set_text(label)
        self.attach_bar.height = dp(34)
        self.attach_bar.opacity = 1

    def _clear_attach(self):
        self._attach = None
        self.attach_lbl.set_text('')
        self.attach_bar.height = 0
        self.attach_bar.opacity = 0

    def _add_bubble(self, text, role='ai'):
        is_user = (role == 'user')
        bg = (0.10, 0.28, 0.16, 1) if is_user else (0.10, 0.14, 0.22, 1)
        card = RoundBox(bg=bg, orientation='vertical', size_hint_y=None, padding=dp(10), spacing=dp(4))
        who = RLabel('تو' if is_user else 'هوش مصنوعی', font_size='12sp', bold=True,
                     color=(C_GREEN if is_user else C_GOLD), halign='right',
                     size_hint_y=None, height=dp(20))
        card.add_widget(who)
        lbl = RLabel(text, font_size='15sp', color=C_TEXT, halign='right', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(8)))
        card.add_widget(lbl)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
        self.log.add_widget(card)
        _fade_in(card)
        Clock.schedule_once(lambda *a: setattr(self.scroll, 'scroll_y', 0), 0.05)
        return lbl

    def _send(self):
        if self._busy:
            toast('صبر کن تا پاسخِ قبلی کامل شود.', 'هوش مصنوعی')
            return
        q = self.inp.query.strip()
        att = self._attach
        if not q and not att:
            return
        self.inp.clear_logical()
        nl = chr(10)

        if att and att['kind'] == 'image':
            shown = (q + '   ' if q else '') + '[تصویر: ' + att['name'] + ']'
            hist = q or 'این تصویر را بررسی کن.'
            send_content = [{'type': 'text', 'text': q or 'این تصویر را بررسی کن و توضیح بده.'},
                            {'type': 'image_url', 'image_url': {'url': att['data_url']}}]
        elif att and att['kind'] == 'text':
            shown = (q + '   ' if q else '') + '[فایل: ' + att['name'] + ']'
            hist = q or ('بررسیِ فایل: ' + att['name'])
            send_content = ((q or 'این فایل را بررسی و خلاصه کن.') + nl + nl +
                            '[محتوای فایلِ «' + att['name'] + '»]:' + nl + att['text'])
        else:
            shown = q
            hist = q
            send_content = q

        self._add_bubble(shown, role='user')
        self._messages.append({'role': 'user', 'content': hist})
        self._clear_attach()
        self._dirty = True
        self._touch_activity()

        self._busy = True
        self._acc = ''
        self._cur_label = self._add_bubble('...', role='ai')

        def _delta(piece):
            self._acc += piece
            if self._cur_label:
                self._cur_label.set_text(self._acc)
                Clock.schedule_once(lambda *a: setattr(self.scroll, 'scroll_y', 0), 0)

        def _done(full):
            self._busy = False
            text = (full or self._acc or '').strip() or '(پاسخی دریافت نشد)'
            if self._cur_label:
                self._cur_label.set_text(text)
            self._messages.append({'role': 'assistant', 'content': text})
            self._cur_label = None
            self._dirty = True
            self._touch_activity()

        def _err(msg):
            self._busy = False
            if self._cur_label:
                self._cur_label.set_text('⚠ ' + msg)
            self._cur_label = None
            toast(msg, 'هوش مصنوعی', kind='error')

        # --- حالتِ «گفت‌وگو دربارهٔ قرآن کریم»: بازیابیِ آیات از کلِ دیتاکاوش، سپس تحلیل ---
        if getattr(self, 'mode', 'discoveries') == 'quran':
            qtext = (q or hist or '').strip()
            # ابتدا نیتِ کاربر را می‌سنجیم: سلام/گپ → پاسخِ گفت‌وگویی؛ پرسشِ قرآنی → بازیابی و تحلیل
            if self._looks_like_chitchat(qtext):
                self._quran_chat_reply(qtext, _delta, _done, _err)
                return
            if self._cur_label:
                self._cur_label.set_text('در حالِ درکِ پرسش…')

            def _routed(is_quran):
                if is_quran:
                    self._run_quran_turn(qtext, _delta, _done, _err)
                else:
                    self._quran_chat_reply(qtext, _delta, _done, _err)

            ai_manager.quran_classify(
                qtext, history=self._messages[-6:-1], on_done=_routed,
                on_error=lambda _m: self._run_quran_turn(qtext, _delta, _done, _err))
            return

        app = App.get_running_app()
        system = ai_manager.build_chat_system(app.favs, app.featured)
        msgs = [{'role': 'system', 'content': system}] + self._messages[-12:]
        msgs[-1] = {'role': 'user', 'content': send_content}
        ai_manager.chat(msgs, on_delta=_delta, on_done=_done, on_error=_err,
                        stream=True, temperature=0.6, max_tokens=1024)

    # ---------- حالتِ گفت‌وگو دربارهٔ قرآن کریم ----------
    def _looks_like_chitchat(self, text):
        """فازِ تند: سلام/تشکر/گپِ کوتاه را بی‌درنگ (بدونِ فراخوانیِ طبقه‌بند) تشخیص می‌دهد."""
        t = (text or '').strip()
        if not t:
            return True
        norm = t.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
        norm = norm.replace('؟', ' ').replace('‌', ' ')
        low = ' ' + ' '.join(norm.split()) + ' '
        greet = ('سلام', 'درود', 'علیک', 'صبح بخیر', 'وقت بخیر', 'شب بخیر',
                 'خداحافظ', 'خدا حافظ', 'بدرود', 'ممنون', 'مرسی', 'سپاس', 'تشکر',
                 'دمت گرم', 'مخلص', 'خوبی', 'چطوری', 'حالت چطور', 'حال شما',
                 'خسته نباش', 'اهلا', 'های', 'سلام‌علیکم')
        words = norm.split()
        if len(words) <= 4:
            for gw in greet:
                if (' ' + gw + ' ') in low or low.strip() == gw:
                    return True
        return False

    def _quran_chat_reply(self, question, on_delta, on_done, on_error):
        """پاسخِ گفت‌وگویی (بدونِ بازیابیِ آیات) برای سلام/گپ/پرسش دربارهٔ خودِ دستیار."""
        history = self._messages[-8:-1]
        try:
            system = ai_manager.build_quran_chat_system()
        except Exception:
            system = 'تو دستیارِ گرم و کوتاه‌پاسخِ بخشِ گفت‌وگو دربارهٔ قرآن هستی.'
        msgs = ([{'role': 'system', 'content': system}] + list(history) +
                [{'role': 'user', 'content': (question or '').strip()}])
        ai_manager.chat(msgs, on_delta=on_delta, on_done=on_done, on_error=on_error,
                        stream=True, temperature=0.6, max_tokens=600)

    def _run_quran_turn(self, question, on_delta, on_done, on_error):
        """دومرحله‌ای: (۱) گرفتنِ کلیدواژه‌های مرتبط از هوش مصنوعی، (۲) جست‌وجوی گستردهٔ آیات
        در کلِ دیتاکاوش، (۳) تحلیلِ زندهٔ آیاتِ یافت‌شده با تأکید بر جانیفتادنِ اشاره‌های مستقیم و غیرمستقیم."""
        history = self._messages[-10:-1]  # تاریخچهٔ پیش از پیامِ جاری

        if self._cur_label:
            self._cur_label.set_text('در حال یافتنِ کلیدواژه‌های مرتبط…')

        def _after_terms(terms):
            if self._cur_label:
                self._cur_label.set_text('در حال جست‌وجوی آیات در سراسرِ قرآن…')

            def _bg():
                try:
                    verses = self._collect_quran_verses(question, terms)
                except Exception:
                    verses = []

                def _ui(_dt):
                    if self._cur_label:
                        self._cur_label.set_text('در حال تحلیلِ %d آیهٔ یافت‌شده…' % len(verses))
                    try:
                        msgs = ai_manager.build_quran_messages(question, verses, history)
                        ai_manager.chat(msgs, on_delta=on_delta, on_done=on_done, on_error=on_error,
                                        stream=True, temperature=0.4, max_tokens=2048)
                    except Exception:
                        on_error('تحلیلِ آیات ممکن نشد.')
                Clock.schedule_once(_ui, 0)

            import threading as _th
            _th.Thread(target=_bg, daemon=True).start()

        # مرحلهٔ ۱: کلیدواژه/ریشه‌های مرتبط (شاملِ اشاره‌های غیرمستقیم). اگر نشد، فقط با واژه‌های خودِ پرسش می‌گردیم
        ai_manager.quran_search_terms(
            question,
            on_done=_after_terms,
            on_error=lambda _m: _after_terms([]),
        )

    def _collect_quran_verses(self, question, terms, cap=110, per_term=45):
        """آیاتِ همخوان با کلیدواژه‌ها را از کلِ دیتاکاوش جمع می‌کند (بدونِ تکرار).
        کلیدواژه‌های خودِ پرسش هم به‌عنوانِ تورِ ایمنی افزوده می‌شوند."""
        app = App.get_running_app()
        seen = set()
        out = []
        try:
            base = list(core.get_dynamic_roots(question))
        except Exception:
            base = []
        all_terms = []
        for t in (list(terms or []) + base + [question]):
            t = (t or '').strip()
            if t and t not in all_terms:
                all_terms.append(t)
        for term in all_terms:
            try:
                res = app.data.search_all(term, limit=per_term)
            except Exception:
                res = []
            for r in res:
                key = (r.get('s'), r.get('a'))
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
                if len(out) >= cap:
                    return out
        return out

    # ---------- ذخیره/بازیابی/جست‌وجوی گفت‌وگو ----------
    IDLE_SECS = 240  # پس از این مدت بی‌کاری، گفت‌وگو خودکار ذخیره و صفحه پاک می‌شود

    def _has_content(self):
        return any(isinstance(m, dict) and str(m.get('content') or '').strip()
                   for m in (self._messages or []))

    def _touch_activity(self, *a):
        try:
            if self._idle_ev is not None:
                self._idle_ev.cancel()
        except Exception:
            pass
        self._idle_ev = None
        if self._has_content():
            try:
                self._idle_ev = Clock.schedule_once(self._on_idle, self.IDLE_SECS)
            except Exception:
                self._idle_ev = None

    def _cancel_idle(self):
        try:
            if self._idle_ev is not None:
                self._idle_ev.cancel()
        except Exception:
            pass
        self._idle_ev = None

    def _on_idle(self, *a):
        self._idle_ev = None
        if getattr(self, '_busy', False) or not self._has_content():
            return
        saved = self._save_current(silent=True, auto=True)
        self._reset_chat()
        if saved:
            toast('گفت‌وگو خودکار ذخیره شد و صفحهٔ چت پاک شد.', 'گفت‌وگو')

    def _reset_chat(self):
        self._cancel_idle()
        self._busy = False
        self._cur_label = None
        self._acc = ''
        self._messages = []
        self._chat_id = None
        self._dirty = False
        self.log.clear_widgets()
        self._clear_attach()
        self.refresh()

    def _new_chat(self):
        if getattr(self, '_busy', False):
            toast('صبر کن تا پاسخِ جاری کامل شود.', 'گفت‌وگو')
            return
        if self._has_content() and self._dirty:
            self._save_current(silent=True, auto=True)
            toast('گفت‌وگوی قبلی ذخیره شد؛ چت جدید آماده است.', 'گفت‌وگو')
        else:
            toast('چت جدید آماده است.', 'گفت‌وگو')
        self._reset_chat()

    def _chat_title(self):
        for m in (self._messages or []):
            if isinstance(m, dict) and m.get('role') == 'user' and str(m.get('content') or '').strip():
                return str(m['content']).strip().replace(chr(10), ' ')[:44]
        for m in (self._messages or []):
            if isinstance(m, dict) and str(m.get('content') or '').strip():
                return str(m['content']).strip().replace(chr(10), ' ')[:44]
        return 'گفت‌وگوی بی‌عنوان'

    def _save_current(self, silent=False, auto=False):
        if not self._has_content():
            if not silent:
                toast('گفت‌وگویی برای ذخیره وجود ندارد.', 'گفت‌وگو', kind='warn')
            return False
        app = App.get_running_app()
        try:
            cid = app.save_chat(getattr(self, 'mode', 'discoveries'),
                                self._messages, chat_id=self._chat_id,
                                title=self._chat_title())
        except Exception:
            if not silent:
                toast('ذخیرهٔ گفت‌وگو ممکن نشد.', 'گفت‌وگو', kind='error')
            return False
        if cid:
            self._chat_id = cid
            self._dirty = False
        if not silent:
            toast('گفت‌وگو ذخیره شد ✓', 'گفت‌وگو')
        return bool(cid)

    def _open_saved(self):
        app = App.get_running_app()
        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        q = PersianTextInput(hint_text=P('جست‌وجو در گفت‌وگوها…'), multiline=False,
                             font_size='14sp', size_hint_y=None, height=dp(48),
                             background_color=(1, 1, 1, 0.95),
                             foreground_color=(0.05, 0.08, 0.14, 1))
        root.add_widget(q)
        sc = ScrollView(do_scroll_x=False, bar_width=dp(4))
        lst = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        lst.bind(minimum_height=lst.setter('height'))
        sc.add_widget(lst)
        root.add_widget(sc)
        p = Popup(title=P('گفت‌وگوهای ذخیره‌شده'), content=root, size_hint=(0.96, 0.92),
                  title_font='ui', title_align='center', separator_color=C_GOLD)

        def _render(*a):
            lst.clear_widgets()
            matches = app.search_chats(q.query.strip(), mode=self.mode)
            if not matches:
                empty = 'چیزی یافت نشد.' if q.query.strip() else 'هنوز گفت‌وگوی ذخیره‌شده‌ای نیست.'
                lst.add_widget(RLabel(empty, font_size='14sp', color=C_MUTED, halign='center',
                                      size_hint_y=None, height=dp(48)))
                return
            for c, snip in matches:
                lst.add_widget(self._saved_row(c, snip, p, _render))

        q.on_change = lambda *a: _render()
        _render()
        p.open()

    def _saved_row(self, chat, snippet, popup, on_change):
        mode_label = 'قرآن کریم' if chat.get('mode') == 'quran' else 'کشفیات'
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(6))
        head = RLabel(chat.get('title') or 'بی‌عنوان', font_size='15sp', bold=True,
                      color=C_TEXT, halign='right', size_hint_y=None)
        head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(head)
        meta = RLabel('%s • %s' % (mode_label, chat.get('date') or ''), font_size='11sp',
                      color=C_MUTED, halign='right', size_hint_y=None, height=dp(18))
        card.add_widget(meta)
        if snippet:
            sn = RLabel(snippet, font_size='12sp', color=C_GOLD, halign='right', size_hint_y=None)
            sn.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
            card.add_widget(sn)
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_open = PillButton('باز کردن', bg=C_GREEN, font_size='12sp')
        b_open.bind(on_release=lambda *a: self._load_chat(chat, popup))
        b_ren = PillButton('تغییر نام', bg=(1, 1, 1, 0.14), font_size='12sp')
        b_ren.bind(on_release=lambda *a: self._rename_chat(chat, on_change))
        b_del = PillButton('حذف', bg=C_RED, font_size='12sp')
        b_del.bind(on_release=lambda *a: self._delete_chat(chat, on_change))
        row.add_widget(b_open)
        row.add_widget(b_ren)
        row.add_widget(b_del)
        card.add_widget(row)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v))
        return card

    def _load_chat(self, chat, popup=None):
        if getattr(self, '_busy', False):
            toast('صبر کن تا پاسخِ جاری کامل شود.', 'گفت‌وگو')
            return
        if self._has_content() and self._dirty and chat.get('id') != self._chat_id:
            self._save_current(silent=True, auto=True)
        self._cancel_idle()
        self.mode = 'quran' if chat.get('mode') == 'quran' else 'discoveries'
        self._messages = [dict(m) for m in (chat.get('messages') or []) if isinstance(m, dict)]
        self._chat_id = chat.get('id')
        self._dirty = False
        self._render_messages()
        if popup:
            popup.dismiss()
        self._touch_activity()

    def _render_messages(self):
        self.log.clear_widgets()
        for m in self._messages:
            role = 'user' if m.get('role') == 'user' else 'ai'
            self._add_bubble(str(m.get('content') or ''), role=role)

    def _rename_chat(self, chat, on_change):
        app = App.get_running_app()
        def _ok(val):
            val = (val or '').strip()
            if not val:
                return
            try:
                app.rename_chat(chat.get('id'), val)
            except Exception:
                pass
            if callable(on_change):
                on_change()
        prompt_text('نامِ تازه برای این گفت‌وگو:', chat.get('title') or '', _ok, title='تغییر نام')

    def _delete_chat(self, chat, on_change):
        app = App.get_running_app()
        def _yes():
            try:
                app.delete_chat(chat.get('id'))
            except Exception:
                pass
            if chat.get('id') == self._chat_id:
                self._chat_id = None
            if callable(on_change):
                on_change()
            toast('گفت‌وگو حذف شد.', 'گفت‌وگو')
        confirm('این گفت‌وگو حذف شود؟', _yes, title='حذفِ گفت‌وگو')

    def on_pre_enter(self, *a):
        if not self.log.children and not self._messages:
            self.refresh()
        self._touch_activity()

    def on_leave(self, *a):
        self._cancel_idle()


# ==================================================================
# اپلیکیشن
# ==================================================================
def _norm_search(s):
    """یکسان‌سازیِ متن برای جست‌وجوی دقیق: کوچک‌سازی، یکدست‌کردنِ ی/ک، حذفِ اعراب و نیم‌فاصله."""
    if not s:
        return ''
    s = str(s)
    s = s.replace('\u064a', '\u06cc').replace('\u0649', '\u06cc')
    s = s.replace('\u0643', '\u06a9')
    s = s.replace('\u200c', ' ')
    for ch in ('\u064b', '\u064c', '\u064d', '\u064e', '\u064f', '\u0650',
               '\u0651', '\u0652', '\u0653', '\u0654', '\u0655', '\u0670'):
        s = s.replace(ch, '')
    return ' '.join(s.lower().split())


def _snippet_for(bodies, tokens, width=64):
    """کوتاه‌ترین برشِ خوانا از متنِ پیام‌ها که یکی از واژه‌های جست‌وجو را دربردارد."""
    for body in bodies:
        norm = _norm_search(body)
        idxs = [i for i in (norm.find(t) for t in tokens) if i >= 0]
        if idxs:
            pos = min(idxs)
            start = max(0, pos - width // 3)
            seg = norm[start:start + width].strip()
            if start > 0:
                seg = '…' + seg
            if start + width < len(norm):
                seg = seg + '…'
            return seg
    return ''


USE_NATIVE_INTRO = True


class QuranMirrorApp(App):
    def build(self):
        self.title = 'قطب‌نمای قرآنی'
        Window.clearcolor = C_BG
        # رفع مشکل پوشاندنِ باکسِ ورودی توسط کیبورد:
        # حالت 'pan' کلِ صفحه را به‌اندازهٔ لازم بالا می‌برد تا باکسِ در حالِ تایپ
        # همیشه بالای کیبورد و در دیدِ کاربر بماند (در همهٔ پنجره‌ها و پاپ‌آپ‌ها).
        try:
            # فقط روی موبایل لازم است (تا کیبوردِ صفحه‌ای باکس را نپوشاند)؛
            # روی ویندوز/دسکتاپ این حالت می‌تواند هنگامِ فوکوسِ باکس باعثِ هنگ/فریز شود.
            if _kivy_platform in ('android', 'ios'):
                # 'below_target' = خودِ Kivy پنجره را دقیقاً به‌اندازهٔ لازم بالا می‌برد
                # تا باکسِ در حالِ تایپ همیشه درست بالایِ کیبورد بایستد (همهٔ صفحه‌ها و پاپ‌آپ‌ها).
                Window.softinput_mode = 'below_target'
        except Exception:
            pass
        # تور ایمنی: خطاهای پیش‌بینی‌نشده به‌جای بستنِ کامل برنامه نادیده گرفته شوند
        try:
            from kivy.base import ExceptionManager, ExceptionHandler

            _guard_state = {'last': 0.0}

            class _AppGuard(ExceptionHandler):
                def handle_exception(self, exc):
                    try:
                        import traceback
                        traceback.print_exc()
                    except Exception:
                        pass
                    # نمایشِ خطا روی صفحه (به‌جای نادیده‌گرفتن کامل) تا علت «کارنکردن دکمه‌ها» دیده شود
                    try:
                        now = Clock.get_boottime()
                        if now - _guard_state['last'] > 2.0:   # جلوگیری از اسپم پاپ‌آپ
                            _guard_state['last'] = now
                            loc = ''
                            try:
                                import traceback as _tb
                                tbs = _tb.extract_tb(exc.__traceback__)
                                for fr in reversed(tbs):
                                    if 'main.py' in (fr.filename or ''):
                                        loc = '\n[main.py:%d %s]' % (fr.lineno, fr.name)
                                        break
                                if not loc and tbs:
                                    fr = tbs[-1]
                                    loc = '\n[%s:%d]' % ((fr.filename or '').split('/')[-1], fr.lineno)
                            except Exception:
                                pass
                            msg = '%s: %s%s' % (type(exc).__name__, exc, loc)
                            Clock.schedule_once(lambda *a: toast(msg[:400], 'خطای داخلی'), 0)
                    except Exception:
                        pass
                    return ExceptionManager.PASS

            ExceptionManager.add_handler(_AppGuard())
        except Exception:
            pass
        # داده
        self.data = core.QuranData(asset('datakavosh.csv'))
        self._init_storage()
        self.load_favs()
        self.load_featured()
        self.load_user_tags()
        self.load_ai_settings()
        self.load_chats()
        self.load_experiments()
        self.load_math_tasks()
        self.load_semantic_tasks()
        self.last_discovery_key = None
        self.last_discovery_section = None
        # صفحات
        sm = ScreenManager(transition=FadeTransition(duration=0.25))
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(MatrixScreen(name='matrix'))
        sm.add_widget(PredictScreen(name='predict'))
        sm.add_widget(LabScreen(name='lab'))
        sm.add_widget(OperatorScreen(name='operator'))
        sm.add_widget(FeaturedScreen(name='featured'))
        sm.add_widget(SearchScreen(name='search'))
        sm.add_widget(TagsScreen(name='tags'))
        sm.add_widget(MediaScreen(name='media'))
        sm.add_widget(BackupScreen(name='backup'))
        sm.add_widget(AboutScreen(name='about'))
        sm.add_widget(GuideScreen(name='guide'))
        sm.add_widget(ChatScreen(name='chat_disc', mode='discoveries'))
        sm.add_widget(ChatScreen(name='chat_quran', mode='quran'))
        sm.add_widget(ExperimentScreen(name='experiment'))
        self.sm = sm
        # بارِ اول: پوششِ مشکیِ تمام‌صفحه را زودتر بگذار تا پیش از ویدئو، پس‌زمینه دیده نشود.
        try:
            if not os.path.exists(self._p('.intro_played')):
                _pre = FloatLayout(size_hint=(1, 1))
                with _pre.canvas.before:
                    Color(0, 0, 0, 1)
                    _pre_bg = Rectangle(pos=(0, 0), size=Window.size)

                def _pre_sync(*a):
                    _pre_bg.pos = _pre.pos
                    _pre_bg.size = _pre.size
                _pre.bind(pos=_pre_sync, size=_pre_sync)
                _pre.size = Window.size
                Window.add_widget(_pre)
                self._intro_overlay = _pre
        except Exception:
            pass
        return sm

    def on_start(self):
        # جریانِ شروع:
        #   • بارِ اول (پس از نصب): ویدئویِ معرفی intro.mp4 تمام‌صفحه پخش می‌شود،
        #     و پس از پایان، اپ با یک فِید نمایان می‌شود. سپس صدایِ همیشگی پخش می‌شود.
        #   • اجراهایِ بعدی: ویدئو پخش نمی‌شود؛ فقط صدایِ همیشگی (voice) پخش می‌شود.
        def _after_intro(*a):
            try:
                self._play_voice_sound()
            except Exception:
                pass
        try:
            flag = self._p('.intro_played')
            first_run = not os.path.exists(flag)
            if first_run:
                # همین حالا علامت بزن تا حتی اگر پخش نیمه‌کاره ماند، بارِ بعد دیگر پخش نشود
                try:
                    with open(flag, 'w', encoding='utf-8') as f:
                        f.write('1')
                except Exception:
                    pass
                self._start_intro(_after_intro)
            else:
                # از دومین اجرا به بعد: افکتِ «باز شدنِ پرده از وسط به چپ و راست»
                # هم‌رنگِ پس‌زمینهٔ اپ، سپس صدایِ همیشگی.
                self._play_open_curtain()
                Clock.schedule_once(_after_intro, 0.15)
        except Exception:
            _after_intro()

    def _play_intro_video(self, on_done):
        """ویدئویِ معرفی را تمام‌صفحه (cover) پخش می‌کند و در پایان با فِید کنار می‌رود."""
        import time as _time
        done = {'v': False}
        st = {'started': False, 'start_wall': 0.0, 'dur': 0.0, 'poll_ev': None}

        def _finish(*a):
            if done['v']:
                return
            done['v'] = True
            ev = st.get('poll_ev')
            if ev is not None:
                try:
                    ev.cancel()
                except Exception:
                    pass
            ov = getattr(self, '_intro_overlay', None)
            vid = getattr(self, '_intro_video', None)
            try:
                if vid is not None:
                    vid.state = 'stop'
                    try:
                        vid.unload()
                    except Exception:
                        pass
            except Exception:
                pass

            def _remove(*a):
                try:
                    if ov is not None:
                        Window.remove_widget(ov)
                except Exception:
                    pass
                self._intro_overlay = None
                self._intro_video = None
                try:
                    on_done()
                except Exception:
                    pass
            if ov is not None:
                try:
                    anim = Animation(opacity=0, d=0.6)
                    anim.bind(on_complete=lambda *a: _remove())
                    anim.start(ov)
                except Exception:
                    _remove()
            else:
                _remove()

        try:
            path = None
            for _cand in ('intro.mp4', 'intro.m4a'):
                _pp = asset(_cand)
                if os.path.exists(_pp):
                    path = _pp
                    break
            if not path:
                _finish()
                return
            try:
                from kivy.uix.video import Video
                from kivy.uix.stencilview import StencilView
            except Exception:
                _finish()
                return

            overlay = getattr(self, '_intro_overlay', None)
            if overlay is None:
                overlay = FloatLayout(size_hint=(1, 1))
                with overlay.canvas.before:
                    Color(0, 0, 0, 1)
                    _bg = Rectangle(pos=overlay.pos, size=overlay.size)

                def _sync_bg(*a):
                    _bg.pos = overlay.pos
                    _bg.size = overlay.size
                overlay.bind(pos=_sync_bg, size=_sync_bg)
                overlay.size = Window.size
                Window.add_widget(overlay)
                self._intro_overlay = overlay

            stencil = StencilView(size_hint=(1, 1))
            overlay.add_widget(stencil)

            vid = Video(source=path, state='play', options={'eos': 'loop'})
            try:
                vid.allow_stretch = True
                vid.keep_ratio = True
                vid.volume = 1.0
            except Exception:
                pass
            vid.size_hint = (None, None)
            stencil.add_widget(vid)

            def _cover(*a):
                try:
                    W, H = float(stencil.width), float(stencil.height)
                    if W <= 1 or H <= 1:
                        return
                    a_v = 1080.0 / 1920.0
                    try:
                        tw, th = vid.texture.size
                        if tw and th:
                            a_v = float(tw) / float(th)
                    except Exception:
                        pass
                    w1, h1 = H * a_v, H
                    if w1 < W:
                        w1, h1 = W, W / a_v
                    vid.size = (w1, h1)
                    vid.pos = (stencil.x + (W - w1) / 2.0, stencil.y + (H - h1) / 2.0)
                except Exception:
                    pass
            stencil.bind(size=_cover, pos=_cover)
            vid.bind(texture=lambda *a: _cover())
            Clock.schedule_once(_cover, 0)

            def _on_touch(inst, touch):
                _finish()
                return True
            overlay.bind(on_touch_down=_on_touch)

            self._intro_video = vid

            def _on_dur(inst, val):
                try:
                    v = float(val or 0)
                    if v > 3.0:
                        st['dur'] = v
                except Exception:
                    pass
            vid.bind(duration=_on_dur)

            def _poll(dt):
                if done['v']:
                    return False
                try:
                    pos = float(vid.position or 0)
                except Exception:
                    pos = 0.0
                now = _time.time()
                if pos > 0.05 and not st['started']:
                    st['started'] = True
                    st['start_wall'] = now
                target = st['dur'] if st['dur'] > 3.0 else 9.5
                if st['started'] and (now - st['start_wall']) >= target + 0.25:
                    _finish()
                    return False
                return True
            st['poll_ev'] = Clock.schedule_interval(_poll, 0.2)

            def _watchdog(dt):
                if done['v']:
                    return
                if not st['started']:
                    _finish()
            Clock.schedule_once(_watchdog, 8)

            Clock.schedule_once(_finish, 30)
        except Exception:
            _finish()

    def _start_intro(self, on_done):
        # On Android, try the native hardware-decoded player first; if the
        # native stack is unavailable, fall back to the Kivy/ffpyplayer path.
        try:
            use_native = bool(USE_NATIVE_INTRO)
        except Exception:
            use_native = True
        if use_native and _kivy_platform == 'android':
            try:
                self._play_intro_video_native(on_done)
                return
            except Exception:
                pass
        self._play_intro_video(on_done)

    def _play_intro_video_native(self, on_done):
        """پخشِ ویدئوی معرفی با VideoViewِ نیتیوِ اندروید (دیکودِ سخت‌افزاری). در صورتِ خطا بی‌صدا واردِ اپ می‌شود."""
        path = None
        for _cand in ('intro.mp4', 'intro.m4a'):
            _pp = asset(_cand)
            if os.path.exists(_pp):
                path = _pp
                break
        if not path:
            on_done()
            return

        # These imports exist only on Android; ImportError -> caller falls back.
        from jnius import autoclass, cast, PythonJavaClass, java_method
        from android.runnable import run_on_ui_thread

        done = {'v': False}
        state = {'root': None, 'vv': None}

        def _proceed_kivy():
            if done['v']:
                return
            done['v'] = True

            def _do(dt):
                ov = getattr(self, '_intro_overlay', None)

                def _rm(*a):
                    try:
                        if ov is not None:
                            Window.remove_widget(ov)
                    except Exception:
                        pass
                    self._intro_overlay = None
                    try:
                        on_done()
                    except Exception:
                        pass
                if ov is not None:
                    try:
                        anim = Animation(opacity=0, d=0.5)
                        anim.bind(on_complete=lambda *a: _rm())
                        anim.start(ov)
                    except Exception:
                        _rm()
                else:
                    _rm()
            Clock.schedule_once(_do, 0)

        @run_on_ui_thread
        def _remove_native():
            try:
                vv = state.get('vv')
                if vv is not None:
                    try:
                        vv.stopPlayback()
                    except Exception:
                        pass
                root = state.get('root')
                if root is not None:
                    par = root.getParent()
                    if par is not None:
                        vg = cast('android.view.ViewGroup', par)
                        vg.removeView(root)
            except Exception:
                pass

        def _end(*a):
            _remove_native()
            _proceed_kivy()

        class _Prepared(PythonJavaClass):
            __javainterfaces__ = ['android/media/MediaPlayer$OnPreparedListener']
            __javacontext__ = 'app'

            @java_method('(Landroid/media/MediaPlayer;)V')
            def onPrepared(self, mp):
                try:
                    mp.setLooping(False)
                    try:
                        mp.setVolume(1.0, 1.0)
                    except Exception:
                        pass
                    vw = mp.getVideoWidth() or 1080
                    vh = mp.getVideoHeight() or 1920
                    activity = autoclass('org.kivy.android.PythonActivity').mActivity
                    dm = activity.getResources().getDisplayMetrics()
                    sw = float(dm.widthPixels)
                    sh = float(dm.heightPixels)
                    a_v = float(vw) / float(vh)
                    cw = sh * a_v
                    ch = sh
                    if cw < sw:
                        cw = sw
                        ch = sw / a_v
                    FLP = autoclass('android.widget.FrameLayout$LayoutParams')
                    Gravity = autoclass('android.view.Gravity')
                    lp = FLP(int(cw), int(ch), Gravity.CENTER)
                    vv = state.get('vv')
                    if vv is not None:
                        vv.setLayoutParams(lp)
                        vv.start()
                except Exception:
                    pass

        class _Completion(PythonJavaClass):
            __javainterfaces__ = ['android/media/MediaPlayer$OnCompletionListener']
            __javacontext__ = 'app'

            @java_method('(Landroid/media/MediaPlayer;)V')
            def onCompletion(self, mp):
                _end()

        class _Error(PythonJavaClass):
            __javainterfaces__ = ['android/media/MediaPlayer$OnErrorListener']
            __javacontext__ = 'app'

            @java_method('(Landroid/media/MediaPlayer;II)Z')
            def onError(self, mp, what, extra):
                _end()
                return True

        prepared = _Prepared()
        completion = _Completion()
        error = _Error()
        # keep strong refs so the Java callbacks are not garbage-collected
        self._intro_native_refs = [prepared, completion, error]

        @run_on_ui_thread
        def _start():
            try:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                FrameLayout = autoclass('android.widget.FrameLayout')
                VideoView = autoclass('android.widget.VideoView')
                VGLP = autoclass('android.view.ViewGroup$LayoutParams')
                FLP = autoclass('android.widget.FrameLayout$LayoutParams')
                Gravity = autoclass('android.view.Gravity')
                AColor = autoclass('android.graphics.Color')
                Uri = autoclass('android.net.Uri')
                JFile = autoclass('java.io.File')

                root = FrameLayout(activity)
                try:
                    root.setBackgroundColor(AColor.BLACK)
                except Exception:
                    pass
                vv = VideoView(activity)
                try:
                    vv.setZOrderOnTop(True)
                except Exception:
                    pass
                lp0 = FLP(VGLP.MATCH_PARENT, VGLP.MATCH_PARENT, Gravity.CENTER)
                root.addView(vv, lp0)

                vv.setOnPreparedListener(prepared)
                vv.setOnCompletionListener(completion)
                vv.setOnErrorListener(error)
                vv.setVideoURI(Uri.fromFile(JFile(path)))

                rlp = VGLP(VGLP.MATCH_PARENT, VGLP.MATCH_PARENT)
                activity.addContentView(root, rlp)
                try:
                    vv.requestFocus()
                except Exception:
                    pass
                vv.start()

                state['root'] = root
                state['vv'] = vv
            except Exception:
                _proceed_kivy()

        _start()

        # safety cap: if completion never fires, enter the app after 20s
        Clock.schedule_once(lambda dt: _end(), 20)

    def _play_voice_sound(self):
        """صدایِ همیشگی (voice) را پخش می‌کند — با چند فرمتِ جایگزین برایِ سازگاریِ ویندوز/اندروید."""
        try:
            from kivy.core.audio import SoundLoader
        except Exception:
            return
        try:
            for fn in ('voice.ogg', 'voice.mp3', 'voice.wav', 'voice.m4a'):
                p = asset(fn)
                if os.path.exists(p):
                    try:
                        s = SoundLoader.load(p)
                    except Exception:
                        s = None
                    if s:
                        self._voice_sound = s
                        Clock.schedule_once(lambda *a: s.play(), 0.15)
                        return
        except Exception:
            pass

    def _play_open_curtain(self, on_done=None):
        """از دومین اجرا به بعد: دو لتِ مشکیِ تیره که ابتدا کلِ صفحه را می‌پوشانند، کمی مکث، سپس بسیار آرام از وسط به چپ و راست باز می‌شوند."""
        try:
            col = (0, 0, 0, 1)  # مشکیِ تیره

            def _dims():
                w, h = Window.size
                if not w or not h:
                    w, h = 1080, 1920
                return float(w), float(h)

            W, H = _dims()
            overlay = FloatLayout(size_hint=(None, None), size=(W, H), pos=(0, 0))

            left = Widget(size_hint=(None, None), size=(W / 2.0 + 2, H), pos=(0, 0))
            with left.canvas:
                Color(*col)
                lr = Rectangle(pos=left.pos, size=left.size)
            left.bind(pos=lambda *a: setattr(lr, 'pos', left.pos),
                      size=lambda *a: setattr(lr, 'size', left.size))

            right = Widget(size_hint=(None, None), size=(W / 2.0 + 2, H), pos=(W / 2.0, 0))
            with right.canvas:
                Color(*col)
                rr = Rectangle(pos=right.pos, size=right.size)
            right.bind(pos=lambda *a: setattr(rr, 'pos', right.pos),
                       size=lambda *a: setattr(rr, 'size', right.size))

            overlay.add_widget(left)
            overlay.add_widget(right)
            overlay.bind(on_touch_down=lambda *a: True)

            def _resize(*a):
                w, h = _dims()
                overlay.size = (w, h)
                left.size = (w / 2.0 + 2, h)
                left.pos = (0, 0)
                right.size = (w / 2.0 + 2, h)
                right.pos = (w / 2.0, 0)
            Window.bind(size=_resize)

            Window.add_widget(overlay)
            self._curtain_overlay = overlay

            def _done(*a):
                try:
                    Window.unbind(size=_resize)
                except Exception:
                    pass
                try:
                    Window.remove_widget(overlay)
                except Exception:
                    pass
                self._curtain_overlay = None
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

            def _open(*a):
                try:
                    Window.unbind(size=_resize)
                except Exception:
                    pass
                w, h = _dims()
                Animation(x=-(w / 2.0) - 4, d=1.6, t='out_cubic').start(left)
                aR = Animation(x=w, d=1.6, t='out_cubic')
                aR.bind(on_complete=lambda *a: _done())
                aR.start(right)

            # پردهٔ مشکی کلِ صفحه را می‌پوشاند، کمی مکث، سپس بازشدنِ بسیار آرام
            Clock.schedule_once(_open, 0.5)
        except Exception:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

    # ---------- ذخیره‌سازی ----------
    # ---------- چرخهٔ حیات: ذخیرهٔ خودکارِ گفت‌وگو هنگامِ بستن/توقفِ اپ ----------
    def _autosave_chat_on_exit(self):
        for _nm in ('chat_disc', 'chat_quran'):
            try:
                scr = self.sm.get_screen(_nm)
                if scr._has_content() and getattr(scr, '_dirty', False):
                    scr._save_current(silent=True, auto=True)
            except Exception:
                pass

    def on_stop(self):
        self._autosave_chat_on_exit()

    def on_pause(self):
        self._autosave_chat_on_exit()
        return True

    def _init_storage(self):
        self.store_dir = self.user_data_dir
        for name in ('favorites.json', 'featured.json', 'user_tags.json'):
            dst = os.path.join(self.store_dir, name)
            if not os.path.exists(dst):
                src = asset(name)
                try:
                    if os.path.exists(src):
                        shutil.copy(src, dst)
                    else:
                        with open(dst, 'w', encoding='utf-8') as f:
                            json.dump([], f, ensure_ascii=False)
                except Exception:
                    pass

    def _p(self, name):
        return os.path.join(self.store_dir, name)

    def load_favs(self):
        try:
            with open(self._p('favorites.json'), encoding='utf-8') as f:
                self.favs = json.load(f)
        except Exception:
            self.favs = []
        if not isinstance(self.favs, list):
            self.favs = []
        for _it in self.favs:
            _normalize_item_modes(_it)

    def save_favs(self):
        _atomic_write_json(self._p('favorites.json'), self.favs, indent=2)

    def load_featured(self):
        try:
            with open(self._p('featured.json'), encoding='utf-8') as f:
                self.featured = json.load(f)
        except Exception:
            self.featured = []
        if not isinstance(self.featured, list):
            self.featured = []
        for _it in self.featured:
            _normalize_item_modes(_it)

    def save_featured(self):
        _atomic_write_json(self._p('featured.json'), self.featured, indent=2)

    def load_user_tags(self):
        try:
            with open(self._p('user_tags.json'), encoding='utf-8') as f:
                self.user_tags = json.load(f)
            if not isinstance(self.user_tags, list):
                self.user_tags = []
        except Exception:
            self.user_tags = []
        try:
            with open(self._p('hidden_tags.json'), encoding='utf-8') as f:
                self.hidden_tags = json.load(f)
            if not isinstance(self.hidden_tags, list):
                self.hidden_tags = []
        except Exception:
            self.hidden_tags = []

    def save_user_tags(self):
        _atomic_write_json(self._p('user_tags.json'), self.user_tags, indent=2)
        _atomic_write_json(self._p('hidden_tags.json'), getattr(self, 'hidden_tags', []), indent=2)

    def _reassign_tag(self, old, new=None):
        """در همهٔ کشف‌های لابراتوار و گلچین، برچسبِ old را به new تغییر می‌دهد
        (یا اگر new=None باشد آن را حذف می‌کند)؛ برچسب‌های چندتایی هم درست مدیریت می‌شوند."""
        sep = chr(1548)
        changed = False
        for lst in (getattr(self, 'favs', []), getattr(self, 'featured', [])):
            if not isinstance(lst, list):
                continue
            for it in lst:
                if not isinstance(it, dict):
                    continue
                rt = str(it.get('relation_type') or '')
                if not rt:
                    continue
                parts = [p.strip() for p in rt.split(sep)]
                parts = [p for p in parts if p and p != 'نامشخص']
                if old not in parts:
                    continue
                out = []
                for p in parts:
                    rep = new if p == old else p
                    if rep and rep not in out:
                        out.append(rep)
                it['relation_type'] = (sep + ' ').join(out) if out else 'نامشخص'
                changed = True
        if changed:
            self.save_favs()
            self.save_featured()

    def delete_tag(self, tag):
        """حذفِ کاملِ یک برچسب (پیش‌فرض یا کاربر) و برداشتنِ آن از همهٔ کشف‌ها."""
        if not tag or tag == 'نامشخص':
            return
        self._reassign_tag(tag, None)
        if tag in getattr(self, 'user_tags', []):
            self.user_tags.remove(tag)
        if tag in TagsScreen.DEFAULT:
            if not isinstance(getattr(self, 'hidden_tags', None), list):
                self.hidden_tags = []
            if tag not in self.hidden_tags:
                self.hidden_tags.append(tag)
        self.save_user_tags()

    def rename_tag(self, old, new):
        """تغییرِ نامِ یک برچسب و به‌روزرسانیِ همهٔ کشف‌ها. خروجی: (ok, msg)."""
        new = (new or '').strip()
        if not old or old == 'نامشخص':
            return (False, 'این برچسب قابلِ ویرایش نیست.')
        if not new:
            return (False, 'نامِ برچسب نمی‌تواند خالی باشد.')
        if new == old:
            return (True, '')
        if new in self.get_all_tags():
            return (False, 'برچسبی با این نام از قبل وجود دارد.')
        self._reassign_tag(old, new)
        if old in getattr(self, 'user_tags', []):
            self.user_tags.remove(old)
        if old in TagsScreen.DEFAULT:
            if not isinstance(getattr(self, 'hidden_tags', None), list):
                self.hidden_tags = []
            if old not in self.hidden_tags:
                self.hidden_tags.append(old)
        if new not in TagsScreen.DEFAULT and new not in self.user_tags:
            self.user_tags.append(new)
        if new in getattr(self, 'hidden_tags', []):
            self.hidden_tags.remove(new)
        self.save_user_tags()
        return (True, '')

    # ---------- تنظیمات هوش مصنوعی ----------
    def load_ai_settings(self):
        self.ai_settings = ai_manager.default_settings()
        try:
            with open(self._p('settings.json'), encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in ('api_key', 'base_url', 'model'):
                    if data.get(k):
                        self.ai_settings[k] = data[k]
        except Exception:
            pass
        # ماژول هوش مصنوعی تنظیمات را «زنده» از همین‌جا می‌خواند
        ai_manager.set_config_provider(lambda: getattr(self, 'ai_settings', {}))

    def save_ai_settings(self, api_key=None, base_url=None, model=None):
        if not isinstance(getattr(self, 'ai_settings', None), dict):
            self.ai_settings = ai_manager.default_settings()
        if api_key is not None:
            self.ai_settings['api_key'] = api_key.strip()
        if base_url is not None:
            self.ai_settings['base_url'] = base_url.strip() or ai_manager.DEFAULT_BASE_URL
        if model is not None:
            self.ai_settings['model'] = model.strip() or ai_manager.DEFAULT_MODEL
        _atomic_write_json(self._p('settings.json'), self.ai_settings, indent=2)

    # ---------- گفت‌وگوهای هوش مصنوعی ----------
    def load_chats(self):
        try:
            with open(self._p('chats.json'), encoding='utf-8') as f:
                self.chats = json.load(f)
        except Exception:
            self.chats = []
        if not isinstance(self.chats, list):
            self.chats = []

    def save_chats(self):
        _atomic_write_json(self._p('chats.json'), getattr(self, 'chats', []), indent=2)

    # ---------- دفترِ پژوهش ----------
    def load_experiments(self):
        try:
            with open(self._p('experiments.json'), encoding='utf-8') as f:
                self.experiments = json.load(f)
        except Exception:
            self.experiments = []
        if not isinstance(self.experiments, list):
            self.experiments = []

    def save_experiments(self):
        _atomic_write_json(self._p('experiments.json'), getattr(self, 'experiments', []), indent=2)

    def exp_create(self, title):
        if not isinstance(getattr(self, 'experiments', None), list):
            self.experiments = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        exp = {'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
               'title': (title or '').strip()[:80] or 'آزمایشِ بی‌عنوان',
               'hypothesis': '', 'method': '', 'result': '', 'control': '',
               'status': 'open', 'items': [], 'date': now, 'updated': now}
        self.experiments.insert(0, exp)
        self.save_experiments()
        return exp

    def exp_add_item(self, exp, item):
        if not isinstance(exp, dict) or not isinstance(item, dict):
            return False
        items = exp.setdefault('items', [])
        key = _exp_item_key(item)
        for it in items:
            if _exp_item_key(it) == key:
                return False
        items.append(dict(item))
        exp['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.save_experiments()
        return True

    def exp_remove_item(self, exp, item):
        if not isinstance(exp, dict):
            return
        key = _exp_item_key(item)
        exp['items'] = [it for it in (exp.get('items') or []) if _exp_item_key(it) != key]
        exp['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.save_experiments()

    def exp_delete(self, exp_id):
        if not isinstance(getattr(self, 'experiments', None), list):
            self.experiments = []
            return
        self.experiments = [e for e in self.experiments
                            if not (isinstance(e, dict) and e.get('id') == exp_id)]
        self.save_experiments()

    # ---------- تسک‌های دفترِ پژوهش (عددی + معنایی) ----------
    def _task_conf(self, kind):
        if kind == 'semantic':
            return ('semantic_tasks', 'semantic_tasks.json', DEFAULT_SEMANTIC_TASKS)
        return ('math_tasks', 'math_tasks.json', DEFAULT_MATH_TASKS)

    def _load_tasks(self, kind):
        attr, fname, defaults = self._task_conf(kind)
        try:
            with open(self._p(fname), encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = []
        if not isinstance(data, list):
            data = []
        if not data:
            data = [{'id': datetime.now().strftime('%Y%m%d%H%M%S%f') + str(i), 'text': t}
                    for i, t in enumerate(defaults)]
            setattr(self, attr, data)
            self._save_tasks(kind)
        else:
            setattr(self, attr, data)
        # تضمینِ حضورِ تسکِ «رجوع به جدول زوج و فرد» در بُعدِ اعداد (حتی روی دادهٔ قدیمی)
        if kind == 'numeric':
            cur = getattr(self, attr, []) or []
            has_eo = any(isinstance(t, dict) and 'رجوع به جدول زوج و فرد' in str(t.get('text', '')) for t in cur)
            if not has_eo:
                cur.insert(0, {'id': datetime.now().strftime('%Y%m%d%H%M%S%f') + 'eo',
                               'text': 'رجوع به جدول زوج و فرد'})
                setattr(self, attr, cur)
                self._save_tasks(kind)

    def _save_tasks(self, kind):
        attr, fname, _d = self._task_conf(kind)
        _atomic_write_json(self._p(fname), getattr(self, attr, []), indent=2)

    def load_math_tasks(self):
        self._load_tasks('numeric')

    def load_semantic_tasks(self):
        self._load_tasks('semantic')

    def save_math_tasks(self):
        self._save_tasks('numeric')

    def task_add(self, text, kind='numeric'):
        text = (text or '').strip()
        if not text:
            return None
        attr, _f, _d = self._task_conf(kind)
        if not isinstance(getattr(self, attr, None), list):
            setattr(self, attr, [])
        t = {'id': datetime.now().strftime('%Y%m%d%H%M%S%f'), 'text': text}
        getattr(self, attr).append(t)
        self._save_tasks(kind)
        return t

    def task_update(self, task_id, text, kind='numeric'):
        attr, _f, _d = self._task_conf(kind)
        for t in (getattr(self, attr, None) or []):
            if isinstance(t, dict) and t.get('id') == task_id:
                t['text'] = (text or '').strip()
                self._save_tasks(kind)
                return True
        return False

    def task_delete(self, task_id, kind='numeric'):
        attr, _f, _d = self._task_conf(kind)
        setattr(self, attr, [t for t in (getattr(self, attr, None) or [])
                             if not (isinstance(t, dict) and t.get('id') == task_id)])
        self._save_tasks(kind)

    def save_chat(self, mode, messages, chat_id=None, title=None):
        msgs = [{'role': (m.get('role') or 'user'), 'content': str(m.get('content') or '')}
                for m in (messages or [])
                if isinstance(m, dict) and str(m.get('content') or '').strip()]
        if not msgs:
            return None
        if not isinstance(getattr(self, 'chats', None), list):
            self.chats = []
        mode = 'quran' if mode == 'quran' else 'discoveries'
        if not title:
            title = ''
            for m in msgs:
                if m['role'] == 'user':
                    title = m['content'].strip().replace(chr(10), ' ')[:44]
                    break
            if not title:
                title = msgs[0]['content'].strip().replace(chr(10), ' ')[:44]
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        if chat_id:
            for c in self.chats:
                if isinstance(c, dict) and c.get('id') == chat_id:
                    c['mode'] = mode
                    c['title'] = title
                    c['date'] = now
                    c['messages'] = msgs
                    self.save_chats()
                    return chat_id
        cid = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.chats.insert(0, {'id': cid, 'mode': mode, 'title': title,
                              'date': now, 'messages': msgs})
        self.save_chats()
        return cid

    def rename_chat(self, chat_id, title):
        title = (title or '').strip()[:60]
        if not chat_id or not title:
            return
        for c in getattr(self, 'chats', []):
            if isinstance(c, dict) and c.get('id') == chat_id:
                c['title'] = title
                self.save_chats()
                return

    def delete_chat(self, chat_id):
        if not isinstance(getattr(self, 'chats', None), list):
            self.chats = []
            return
        self.chats = [c for c in self.chats
                      if not (isinstance(c, dict) and c.get('id') == chat_id)]
        self.save_chats()

    def search_chats(self, query, mode=None):
        chats = [c for c in getattr(self, 'chats', []) if isinstance(c, dict)]
        if mode:
            want = 'quran' if mode == 'quran' else 'discoveries'
            chats = [c for c in chats
                     if ('quran' if c.get('mode') == 'quran' else 'discoveries') == want]
        qn = _norm_search(query or '')
        if not qn:
            return [(c, '') for c in chats]
        tokens = [t for t in qn.split(' ') if t]
        out = []
        for c in chats:
            bodies = [str(m.get('content') or '') for m in (c.get('messages') or [])
                      if isinstance(m, dict)]
            hay = _norm_search(str(c.get('title') or '') + ' ' + ' '.join(bodies))
            if all(t in hay for t in tokens):
                out.append((c, _snippet_for(bodies, tokens)))
        return out

    def get_all_tags(self):
        # برچسب‌ها فقط از منابعِ صریح ساخته می‌شوند: پیش‌فرض‌ها + برچسب‌هایی که کاربر دستی ساخته.
        # پیش‌فرض‌هایی که کاربر حذف کرده (hidden_tags) نمایش داده نمی‌شوند.
        tags = set(TagsScreen.DEFAULT) | {'نامشخص'}
        tags.update(self.user_tags)
        hidden = set(getattr(self, 'hidden_tags', []) or [])
        tags = {t for t in tags if t == 'نامشخص' or t not in hidden}
        return sorted(tags)

    # ---------- عملیات کشف ----------
    def add_discovery(self, seed, target):
        entry = {
            'mode': normalize_mode(target.get('mode', '')),
            'seed_s': seed['s'], 'seed_a': seed['a'],
            'seed_arb': seed['arb'], 'seed_pers': seed['pers'],
            'target_s': target['s'], 'target_a': target['a'],
            'target_arb': target.get('arb', ''), 'target_pers': target.get('pers', ''),
            'note': '', 'relation_type': 'نامشخص',
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        # جلوگیری از تکرار
        for it in self.favs:
            if (it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a'),
                    it.get('mode')) == (entry['seed_s'], entry['seed_a'], entry['target_s'],
                                        entry['target_a'], entry['mode']):
                toast('این کشف قبلاً ثبت شده است.', 'تکرار')
                return
        entry.setdefault('note', '')
        self.favs.append(entry)
        self.save_favs()
        self.last_discovery_key = discovery_key(entry)
        self.last_discovery_section = lab_section_of(entry)
        open_note_editor(entry, 'lab', title='ثبت تحلیل کشف',
                         intro='کشف در لابراتوار ثبت شد. تحلیل خود را ثبت کنید:',
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)),
                         on_cancel=lambda: self._discard_discovery(entry),
                         saved_msg='کشف با موفقیت در لابراتوار ثبت شد ✓')

    def add_featured(self, item, screen=None):
        for it in self.featured:
            if (it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a')) == \
               (item.get('seed_s'), item.get('seed_a'), item.get('target_s'), item.get('target_a')):
                toast('این مورد در گلچین هست.', 'تکرار')
                return
        self.featured.append(dict(item))
        self.save_featured()
        toast('به گلچین اضافه شد. ', 'گلچین')

    def add_all_featured(self):
        existing = {(it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a'))
                    for it in self.featured}
        n = 0
        for it in self.favs:
            key = (it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a'))
            if key not in existing:
                self.featured.append(dict(it))
                existing.add(key)
                n += 1
        self.save_featured()
        return n

    # ---------- خروجیِ زیبای گلچین (Word / PDF / Excel) ----------
    def _build_featured_groups(self):
        """گلچین را بر اساسِ عملگرها گروه‌بندی می‌کند (ورودیِ export_util)."""
        import export_util
        op_names = dict(OPERATORS)

        def _ref(s, a):
            return 'سوره %s آیهٔ %s' % (export_util.fa_num(s), export_util.fa_num(a))

        grouped = {}
        for it in self.featured:
            k = op_of(it)
            rec = {
                'mode': it.get('mode', ''),
                'is_doubtful': bool(it.get('is_doubtful', False)),
                'relation_type': it.get('relation_type', 'نامشخص'),
                'note': it.get('note', ''),
                'date': it.get('date', ''),
                'seed_ref': _ref(it.get('seed_s'), it.get('seed_a')),
                'seed_arb': it.get('seed_arb', ''),
                'seed_pers': it.get('seed_pers', ''),
                'targets': [],
            }
            if 'all_targets' in it:
                for t in it.get('all_targets', []):
                    rec['targets'].append({
                        'ref': _ref(t.get('s'), t.get('a')),
                        'arb': t.get('arb', ''),
                        'pers': t.get('pers', ''),
                    })
            else:
                rec['targets'].append({
                    'ref': _ref(it.get('target_s'), it.get('target_a')),
                    'arb': it.get('target_arb', ''),
                    'pers': it.get('target_pers', ''),
                })
            grouped.setdefault(k, []).append(rec)
        groups = []
        for k, _t in OPERATORS:
            if k in grouped:
                groups.append({'op_title': op_names.get(k, k), 'records': grouped[k]})
        return groups

    def export_featured_doc(self, kind):
        """خروجیِ گلچین به سه قالب: kind = 'docx' | 'pdf' | 'xlsx'. مسیرِ فایل را برمی‌گرداند."""
        if not self.featured:
            return None
        try:
            import export_util
            groups = self._build_featured_groups()
            ext = {'docx': 'docx', 'pdf': 'pdf', 'xlsx': 'xlsx'}[kind]
            out = self._p('golchin_%s.%s' % (datetime.now().strftime('%Y%m%d_%H%M'), ext))
            return export_util.generate(kind, groups, out, font_path=asset('font.ttf'),
                                        title='گلچینِ آیاتِ آینه‌ای')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print('export error:', kind, e)
            return None

    # ---------- خروجی JSON تمیز (برای هر عملگر) ----------
    def _clean_by_operator(self, items):
        op_names = dict(OPERATORS)
        grouped = {}
        for it in items:
            k = op_of(it)
            entry = {
                'mode': it.get('mode', ''),
                'seed': {'sura': it.get('seed_s'), 'ayah': it.get('seed_a'),
                         'arabic': it.get('seed_arb', ''), 'translation': it.get('seed_pers', '')},
                'target': {'sura': it.get('target_s'), 'ayah': it.get('target_a'),
                           'arabic': it.get('target_arb', ''), 'translation': it.get('target_pers', '')},
                'relation_type': it.get('relation_type', 'نامشخص'),
                'is_doubtful': bool(it.get('is_doubtful', False)),
                'note': it.get('note', ''),
                'date': it.get('date', ''),
            }
            grouped.setdefault(k, {'operator': k, 'operator_name': op_names.get(k, k), 'items': []})
            grouped[k]['items'].append(entry)
        return [grouped[k] for k, _ in OPERATORS if k in grouped]

    def export_clean_json(self, filename, payload):
        out = self._p(filename)
        _atomic_write_json(out, payload, indent=2)
        return out

    def build_backup_json(self):
        if not self.favs and not self.featured:
            return None
        payload = {
            'app': 'قطب‌نمای قرآنی',
            'version': '3.0',
            'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'lab': self._clean_by_operator(self.favs),
            'featured': self._clean_by_operator(self.featured),
            'tags': self.get_all_tags(),
        }
        return self.export_clean_json('backup_%s.json' % datetime.now().strftime('%Y%m%d_%H%M'), payload)

    def build_backup_zip(self):
        """پشتیبانِ کاملِ سازگار با نسخهٔ ویندوز.
        یک فایل ZIP می‌سازد که شاملِ favorites.json / featured.json / user_tags.json
        (همان قالبِ خامِ داخلی) است؛ نسخهٔ ویندوز این ZIP را مستقیماً «بازیابی» می‌کند
        و خودِ اپ هم آن را کامل می‌خواند. یک نسخهٔ خوانا (backup_readable.json) هم صرفاً
        برای مطالعهٔ انسانی داخلِ ZIP گذاشته می‌شود و برای بازیابی لازم نیست."""
        if not self.favs and not self.featured:
            return None
        # ابتدا آخرین وضعیت را روی دیسک ذخیره کن تا ZIP دقیقاً به‌روز باشد
        self.save_favs()
        self.save_featured()
        self.save_user_tags()
        fname = 'QuranCompass_Backup_%s.zip' % datetime.now().strftime('%Y%m%d_%H%M%S')
        out = self._p(fname)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in ('favorites.json', 'featured.json', 'user_tags.json'):
                pth = self._p(name)
                if os.path.exists(pth):
                    z.write(pth, name)
            try:
                readable = {
                    'app': 'قطب‌نمای قرآنی',
                    'version': '3.0',
                    'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'lab': self._clean_by_operator(self.favs),
                    'featured': self._clean_by_operator(self.featured),
                    'tags': self.get_all_tags(),
                }
                z.writestr('backup_readable.json', json.dumps(readable, ensure_ascii=False, indent=2))
            except Exception:
                pass
        return out

    def export_featured_json(self):
        if not self.featured:
            return None
        payload = {
            'app': 'قطب‌نمای قرآنی',
            'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'featured': self._clean_by_operator(self.featured),
        }
        return self.export_clean_json('golchin_%s.json' % datetime.now().strftime('%Y%m%d_%H%M'), payload)

    def _discard_discovery(self, entry):
        """حذفِ کشفی که هنگامِ ثبت به‌طورِ موقت افزوده شده، وقتی کاربر «انصراف»
        می‌زند (تا دیگر الکی در لابراتوار نماند)."""
        try:
            for i, it in enumerate(self.favs):
                if it is entry:
                    del self.favs[i]
                    self.save_favs()
                    break
        except Exception:
            pass
        try:
            if getattr(self, 'last_discovery_key', None) == discovery_key(entry):
                self.last_discovery_key = None
        except Exception:
            pass

    # ---------- کشف گروهی و جفتی ----------
    def add_group_discovery(self, seed, targets, note='', relation_type='نامشخص', is_doubtful=False):
        """ثبت یک کشف گروهی با چند مقصد."""
        if not targets:
            toast('حداقل یک مقصد انتخاب کنید.', 'خطا')
            return
        entry = {
            'mode': 'گروهی',
            'seed_s': seed['s'], 'seed_a': seed['a'],
            'seed_arb': seed['arb'], 'seed_pers': seed['pers'],
            'all_targets': [{'s': t['s'], 'a': t['a'], 'arb': t.get('arb', ''),
                             'pers': t.get('pers', ''), 'operator': t.get('mode', '')}
                            for t in targets],
            'note': note, 'relation_type': relation_type, 'is_doubtful': bool(is_doubtful),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self.favs.append(entry)
        self.save_favs()
        self.last_discovery_key = discovery_key(entry)
        self.last_discovery_section = lab_section_of(entry)
        open_note_editor(entry, 'lab', title='ثبت تحلیل کشف گروهی',
                         intro='کشف گروهی با %d مقصد ثبت شد. تحلیل و وضعیت تردید را انتخاب کنید:' % len(targets),
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)),
                         on_cancel=lambda: self._discard_discovery(entry),
                         saved_msg='کشف گروهی با موفقیت ثبت شد ✓')

    def add_pair_discovery(self, seed, ta, tb, note='', relation_type='نامشخص', is_doubtful=False):
        """ثبت یک جفت عملگری (دو مقصد). کارت اول نوع عملگر را تعیین می‌کند."""
        op_key = op_of({'mode': ta.get('mode', '')})
        entry = {
            'mode': 'جفت عملگری', 'pair_type': 'operator_pair', 'op_key': op_key,
            'seed_s': seed['s'], 'seed_a': seed['a'],
            'seed_arb': seed['arb'], 'seed_pers': seed['pers'],
            'all_targets': [
                {'s': ta['s'], 'a': ta['a'], 'arb': ta.get('arb', ''), 'pers': ta.get('pers', ''), 'operator': ta.get('mode', '')},
                {'s': tb['s'], 'a': tb['a'], 'arb': tb.get('arb', ''), 'pers': tb.get('pers', ''), 'operator': tb.get('mode', '')},
            ],
            'note': note, 'relation_type': relation_type, 'is_doubtful': bool(is_doubtful),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self.favs.append(entry)
        self.save_favs()
        self.last_discovery_key = discovery_key(entry)
        self.last_discovery_section = lab_section_of(entry)
        open_note_editor(entry, 'lab', title='ثبت تحلیل جفت عملگری',
                         intro='جفت عملگری زیر بخش %s ثبت شد. تحلیل و وضعیت تردید را انتخاب کنید:' % op_key,
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)),
                         on_cancel=lambda: self._discard_discovery(entry),
                         saved_msg='جفت عملگری با موفقیت ثبت شد ✓')

    def remove_target_from_group(self, group_item, target_index):
        """حذف یک مقصد از یک کشف گروهی/جفتی."""
        found = None
        for f in self.favs:
            if (f.get('mode') == group_item.get('mode') and
                    f.get('seed_s') == group_item.get('seed_s') and
                    f.get('seed_a') == group_item.get('seed_a') and
                    f.get('seed_arb') == group_item.get('seed_arb') and
                    'all_targets' in f):
                found = f
                break
        if found is None:
            return False, 'کشف مورد نظر یافت نشد.'
        if 0 <= target_index < len(found['all_targets']):
            del found['all_targets'][target_index]
            if not found['all_targets']:
                self.favs.remove(found)
                self.save_favs()
                return True, 'آخرین مقصد حذف شد؛ کل کشف گروهی پاک شد.'
            self.save_favs()
            return True, 'مقصد از گروه حذف شد.'
        return False, 'ایندکس نامعتبر است.'

    # ---------- بازیابی ----------
    def restore_backup(self, payload):
        """بازیابی کشفیات و گلچین از محتوای JSON پشتیبان."""
        favs, featured = features.parse_backup(payload)
        self.favs = favs if isinstance(favs, list) else []
        self.featured = featured if isinstance(featured, list) else []
        for _it in self.favs:
            _normalize_item_modes(_it)
        for _it in self.featured:
            _normalize_item_modes(_it)
        self.save_favs()
        self.save_featured()
        return len(favs), len(featured)

    # ---------- بارگذاری از فایل JSON ----------
    def read_text_file(self, path):
        with open(path, encoding='utf-8') as f:
            return f.read()

    def _extract_items(self, payload, target):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if 'lab' in payload or 'featured' in payload:
                favs, featured = features.parse_backup(payload)
                return favs if target == 'lab' else featured
            if target == 'lab' and 'favs' in payload:
                return payload.get('favs') or []
            if 'featured' in payload:
                return payload.get('featured') or []
        return []

    def _parse_json_tolerant(self, text):
        """پارس بردبار JSON: در برابر «Extra data»، دادهٔ تکراری/اضافه،
        BOM و JSON خط‌به‌خط مقاوم است. (payload, error) برمی‌گردند."""
        import json as _json
        s = (text or '')
        # حذف BOM و نویسه‌های نامرئی ابتدا/انتها
        s = s.replace('\ufeff', '').replace('\u200b', '').strip()
        if not s:
            return None, 'متن خالی است.'
        # ۱) حالت عادی
        try:
            return _json.loads(s), None
        except Exception:
            pass
        # ۲) پارس مقادیر پشت‌سرهم و نادیده‌گرفتن دادهٔ اضافهٔ انتها
        dec = _json.JSONDecoder()
        collected = []
        idx, n = 0, len(s)
        while idx < n:
            while idx < n and s[idx] in ' \t\r\n,;\ufeff':
                idx += 1
            if idx >= n:
                break
            try:
                val, end = dec.raw_decode(s, idx)
            except Exception:
                break
            collected.append(val)
            if end <= idx:
                break
            idx = end
        if collected:
            if len(collected) == 1:
                return collected[0], None
            merged = []
            only_lists = True
            for v in collected:
                if isinstance(v, list):
                    merged.extend(v)
                else:
                    only_lists = False
            if only_lists:
                return merged, None
            return collected[0], None
        # ۳) JSON خط‌به‌خط
        out = []
        for line in s.splitlines():
            line = line.strip().rstrip(',')
            if not line or line in ('[', ']', '{', '}'):
                continue
            try:
                out.append(_json.loads(line))
            except Exception:
                pass
        if out:
            return out, None
        return None, 'قالب JSON قابل خواندن نبود.'

    def _import_item_list(self, items, target='lab', mode='merge'):
        """هستهٔ واردکردنِ فهرستِ کشف‌ها به لابراتوار یا گلچین (با حذفِ تکراری‌ها)."""
        if not isinstance(items, list):
            return (0, 0, 'ساختار فایل قابل‌شناسایی نیست.')
        dest = [] if mode == 'replace' else (self.favs if target == 'lab' else self.featured)
        existing = set()
        for it in dest:
            try:
                existing.add(discovery_key(it))
            except Exception:
                pass
        added = 0
        for it in items:
            if not isinstance(it, dict) or not it.get('seed_s'):
                continue
            it.setdefault('note', '')
            it.setdefault('relation_type', 'نامشخص')
            it.setdefault('is_doubtful', False)
            _normalize_item_modes(it)
            try:
                k = discovery_key(it)
            except Exception:
                k = None
            if k is not None and k in existing:
                continue
            dest.append(it)
            if k is not None:
                existing.add(k)
            added += 1
        if target == 'lab':
            self.favs = dest
            self.save_favs()
        else:
            self.featured = dest
            self.save_featured()
        return (added, len(dest), '')

    def import_items_json(self, text, target='lab', mode='merge'):
        payload, perr = self._parse_json_tolerant(text)
        if perr:
            return (0, 0, 'JSON نامعتبر: %s' % perr)
        items = self._extract_items(payload, target)
        return self._import_item_list(items, target, mode)

    def _merge_user_tags(self, raw_or_list):
        """برچسب‌های شخصی را از یک فهرست/متنِ JSON با برچسب‌های فعلی ادغام می‌کند.
        برچسب‌های پیش‌فرض، «نامشخص» و برچسب‌های ترکیبی (چنداتیکتی) اضافه نمی‌شوند."""
        try:
            tags = raw_or_list
            if isinstance(raw_or_list, str):
                tags = json.loads(raw_or_list)
            if not isinstance(tags, list):
                return
            sep = chr(1548)
            changed = False
            for t in tags:
                if not isinstance(t, str):
                    continue
                t = t.strip()
                if not t or t == 'نامشخص' or t in TagsScreen.DEFAULT or sep in t:
                    continue
                if t not in self.user_tags:
                    self.user_tags.append(t)
                    changed = True
            if changed:
                self.save_user_tags()
        except Exception:
            pass

    def import_from_path(self, path, target='lab', mode='merge'):
        """بارگذاریِ قدرتمند و بی‌خطا از:
          • فایلِ ZIP پشتیبان (نسخهٔ ویندوز یا خودِ اپ): favorites.json + featured.json + user_tags.json
          • فایلِ JSON کاملِ خروجیِ اپ (شاملِ lab/featured/tags) ← هر دو بخش و برچسب‌ها بازیابی می‌شوند
          • فایلِ JSON خام یا تک‌بخشی ← به مقصدِ انتخاب‌شده وارد می‌شود
        هرگز کرش نمی‌کند؛ خروجی: (added, total, err)."""
        import os as _os
        import zipfile as _zip
        try:
            if not path or not _os.path.exists(path):
                return (0, 0, 'فایل یافت نشد.')
            with open(path, 'rb') as _f:
                head = _f.read(4)
            # ---------- فایلِ ZIP ----------
            if head[:2] == b'PK':
                try:
                    with _zip.ZipFile(path) as z:
                        names = z.namelist()

                        def _member(basename):
                            for nm in names:
                                if nm.split('/')[-1].lower() == basename:
                                    return z.read(nm).decode('utf-8-sig', 'replace')
                            return None
                        favs_raw = _member('favorites.json')
                        feat_raw = _member('featured.json')
                        tags_raw = _member('user_tags.json')
                        readable = _member('backup_readable.json')
                except Exception as e:
                    return (0, 0, 'خواندن فایل ZIP ممکن نشد: %s' % str(e)[:80])
                # اگر فقط نسخهٔ خوانا داخلِ ZIP بود
                if favs_raw is None and feat_raw is None and readable is not None:
                    return self._restore_full_text(readable, mode, target)
                if favs_raw is None and feat_raw is None:
                    return (0, 0, 'داخلِ فایل ZIP، favorites.json یا featured.json پیدا نشد.')
                total_added = 0
                grand_total = 0
                if favs_raw is not None:
                    a, t, err = self.import_items_json(favs_raw, 'lab', mode)
                    if err:
                        return (0, 0, err)
                    total_added += a
                    grand_total += t
                if feat_raw is not None:
                    a, t, err = self.import_items_json(feat_raw, 'featured', mode)
                    if err:
                        return (0, 0, err)
                    total_added += a
                    grand_total += t
                if tags_raw is not None:
                    self._merge_user_tags(tags_raw)
                return (total_added, grand_total, '')
            # ---------- فایلِ متنیِ JSON ----------
            try:
                with open(path, encoding='utf-8-sig', errors='replace') as _f:
                    raw = _f.read()
            except Exception as e:
                return (0, 0, 'خواندن فایل ممکن نشد: %s' % str(e)[:80])
            return self._restore_full_text(raw, mode, target)
        except Exception as e:
            return (0, 0, 'خطا در بارگذاری: %s' % str(e)[:80])

    def _restore_full_text(self, raw, mode='merge', target='lab'):
        """اگر متن یک «پشتیبانِ کامل» باشد (شاملِ lab/featured)، هر دو بخش و برچسب‌ها را بازیابی می‌کند؛
        در غیرِ این‌صورت به‌صورتِ تک‌بخشی به مقصدِ انتخاب‌شده وارد می‌کند."""
        payload, perr = self._parse_json_tolerant(raw)
        if perr:
            return (0, 0, 'JSON نامعتبر: %s' % perr)
        if isinstance(payload, dict) and ('lab' in payload or 'featured' in payload):
            favs, featured = features.parse_backup(payload)
            fa, ft, err = self._import_item_list(favs, 'lab', mode)
            if err:
                return (0, 0, err)
            xa, xt, err = self._import_item_list(featured, 'featured', mode)
            if err:
                return (0, 0, err)
            tags = payload.get('tags')
            if isinstance(tags, list):
                self._merge_user_tags(tags)
            return (fa + xa, ft + xt, '')
        # تک‌بخشی (فهرستِ خام یا فایلِ favorites/featured تنها)
        return self.import_items_json(raw, target, mode)

    # ---------- پشتیبان ----------
    def make_backup(self, dest_dir=None):
        fname = 'backup_%s.zip' % datetime.now().strftime('%Y%m%d_%H%M')
        if dest_dir:
            out = os.path.join(dest_dir, fname)
        else:
            out = self._p(fname)
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in ('favorites.json', 'featured.json', 'user_tags.json'):
                pth = self._p(name)
                if os.path.exists(pth):
                    z.write(pth, name)
        return out


if __name__ == '__main__':
    QuranMirrorApp().run()
