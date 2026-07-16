# -*- coding: utf-8 -*-
"""
ابزار اشتراک‌گذاری فایل/متن روی اندروید (روبیکا، بله، تلگرام و ...).
روی اندروید از Android Share Sheet (ACTION_SEND) استفاده می‌کند تا فایل مستقیم
در اپ‌های پیام‌رسان باز شود. روی دسکتاپ فقط فایل را کنار برنامه ذخیره می‌کند.
"""
import os
import shutil

try:
    from kivy.utils import platform
except Exception:
    platform = None


def _android_share_file(path, mime='application/json', title='اشتراک‌گذاری پشتیبان'):
    """اشتراک یک فایل با Share Sheet اندروید از طریق FileProvider."""
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    File = autoclass('java.io.File')
    FileProvider = autoclass('androidx.core.content.FileProvider')
    String = autoclass('java.lang.String')

    activity = PythonActivity.mActivity
    jfile = File(path)
    authority = str(activity.getPackageName()) + '.fileprovider'
    uri = FileProvider.getUriForFile(activity, String(authority), jfile)

    intent = Intent(Intent.ACTION_SEND)
    intent.setType(String(mime))
    intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

    chooser = Intent.createChooser(intent, cast('java.lang.CharSequence', String(title)))
    chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    activity.startActivity(chooser)
    return True


def _android_share_text(text, title='اشتراک‌گذاری'):
    """اشتراک متن ساده (fallback در صورت نبود FileProvider)."""
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    activity = PythonActivity.mActivity
    intent = Intent(Intent.ACTION_SEND)
    intent.setType(String('text/plain'))
    intent.putExtra(Intent.EXTRA_TEXT, cast('java.lang.CharSequence', String(text)))
    chooser = Intent.createChooser(intent, cast('java.lang.CharSequence', String(title)))
    chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    activity.startActivity(chooser)
    return True


def share_file(path, mime='application/json', title='اشتراک‌گذاری پشتیبان'):
    """فایل را به اشتراک می‌گذارد.
    خروجی: (ok: bool, message: str)
    """
    if not path or not os.path.exists(path):
        return False, 'فایل برای اشتراک‌گذاری یافت نشد.'

    if platform == 'android':
        try:
            _android_share_file(path, mime, title)
            return True, 'پنجرهٔ اشتراک‌گذاری باز شد. اپ مقصد (روبیکا/بله/تلگرام) را انتخاب کنید.'
        except Exception as e:
            # تلاش برای اشتراک متنی به‌عنوان جایگزین
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    _android_share_text(f.read(), title)
                return True, 'فایل به‌صورت متن به اشتراک گذاشته شد (اشتراک فایلی در دسترس نبود).'
            except Exception as e2:
                return False, 'اشتراک‌گذاری ممکن نشد: %s' % e2
    else:
        # دسکتاپ: فقط کنار برنامه نگه می‌داریم و مسیر را برمی‌گردانیم
        try:
            dest = os.path.join(os.getcwd(), os.path.basename(path))
            if os.path.abspath(dest) != os.path.abspath(path):
                shutil.copy(path, dest)
            return True, 'روی دسکتاپ اشتراک‌گذاری در دسترس نیست. فایل ذخیره شد:\n' + dest
        except Exception as e:
            return True, 'فایل آماده است:\n' + path


# ------------------------------------------------------------------
# ذخیرهٔ فایل در حافظهٔ گوشی با پنجرهٔ انتخاب مسیر پویا (Storage Access Framework)
# روی اندروید API 24+ بدون نیاز به مجوز؛ فایل واقعی JSON در مای فایلز ذخیره می‌شود.
# اگر then_share=True باشد، پس از ذخیره، همین فایل با پنجرهٔ اشتراک‌گذاری به پیام‌رسان‌ها فرستاده می‌شود.
# ------------------------------------------------------------------
def save_file_to_device(path, on_done=None, mime='application/json', then_share=False,
                        share_title='اشتراک‌گذاری فایل'):
    """ذخیرهٔ فایل در مکان انتخابی کاربر. on_done(ok: bool, message: str) فراخوانده می‌شود."""
    if not path or not os.path.exists(path):
        if on_done:
            on_done(False, 'فایل برای ذخیره یافت نشد.')
        return
    if platform == 'android':
        try:
            _android_save_document(path, on_done, mime, then_share, share_title)
        except Exception as e:
            if on_done:
                on_done(False, 'باز کردن پنجرهٔ ذخیره ممکن نشد: %s' % e)
    else:
        try:
            dest = os.path.join(os.getcwd(), os.path.basename(path))
            if os.path.abspath(dest) != os.path.abspath(path):
                shutil.copy(path, dest)
            if on_done:
                on_done(True, 'فایل ذخیره شد:\n' + dest)
        except Exception as e:
            if on_done:
                on_done(False, 'ذخیره ممکن نشد: %s' % e)


