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
from datetime import datetime

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
from rtl import rtl, rtl_multiline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# اگر پوشهٔ assets وجود داشته باشد از آن استفاده می‌کنیم؛ وگرنه فایل‌ها را از همین پوشهٔ اصلی می‌خوانیم
# (روی گیت‌هاب فایل‌ها در ریشه هستند، روی ویندوز داخل assets)
ASSET_DIR = os.path.join(BASE_DIR, 'assets')
if not os.path.isdir(ASSET_DIR):
    ASSET_DIR = BASE_DIR


def asset(name):
    return os.path.join(ASSET_DIR, name)


# ---- ثبت فونت‌ها ----
LabelBase.register(name='arabic', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))
LabelBase.register(name='ui', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))
# فونت پیش‌فرض kivy (Roboto) را هم به font.ttf تغییر می‌دهیم تا
# همهٔ ویجت‌ها (منوی کشویی Spinner، عنوان Popup، دکمه‌های ساده، فایل‌یاب) فارسی را درست نشان دهند.
LabelBase.register(name='Roboto', fn_regular=asset('font.ttf'), fn_bold=asset('font.ttf'))

# ---- پالت رنگ ----
C_BG = (0.05, 0.08, 0.14, 1)
C_PANEL = (1, 1, 1, 0.10)
C_PANEL_SOLID = (0.10, 0.14, 0.22, 1)
# نسخه و نشانهٔ بیلد (روی صفحهٔ خانه نشان داده می‌شود) — هر بار کد را عوض کردی این را هم بالا ببر
BUILD_VERSION = '3.2'
BUILD_TAG = '2026-07-17'

C_GOLD = (0.95, 0.77, 0.36, 1)
C_BLUE = (0.15, 0.55, 0.92, 1)
C_PURPLE = (0.61, 0.28, 0.80, 1)
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
    """جعبهٔ گوشه‌گرد با پس‌زمینه."""
    def __init__(self, bg=C_PANEL_SOLID, radius=18, border=None, **kw):
        super().__init__(**kw)
        self._bg = bg
        self._radius = radius
        self._border = border
        with self.canvas.before:
            if border:
                self._bcol = Color(*border)
                self._brect = RoundedRectangle(radius=[radius])
            self._col = Color(*bg)
            self._rect = RoundedRectangle(radius=[radius])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        if self._border:
            self._brect.pos = (self.x - dp(1.5), self.y - dp(1.5))
            self._brect.size = (self.width + dp(3), self.height + dp(3))

    def set_bg(self, color):
        self._col.rgba = color


class ClickCard(ButtonBehavior, RoundBox):
    """کارت شیشه‌ایِ کلیک‌پذیر (برای ردیف‌های فهرست نتایج)."""
    pass


class PillButton(Button):
    """دکمهٔ گوشه‌گرد رنگی با انیمیشن فشردن."""
    def __init__(self, text='', bg=C_BLUE, fg=(1, 1, 1, 1), radius=14, font_size='16sp', **kw):
        super().__init__(**kw)
        self.background_normal = ''
        self.background_color = (0, 0, 0, 0)
        self.font_name = 'ui'
        self.color = fg
        self.font_size = font_size
        self.text = P(text)
        self._bg = list(bg)
        self._radius = radius
        with self.canvas.before:
            self._col = Color(*self._bg)
            self._rect = RoundedRectangle(radius=[radius])
        self.bind(pos=self._upd, size=self._upd, state=self._state)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _state(self, *a):
        if self.state == 'down':
            self._col.rgba = [min(1, c * 1.25) for c in self._bg[:3]] + [self._bg[3]]
        else:
            self._col.rgba = self._bg

    def set_text(self, text):
        self.text = P(text)


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
    """رفع مشکل کیبورد اندروید: با یک بار لمس، فوکوس و کیبورد پایدار می‌ماند
    (به‌جای اینکه کیبورد بالا بیاید و بلافاصله بسته شود)."""
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            super().on_touch_down(touch)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        was = (touch.grab_current is self)
        res = super().on_touch_up(touch)
        if was or self.collide_point(*touch.pos):
            def _refocus(dt):
                if not self.focus:
                    self.focus = True
            Clock.schedule_once(_refocus, 0.05)
        return res


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

    def _render(self):
        self._guard = True
        try:
            self.text = rtl(self._logical) if self._logical else ''
            self.cursor = (len(self.text), 0)
        finally:
            self._guard = False
        if self.on_change:
            self.on_change(self._logical)

    def insert_text(self, substring, from_undo=False):
        if self._guard or from_undo:
            return super().insert_text(substring, from_undo=from_undo)
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


class SeedInput(_KbFocusMixin, TextInput):
    """ورودی عددی بذر که با یک تاچ ساده فوکوس می‌گیرد و کیبورد را بالا می‌آورد
    (رفع مشکل بالا نیامدنِ کیبورد داخل ScrollView)."""
    pass


def toast(message, title='پیام'):
    content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
    content.add_widget(RLabel(message, font_size='16sp', halign='center'))
    p = Popup(title=P(title), content=content, size_hint=(0.85, 0.4),
              title_font='ui', title_align='center', separator_color=C_GOLD)
    btn = PillButton('باشه', bg=C_BLUE, size_hint_y=None, height=dp(46))
    btn.bind(on_release=p.dismiss)
    content.add_widget(btn)
    p.open()
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


