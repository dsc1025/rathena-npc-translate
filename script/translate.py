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


SEP = '<<<SEP>>>'
CLR_TOKEN = '<<<CLR{}>>>'
BR_TOKEN = '<<<BR{}>>>'

clr_re = re.compile(r"\^[0-9a-fA-F]{6}")
br_re = re.compile(r"[\[\]]")

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
        # If translation via deep-translator fails, return original text (no fallback)
        print(f'translate_text: deep-translator failed ({type(e).__name__}: {e}), returning original text', file=sys.stderr)
        return text


def translate_protected_list(protected_texts, target='zh-cn'):
    """Translate a list of already-protected strings as a single request to
    preserve context. Returns a list of translated strings of the same length.
    If the translator returns no meaningful change, the original protected
    strings are returned for those positions.
    """
    if not protected_texts:
        return []
    combined = SEP.join(protected_texts)
    translated_combined = translate_text(combined, target=target)
    translated_parts = translated_combined.split(SEP)
    if len(translated_parts) == len(protected_texts):
        # normalize returns: keep original if translator produced identical text
        out = []
        for orig, t in zip(protected_texts, translated_parts):
            if (t is None) or (t.strip() == orig.strip()):
                out.append(orig)
            else:
                out.append(t)
        return out

    # Split mismatch: translate individually and fall back to originals on no-op
    out = []
    for p in protected_texts:
        if re.fullmatch(r"[.．。…]{1,}", p.strip()):
            out.append(p)
            continue
        t = translate_text(p, target=target)
        if (t is None) or (t.strip() == p.strip()):
            out.append(p)
        else:
            out.append(t)
    return out


def choose_translation(orig_protected, candidate):
    """Return candidate if it's a meaningful translation of orig_protected,
    otherwise return orig_protected.
    """
    if (candidate is None) or (candidate.strip() == orig_protected.strip()):
        return orig_protected
    return candidate


def protect_color_codes(s):
    codes = []
    def _repl(m):
        idx = len(codes)
        codes.append(m.group(0))
        return CLR_TOKEN.format(idx)
    prov = clr_re.sub(_repl, s)
    return prov, codes


def protect_brackets(s):
    codes = []
    def _repl(m):
        idx = len(codes)
        codes.append(m.group(0))
        return BR_TOKEN.format(idx)
    prov = br_re.sub(_repl, s)
    return prov, codes


def restore_brackets(s, codes):
    for i, c in enumerate(codes):
        s = s.replace(BR_TOKEN.format(i), c)
    return s


def restore_color_codes(s, codes):
    for i, c in enumerate(codes):
        s = s.replace(CLR_TOKEN.format(i), c)
    return s