def _android_save_document(path, on_done, mime='application/json', then_share=False,
                           share_title='اشتراک‌گذاری فایل'):
    from jnius import autoclass, cast
    from android import activity as _act
    from kivy.clock import Clock
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    activity = PythonActivity.mActivity
    REQUEST = 0x4A54

    def _cb(ok, msg):
        if on_done:
            Clock.schedule_once(lambda dt: on_done(ok, msg), 0)

    def _share_uri(uri):
        try:
            si = Intent(Intent.ACTION_SEND)
            si.setType(String(mime))
            si.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
            si.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            chooser = Intent.createChooser(si, cast('java.lang.CharSequence', String(share_title)))
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(chooser)
        except Exception:
            pass

    def _on_result(request, result, intent):
        if request != REQUEST:
            return
        try:
            _act.unbind(on_activity_result=_on_result)
        except Exception:
            pass
        if result != -1 or intent is None:   # Activity.RESULT_OK == -1
            _cb(False, 'ذخیره لغو شد.')
            return
        try:
            uri = intent.getData()
            resolver = activity.getContentResolver()
            out = resolver.openOutputStream(uri)
            OutputStreamWriter = autoclass('java.io.OutputStreamWriter')
            writer = OutputStreamWriter(out, String('UTF-8'))
            with open(path, 'r', encoding='utf-8') as f:
                writer.write(String(f.read()))
            writer.flush()
            writer.close()
            try:
                out.close()
            except Exception:
                pass
            if then_share:
                _share_uri(uri)
                _cb(True, 'فایل در گوشی ذخیره شد و پنجرهٔ اشتراک‌گذاری باز شد.')
            else:
                _cb(True, 'فایل در حافظهٔ گوشی ذخیره شد.')
        except Exception as e:
            _cb(False, 'ذخیرهٔ فایل ممکن نشد: %s' % e)

    _act.bind(on_activity_result=_on_result)
    intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType(String(mime))
    intent.putExtra(Intent.EXTRA_TITLE, String(os.path.basename(path)))
    activity.startActivityForResult(intent, REQUEST)


def _android_public_html_path(filename='gozaresh.html'):
    """مسیری در پوشهٔ عمومی Download که مرورگرها اجازهٔ خواندنش را دارند."""
    from jnius import autoclass
    Environment = autoclass('android.os.Environment')
    dl = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
    return os.path.join(dl.getAbsolutePath(), filename)


def _android_open_html(path):
    """نمایش فایل HTML با پنجرهٔ «انتخاب مرورگر» (ACTION_VIEW + createChooser).
    فایل به پوشهٔ عمومی Download کپی می‌شود تا مرورگرها بتوانند آن را بخوانند
    (بدون نیاز به ثبت FileProvider در منیفست)."""
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    File = autoclass('java.io.File')
    String = autoclass('java.lang.String')
    StrictMode = autoclass('android.os.StrictMode')
    VmPolicyBuilder = autoclass('android.os.StrictMode$VmPolicy$Builder')
    activity = PythonActivity.mActivity

    # کپی به پوشهٔ عمومی (مرورگر به حافظهٔ خصوصی اپ دسترسی ندارد)
    target = path
    try:
        pub = _android_public_html_path(os.path.basename(path))
        if os.path.abspath(pub) != os.path.abspath(path):
            import shutil
            shutil.copyfile(path, pub)
            target = pub
    except Exception:
        target = path

    # اجازهٔ عبور file:// در اندروید ۷+ (جلوگیری از FileUriExposedException)
    try:
        StrictMode.setVmPolicy(VmPolicyBuilder().build())
    except Exception:
        pass

    uri = Uri.fromFile(File(target))
    view = Intent(Intent.ACTION_VIEW)
    view.setDataAndType(uri, String('text/html'))
    view.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    title = cast('java.lang.CharSequence', String('نمایش گزارش با مرورگر:'))
    chooser = Intent.createChooser(view, title)
    chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    activity.startActivity(chooser)
    return True


