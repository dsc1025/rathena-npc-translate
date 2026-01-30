#!/usr/bin/env python3
"""
transtate.py

Translate `mes "..."` strings in rAthena NPC script files to Chinese (Simplified) while
preserving variables (concatenations like "" + strcharinfo(0) + "") and
color codes like ^4d4dff or ^000000.

Usage:
    python transtate.py input_file [--start N] [--line M]
    (Use `--line 0` to translate until the end of file)

Requirements:
    - Python 3.7+
    - Recommended: install deep-translator:
        pip install deep-translator

Behavior:
    - Finds lines starting with or containing `mes` and parses the expression
      that follows (string literals and concatenated variables/operators).
    - Concatenates adjacent string literals into a single chunk for better
      translation context, protecting color codes and re-inserting variables
      and operators unchanged.
        - Writes an output file with translated `mes` strings. By default the
            output filename is the input filename appended with `.zh-cn.txt`.

"""

import os
import re
import sys
import argparse
import traceback
from tqdm import tqdm as _tqdm
from deep_translator import GoogleTranslator as DT_GoogleTranslator
import json
import urllib.request
import urllib.parse



SEP = '<<<SEP>>>'
CLR_TOKEN = '<<<CLR{}>>>'

clr_re = re.compile(r"\^[0-9a-fA-F]{6}")

string_re = re.compile(r'"([^\"]*)"')
mes_line_re = re.compile(r'(?P<prefix>\bmes\b\s*)(?P<expr>.+)$')
npctalk_line_re = re.compile(r'(?P<prefix>\bnpctalk\b\s*)(?P<expr>.+)$')
select_line_re = re.compile(r'(?P<prefix>\bselect\b\s*)(?P<expr>.+)$')


def translate_text(text, target='zh-cn'):
    # normalize target language codes for downstream libraries
    def _normalize_target(t):
        if not t:
            return t
        if isinstance(t, str):
            tl = t.lower()
            if tl in ('zh-cn', 'zh_cn', 'zhcn', 'zh'):
                return 'zh-CN'
        return t

    target = _normalize_target(target)

    # Prefer deep-translator's GoogleTranslator
    try:
        t = DT_GoogleTranslator(source='auto', target=target)
        res = t.translate(text)
        if res is None:
            return text
        return res
    except Exception as e:
        print(f'translate_text: deep-translator failed ({type(e).__name__}: {e}), falling back to LibreTranslate', file=sys.stderr)

    # Fallback: LibreTranslate public instance
    def translate_via_libre(q, tgt='zh-cn'):
        url = 'https://libretranslate.de/translate'
        data = urllib.parse.urlencode({
            'q': q,
            'source': 'auto',
            'target': tgt,
            'format': 'text'
        }).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.load(resp)
                return result.get('translatedText', q) or q
        except Exception:
            return q

    return translate_via_libre(text, target)


def protect_color_codes(s):
    codes = []
    def _repl(m):
        idx = len(codes)
        codes.append(m.group(0))
        return CLR_TOKEN.format(idx)
    prov = clr_re.sub(_repl, s)
    return prov, codes


def restore_color_codes(s, codes):
    for i, c in enumerate(codes):
        s = s.replace(CLR_TOKEN.format(i), c)
    return s


def process_mes_expression(expr, target='zh-cn'):
    # find all string literal matches and their spans
    matches = list(string_re.finditer(expr))
    if not matches:
        return expr  # nothing to translate

    string_parts = []

    for m in matches:
        content = m.group(1)
        protected, codes = protect_color_codes(content)
        # keep original content for special-case checks (ellipsis, etc.)
        string_parts.append((protected, codes, content))

    # Combine string parts into one text joined by SEP to preserve context
    combined = SEP.join(p[0] for p in string_parts)

    # Translate combined text
    translated_combined = translate_text(combined, target=target)

    # Split back
    translated_parts = translated_combined.split(SEP)
    if len(translated_parts) != len(string_parts):
        # If splitting failed, fall back to translating each individually
        translated_parts = []
        for (orig, codes, raw_orig) in string_parts:
            # If the original raw content is only ellipses (e.g. '...', '……'), skip translating
            if re.fullmatch(r"[.．。…]{1,}", raw_orig.strip()):
                translated_parts.append(orig)
                continue
            t = translate_text(orig, target=target)
            # if translator returned same protected text (likely a failure/no-op) or empty, keep original
            if (t is None) or (t.strip() == orig.strip()):
                translated_parts.append(orig)
            else:
                translated_parts.append(t)

    # Restore color codes for each
    restored_parts = []
    for (tpart, (orig, codes, raw_orig)) in zip(translated_parts, string_parts):
        # If the raw original is only ellipses, keep it untranslated
        if re.fullmatch(r"[.．。…]{1,}", raw_orig.strip()):
            use_text = orig
        else:
            # If translator returned same as protected original, use original content
            use_text = tpart
            if (tpart is None) or (tpart.strip() == orig.strip()):
                use_text = orig
        s = restore_color_codes(use_text, codes)
        # Escape any double quotes in translated text
        s = s.replace('"', '\\"')
        restored_parts.append(s)

    # Rebuild expression by replacing string literals in original expr with translated ones
    out = []
    last = 0
    for (m, new_str) in zip(matches, restored_parts):
        start, end = m.span()
        # keep everything between last and start (operators, +, spaces)
        out.append(expr[last:start])
        # put quoted translated string
        out.append('"' + new_str + '"')
        last = end
    out.append(expr[last:])
    return ''.join(out)