def process_mes_expression(expr, target='zh-cn'):
    # First, replace F_Navi(...) first-string args with placeholders so they
    # won't be re-processed by the generic literal translation below.
    replaced_expr, fnav_map = replace_f_navi_in_text(expr, target=target)

    # find all string literal matches and their spans in the replaced expr
    matches = list(string_re.finditer(replaced_expr))
    if not matches:
        # restore any F_Navi placeholders and return
        res = replaced_expr
        for k, v in fnav_map.items():
            res = res.replace(k, v)
        return res

    # Build protected parts for all string literals (remaining ones need translation)
    string_parts = []
    for m in matches:
        content = m.group(1)
        protected, color_codes = protect_color_codes(content)
        protected, br_codes = protect_brackets(protected)
        string_parts.append((protected, color_codes, br_codes, content))

    protected_texts = [p[0] for p in string_parts]
    translated_parts = translate_protected_list(protected_texts, target=target) if protected_texts else []

    # Restore color codes and assemble final replacement texts in order
    restored_parts = []
    for (tpart, (prot, color_codes, br_codes, raw_orig)) in zip(translated_parts, string_parts):
        if re.fullmatch(r"[.．。…]{1,}", raw_orig.strip()):
            use_text = prot
        else:
            use_text = choose_translation(prot, tpart)
        s = restore_brackets(use_text, br_codes)
        s = restore_color_codes(s, color_codes)
        s = s.replace('"', '\\"')
        restored_parts.append(s)

    # Rebuild expression by replacing string literals in replaced_expr with translated ones
    out = []
    last = 0
    for (m, new_str) in zip(matches, restored_parts):
        start, end = m.span()
        out.append(replaced_expr[last:start])
        out.append('"' + new_str + '"')
        last = end
    out.append(replaced_expr[last:])
    res = ''.join(out)

    # Restore F_Navi placeholders
    for k, v in fnav_map.items():
        res = res.replace(k, v)
    return res


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
            protected, color_codes = protect_color_codes(before)
            protected, br_codes = protect_brackets(protected)
            t = translate_text(protected, target=target)
            chosen = choose_translation(protected, t)
            if chosen == protected:
                translated = before + sep + after
            else:
                restored = restore_brackets(chosen, br_codes)
                restored = restore_color_codes(restored, color_codes)
                restored = restored.replace('"', '\\"')
                translated = restored + sep + after
        elif i <= 1:
            protected, color_codes = protect_color_codes(content)
            protected, br_codes = protect_brackets(protected)
            t = translate_text(protected, target=target)
            chosen = choose_translation(protected, t)
            restored = restore_brackets(chosen, br_codes)
            restored = restore_color_codes(restored, color_codes)
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
            prot, color_codes = protect_color_codes(raw)
            prot, br_codes = protect_brackets(prot)
            protected_items.append((prot, color_codes, br_codes, raw))

    # Translate combined protected texts to preserve context
    translated_pieces = translate_protected_list([p[0] for p in protected_items], target=target)

    # Restore color codes and reassemble final string parts in order
    restored_parts = []
    ti = 0
    for i, raw in enumerate(parts):
        if not translate_flags[i]:
            restored_parts.append(raw)
        else:
            tpart = translated_pieces[ti]
            prot, color_codes, br_codes, raw_orig = protected_items[ti]
            ti += 1
            if re.fullmatch(r"[.．。…]{1,}", raw_orig.strip()):
                use_text = prot
            else:
                use_text = tpart
                if (tpart is None) or (tpart.strip() == prot.strip()):
                    use_text = prot
            s = restore_brackets(use_text, br_codes)
            s = restore_color_codes(s, color_codes)
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