def open_html(path):
    """فایل HTML را در مرورگر باز می‌کند. خروجی: (ok, message)"""
    if not path or not os.path.exists(path):
        return False, 'فایل HTML یافت نشد.'
    if platform == 'android':
        try:
            _android_open_html(path)
            return True, 'پنجرهٔ انتخاب مرورگر باز شد.'
        except Exception as e:
            return False, 'باز کردن مرورگر ممکن نشد: %s' % e
    else:
        try:
            import webbrowser
            webbrowser.open('file://' + os.path.abspath(path))
            return True, 'گزارش در مرورگر باز شد.'
        except Exception as e:
            return True, 'فایل آماده است:\n' + path


# ------------------------------------------------------------------
# انتخاب فایل با پنجرهٔ بومی دستگاه (بدون نیاز به وارد کردن دستی مسیر)
# روی اندروید از Storage Access Framework استفاده می‌کند؛ نیاز به مجوز ندارد.
# ------------------------------------------------------------------
def pick_text_file(on_text, mime='application/json'):
    """پنجرهٔ انتخاب فایل بومی را باز می‌کند و محتوای متنی فایل انتخاب‌شده را
    از طریق فراخوانی on_text(text_or_None, message) برمی‌گرداند."""
    if platform == 'android':
        try:
            _android_pick_text(on_text, mime)
        except Exception as e:
            on_text(None, 'باز کردن انتخابگر فایل ممکن نشد: %s' % e)
    else:
        _desktop_pick_text(on_text)


def _read_uri_text(activity, uri):
    from jnius import autoclass
    String = autoclass('java.lang.String')
    resolver = activity.getContentResolver()
    stream = resolver.openInputStream(uri)
    InputStreamReader = autoclass('java.io.InputStreamReader')
    BufferedReader = autoclass('java.io.BufferedReader')
    StringBuilder = autoclass('java.lang.StringBuilder')
    reader = BufferedReader(InputStreamReader(stream, String('UTF-8')))
    sb = StringBuilder()
    line = reader.readLine()
    while line is not None:
        sb.append(line)
        sb.append(String('\n'))
        line = reader.readLine()
    reader.close()
    try:
        stream.close()
    except Exception:
        pass
    return sb.toString()


def _copy_uri_to_file(activity, uri, dest_path):
    """محتوای یک URI را در یک فایل محلی کپی می‌کند (باینری‌امن، مناسب ZIP).
    کپی کاملاً سمت جاوا انجام می‌شود تا بایت‌ها سالم بمانند."""
    from jnius import autoclass
    resolver = activity.getContentResolver()
    FileOutputStream = autoclass('java.io.FileOutputStream')
    # روش ۱: android.os.FileUtils.copy (اندروید ۱۰+) — مطمئن‌ترین
    try:
        FileUtils = autoclass('android.os.FileUtils')
        istream = resolver.openInputStream(uri)
        if istream is None:
            raise IOError('input stream is null')
        ostream = FileOutputStream(dest_path)
        try:
            FileUtils.copy(istream, ostream)
        finally:
            try:
                ostream.flush()
                ostream.close()
            except Exception:
                pass
            try:
                istream.close()
            except Exception:
                pass
        return dest_path
    except Exception:
        pass
    # روش ۲ (جایگزین): کپی بایت‌به‌بایت با بافر جاوا
    istream = resolver.openInputStream(uri)
    if istream is None:
        raise IOError('input stream is null')
    BufferedInputStream = autoclass('java.io.BufferedInputStream')
    bis = BufferedInputStream(istream, 65536)
    ostream = FileOutputStream(dest_path)
    try:
        b = bis.read()
        while b != -1:
            ostream.write(b)
            b = bis.read()
    finally:
        try:
            ostream.flush()
            ostream.close()
        except Exception:
            pass
        try:
            bis.close()
        except Exception:
            pass
        try:
            istream.close()
        except Exception:
            pass
    return dest_path