# ==================================================================
# صفحهٔ پایه (پس‌زمینه + هدر)
# ==================================================================
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
            back = PillButton('بازگشت', bg=(1, 1, 1, 0.14), size_hint_x=None, width=dp(110),
                              font_size='14sp')
            back.bind(on_release=self.go_back)
            header.add_widget(back)
        else:
            header.add_widget(Widget(size_hint_x=None, width=dp(4)))
        self.title_label = RLabel(title, font_name='ui', bold=True, font_size='19sp',
                                  halign='center', color=C_GOLD)
        header.add_widget(self.title_label)
        header.add_widget(Widget(size_hint_x=None, width=dp(110) if show_back else dp(4)))
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
            self.header.height = dp(74)
            self.title_label.font_name = 'arabic'
            self.title_label.color = C_GOLD
            self.title_label.font_size = '16sp'
            self.title_label.set_text('به نام الله برای الله')
            _va = (Animation(opacity=0.45, duration=1.8) + Animation(opacity=1, duration=1.8))
            _va.repeat = True
            _va.start(self.title_label)
        except Exception:
            pass

        title = RLabel('قطب‌نمای قرآنی', bold=True, font_size='30sp', halign='center',
                       color=C_TEXT, size_hint_y=None, height=dp(46))
        subtitle = RLabel('پردازش آینه‌ای (هولوگرافیک)', font_size='15sp', halign='center',
                          color=C_MUTED, size_hint_y=None, height=dp(28))
        content.add_widget(title)
        content.add_widget(subtitle)
        # نشانهٔ نسخه/بیلد — برای اطمینان از اینکه دقیقاً همین کد روی گوشی اجرا می‌شود
        build_tag = RLabel('« إِنَّا نَحْنُ نَزَّلْنَا الذِّکْرَ وَإِنَّا لَهُ لَحَافِظُونَ »',
                           arabic=True, font_size='12sp', halign='center', color=C_GOLD,
                           size_hint_y=None, height=dp(24))
        content.add_widget(build_tag)

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
        _neon_border(vbtn, C_BLUE, width=1.4, alpha=0.9)
        vbtn_all = PillButton('نمایش لیست جستجو', bg=(1, 1, 1, 0.10), fg=C_TEXT)
        vbtn_all.bind(on_release=lambda *a: self.show_all_results())
        _neon_border(vbtn_all, C_GOLD, width=1.4, alpha=0.9)
        vbtnrow.add_widget(vbtn)
        vbtnrow.add_widget(vbtn_all)
        vsbox.add_widget(vbtnrow)
        content.add_widget(vsbox)
        _neon_border(vsbox, C_BLUE)

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
        apply_glow(self.verse_box, C_GOLD)

        # پنل ورودی بذر
        seedbox = RoundBox(bg=(1, 1, 1, 0.09), orientation='vertical', size_hint_y=None,
                           height=dp(230), padding=dp(14), spacing=dp(10))
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
        b_sem = PillButton('پیش‌بینی (معنا)', bg=C_PURPLE, fg=HOME_FG)
        b_sem.bind(on_release=lambda *a: self.run('semantic'))
        b_num = PillButton('پیش‌بینی (اعداد)', bg=C_BLUE, fg=HOME_FG)
        b_num.bind(on_release=lambda *a: self.run('numeric'))
        prow.add_widget(b_sem)
        prow.add_widget(b_num)
        seedbox.add_widget(prow)
        content.add_widget(seedbox)
        apply_glow(seedbox, C_GOLD)

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
            _neon_border(b, color, width=1.6, alpha=0.85)
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
        res = app.data.find_by_text(q)
        if not res:
            self.verse_meta.set_text('')
            self.verse_meta.height = dp(0)
            self.verse.color = C_RED
            self.verse.set_text('آیه‌ای مطابق این متن یافت نشد')
            toast('آیه‌ای با این متن پیدا نشد؛ دکمهٔ «نمایش همه» را امتحان کنید.', 'یافت نشد')
            return
        s, a = res
        self._show_verse_result(s, a)

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
        results = app.data.search_all(q, limit=2000)
        if not results:
            toast('هیچ آیه‌ای برای این عبارت پیدا نشد.', 'یافت نشد')
            return

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
                             size_hint_y=None, height=dp(124), padding=dp(8), spacing=dp(2))
            card.add_widget(RLabel('سوره %s ، آیه %s' % (s, a), font_size='12sp',
                                   halign='right', color=C_ORANGE, size_hint_y=None, height=dp(20)))
            card.add_widget(RLabel(arb_s, arabic=True, font_size='15sp', halign='right',
                                   color=C_TEXT, size_hint_y=None, height=dp(46)))
            card.add_widget(RLabel(pers_s, font_size='13sp', halign='right',
                                   color=C_MUTED, size_hint_y=None, height=dp(36)))
            card.bind(on_release=lambda inst, ss=s, aa=a: self._pick_result(ss, aa, popup))
            return card

        def _load_batch(*a):
            start = state['shown']
            for r in results[start:start + BATCH]:
                grid.add_widget(_make_row(r))
            state['shown'] = min(len(results), start + BATCH)
            header.set_text('%s — %d از %d' % (head_txt, state['shown'], len(results)))
            state['loading'] = False

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


