# -*- coding: utf-8 -*-
"""خروجیِ زیبای گلچین: Word (.docx) / PDF / Excel (.xlsx)

این ماژول کاملاً خالص (pure-python) است و هیچ وابستگیِ سنگینی ندارد:
  * docx و xlsx با zipfile + XML دستی ساخته می‌شوند (بدون python-docx / openpyxl).
  * pdf با امبدِ فونتِ TrueType خودِ اپ (font.ttf) به صورتِ CIDFontType2/Identity-H
    ساخته می‌شود (بدون reportlab / fpdf).
تنها وابستگیِ اختیاری arabic_reshaper + python-bidi است که همین الان در requirements هستند
(برای شکل‌دهیِ متنِ عربی/فارسی در PDF). اگر نباشند، متن خام نوشته می‌شود.

ورودیِ همهٔ توابع، ساختارِ groups است:
    groups = [
        {'op_title': 'جابجایی خالص بذر', 'records': [record, ...]},
        ...
    ]
    record = {
        'mode': str, 'is_doubtful': bool, 'relation_type': str,
        'note': str, 'date': str,
        'seed_ref': str, 'seed_arb': str, 'seed_pers': str,
        'targets': [ {'ref': str, 'arb': str, 'pers': str}, ... ],
    }
"""

import io
import os
import struct
import zlib
import zipfile
from datetime import datetime

# ---------------- شکل‌دهیِ متن (فقط برای PDF) ----------------
try:
    import arabic_reshaper as _ar
    from bidi.algorithm import get_display as _get_display
    try:
        _RESHAPER = _ar.ArabicReshaper(configuration={
            'delete_harakat': False,
            'ARABIC LIGATURE ALLAH': 'no',
        })
    except Exception:
        _RESHAPER = None
    _HAS_SHAPE = True
except Exception:
    _HAS_SHAPE = False
    _RESHAPER = None
    _get_display = None


def _shape(s):
    """متنِ منطقی را به ترتیبِ دیداریِ راست‌به‌چپ (برای PDF) تبدیل می‌کند."""
    if not s:
        return ''
    if not _HAS_SHAPE:
        return s
    try:
        reshaped = _RESHAPER.reshape(s) if _RESHAPER is not None else _ar.reshape(s)
        return _get_display(reshaped)
    except Exception:
        return s


# ---------------- پالتِ رنگ (hex) ----------------
COL_TITLE = 'B9770E'   # عنوانِ اصلی — کهربایی
COL_OP = '784212'      # نامِ عملگر — قهوه‌ایِ سوخته
COL_REF = '5D6D7E'     # مرجعِ سوره/آیه — خاکستری
COL_ARABIC = '145A32'  # متنِ عربی — سبزِ تیره
COL_TRANS = '6C3483'   # ترجمه — بنفش
COL_NOTE = '1B4F72'    # متنِ تحلیل — آبیِ تیره
COL_META = 'B03A2E'    # رفتار/تردیدی و برچسبِ تحلیل — قرمز
COL_RULE = 'D4AC0D'    # خطِ جداکننده — طلایی
COL_HEADER_BG = 'FCF3CF'  # پس‌زمینهٔ سرستونِ اکسل

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def fa_num(v):
    try:
        return str(v).translate(_FA_DIGITS)
    except Exception:
        return str(v)