def pick_file(on_file, mime='*/*'):
    """پنجرهٔ انتخاب فایل بومی را باز می‌کند و مسیر یک کپی محلی از فایل را
    از طریق on_file(path_or_None, message) برمی‌گرداند. برای ZIP و JSON مناسب است."""
    if platform == 'android':
        try:
            _android_pick_file(on_file, mime)
        except Exception as e:
            on_file(None, 'باز کردن انتخابگر فایل ممکن نشد: %s' % e)
    else:
        _desktop_pick_file(on_file)


def ensure_all_files_access():
    """در اندروید ۱۱+ برای خواندن فایل‌های دلخواه (مثل ZIP در Download) به
    دسترسی «همهٔ فایل‌ها» نیاز است. اگر نباشد، صفحهٔ تنظیمات باز می‌شود.
    True یعنی دسترسی هست؛ False یعنی از کاربر خواسته شد."""
    if platform != 'android':
        return True
    try:
        from jnius import autoclass
        VERSION = autoclass('android.os.Build$VERSION')
        if VERSION.SDK_INT < 30:
            # اندروید ۱۰ و پایین‌تر: مجوز معمولی کافی است
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.READ_EXTERNAL_STORAGE,
                                     Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass
            return True
        Environment = autoclass('android.os.Environment')
        if Environment.isExternalStorageManager():
            return True
        # باز کردن صفحهٔ «دسترسی به همهٔ فایل‌ها» برای این برنامه
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        Uri = autoclass('android.net.Uri')
        activity = PythonActivity.mActivity
        try:
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(Uri.parse('package:' + activity.getPackageName()))
            activity.startActivity(intent)
        except Exception:
            intent = Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION)
            activity.startActivity(intent)
        return False
    except Exception:
        return True


def _android_pick_file(on_file, mime='*/*'):
    # روی برخی گوشی‌ها انتخاب‌گر سیستمی (SAF) هنگام بازگشت برنامه را می‌بندد.
    # به‌جای آن از یک مرورگر فایل درون‌برنامه‌ای استفاده می‌کنیم که کرش نمی‌کند.
    import os
    granted = True
    try:
        granted = ensure_all_files_access()
    except Exception:
        pass
    if not granted:
        on_file(None, 'لطفاً در صفحه‌ای که باز شد، دسترسی «همهٔ فایل‌ها» را برای این برنامه فعال کنید، سپس دوباره دکمهٔ انتخاب فایل را بزنید.')
        return
    start = '/storage/emulated/0'
    if not os.path.isdir(start):
        for cand in ('/sdcard', os.path.expanduser('~')):
            if os.path.isdir(cand):
                start = cand
                break
    _desktop_browse(on_file, exts=('.json', '.zip'),
                    title='انتخاب فایل ZIP یا JSON', want_path=True, start_dir=start)


def _android_pick_text(on_text, mime='application/json'):
    from jnius import autoclass
    from android import activity as _act
    from kivy.clock import Clock
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    activity = PythonActivity.mActivity
    REQUEST = 0x4A53

    def _cb(text, msg):
        Clock.schedule_once(lambda dt: on_text(text, msg), 0)

    def _on_result(request, result, intent):
        if request != REQUEST:
            return
        try:
            _act.unbind(on_activity_result=_on_result)
        except Exception:
            pass
        if result != -1 or intent is None:   # Activity.RESULT_OK == -1
            _cb(None, 'انتخاب فایل لغو شد.')
            return
        try:
            uri = intent.getData()
            text = _read_uri_text(activity, uri)
            _cb(text, '')
        except Exception as e:
            _cb(None, 'خواندن فایل ممکن نشد: %s' % e)

    _act.bind(on_activity_result=_on_result)
    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)
    intent.setType(String(mime))
    activity.startActivityForResult(intent, REQUEST)