def apply_glow(widget, color=None, speed=1.4):
    """نور افکتی نرم که دور یک کارت می‌تپد/می‌چرخد."""
    from kivy.graphics import Color as _Color, Line as _Line
    col = color or C_GOLD
    with widget.canvas.after:
        gc = _Color(col[0], col[1], col[2], 0.14)
        gl = _Line(width=1.6)

    def _upd(*a):
        try:
            gl.rounded_rectangle = (widget.x + dp(1), widget.y + dp(1),
                                    widget.width - dp(2), widget.height - dp(2), dp(14))
        except Exception:
            pass
    widget.bind(pos=_upd, size=_upd)
    Clock.schedule_once(_upd, 0)
    anim = Animation(a=0.85, duration=speed) + Animation(a=0.12, duration=speed)
    anim.repeat = True
    anim.start(gc)
    _register_glow(anim, gc, widget)
    return gl


def verse_card(mode, s, a, arb, pers, is_seed=False, is_fallback=False, reason='',
               on_save=None, score_text='', on_select=None, selected=False):
    bg = (0.16, 0.13, 0.05, 1) if is_seed else ((0.22, 0.08, 0.08, 1) if is_fallback else (0.10, 0.14, 0.22, 1))
    border = C_GOLD if is_seed else (C_RED if is_fallback else None)
    card = RoundBox(bg=bg, border=border, orientation='vertical', size_hint_y=None,
                    padding=dp(12), spacing=dp(6))
    head = RLabel(f'{mode}   سوره {s} ، آیه {a}', bold=True, font_size='15sp',
                  color=(C_GOLD if is_seed else C_ORANGE), halign='right', size_hint_y=None)
    head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
    card.add_widget(head)
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
        _prune_glows()   # لغو انیمیشن‌های کارت‌����ای حذف‌شده تا ترد UI آزاد بماند
        self._update_reg_bar()
        if not self._cards:
            self.list.add_widget(RLabel('داده‌ای برای این بذر یافت نشد.', font_size='15sp',
                                        halign='center', color=C_MUTED, size_hint_y=None, height=dp(60)))
            return
        self._seed_card = self._cards[0]
        self.list.add_widget(self._make_card(0, is_seed=True))
        for i in range(1, len(self._cards)):
            if self._cards[i].get('kind') != 'target':
                continue
            if i in self._hidden:
                continue
            self.list.add_widget(self._make_card(i, is_seed=False))

    def _make_card(self, idx, is_seed=False):
        c = self._resolved(idx)
        is_fb = c.get('is_fallback', False)
        bg = (0.16, 0.13, 0.05, 1) if is_seed else ((0.22, 0.08, 0.08, 1) if is_fb else (0.10, 0.14, 0.22, 1))
        border = C_GOLD if is_seed else (C_RED if is_fb else None)
        card = RoundBox(bg=bg, border=border, orientation='vertical', size_hint_y=None,
                        padding=dp(12), spacing=dp(6))

        # ردیف بالای کارت: نشان عملگر (چپ) + ضربدر حذف (راست)
        toprow = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(6))
        if is_seed:
            badge = _neon_badge('بذر', C_GOLD, size=(dp(48), dp(26)))
        elif self.mode == 'rotation':
            _rot = (c.get('mode', '').split('←')[0].split('(')[0].strip() or 'چرخش')
            badge = _neon_badge(_rot, C_PURPLE, size=(dp(104), dp(26)))
        else:
            badge = _neon_badge(op_of({'mode': c.get('mode', '')}), C_BLUE, size=(dp(42), dp(26)))
        toprow.add_widget(badge)
        toprow.add_widget(Widget())
        if not is_seed:
            xb = PillButton('حذف موقت', bg=C_RED, fg=(1, 1, 1, 1), size_hint_x=None, width=dp(100), font_size='12sp')
            xb.bind(on_release=lambda *a, i=idx: self._hide_card(i))
            toprow.add_widget(xb)
        card.add_widget(toprow)

        head = RLabel('%s   سوره %s ، آیه %s' % (c.get('mode', ''), c['s'], c['a']), bold=True,
                      font_size='15sp', color=(C_GOLD if is_seed else C_ORANGE), halign='right', size_hint_y=None)
        head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(head)
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

        # نور دور کارت
        gcol = C_GOLD if is_seed else (C_GREEN if (self.mode != 'rotation' and self._select_mode == 'group')
                                       else (C_RED if is_fb else C_BLUE))
        apply_glow(card, gcol)

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
                self.list.add_widget(RLabel('هیچ مقصد معتبری با الگوریتم عددی یافت نشد.',
                                            font_size='15sp', halign='center', color=C_MUTED,
                                            size_hint_y=None, height=dp(60)))
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


def _verse_block(border, s, a, arb, pers):
    c = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=border, orientation='vertical',
                 size_hint_y=None, padding=dp(10), spacing=dp(4))
    c.add_widget(_auto_label('سوره %s ، آیه %s' % (s, a), font_size='12sp', color=C_MUTED, halign='right'))
    c.add_widget(_auto_label('« %s »' % (arb or ''), arabic=True, font_size='18sp', color=C_TEXT, halign='center'))
    c.add_widget(_auto_label('ترجمه: ' + (pers or ''), font_size='13sp', color=C_MUTED, halign='right'))
    c.bind(minimum_height=lambda i, v: setattr(c, 'height', v + dp(24)))
    return c