def _hex_rgb(h):
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def _xml_escape(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _clean(s):
    return (s or '').strip()


# ==================================================================
#  Word (.docx)  —  ساختِ دستیِ OOXML
# ==================================================================
def _w_run(text, color, size_pt, bold=False):
    """یک run راست‌به‌چپ با رنگ/اندازه."""
    sz = int(round(size_pt * 2))  # half-points
    b = '<w:b/><w:bCs/>' if bold else ''
    return (
        '<w:r><w:rPr>'
        '<w:rFonts w:ascii="Tahoma" w:hAnsi="Tahoma" w:cs="Tahoma"/>'
        '%s'
        '<w:color w:val="%s"/>'
        '<w:sz w:val="%d"/><w:szCs w:val="%d"/>'
        '<w:rtl/>'
        '</w:rPr>'
        '<w:t xml:space="preserve">%s</w:t></w:r>'
    ) % (b, color, sz, sz, _xml_escape(text))


def _w_para(runs_xml, align='right', before=40, after=40, line=264, border_color=None):
    jc = {'right': 'right', 'center': 'center', 'left': 'left'}.get(align, 'right')
    bdr = ''
    if border_color:
        bdr = ('<w:pBdr><w:bottom w:val="single" w:sz="12" w:space="4" w:color="%s"/></w:pBdr>'
               % border_color)
    return (
        '<w:p><w:pPr>'
        '<w:bidi/>'
        '%s'
        '<w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="auto"/>'
        '<w:jc w:val="%s"/>'
        '</w:pPr>%s</w:p>'
    ) % (bdr, before, after, line, jc, runs_xml)


def _w_divider():
    # پاراگرافِ خالی با خطِ پایینیِ طلایی — جداکنندهٔ کشف‌ها
    return _w_para('', align='center', before=60, after=120, line=120, border_color=COL_RULE)


def build_docx(groups, out_path, title='گلچینِ آیاتِ آینه‌ای'):
    body = []
    # عنوانِ اصلی
    body.append(_w_para(_w_run(title, COL_TITLE, 22, bold=True), align='center',
                        before=0, after=60, line=240))
    body.append(_w_para(_w_run('تاریخِ خروجی: ' + fa_num(datetime.now().strftime('%Y/%m/%d')),
                               COL_REF, 10), align='center', before=0, after=40, line=240))
    body.append(_w_para('', align='center', before=0, after=40, line=60, border_color=COL_RULE))

    for grp in groups:
        recs = grp.get('records') or []
        if not recs:
            continue
        # نامِ عملگر
        body.append(_w_para(
            _w_run('◆  ' + grp.get('op_title', '') + '  (' + fa_num(len(recs)) + ' کشف)',
                   COL_OP, 15, bold=True),
            align='right', before=160, after=60, line=252))
        for idx, rec in enumerate(recs, 1):
            # سرخطِ کشف: شماره + حالت
            head = fa_num(idx) + 'ـ  ' + _clean(rec.get('mode')) or fa_num(idx)
            meta = _clean(rec.get('relation_type')) or 'نامشخص'
            if rec.get('is_doubtful'):
                meta += ' — تردیدی'
            runs = _w_run(head + '   —   رفتار: ' + meta, COL_META, 12, bold=True)
            body.append(_w_para(runs, align='right', before=80, after=30, line=252))
            # بذر
            body.append(_w_para(_w_run('گزارهٔ بذر — ' + _clean(rec.get('seed_ref')), COL_REF, 10, bold=True),
                                align='right', before=30, after=10, line=240))
            if _clean(rec.get('seed_arb')):
                body.append(_w_para(_w_run(_clean(rec.get('seed_arb')), COL_ARABIC, 15, bold=True),
                                    align='right', before=0, after=6, line=276))
            if _clean(rec.get('seed_pers')):
                body.append(_w_para(_w_run(_clean(rec.get('seed_pers')), COL_TRANS, 12),
                                    align='right', before=0, after=20, line=264))
            # مقصدها
            targets = rec.get('targets') or []
            for t in targets:
                lbl = 'آیهٔ آینه‌ای — ' + _clean(t.get('ref'))
                body.append(_w_para(_w_run(lbl, COL_REF, 10, bold=True),
                                    align='right', before=20, after=10, line=240))
                if _clean(t.get('arb')):
                    body.append(_w_para(_w_run(_clean(t.get('arb')), COL_ARABIC, 15, bold=True),
                                        align='right', before=0, after=6, line=276))
                if _clean(t.get('pers')):
                    body.append(_w_para(_w_run(_clean(t.get('pers')), COL_TRANS, 12),
                                        align='right', before=0, after=20, line=264))
            # تحلیل
            if _clean(rec.get('note')):
                body.append(_w_para(_w_run('تحلیل:', COL_META, 11, bold=True),
                                    align='right', before=20, after=6, line=240))
                for para in _clean(rec.get('note')).split('\n'):
                    body.append(_w_para(_w_run(para, COL_NOTE, 12),
                                        align='right', before=0, after=16, line=276))
            # جداکنندهٔ کشف
            body.append(_w_divider())

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        + ''.join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:bidi/></w:sectPr>'
        '</w:body></w:document>'
    )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document)
    return out_path