def _desktop_browse(deliver, exts=('.json',), title='انتخاب فایل', want_path=False, start_dir=None):
    """مرورگر فایل ساده و فارسی‌خوان برای دسکتاپ (همهٔ نام‌ها با rtl شکل‌دهی می‌شوند).
    اگر want_path=True باشد مسیر فایل انتخاب‌شده برگردانده می‌شود، وگرنه متن آن."""
    import os
    try:
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.label import Label
        from kivy.metrics import dp
    except Exception as e:
        deliver(None, 'انتخابگر فایل در دسترس نیست: %s' % e)
        return
    try:
        from rtl import rtl as _r
    except Exception:
        _r = lambda x: x

    exts = tuple(x.lower() for x in exts)
    _start = start_dir if (start_dir and os.path.isdir(start_dir)) else os.path.expanduser('~')
    state = {'cwd': _start}
    root = BoxLayout(orientation='vertical', spacing=6, padding=6)
    path_lbl = Label(text='', font_name='ui', size_hint_y=None, height=dp(30),
                     halign='right', valign='middle', shorten=True)
    path_lbl.bind(size=lambda i, v: setattr(i, 'text_size', v))
    root.add_widget(path_lbl)
    sv = ScrollView()
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
    grid.bind(minimum_height=grid.setter('height'))
    sv.add_widget(grid)
    root.add_widget(sv)
    pop = Popup(title=_r(title), content=root, size_hint=(0.96, 0.96))

    def _btn(label_text, cb, bg=(0.20, 0.22, 0.28, 1)):
        b = Button(text=_r(label_text), font_name='ui', size_hint_y=None, height=dp(42),
                   halign='right', valign='middle', background_normal='', background_color=bg)
        b.bind(size=lambda i, v: setattr(i, 'text_size', (v[0] - dp(16), v[1])))
        b.bind(on_release=lambda *a: cb())
        return b

    def _go_up():
        cur = state['cwd'].rstrip('/\\')
        parent = os.path.dirname(cur)
        if parent and parent != state['cwd']:
            _list(parent)

    def _pick(fp):
        pop.dismiss()
        if want_path:
            deliver(fp, '')
            return
        try:
            with open(fp, encoding='utf-8') as f:
                deliver(f.read(), '')
        except Exception as e:
            deliver(None, 'خواندن فایل ممکن نشد: %s' % e)

    def _list(path):
        state['cwd'] = path
        path_lbl.text = _r('پوشه: ' + path)
        grid.clear_widgets()
        grid.add_widget(_btn('.. (بازگشت به پوشهٔ بالا)', _go_up, bg=(0.16, 0.18, 0.24, 1)))
        for _lbl, _sp in (('⬇  Download', '/storage/emulated/0/Download'),
                          ('📄  Documents', '/storage/emulated/0/Documents'),
                          ('🏠  حافظهٔ داخلی', '/storage/emulated/0')):
            if os.path.isdir(_sp) and os.path.abspath(_sp) != os.path.abspath(path):
                grid.add_widget(_btn(_lbl, lambda pp=_sp: _list(pp), bg=(0.12, 0.20, 0.30, 1)))
        try:
            entries = sorted(os.listdir(path), key=lambda x: x.lower())
        except Exception as e:
            grid.add_widget(_btn('خطا در باز کردن پوشه', lambda: None, bg=(0.4, 0.15, 0.15, 1)))
            return
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        files = [e for e in entries if e.lower().endswith(exts)]
        for d in dirs:
            grid.add_widget(_btn('📁  ' + d, lambda dd=d: _list(os.path.join(path, dd))))
        for f in files:
            grid.add_widget(_btn('📄  ' + f, lambda ff=f: _pick(os.path.join(path, ff)), bg=(0.13, 0.30, 0.20, 1)))
        if not dirs and not files:
            grid.add_widget(_btn('(فایل مناسب یا پوشه‌ای نیست)', lambda: None, bg=(0.16, 0.18, 0.24, 1)))

    row = BoxLayout(size_hint_y=None, height=dp(46), spacing=6)
    cancel = Button(text=_r('انصراف'), font_name='ui', background_normal='', background_color=(0.5, 0.2, 0.2, 1))
    cancel.bind(on_release=lambda *a: (pop.dismiss(), deliver(None, 'لغو شد.')))
    row.add_widget(cancel)
    root.add_widget(row)

    _list(state['cwd'])
    pop.open()


def _desktop_pick_text(on_text):
    _desktop_browse(on_text, exts=('.json',), title='انتخاب فایل JSON', want_path=False)


def _desktop_pick_file(on_file):
    _desktop_browse(on_file, exts=('.json', '.zip'), title='انتخاب فایل ZIP یا JSON', want_path=True)