def generate_default_analysis(e):
    """متن تحلیل پیش‌فرض برای یک کشف تولید می‌کند."""
    seed_txt = e.get('seed_pers', '') or e.get('seed_arb', '')
    tgt_txt = e.get('target_pers', '') or e.get('target_arb', '')
    return (
        'گره: %s\n'
        'مبدأ → سوره %s ، آیه %s\n%s\n'
        'مقصد → سوره %s ، آیه %s\n%s\n'
        'برداشت اولیه: ارتباط معنایی/عددی میان این دو آیه قابل بررسی است؛ لطفاً تحلیل خود را کامل کنید.'
        % (e.get('mode', ''), e.get('seed_s'), e.get('seed_a'), seed_txt,
           e.get('target_s'), e.get('target_a'), tgt_txt))


def open_note_editor(item, source='lab', title='ویرایش تحلیل', intro=None, on_saved=None):
    """پنجرهٔ ثبت/ویرایش تحلیل یک کشف (با برچسب و وضعیت تردید)."""
    app = App.get_running_app()
    content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
    if intro:
        content.add_widget(RLabel(intro, font_size='14sp', color=C_GOLD, halign='center',
                                  size_hint_y=None, height=dp(50)))
    content.add_widget(RLabel('تحلیل شما:', font_size='15sp', size_hint_y=None, height=dp(26)))
    # فیلد متن انعطاف‌پذیر — با بازشدنِ کیبورد خودرا جمع می‌کند تا دکمه‌ها (وضعیت/ذخیره) از کادر بیرون نزنند
    ti = PersianTextInput(multiline=True, font_size='15sp',
                          size_hint_y=1, background_color=(1, 1, 1, 0.95),
                          foreground_color=(0.05, 0.08, 0.14, 1))
    ti.set_logical(item.get('note', ''))
    content.add_widget(ti)
    tags = list(app.get_all_tags())
    _cur_tag = item.get('relation_type') or 'نامشخص'
    if _cur_tag not in tags:
        tags = tags + [_cur_tag]
    tag_state = {'tag': _cur_tag}
    content.add_widget(RLabel('برچسب تحلیلی (رفتار شبکه) — یکی را انتخاب کنید:', font_size='14sp',
                              color=C_GOLD, size_hint_y=None, height=dp(26)))
    _chip_sv = ScrollView(size_hint_y=None, height=dp(116), bar_width=dp(4))
    _chip_grid = GridLayout(cols=2, size_hint_y=None, spacing=dp(6), padding=(dp(2), dp(2)))
    _chip_grid.bind(minimum_height=_chip_grid.setter('height'))
    _chip_sv.add_widget(_chip_grid)
    _chip_btns = {}

    def _sel_tag(t):
        tag_state['tag'] = t
        for _tt, _b in _chip_btns.items():
            _sel = (_tt == t)
            _b._bg = list(C_GOLD if _sel else (1, 1, 1, 0.10))
            _b.color = (0.05, 0.08, 0.14, 1) if _sel else HOME_FG
            _b._state()
    for _t in tags:
        _cb = PillButton(_t, bg=(1, 1, 1, 0.10), fg=HOME_FG, size_hint_y=None,
                         height=dp(42), font_size='13sp', radius=14)
        _cb.bind(on_release=lambda _inst, _tt=_t: _sel_tag(_tt))
        _chip_btns[_t] = _cb
        _chip_grid.add_widget(_cb)
    content.add_widget(_chip_sv)
    _sel_tag(tag_state['tag'])
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
    ep = Popup(title=P(title), content=content, size_hint=(0.94, 0.75),
               title_font='ui', title_align='center', separator_color=C_GOLD)
    row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
    sv = PillButton('ذخیره', bg=C_GREEN)
    def _sv(*a):
        item['note'] = ti.query
        item['relation_type'] = tag_state['tag']
        item['is_doubtful'] = state['d']
        if source == 'lab':
            app.save_favs()
        else:
            app.save_featured()
        ep.dismiss()
        if on_saved:
            on_saved()
    sv.bind(on_release=_sv)
    cn = PillButton('انصراف', bg=C_RED)
    cn.bind(on_release=ep.dismiss)
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
        content.add_widget(RLabel('تحلیل شما:', font_size='15sp', size_hint_y=None, height=dp(26)))
        ti = PersianTextInput(multiline=True, font_size='15sp',
                              size_hint_y=1, background_color=(1, 1, 1, 0.95),
                              foreground_color=(0.05, 0.08, 0.14, 1))
        ti.set_logical(item.get('note', ''))
        content.add_widget(ti)
        tags = app.get_all_tags()
        content.add_widget(RLabel('برچسب (رفتار شبکه):', font_size='15sp', size_hint_y=None, height=dp(26)))
        sp = Spinner(text=P(item.get('relation_type', 'نامشخص')), values=[P(t) for t in tags],
                     font_name='ui', size_hint_y=None, height=dp(44))
        content.add_widget(sp)
        tag_map = {P(t): t for t in tags}
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
        ep = Popup(title=P('ویرایش تحلیل'), content=content, size_hint=(0.92, 0.72),
                   title_font='ui', title_align='center', separator_color=C_GOLD)
        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
        sv = PillButton('ذخیره', bg=C_GREEN)

        def _sv(*a):
            item['note'] = ti.query
            item['relation_type'] = tag_map.get(sp.text, 'نامشخص')
            item['is_doubtful'] = _st['d']
            if source == 'lab':
                app.save_favs()
            else:
                app.save_featured()
            ep.dismiss()
            p.dismiss()
            _refresh_parent()
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
    close = PillButton('بستن', bg=(1, 1, 1, 0.14), size_hint_y=None, height=dp(46))
    close.bind(on_release=p.dismiss)
    root.add_widget(close)
    p.open()


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
            self.grid.add_widget(RLabel('هنوز کشفی ثبت نشده است. از صفحهٔ پردازش، کشف ثبت کنید.',
                                        font_size='15sp', halign='center', color=C_MUTED,
                                        size_hint_y=None, height=dp(80)))
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
                apply_glow(b, C_GREEN, speed=0.6)

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
        items = app.favs if self.source == 'lab' else app.featured
        key_fn = lab_section_of if self.source == 'lab' else op_of
        matched = [it for it in items if key_fn(it) == self.op_key]
        if not matched:
            self.list.add_widget(RLabel('کشفی در این بخش نیست.', font_size='15sp',
                                        halign='center', color=C_MUTED, size_hint_y=None, height=dp(70)))
            return
        last_key = getattr(app, 'last_discovery_key', None)
        for it in matched:
            card = self._group_card(it) if 'all_targets' in it else self._card(it)
            self.list.add_widget(card)
            if last_key is not None and discovery_key(it) == last_key:
                apply_glow(card, C_GREEN, speed=0.6)

    def _card(self, item):
        border = C_GOLD if self.source == 'featured' else C_BLUE
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=border, orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(4))
        pair = RLabel('سوره %s:%s     سوره %s:%s' % (item.get('seed_s'), item.get('seed_a'),
                      item.get('target_s'), item.get('target_a')),
                      font_size='13sp', color=C_MUTED, halign='center', size_hint_y=None)
        pair.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(pair)
        a2 = RLabel('« %s »' % (item.get('target_arb', '')), arabic=True, font_size='16sp',
                    halign='center', color=C_TEXT, size_hint_y=None)
        a2.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(a2)
        extra = '  (تردیدی)' if item.get('is_doubtful') else ''
        rel = RLabel('رفتار: %s%s' % (item.get('relation_type', 'نامشخص'), extra), font_size='12sp',
                     color=C_ORANGE, halign='right', size_hint_y=None)
        rel.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(rel)
        btn = PillButton('مشاهده و ویرایش', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        btn.bind(on_release=lambda *a, it=item: show_discovery(it, self.source, self))
        card.add_widget(btn)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v + dp(20)))
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
        a1 = RLabel('« %s »' % item.get('seed_arb', ''), arabic=True, font_size='15sp',
                    halign='center', color=C_TEXT, size_hint_y=None)
        a1.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(a1)
        extra = '  (تردیدی)' if item.get('is_doubtful') else ''
        rel = RLabel('رفتار: %s%s' % (item.get('relation_type', 'نامشخص'), extra), font_size='12sp',
                     color=C_ORANGE, halign='right', size_hint_y=None)
        rel.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(rel)
        btn = PillButton('مشاهده و ویرایش', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        btn.bind(on_release=lambda *a, it=item: show_discovery(it, self.source, self))
        card.add_widget(btn)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v + dp(20)))
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
        b_word = PillButton('اشتراک‌گذاری فایل JSON', bg=C_BLUE, font_size='13sp')
        b_word.bind(on_release=lambda *a: self.share_json())
        b_save = PillButton('ذخیره در گوشی', bg=C_GOLD, fg=(0.05, 0.08, 0.14, 1), font_size='13sp')
        b_save.bind(on_release=lambda *a: self.save_json_device())
        b_clear = PillButton('پاک کردن کل', bg=C_RED, font_size='13sp')
        b_clear.bind(on_release=lambda *a: self.clear_all())
        top.add_widget(b_word)
        top.add_widget(b_save)
        top.add_widget(b_clear)
        self.body(top)
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
            self.grid.add_widget(RLabel('گلچین خالی است.', font_size='15sp', halign='center',
                                        color=C_MUTED, size_hint_y=None, height=dp(60)))
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