# ==================================================================
#  Excel (.xlsx)  —  ساختِ دستیِ OOXML
# ==================================================================
def _xlsx_cell(col, row, text, style=0):
    ref = '%s%d' % (col, row)
    return ('<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (ref, style, _xml_escape(text)))


def build_xlsx(groups, out_path, title='گلچینِ آیاتِ آینه‌ای'):
    headers = ['عملگر', 'حالت', 'مرجعِ بذر', 'عربیِ بذر', 'ترجمهٔ بذر',
               'مرجعِ مقصد', 'عربیِ مقصد', 'ترجمهٔ مقصد', 'رفتار',
               'تردیدی', 'تحلیل', 'تاریخ']
    cols = [chr(ord('A') + i) for i in range(len(headers))]
    rows_xml = []
    r = 1
    # سرستون
    cells = ''.join(_xlsx_cell(cols[i], r, headers[i], style=1) for i in range(len(headers)))
    rows_xml.append('<row r="%d">%s</row>' % (r, cells))
    r += 1
    for grp in groups:
        for rec in (grp.get('records') or []):
            targets = rec.get('targets') or [{}]
            for ti, t in enumerate(targets):
                vals = [
                    grp.get('op_title', '') if ti == 0 else '',
                    _clean(rec.get('mode')) if ti == 0 else '',
                    _clean(rec.get('seed_ref')) if ti == 0 else '',
                    _clean(rec.get('seed_arb')) if ti == 0 else '',
                    _clean(rec.get('seed_pers')) if ti == 0 else '',
                    _clean(t.get('ref')),
                    _clean(t.get('arb')),
                    _clean(t.get('pers')),
                    _clean(rec.get('relation_type')) if ti == 0 else '',
                    ('بلی' if rec.get('is_doubtful') else 'خیر') if ti == 0 else '',
                    _clean(rec.get('note')) if ti == 0 else '',
                    _clean(rec.get('date')) if ti == 0 else '',
                ]
                cells = ''.join(_xlsx_cell(cols[i], r, vals[i], style=(2 if i in (3, 6) else 0))
                                for i in range(len(headers)))
                rows_xml.append('<row r="%d">%s</row>' % (r, cells))
                r += 1

    last_col = cols[-1]
    cols_widths = [16, 20, 14, 34, 30, 14, 34, 30, 16, 8, 44, 12]
    cols_xml = ''.join('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w)
                       for i, w in enumerate(cols_widths))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView rightToLeft="1" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        '<cols>' + cols_xml + '</cols>'
        '<sheetData>' + ''.join(rows_xml) + '</sheetData>'
        '<autoFilter ref="A1:%s1"/>' % last_col +
        '</worksheet>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="11"/><name val="Tahoma"/></font>'
        '<font><b/><sz val="11"/><color rgb="FF784212"/><name val="Tahoma"/></font>'
        '<font><sz val="12"/><color rgb="FF145A32"/><name val="Tahoma"/></font>'
        '</fonts>'
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFCF3CF"/></patternFill></fill>'
        '</fills>'
        '<borders count="2">'
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left/><right/>'
        '<top style="thin"><color rgb="FFD4AC0D"/></top>'
        '<bottom style="thin"><color rgb="FFD4AC0D"/></bottom><diagonal/></border>'
        '</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment horizontal="right" vertical="top" wrapText="1" readingOrder="2"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1" readingOrder="2"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment horizontal="right" vertical="top" wrapText="1" readingOrder="2"/></xf>'
        '</cellXfs>'
        '</styleSheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
        % _xml_escape((title or 'گلچین')[:31])
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/styles.xml', styles)
        z.writestr('xl/worksheets/sheet1.xml', sheet)
    return out_path


# ==================================================================
#  PDF  —  امبدِ فونتِ TrueType (CIDFontType2 / Identity-H)
# ==================================================================
def _read_ttf_tables(data):
    numTables = struct.unpack('>H', data[4:6])[0]
    tables = {}
    off = 12
    for _ in range(numTables):
        tag = data[off:off + 4].decode('latin-1')
        offset, length = struct.unpack('>II', data[off + 8:off + 16])
        tables[tag] = (offset, length)
        off += 16
    return tables


def _cmap4(data, off):
    segX2 = struct.unpack('>H', data[off + 6:off + 8])[0]
    segCount = segX2 // 2
    p = off + 14
    end = struct.unpack('>%dH' % segCount, data[p:p + segX2]); p += segX2
    p += 2
    start = struct.unpack('>%dH' % segCount, data[p:p + segX2]); p += segX2
    idDelta = struct.unpack('>%dh' % segCount, data[p:p + segX2]); p += segX2
    idRangeOffset_pos = p
    idRangeOffset = struct.unpack('>%dH' % segCount, data[p:p + segX2]); p += segX2
    mapping = {}
    for i in range(segCount):
        s, e = start[i], end[i]
        if s == 0xFFFF:
            continue
        for c in range(s, e + 1):
            if idRangeOffset[i] == 0:
                g = (c + idDelta[i]) & 0xFFFF
            else:
                gi_off = idRangeOffset_pos + i * 2 + idRangeOffset[i] + (c - s) * 2
                if gi_off + 2 > len(data):
                    continue
                g = struct.unpack('>H', data[gi_off:gi_off + 2])[0]
                if g != 0:
                    g = (g + idDelta[i]) & 0xFFFF
            if g != 0:
                mapping[c] = g
    return mapping


def _cmap12(data, off):
    nGroups = struct.unpack('>I', data[off + 12:off + 16])[0]
    p = off + 16
    mapping = {}
    for _ in range(nGroups):
        startC, endC, startG = struct.unpack('>III', data[p:p + 12]); p += 12
        if endC - startC > 70000:
            continue
        for c in range(startC, endC + 1):
            mapping[c] = startG + (c - startC)
    return mapping


def _parse_cmap(data, cmap_off):
    numSub = struct.unpack('>H', data[cmap_off + 2:cmap_off + 4])[0]
    chosen = None
    chosen_score = -1
    for i in range(numSub):
        pid, eid, sub_off = struct.unpack('>HHI', data[cmap_off + 4 + i * 8:cmap_off + 4 + i * 8 + 8])
        so = cmap_off + sub_off
        fmt = struct.unpack('>H', data[so:so + 2])[0]
        if fmt not in (4, 12):
            continue
        score = 1
        if pid == 3 and eid == 10:
            score = 5
        elif pid == 3 and eid == 1:
            score = 4
        elif pid == 0:
            score = 3
        if fmt == 12:
            score += 0.5
        if score > chosen_score:
            chosen = (so, fmt)
            chosen_score = score
    if not chosen:
        return {}
    so, fmt = chosen
    return _cmap4(data, so) if fmt == 4 else _cmap12(data, so)


def _parse_font(font_bytes):
    data = font_bytes
    tables = _read_ttf_tables(data)
    head_off = tables['head'][0]
    unitsPerEm = struct.unpack('>H', data[head_off + 18:head_off + 20])[0] or 1000
    xMin, yMin, xMax, yMax = struct.unpack('>hhhh', data[head_off + 36:head_off + 44])
    hhea_off = tables['hhea'][0]
    ascent, descent = struct.unpack('>hh', data[hhea_off + 4:hhea_off + 8])
    numHMetrics = struct.unpack('>H', data[hhea_off + 34:hhea_off + 36])[0]
    maxp_off = tables['maxp'][0]
    numGlyphs = struct.unpack('>H', data[maxp_off + 4:maxp_off + 6])[0]
    hmtx_off = tables['hmtx'][0]
    advances = []
    p = hmtx_off
    last = 0
    for _ in range(numHMetrics):
        aw = struct.unpack('>H', data[p:p + 2])[0]
        p += 4
        advances.append(aw)
        last = aw
    for _ in range(numGlyphs - numHMetrics):
        advances.append(last)
    cmap = _parse_cmap(data, tables['cmap'][0])
    return {
        'unitsPerEm': unitsPerEm,
        'bbox': (xMin, yMin, xMax, yMax),
        'ascent': ascent, 'descent': descent,
        'numGlyphs': numGlyphs, 'advances': advances, 'cmap': cmap,
    }


class _PdfBuilder:
    def __init__(self, font_bytes, page_w=595.28, page_h=841.89, margin=54.0):
        self.font_bytes = font_bytes
        self.font = _parse_font(font_bytes)
        self.page_w = page_w
        self.page_h = page_h
        self.margin = margin
        self.pages = []
        self.cur = []
        self.y = page_h - margin

    # --- اندازه‌گیری و شکل‌دهی ---
    def _gid(self, ch):
        return self.font['cmap'].get(ord(ch), 0)

    def _text_width(self, shaped, size):
        adv = self.font['advances']
        upm = self.font['unitsPerEm']
        total = 0
        for ch in shaped:
            g = self._gid(ch)
            if 0 <= g < len(adv):
                total += adv[g]
        return total * size / upm

    def _glyphs_hex(self, shaped):
        out = []
        for ch in shaped:
            out.append('%04X' % self._gid(ch))
        return ''.join(out)

    def _wrap(self, para, size, max_w):
        words = para.split(' ')
        lines = []
        cur = ''
        for w in words:
            trial = w if not cur else cur + ' ' + w
            if (not cur) or self._text_width(_shape(trial), size) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or ['']

    # --- صفحه ---
    def _newpage(self):
        self.pages.append(self.cur)
        self.cur = []
        self.y = self.page_h - self.margin

    def _ensure(self, needed):
        if self.y - needed < self.margin:
            self._newpage()

    def _emit_text(self, x, baseline, shaped, size, color):
        r, g, b = color
        self.cur.append('BT /F0 %.2f Tf %.4f %.4f %.4f rg %.2f %.2f Td <%s> Tj ET'
                        % (size, r, g, b, x, baseline, self._glyphs_hex(shaped)))

    def paragraph(self, logical, color_hex, size, align='right',
                  line_gap=1.4, before=0.0, after=4.0):
        logical = logical or ''
        color = _hex_rgb(color_hex)
        if before:
            self.y -= before
        max_w = self.page_w - 2 * self.margin
        for para in logical.split('\n'):
            for ln in self._wrap(para, size, max_w):
                shaped = _shape(ln)
                lh = size * line_gap
                self._ensure(lh)
                self.y -= size
                w = self._text_width(shaped, size)
                if align == 'right':
                    x = self.page_w - self.margin - w
                elif align == 'center':
                    x = (self.page_w - w) / 2.0
                else:
                    x = self.margin
                self._emit_text(x, self.y, shaped, size, color)
                self.y -= (lh - size)
        if after:
            self.y -= after

    def rule(self, color_hex=COL_RULE, thickness=1.2, pad=4.0):
        self.y -= pad
        self._ensure(thickness + pad)
        r, g, b = _hex_rgb(color_hex)
        x1 = self.margin
        x2 = self.page_w - self.margin
        self.cur.append('%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S'
                        % (r, g, b, thickness, x1, self.y, x2, self.y))
        self.y -= pad

    def space(self, h):
        self.y -= h

    # --- ساختِ فایل ---
    def save(self, out_path):
        if self.cur or not self.pages:
            self.pages.append(self.cur)
        upm = self.font['unitsPerEm']
        scale = 1000.0 / upm
        objs = []  # list of bytes bodies (without "N 0 obj")

        def add(body):
            objs.append(body)
            return len(objs)  # 1-based object number

        # رزروِ شماره‌ها: به ترتیب ایجاد می‌کنیم
        # 1: Catalog, 2: Pages
        catalog_no = add(b'')  # placeholder 1
        pages_no = add(b'')    # placeholder 2

        # فونت
        fontfile_raw = self.font_bytes
        fontfile_comp = zlib.compress(fontfile_raw)
        fontfile_no = add(
            b'<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n'
            % (len(fontfile_comp), len(fontfile_raw))
            + fontfile_comp + b'\nendstream'
        )
        xMin, yMin, xMax, yMax = self.font['bbox']
        bbox = '[%d %d %d %d]' % (int(xMin * scale), int(yMin * scale),
                                  int(xMax * scale), int(yMax * scale))
        asc = int(self.font['ascent'] * scale)
        desc = int(self.font['descent'] * scale)
        descriptor_no = add(
            ('<< /Type /FontDescriptor /FontName /AppFont /Flags 4 /FontBBox %s '
             '/ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d /StemV 80 '
             '/FontFile2 %d 0 R >>' % (bbox, asc, desc, asc, fontfile_no)).encode('latin-1')
        )
        # W array — پهنایِ همهٔ گلیف‌ها
        adv = self.font['advances']
        w_vals = ' '.join(str(int(round(a * scale))) for a in adv)
        cidfont_no = add(
            ('<< /Type /Font /Subtype /CIDFontType2 /BaseFont /AppFont '
             '/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> '
             '/FontDescriptor %d 0 R /CIDToGIDMap /Identity /DW 1000 /W [0 [%s]] >>'
             % (descriptor_no, w_vals)).encode('latin-1')
        )
        font_no = add(
            ('<< /Type /Font /Subtype /Type0 /BaseFont /AppFont /Encoding /Identity-H '
             '/DescendantFonts [%d 0 R] >>' % cidfont_no).encode('latin-1')
        )

        # صفحات + محتوا
        page_nos = []
        for content_lines in self.pages:
            stream = ('\n'.join(content_lines)).encode('latin-1', 'replace')
            comp = zlib.compress(stream)
            content_no = add(
                b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(comp)
                + comp + b'\nendstream'
            )
            page_body = (
                '<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] '
                '/Resources << /Font << /F0 %d 0 R >> >> /Contents %d 0 R >>'
                % (pages_no, self.page_w, self.page_h, font_no, content_no)
            ).encode('latin-1')
            page_nos.append(add(page_body))

        # پر کردنِ Catalog و Pages
        kids = ' '.join('%d 0 R' % n for n in page_nos)
        objs[pages_no - 1] = ('<< /Type /Pages /Count %d /Kids [%s] >>'
                              % (len(page_nos), kids)).encode('latin-1')
        objs[catalog_no - 1] = ('<< /Type /Catalog /Pages %d 0 R >>' % pages_no).encode('latin-1')

        # نوشتنِ فایل + xref
        out = io.BytesIO()
        out.write(b'%PDF-1.5\n%\xe2\xe3\xcf\xd3\n')
        offsets = [0] * (len(objs) + 1)
        for i, body in enumerate(objs, 1):
            offsets[i] = out.tell()
            out.write(('%d 0 obj\n' % i).encode('latin-1'))
            out.write(body)
            out.write(b'\nendobj\n')
        xref_pos = out.tell()
        n = len(objs) + 1
        out.write(('xref\n0 %d\n' % n).encode('latin-1'))
        out.write(b'0000000000 65535 f \n')
        for i in range(1, n):
            out.write(('%010d 00000 n \n' % offsets[i]).encode('latin-1'))
        out.write(('trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF'
                   % (n, catalog_no, xref_pos)).encode('latin-1'))
        with open(out_path, 'wb') as f:
            f.write(out.getvalue())
        return out_path


def build_pdf(groups, out_path, font_path, title='گلچینِ آیاتِ آینه‌ای'):
    with open(font_path, 'rb') as f:
        font_bytes = f.read()
    pdf = _PdfBuilder(font_bytes)
    # عنوان
    pdf.paragraph(title, COL_TITLE, 21, align='center', before=6, after=6)
    pdf.paragraph('تاریخِ خروجی: ' + fa_num(datetime.now().strftime('%Y/%m/%d')),
                  COL_REF, 10, align='center', after=6)
    pdf.rule()
    for grp in groups:
        recs = grp.get('records') or []
        if not recs:
            continue
        pdf.paragraph('◆  ' + grp.get('op_title', '') + '  (' + fa_num(len(recs)) + ' کشف)',
                      COL_OP, 15, align='right', before=14, after=6)
        for idx, rec in enumerate(recs, 1):
            meta = _clean(rec.get('relation_type')) or 'نامشخص'
            if rec.get('is_doubtful'):
                meta += ' — تردیدی'
            head = fa_num(idx) + 'ـ  ' + (_clean(rec.get('mode')) or 'کشف')
            pdf.paragraph(head + '   —   رفتار: ' + meta, COL_META, 12, align='right',
                          before=8, after=4)
            pdf.paragraph('گزارهٔ بذر — ' + _clean(rec.get('seed_ref')), COL_REF, 10,
                          align='right', before=2, after=2)
            if _clean(rec.get('seed_arb')):
                pdf.paragraph(_clean(rec.get('seed_arb')), COL_ARABIC, 15, align='right', after=3)
            if _clean(rec.get('seed_pers')):
                pdf.paragraph(_clean(rec.get('seed_pers')), COL_TRANS, 12, align='right', after=6)
            for t in (rec.get('targets') or []):
                pdf.paragraph('آیهٔ آینه‌ای — ' + _clean(t.get('ref')), COL_REF, 10,
                              align='right', before=2, after=2)
                if _clean(t.get('arb')):
                    pdf.paragraph(_clean(t.get('arb')), COL_ARABIC, 15, align='right', after=3)
                if _clean(t.get('pers')):
                    pdf.paragraph(_clean(t.get('pers')), COL_TRANS, 12, align='right', after=6)
            if _clean(rec.get('note')):
                pdf.paragraph('تحلیل:', COL_META, 11, align='right', before=4, after=3)
                pdf.paragraph(_clean(rec.get('note')), COL_NOTE, 12, align='right', after=6)
            pdf.rule()
    return pdf.save(out_path)


# ==================================================================
#  درگاهِ یکپارچه
# ==================================================================
def generate(kind, groups, out_path, font_path=None, title='گلچینِ آیاتِ آینه‌ای'):
    kind = (kind or '').lower()
    if kind in ('docx', 'word'):
        return build_docx(groups, out_path, title=title)
    if kind in ('xlsx', 'excel'):
        return build_xlsx(groups, out_path, title=title)
    if kind == 'pdf':
        return build_pdf(groups, out_path, font_path, title=title)
    raise ValueError('unknown kind: %s' % kind)
