[app]

title = Quran Mirror
package.name = quranmirror
package.domain = ir.parsavesta.quranmirror

source.dir = .
source.include_exts = py,csv,json,ttf,otf,jpg,jpeg,png,mp3,mp4,pdf,txt
source.include_patterns = assets/*
source.exclude_dirs = tests, bin, .git, __pycache__, .buildozer

version = 4.2
# شمارهٔ عددی نسخه (versionCode) — هر بار بیلد جدید باید بزرگ‌تر شود
# تا اندروید نسخهٔ قبلی را واقعاً جایگزین کند (نه اینکه قدیمی را نگه دارد)
android.numeric_version = 4020000

# ================== شکل‌دهیِ بومیِ متن با PANGO ==================
# pango: ارائه‌دهندهٔ متنِ Kivy که حروفِ عربی/فارسی را به‌صورتِ بومی
#   «متصل» و راست‌به‌چپ (RTL) شکل می‌دهد تا تایپ/ویرایش/انتخاب کاملاً طبیعی شود.
# زنجیرهٔ وابستگی: pango → harfbuzz + freetype + fribidi + glib (glib با meson/ninja ساخته می‌شود).
#   harfbuzz و freetype را صریح ذکر کردیم تا قطعاً ساخته شوند و Kivy به آن‌ها لینک شود.
#   arabic_reshaper + python-bidi هم به‌عنوانِ لایهٔ پشتیبان (اگر pango نبود ← sdl2) باقی می‌مانند.
requirements = python3,kivy==2.3.0,arabic_reshaper,python-bidi==0.4.2,pyjnius,plyer,pypdf,freetype,harfbuzz,pango

orientation = portrait
fullscreen = 0

# حالت واکنش پنجره به کیبورد
android.window_soft_input_mode = adjustPan

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

# bootstrap باید sdl2 بماند؛ pango «ارائه‌دهندهٔ متن» است نه bootstrap پنجره، پس در کنارِ sdl2 کار می‌کند.
p4a.bootstrap = sdl2
p4a.source_dir = /home/runner/p4a

# ================== اصلاحِ کامپایلِ harfbuzz ==================
# سورسِ harfbuzz با -Werror ساخته می‌شود و کلنگِ NDK r25b یک هشدارِ ساده را به خطا
# تبدیل می‌کرد (hb-subset-cff1.cc: 'supp_size' set but not used) و کلِ بیلد را می‌شکست.
# این پوشه یک recipeِ محلی دارد که فقط -Wno-error را به فلگ‌های کامپایلِ harfbuzz اضافه می‌کند.
p4a.local_recipes = ./p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