# ==================================================================
# جستجو
# ==================================================================
class SearchScreen(BaseScreen):
    def __init__(self, **kw):
        super().__init__(title='جستجو در کشفیات', **kw)
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.q = PersianTextInput(hint_text=P('جستجو در لابراتوار و گلچین...'), font_size='15sp',
                                  background_color=(1, 1, 1, 0.95), foreground_color=(0.05, 0.08, 0.14, 1),
                                  padding=[dp(8), dp(14)])
        self.q.bind(on_text_validate=lambda *a: self.do_search())
        b = PillButton('جستجو', bg=C_BLUE, size_hint_x=None, width=dp(96), font_size='14sp')
        b.bind(on_release=lambda *a: self.do_search())
        top.add_widget(self.q)
        top.add_widget(b)
        self.body(top)
        self.info = RLabel('', font_size='13sp', halign='center', color=C_MUTED,
                           size_hint_y=None, height=dp(24))
        self.body(self.info)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8), padding=dp(4))
        self.list.bind(minimum_height=self.list.setter('height'))
        self.scroll.add_widget(self.list)
        self.body(self.scroll)

    def refresh(self):
        self.list.clear_widgets()
        self.info.set_text('متن را وارد کنید و دکمهٔ جستجو را بزنید.')

    def _haystack(self, it):
        parts = [it.get('seed_arb', ''), it.get('target_arb', ''), it.get('seed_pers', ''),
                 it.get('target_pers', ''), it.get('mode', ''), it.get('relation_type', ''),
                 it.get('note', ''),
                 'سوره %s:%s' % (it.get('seed_s'), it.get('seed_a')),
                 'سوره %s:%s' % (it.get('target_s'), it.get('target_a'))]
        return core.strip_harakat(' '.join(str(x) for x in parts))

    def do_search(self):
        app = App.get_running_app()
        term = core.strip_harakat(self.q.query.strip())
        self.list.clear_widgets()
        if len(term) < 2:
            self.info.set_text('حداقل ۲ حرف وارد کنید.')
            return
        results = []
        for it in app.favs:
            if term in self._haystack(it):
                results.append(('lab', it))
        for it in app.featured:
            if term in self._haystack(it):
                results.append(('featured', it))
        self.info.set_text('%d نتیجه در لابراتوار و گلچین' % len(results))
        for source, it in results:
            self.list.add_widget(self._result_card(source, it))

    def _result_card(self, source, item):
        border = C_GOLD if source == 'featured' else C_BLUE
        tag = 'گلچین' if source == 'featured' else 'لابراتوار'
        card = RoundBox(bg=(0.10, 0.14, 0.22, 1), border=border, orientation='vertical',
                        size_hint_y=None, padding=dp(10), spacing=dp(4))
        head = RLabel('[%s] %s' % (tag, item.get('mode', '')), bold=True, font_size='13sp',
                      color=(C_GOLD if source == 'featured' else C_BLUE), halign='right', size_hint_y=None)
        head.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(4)))
        card.add_widget(head)
        pair = RLabel('سوره %s:%s     سوره %s:%s' % (item.get('seed_s'), item.get('seed_a'),
                      item.get('target_s'), item.get('target_a')),
                      font_size='12sp', color=C_MUTED, halign='center', size_hint_y=None)
        pair.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(2)))
        card.add_widget(pair)
        a2 = RLabel('« %s »' % item.get('target_arb', ''), arabic=True, font_size='16sp',
                    halign='center', color=C_TEXT, size_hint_y=None)
        a2.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(6)))
        card.add_widget(a2)
        btn = PillButton('مشاهدهٔ جزئیات', bg=C_BLUE, size_hint_y=None, height=dp(40), font_size='13sp')
        btn.bind(on_release=lambda *a, it=item, sc=source: show_discovery(it, sc, self))
        card.add_widget(btn)
        card.bind(minimum_height=lambda i, v: setattr(card, 'height', v + dp(20)))
        return card