def replace_f_navi_in_text(text, target='zh-cn'):
    """Find F_Navi(...) calls in text and replace the first quoted argument
    inside each call with a placeholder. Return (modified_text, mapping)
    where mapping maps placeholder -> final quoted string (including quotes).
    The placeholder is safe (not quoted) so callers can translate other
    literals and later restore the placeholders.
    """
    out = []
    last = 0
    mapping = {}
    counter = 0
    for fn_m in re.finditer(r'F_Navi\s*\(', text):
        fn_start = fn_m.start()
        # find matching closing paren (simple scan)
        depth = 0
        fn_end = None
        for i in range(fn_m.end(), len(text)):
            ch = text[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    fn_end = i + 1
                    break
                else:
                    depth -= 1
        if fn_end is None:
            fn_end = len(text)

        out.append(text[last:fn_start])
        fn_text = text[fn_start:fn_end]
        matches = list(string_re.finditer(fn_text))
        if not matches:
            out.append(fn_text)
            last = fn_end
            continue

        m0 = matches[0]
        content = m0.group(1)
        protected, color_codes = protect_color_codes(content)
        protected, br_codes = protect_brackets(protected)
        translated = translate_protected_list([protected], target=target)[0]
        restored = restore_brackets(translated, br_codes)
        restored = restore_color_codes(restored, color_codes)
        restored = restored.replace('"', '\\"')

        placeholder = f'__F_NAV_{counter}__'
        mapping[placeholder] = '"' + restored + '"'

        start0, end0 = m0.span()
        fn_modified = fn_text[:start0] + placeholder + fn_text[end0:]
        out.append(fn_modified)
        last = fn_end
        counter += 1

    out.append(text[last:])
    return ''.join(out), mapping


def process_f_navi_in_line(line, target='zh-cn'):
    # Use the centralized replacer to handle F_Navi first-arg translation
    replaced, fnav_map = replace_f_navi_in_text(line, target=target)
    # restore placeholders immediately and return
    for k, v in fnav_map.items():
        replaced = replaced.replace(k, v)
    return replaced


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
        # writer wrapper: previously replaced a hardcoded author name; instead
        # detect the `//===== By:` header and replace the following `//=` line
        # with a canonical author value (ding).
        def write_line(txt):
            fo.write(txt)
        use_tqdm = _tqdm is not None
        if use_tqdm:
            it = _tqdm(range(resume_idx, end_idx), total=(end_idx - start_idx), initial=(resume_idx - start_idx), unit='line')
        else:
            it = range(resume_idx, end_idx)

        for idx in it:
            line = lines[idx]
            stripped = line.strip()

            # If the line is a comment (starts with '//'), copy it verbatim
            # and do not perform any special-case header modifications.
            if stripped.startswith('//'):
                write_line(line)
                continue
            # Prefer mes handling
            m = mes_line_re.search(line)
            if m:
                expr = m.group('expr').rstrip('\r\n')
                new_expr = process_mes_expression(expr, target=target)
                new_line = line[:m.start('expr')] + new_expr + '\n'
                write_line(new_line)
            else:
                # For non-mes lines, translate first string inside any F_Navi(...) calls
                try:
                    line = process_f_navi_in_line(line, target=target)
                except Exception as e:
                    # don't let F_Navi post-processing break the run; log error
                    print(f'process_f_navi_in_line failed: {e}', file=sys.stderr)
                    traceback.print_exc()
                # Handle npctalk lines: translate first two string args
                n = npctalk_line_re.search(line)
                if n:
                    expr = n.group('expr').rstrip('\r\n')
                    new_expr = process_npctalk_expression(expr, target=target)
                    new_line = line[:n.start('expr')] + new_expr + '\n'
                    write_line(new_line)
                else:
                    # Handle select(...) lines: translate string literals containing English
                    s = select_line_re.search(line)
                    if s:
                        expr = s.group('expr').rstrip('\r\n')
                        new_expr = process_select_expression(expr, target=target)
                        new_line = line[:s.start('expr')] + new_expr + '\n'
                        write_line(new_line)
                    else:
                        write_line(line)
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


class TranslateEngine:
    """Lightweight wrapper class around the module-level translation functions.

    This class keeps the existing functions intact but provides a simple
    object-oriented API for callers and batch scripts.
    """
    def __init__(self, target='zh-cn'):
        self.target = target

    def translate_text(self, text):
        return translate_text(text, target=self.target)

    def translate_protected_list(self, protected_texts):
        return translate_protected_list(protected_texts, target=self.target)

    def process_file(self, infile, outfile=None, start_line=1, n_lines=0, force=False):
        if outfile is None:
            base, _ = os.path.splitext(infile)
            outfile = base + '.zh-cn.txt'
        return process_file(infile, outfile, target=self.target, start_line=start_line, n_lines=n_lines, force=force)

    def process_mes_expression(self, expr):
        return process_mes_expression(expr, target=self.target)

    def process_npctalk_expression(self, expr):
        return process_npctalk_expression(expr, target=self.target)

    def process_select_expression(self, expr):
        return process_select_expression(expr, target=self.target)

    def replace_f_navi_in_text(self, text):
        return replace_f_navi_in_text(text, target=self.target)

    def process_f_navi_in_line(self, line):
        return process_f_navi_in_line(line, target=self.target)