def process_npctalk_expression(expr, target='zh-cn'):
    # find string literals
    matches = list(string_re.finditer(expr))
    if not matches:
        return expr

    translated_parts = []
    for i, m in enumerate(matches):
        content = m.group(1)
        # if content is empty, preserve original
        if content == '':
            translated_parts.append(content)
            continue
        # For second argument (index 1), preserve suffix after '#'
        if i == 1 and '#' in content:
            before, sep, after = content.partition('#')
            protected, codes = protect_color_codes(before)
            t = translate_text(protected, target=target)
            # if translation failed (no-op), keep original before+sep+after
            if (t is None) or (t.strip() == protected.strip()):
                translated = before + sep + after
            else:
                restored = restore_color_codes(t, codes)
                restored = restored.replace('"', '\\"')
                translated = restored + sep + after
        elif i <= 1:
            protected, codes = protect_color_codes(content)
            t = translate_text(protected, target=target)
            if (t is None) or (t.strip() == protected.strip()):
                restored = restore_color_codes(protected, codes)
            else:
                restored = restore_color_codes(t, codes)
            translated = restored.replace('"', '\\"')
        else:
            translated = content
        translated_parts.append(translated)

    # Rebuild expression by replacing string literals in original expr with translated ones
    out = []
    last = 0
    for (m, new_str) in zip(matches, translated_parts):
        start, end = m.span()
        out.append(expr[last:start])
        out.append('"' + new_str + '"')
        last = end
    out.append(expr[last:])
    return ''.join(out)


def process_select_expression(expr, target='zh-cn'):
    # Translate string literals inside select(...) when they contain English letters
    matches = list(string_re.finditer(expr))
    if not matches:
        return expr

    # Decide which string parts need translation (contains ASCII letters)
    parts = [m.group(1) for m in matches]
    translate_flags = [True if re.search(r'[A-Za-z]', p) else False for p in parts]

    # If nothing to translate, return original
    if not any(translate_flags):
        return expr

    # Protect color codes for parts that will be translated
    protected_items = []  # list of (protected, codes, raw)
    for flag, raw in zip(translate_flags, parts):
        if flag:
            prot, codes = protect_color_codes(raw)
            protected_items.append((prot, codes, raw))

    # Translate combined protected texts to preserve context
    combined = SEP.join(p[0] for p in protected_items)
    translated_combined = translate_text(combined, target=target)

    # Split back into translated pieces; if splitting count mismatches, translate individually
    translated_pieces = translated_combined.split(SEP)
    if len(translated_pieces) != len(protected_items):
        translated_pieces = []
        for prot, codes, raw in protected_items:
            if re.fullmatch(r"[.．。…]{1,}", raw.strip()):
                translated_pieces.append(prot)
                continue
            t = translate_text(prot, target=target)
            if (t is None) or (t.strip() == prot.strip()):
                translated_pieces.append(prot)
            else:
                translated_pieces.append(t)

    # Restore color codes and reassemble final string parts in order
    restored_parts = []
    ti = 0
    for i, raw in enumerate(parts):
        if not translate_flags[i]:
            restored_parts.append(raw)
        else:
            tpart = translated_pieces[ti]
            prot, codes, raw_orig = protected_items[ti]
            ti += 1
            if re.fullmatch(r"[.．。…]{1,}", raw_orig.strip()):
                use_text = prot
            else:
                use_text = tpart
                if (tpart is None) or (tpart.strip() == prot.strip()):
                    use_text = prot
            s = restore_color_codes(use_text, codes)
            s = s.replace('"', '\\"')
            restored_parts.append(s)

    # Rebuild expression by replacing string literals in original expr with translated ones
    out = []
    last = 0
    for (m, new_str) in zip(matches, restored_parts):
        start, end = m.span()
        out.append(expr[last:start])
        out.append('"' + new_str + '"')
        last = end
    out.append(expr[last:])
    return ''.join(out)