# ==================================================================
# مدیریت برچسب‌ها
# ==================================================================
class TagsScreen(BaseScreen):
    DEFAULT = ["تقابل کامل", "گفت و گو", "زاویه دید متفاوت", "مکمل و بسط‌دهنده", "علت و معلول"]

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
            if tag not in self.DEFAULT and tag != 'نامشخص':
                b = PillButton('', bg=C_RED, size_hint_x=None, width=dp(56), font_size='14sp')
                b.bind(on_release=lambda x, t=tag: self.del_tag(t))
                row.add_widget(b)
            self.list.add_widget(row)

    def add_tag(self):
        app = App.get_running_app()
        t = self.q.query.strip()
        if not t:
            return
        if t in app.get_all_tags():
            toast('این برچسب قبلاً وجود دارد.', 'تکرار')
            return
        app.user_tags.append(t)
        app.save_user_tags()
        self.q.clear_logical()
        self.refresh()

    def del_tag(self, tag):
        app = App.get_running_app()
        def _do():
            if tag in app.user_tags:
                app.user_tags.remove(tag)
            for it in app.favs:
                if it.get('relation_type') == tag:
                    it['relation_type'] = 'نامشخص'
            app.save_user_tags()
            app.save_favs()
            self.refresh()
        confirm(f'برچسب «{tag}» حذف شود؟ (کشفیات مربوطه به نامشخص تغییر می‌کند)', _do, 'حذف برچسب')


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
            path = app.build_backup_json()
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
        share_util.save_file_to_device(path, on_done=_cb, mime='application/json', then_share=share)

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
    SECTIONS = [
        ('انتخاب بذر (سوره و آیه)', 'در صفحهٔ اصلی شمارهٔ سوره و آیه را وارد کنید. این «بذر» مبنای همهٔ پردازش‌هاست. اگر آیه‌ای خارج از محدوده وارد شود، به نزدیک‌ترین آیهٔ معتبر اصلاح می‌شود.'),
        ('پردازش ماتریس', 'هفت عملگر آینه‌ای (جابجایی و تقارن سوره/آیه) را روی بذر اعمال می‌کند و هفت آیهٔ مقصد را با متن کامل عربی و ترجمه نشان می‌دهد. هر مقصد را با دکمهٔ «ثبت این کشف» در لابراتوار ذخیره کنید.'),
        ('پیش‌بینی (معنا)', 'مقاصد آینه‌ای را بر اساس اشتراک واژگانی و ارتباط معنایی با بذر رتبه‌بندی می‌کند تا محتمل‌ترین تناظرها بالاتر بیایند.'),
        ('پیش‌بینی (اعداد)', 'با فیلترهای عددی مانند نیم‌کرهٔ سوره، اثر انگشت رقمی و تلورانس، نامزدهای عددی را غربال و اولویت‌بندی می‌کند.'),
        ('لابراتوار کشفیات', 'همهٔ کشف‌های ثبت‌شدهٔ شما اینجاست و بر اساس هفت عملگر دسته‌بندی شده. روی هر عملگر بزنید تا کشف‌های همان دسته باز شود؛ سپس روی هر کشف بزنید تا جزئیات کامل (عربی + ترجمهٔ مبدأ و مقصد) با امکان گلچین، ویرایش تحلیل، حذف و کپی را ببینید.'),
        ('گلچین برگزیده', 'کشف‌های مهم را از لابراتوار به گلچین می‌آورید. اینجا هم مانند لابراتوار بر اساس عملگرها دسته‌بندی شده و می‌توانید از کل گلچین خروجی JSON تمیز بگیرید.'),
        ('جستجوی آیات', 'در میان کشفیات لابراتوار و گلچین جستجو می‌کند (نه کل قرآن). متن عربی، ترجمه، برچسب و تحلیل شما جستجو می‌شود.'),
        ('مدیریت برچسب‌ها', 'برچسب‌های «رفتار آیه» (مانند تقابل کامل، گفت‌وگو، علت و معلول) را می‌سازید یا حذف می‌کنید تا هنگام ثبت تحلیل به کشف‌ها نسبت دهید.'),
        ('رسانه و معرفی', 'در این بخش «چند کلام از طراح» را می‌شنوید. صدای کوتاه معرفی هنگام باز شدن برنامه یک‌بار پخش می‌شود.'),
        ('پشتیبان و بازیابی', 'از داده‌های خود (کشفیات، گلچین، برچسب‌ها) نسخهٔ پشتیبان JSON بگیرید تا اطلاعاتتان امن بماند.'),
        ('درباره', 'معرفی اپلیکیشن و راه‌های ارتباط با مؤلف (سایت مرجع و شناسهٔ پیام‌رسان بله).'),
    ]

    def __init__(self, **kw):
        super().__init__(title='راهنما', **kw)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(8))
        box.bind(minimum_height=box.setter('height'))
        box.add_widget(RLabel('روی هر بخش بزنید تا توضیح کامل آن باز شود.', font_size='14sp',
                              color=C_MUTED, halign='center', size_hint_y=None, height=dp(34)))
        for title, body in self.SECTIONS:
            b = PillButton(title, bg=(0.16, 0.13, 0.05, 1), size_hint_y=None, height=dp(56), font_size='15sp')
            b.bind(on_release=lambda inst, t=title, d=body: self.show_help(t, d))
            box.add_widget(b)
        gt = asset('guide_table.png')
        if os.path.exists(gt):
            img = Image(source=gt, size_hint_y=None, height=dp(200), allow_stretch=True, keep_ratio=True)
            box.add_widget(img)
        scroll.add_widget(box)
        self.body(scroll)

    def show_help(self, title, body):
        content = BoxLayout(orientation='vertical', padding=dp(14), spacing=dp(10))
        sc = ScrollView(do_scroll_x=False, bar_width=dp(4))
        inner = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(4))
        inner.bind(minimum_height=inner.setter('height'))
        lbl = RLabel(body, font_size='15sp', color=C_TEXT, halign='right', size_hint_y=None)
        lbl.bind(texture_size=lambda i, v: setattr(i, 'height', v[1] + dp(10)))
        inner.add_widget(lbl)
        sc.add_widget(inner)
        content.add_widget(sc)
        p = Popup(title=P(title), content=content, size_hint=(0.92, 0.6),
                  title_font='ui', title_align='center', separator_color=C_GOLD)
        btn = PillButton('بستن', bg=C_BLUE, size_hint_y=None, height=dp(46))
        btn.bind(on_release=p.dismiss)
        content.add_widget(btn)
        p.open()

    def refresh(self):
        pass


