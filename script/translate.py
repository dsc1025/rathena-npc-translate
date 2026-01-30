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

    # Default: translate all string literals unless they're additional params inside F_Navi calls
    translate_flags = [True] * len(matches)

    # Find F_Navi(...) spans and mark only the first quoted string inside each call for translation
    for fn_m in re.finditer(r'F_Navi\s*\(', expr):
        fn_start = fn_m.start()
        # find the matching closing paren for this F_Navi call (simple scan, single-line assumption)
        depth = 0
        fn_end = None
        for i in range(fn_m.end(), len(expr)):
            ch = expr[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    fn_end = i + 1
                    break
                else:
                    depth -= 1
        if fn_end is None:
            fn_end = len(expr)

        # collect indices of string matches within this F_Navi span
        inside_idxs = [i for i, mm in enumerate(matches) if mm.start() >= fn_start and mm.end() <= fn_end]
        if inside_idxs:
            # only the first string literal inside F_Navi should be translated
            for k, idx in enumerate(inside_idxs):
                translate_flags[idx] = (k == 0)

    # Build protected parts only for those that will be translated; preserve others as originals
    string_parts = []  # parallel to matches; either tuple or None
    for i, m in enumerate(matches):
        content = m.group(1)
        if translate_flags[i]:
            protected, codes = protect_color_codes(content)
            string_parts.append((protected, codes, content))
        else:
            string_parts.append(None)

    # Combine protected texts for translation (only those flagged)
    protected_texts = [p[0] for p in string_parts if p is not None]
    translated_parts = []
    if protected_texts:
        combined = SEP.join(protected_texts)
        translated_combined = translate_text(combined, target=target)
        translated_parts = translated_combined.split(SEP)
        if len(translated_parts) != len(protected_texts):
            # fallback: translate individually
            translated_parts = []
            for p in protected_texts:
                # if original is just ellipses, skip
                if re.fullmatch(r"[.．。…]{1,}", p.strip()):
                    translated_parts.append(p)
                    continue
                t = translate_text(p, target=target)
                if (t is None) or (t.strip() == p.strip()):
                    translated_parts.append(p)
                else:
                    translated_parts.append(t)

    # Restore color codes and assemble final replacement texts in order
    restored_parts = []
    ti = 0
    for idx, p in enumerate(string_parts):
        if p is None:
            # not translated: keep original raw content
            restored_parts.append(matches[idx].group(1))
        else:
            prot, codes, raw_orig = p
            tpart = translated_parts[ti] if ti < len(translated_parts) else prot
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


def process_f_navi_in_line(line, target='zh-cn'):
    # Process all F_Navi(...) occurrences in a single line, translating only the
    # first quoted string inside each call. Returns the updated line.
    out = []
    last = 0
    for fn_m in re.finditer(r'F_Navi\s*\(', line):
        fn_start = fn_m.start()
        # find matching closing paren (simple scan)
        depth = 0
        fn_end = None
        for i in range(fn_m.end(), len(line)):
            ch = line[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    fn_end = i + 1
                    break
                else:
                    depth -= 1
        if fn_end is None:
            fn_end = len(line)

        # Append text before this F_Navi
        out.append(line[last:fn_start])

        fn_text = line[fn_start:fn_end]
        # find string literals inside fn_text
        matches = list(string_re.finditer(fn_text))
        if not matches:
            # nothing to do
            out.append(fn_text)
            last = fn_end
            continue

        # Only translate the first quoted string inside F_Navi
        m0 = matches[0]
        content = m0.group(1)
        protected, codes = protect_color_codes(content)
        t = translate_text(protected, target=target)
        if (t is None) or (t.strip() == protected.strip()):
            use = protected
        else:
            use = t
        restored = restore_color_codes(use, codes)
        restored = restored.replace('"', '\\"')

        # Rebuild fn_text with replaced first string
        fn_out = []
        last_i = 0
        start0, end0 = m0.span()
        fn_out.append(fn_text[last_i:start0])
        fn_out.append('"' + restored + '"')
        last_i = end0
        fn_out.append(fn_text[last_i:])
        out.append(''.join(fn_out))
        last = fn_end

    out.append(line[last:])
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
                # For non-mes lines, translate first string inside any F_Navi(...) calls
                try:
                    line = process_f_navi_in_line(line, target=target)
                except Exception:
                    # don't let F_Navi post-processing break the run
                    pass
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