def process_file(infile, outfile, target='zh-cn', start_line=1, n_lines=0, force=False):
    # Read input with replacement on decode errors to avoid UnicodeDecodeError
    with open(infile, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    total = len(lines)
    # Convert start_line (1-based) to index
    start_idx = max(0, start_line - 1)
    # Determine end index
    if n_lines and n_lines > 0:
        end_idx = min(start_idx + n_lines, total)
    else:
        end_idx = total

    # If outfile exists, read how many lines already written
    resume_idx = start_idx
    if os.path.exists(outfile):
        try:
            with open(outfile, 'r', encoding='utf-8') as fo:
                existing = fo.readlines()
            if force:
                # Force should truncate the output *preserving already translated lines* up to start_idx.
                # If existing output is shorter than start_idx, pad with original input lines to keep alignment.
                keep = existing[:start_idx]
                if len(keep) < start_idx:
                    # pad with original (untranslated) input lines to reach start_idx
                    keep.extend(lines[len(existing):start_idx])
                with open(outfile, 'w', encoding='utf-8') as fo2:
                    fo2.writelines(keep)
                resume_idx = start_idx
            else:
                resume_idx = max(len(existing), start_idx)
                if resume_idx > end_idx:
                    # already translated requested range
                    print(f'Output already contains requested range (lines {start_idx+1}-{end_idx}).')
                    return
        except Exception:
            resume_idx = start_idx
    else:
        # outfile doesn't exist: if start_idx > 0, pre-fill with original lines to keep alignment
        if start_idx > 0:
            with open(outfile, 'w', encoding='utf-8') as fo:
                fo.writelines(lines[0:start_idx])
            resume_idx = start_idx

    print(f'Translating lines {start_idx+1}-{end_idx} (total file lines: {total}), resuming at line {resume_idx+1}')

    # Open output in append mode and write processed lines as we go
    with open(outfile, 'a', encoding='utf-8') as fo:
        use_tqdm = _tqdm is not None
        if use_tqdm:
            it = _tqdm(range(resume_idx, end_idx), total=(end_idx - start_idx), initial=(resume_idx - start_idx), unit='line')
        else:
            it = range(resume_idx, end_idx)

        for idx in it:
            line = lines[idx]
            # Prefer mes handling
            m = mes_line_re.search(line)
            if m:
                expr = m.group('expr').rstrip('\r\n')
                new_expr = process_mes_expression(expr, target=target)
                new_line = line[:m.start('expr')] + new_expr + '\n'
                fo.write(new_line)
            else:
                # Handle npctalk lines: translate first two string args
                n = npctalk_line_re.search(line)
                if n:
                    expr = n.group('expr').rstrip('\r\n')
                    new_expr = process_npctalk_expression(expr, target=target)
                    new_line = line[:n.start('expr')] + new_expr + '\n'
                    fo.write(new_line)
                else:
                    # Handle select(...) lines: translate string literals containing English
                    s = select_line_re.search(line)
                    if s:
                        expr = s.group('expr').rstrip('\r\n')
                        new_expr = process_select_expression(expr, target=target)
                        new_line = line[:s.start('expr')] + new_expr + '\n'
                        fo.write(new_line)
                    else:
                        fo.write(line)
            fo.flush()
            if not use_tqdm:
                print(f'Translated line {idx+1}/{end_idx}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Translate mes strings in rAthena NPC scripts')
    ap.add_argument('infile', help='Input script file')
    ap.add_argument('--start', type=int, default=1, help='Start line number (1-based, default: 1)')
    ap.add_argument('--line', type=int, default=0, help='Number of lines to translate (0 = all, default: 0)')
    ap.add_argument('--force', action='store_true', help='Force overwrite output for requested range')
    args = ap.parse_args()

    infile = args.infile
    base, _ext = os.path.splitext(infile)
    outfile = base + '.zh-cn.txt'

    print(f'Translating {infile} -> {outfile} (target=zh-cn)')
    process_file(infile, outfile, target='zh-cn', start_line=args.start, n_lines=args.line, force=args.force)
    print('Done.')