# ==================================================================
# اپلیکیشن
# ==================================================================
class QuranMirrorApp(App):
    def build(self):
        self.title = 'قطب‌نمای قرآنی'
        Window.clearcolor = C_BG
        # رفع مشکل بالا نیامدن کیبورد + جلوگیری از پوشاندن ورودی توسط کیبورد
        try:
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
                            msg = '%s: %s' % (type(exc).__name__, exc)
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
        self.sm = sm
        return sm

    def on_start(self):
        try:
            from kivy.core.audio import SoundLoader
            path = asset('voice.mp3')
            if os.path.exists(path):
                snd = SoundLoader.load(path)
                if snd:
                    self._intro_sound = snd
                    Clock.schedule_once(lambda *a: snd.play(), 0.6)
        except Exception:
            pass

    # ---------- ذخیره‌سازی ----------
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

    def save_favs(self):
        with open(self._p('favorites.json'), 'w', encoding='utf-8') as f:
            json.dump(self.favs, f, ensure_ascii=False, indent=2)

    def load_featured(self):
        try:
            with open(self._p('featured.json'), encoding='utf-8') as f:
                self.featured = json.load(f)
        except Exception:
            self.featured = []

    def save_featured(self):
        with open(self._p('featured.json'), 'w', encoding='utf-8') as f:
            json.dump(self.featured, f, ensure_ascii=False, indent=2)

    def load_user_tags(self):
        try:
            with open(self._p('user_tags.json'), encoding='utf-8') as f:
                self.user_tags = json.load(f)
        except Exception:
            self.user_tags = []

    def save_user_tags(self):
        with open(self._p('user_tags.json'), 'w', encoding='utf-8') as f:
            json.dump(self.user_tags, f, ensure_ascii=False, indent=2)

    def get_all_tags(self):
        tags = set(TagsScreen.DEFAULT) | {'نامشخص'}
        for it in self.favs:
            t = it.get('relation_type')
            if t:
                tags.add(t)
        tags.update(self.user_tags)
        return sorted(tags)

    # ---------- عملیات کشف ----------
    def add_discovery(self, seed, target):
        entry = {
            'mode': target.get('mode', ''),
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
        if not entry.get('note'):
            entry['note'] = generate_default_analysis(entry)
        self.favs.append(entry)
        self.save_favs()
        self.last_discovery_key = discovery_key(entry)
        self.last_discovery_section = lab_section_of(entry)
        open_note_editor(entry, 'lab', title='ثبت تحلیل کشف',
                         intro='کشف در لابراتوار ثبت شد. تحلیل خود را ثبت کنید:',
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)))

    def add_featured(self, item, screen=None):
        for it in self.featured:
            if (it.get('seed_s'), it.get('seed_a'), it.get('target_s'), it.get('target_a')) == \
               (item.get('seed_s'), item.get('seed_a'), item.get('target_s'), item.get('target_a')):
                toast('این مورد در گلچین هست.', 'تکرار')
                return
        self.featured.append(dict(item))
        self.save_featured()
        toast('به گل��ین اضافه شد. ', 'گلچین')

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

    # ---------- خروجی JSON تمیز ----------
    def export_featured_word(self):
        if not self.featured:
            return None
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            doc = Document()
            h = doc.add_heading('', level=0)
            run = h.add_run('گلچین آیات آینه‌ای')
            run.font.size = Pt(20)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for i, it in enumerate(self.featured, 1):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                r = p.add_run(f"{i}. [{it.get('mode', '')}] سوره {it.get('seed_s')}:{it.get('seed_a')} سوره {it.get('target_s')}:{it.get('target_a')}")
                r.bold = True
                for key in ('seed_arb', 'seed_pers', 'target_arb', 'target_pers'):
                    par = doc.add_paragraph(it.get(key, ''))
                    par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if it.get('note'):
                    par = doc.add_paragraph('یادداشت: ' + it['note'])
                    par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                doc.add_paragraph('—' * 20)
            out = self._p('golchin_%s.docx' % datetime.now().strftime('%Y%m%d_%H%M'))
            doc.save(out)
            return out
        except Exception as e:
            print('word export error:', e)
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
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
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

    def export_featured_json(self):
        if not self.featured:
            return None
        payload = {
            'app': 'قطب‌نمای قرآنی',
            'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'featured': self._clean_by_operator(self.featured),
        }
        return self.export_clean_json('golchin_%s.json' % datetime.now().strftime('%Y%m%d_%H%M'), payload)

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
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)))

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
                         on_saved=lambda: setattr(self, 'last_discovery_section', lab_section_of(entry)))

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
        self.favs = favs
        self.featured = featured
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
        BOM و JSON خط‌به‌خط مقاوم است. (payload, error) برمی‌گرداند."""
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

    def import_items_json(self, text, target='lab', mode='merge'):
        payload, perr = self._parse_json_tolerant(text)
        if perr:
            return (0, 0, 'JSON نامعتبر: %s' % perr)
        items = self._extract_items(payload, target)
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

    def import_from_path(self, path, target='lab', mode='merge'):
        """بارگذاری امن از یک فایل: هم JSON خام و ه�� فایل ZIP خروجی ویندوز.
        هرگز کرش نمی‌کند؛ در صورت خطا پیام برمی‌گرداند."""
        import os as _os
        import zipfile as _zip
        try:
            if not path or not _os.path.exists(path):
                return (0, 0, 'فایل یافت نشد.')
            with open(path, 'rb') as _f:
                head = _f.read(4)
            if head[:2] == b'PK':
                member = 'featured.json' if target == 'featured' else 'favorites.json'
                try:
                    with _zip.ZipFile(path) as z:
                        names = z.namelist()
                        pick = None
                        for nm in names:
                            if nm.split('/')[-1].lower() == member:
                                pick = nm
                                break
                        if pick is None:
                            for nm in names:
                                if nm.lower().endswith('.json'):
                                    pick = nm
                                    break
                        if pick is None:
                            return (0, 0, 'داخل فایل ZIP، فایل JSON پیدا نشد.')
                        raw = z.read(pick).decode('utf-8-sig', 'replace')
                except Exception as e:
                    return (0, 0, 'خواندن فایل ZIP ممکن نشد: %s' % str(e)[:80])
                return self.import_items_json(raw, target, mode)
            # در غیر این صورت، فایل متنی JSON است
            try:
                with open(path, encoding='utf-8-sig', errors='replace') as _f:
                    raw = _f.read()
            except Exception as e:
                return (0, 0, 'خواندن فایل ممکن نشد: %s' % str(e)[:80])
            return self.import_items_json(raw, target, mode)
        except Exception as e:
            return (0, 0, 'خطا در بارگذاری: %s' % str(e)[:80])

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
