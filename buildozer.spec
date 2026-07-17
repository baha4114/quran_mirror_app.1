[app]

title = Quran Mirror
package.name = quranmirror
package.domain = ir.parsavesta.quranmirror

source.dir = .
source.include_exts = py,csv,json,ttf,otf,jpg,jpeg,png,mp3,mp4,pdf,txt
source.include_patterns = assets/*
source.exclude_dirs = tests, bin, .git, __pycache__, .buildozer

version = 3.2
# شمارهٔ عددی نسخه (versionCode) — هر بار بیلد جدید باید بزرگ‌تر شود
# تا اندروید نسخهٔ قبلی را واقعاً جایگزین کند (نه اینکه قدیمی را نگه دارد)
android.numeric_version = 3020000

requirements = python3,kivy==2.3.0,arabic_reshaper,python-bidi==0.4.2,pyjnius

orientation = portrait
fullscreen = 0

# حالت واکنش پنجره به کیبورد: adjustResize باعث می‌شود هنگام باز شدن کیبورد، پنجره کوچک شود و
# باکسِ در حالِ تایپ خودکار بالای کیبورد بیاید (نه زیرش).
android.window_soft_input_mode = adjustResize

# تصویر صفحهٔ شروع — bg.jpg در ریشهٔ ریپوست (نه داخل assets)
presplash.filename = %(source.dir)s/bg.jpg
android.presplash_color = #0d1424

android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE

android.api = 34
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b

android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = 1
android.enable_androidx = True
android.gradle_dependencies = androidx.core:core:1.10.1

p4a.bootstrap = sdl2
p4a.source_dir = /home/runner/p4a

[buildozer]
log_level = 2
warn_on_root = 1
