#!/usr/bin/env python3
"""Check `npc:` files in a single .conf file.

Usage:
    python script/switch_npc_path.py <input.conf>
    python script/switch_npc_path.py npc/re/scripts_athena.conf
    python script/switch_npc_path.py npc/re/scripts_athena.conf --suffix

Description:
    Scan a single .conf file for lines containing `npc: <path>`, resolve those
    paths (paths starting with `npc/` are resolved from the project root),
    and check whether the corresponding `.zh-cn.txt` file exists.

Output:
    - Missing entries are printed as:
        MISSING <file>:<lineno>: npc: <ref>
    - A one-line summary is printed:
        All <total>, Checked <have_zh>, missing: <missing>, converted: <converted>

Options:
    --suffix    Update the .conf in-place, replacing `.txt` -> `.zh-cn.txt`
                when the `.zh-cn.txt` counterpart exists (overwrites file).
"""
from pathlib import Path
import re
import sys
import argparse
import os

# Project root (two levels up from this script: project_root/script/this_file)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def scan_file(conf_path: Path):
    pattern = re.compile(r"\bnpc\s*:\s*(.+)", re.IGNORECASE)
    try:
        text = conf_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f'Failed to read {conf_path}: {e}', file=sys.stderr)
        return []

    results = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped_line = line.lstrip()
        if stripped_line.startswith('//') or stripped_line.startswith('#') or stripped_line.startswith(';'):
            continue
        m = pattern.search(line)
        if not m:
            continue
        raw = m.group(1).strip()
        for sep in ('//', '#', ';'):
            if sep in raw:
                raw = raw.split(sep, 1)[0].strip()
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            raw = raw[1:-1]
        raw = raw.strip()
        if not raw:
            continue
        # If the file already uses zh-cn suffix, skip it entirely
        if raw.lower().endswith('.zh-cn.txt'):
            continue
        # If the file starts with `npc/...`, resolve from project root
        normalized = raw.lstrip('/\\')
        lower = normalized.lower()
        if lower.startswith('npc' + os.sep) or lower.startswith('npc/') or lower == 'npc':
            resolved = (PROJECT_ROOT / normalized).resolve()
        else:
            resolved = (conf_path.parent / raw).resolve()
        # For comparison, use same-base filename with `.zh-cn.txt` suffix
        zh_resolved = resolved.with_suffix('.zh-cn.txt')
        exists = zh_resolved.exists()
        results.append((lineno, raw, str(zh_resolved), exists))
    return results


def main():
    ap = argparse.ArgumentParser(description='Check `npc:` files in a single .conf file')
    ap.add_argument('input', help='Path to the input .conf file')
    ap.add_argument('--suffix', action='store_true', help='Update the .conf replacing .txt -> .zh-cn.txt when counterpart exists (overwrites file)')
    args = ap.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'Input not found: {input_path}', file=sys.stderr)
        sys.exit(2)

    results = scan_file(input_path)
    if not results:
        print(f'No `npc:` files found in {input_path}')
        return

    missing_list = [(lineno, ref, resolved) for lineno, ref, resolved, exists in results if not exists]
    # Count existing `.zh-cn.txt` lines in the file (include commented-out lines excluded)
    pattern = re.compile(r"\bnpc\s*:\s*(.+)", re.IGNORECASE)
    existing_zh = 0
    total_all = 0
    text_all = input_path.read_text(encoding='utf-8', errors='ignore')
    for line in text_all.splitlines():
        stripped = line.lstrip()
        if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith(';'):
            continue
        m2 = pattern.search(line)
        if not m2:
            continue
        ref = m2.group(1).strip()
        total_all += 1
        # strip inline comments
        for sep in ('//', '#', ';'):
            if sep in ref:
                ref = ref.split(sep, 1)[0].strip()
        # strip quotes
        if (ref.startswith('"') and ref.endswith('"')) or (ref.startswith("'") and ref.endswith("'")):
            ref = ref[1:-1]
        if ref.lower().endswith('.zh-cn.txt'):
            existing_zh += 1
    converted = existing_zh
    for lineno, ref, resolved in missing_list:
        try:
            rel = str(input_path.resolve().relative_to(PROJECT_ROOT))
        except Exception:
            rel = str(input_path)
        print(f'MISSING {rel}:{lineno}: npc: {ref}')

    # Count how many non-`.zh-cn` entries have a corresponding .zh-cn.txt
    has_zh_in_results = sum(1 for _, _, _, exists in results if exists)
    print(f'All {total_all}, Checked {has_zh_in_results} files, missing: {len(missing_list)}, converted: {converted}')

    if args.suffix:
        # Apply replacements in-place: change .txt -> .zh-cn.txt when counterpart exists
        pattern = re.compile(r"\bnpc\s*:\s*(.+)", re.IGNORECASE)
        text = input_path.read_text(encoding='utf-8', errors='ignore')
        lines = text.splitlines()
        new_lines = lines.copy()
        changes = []
        for idx, line in enumerate(lines):
            stripped_line = line.lstrip()
            if stripped_line.startswith('//') or stripped_line.startswith('#') or stripped_line.startswith(';'):
                continue
            m = pattern.search(line)
            if not m:
                continue
            group_text = m.group(1)
            g_strip = group_text.strip()
            # separate inline comment inside group_text
            comment_part = ''
            ref_part = g_strip
            for sep in ('//', '#', ';'):
                p = g_strip.find(sep)
                if p != -1:
                    ref_part = g_strip[:p].strip()
                    comment_part = g_strip[p:]
                    break
            # detect quotes
            quote = ''
            ref_noq = ref_part
            if (ref_part.startswith('"') and ref_part.endswith('"')) or (ref_part.startswith("'") and ref_part.endswith("'")):
                quote = ref_part[0]
                ref_noq = ref_part[1:-1]

            normalized = ref_noq.lstrip('/\\')
            lower = normalized.lower()
            if lower.startswith('npc' + os.sep) or lower.startswith('npc/') or lower == 'npc':
                resolved = (PROJECT_ROOT / normalized).resolve()
            else:
                resolved = (input_path.parent / ref_noq).resolve()

            zh_resolved = resolved.with_suffix('.zh-cn.txt')
            if zh_resolved.exists() and not ref_noq.lower().endswith('.zh-cn.txt'):
                # build new ref with zh-cn suffix
                if ref_noq.lower().endswith('.txt'):
                    new_ref_noq = ref_noq[:-4] + '.zh-cn.txt'
                else:
                    new_ref_noq = ref_noq + '.zh-cn.txt'
                new_ref = (quote + new_ref_noq + quote) if quote else new_ref_noq
                # replace ref_part inside group_text once
                new_group = group_text.replace(ref_part, new_ref, 1)
                new_line = line[:m.start(1)] + new_group + line[m.end(1):]
                new_lines[idx] = new_line
                try:
                    rel = str(input_path.resolve().relative_to(PROJECT_ROOT))
                except Exception:
                    rel = str(input_path)
                changes.append((idx + 1, ref_noq, new_ref_noq))

        if changes:
            input_path.write_text('\n'.join(new_lines), encoding='utf-8')
            print(f'Converted {len(changes)} entries to .zh-cn.txt')


if __name__ == '__main__':
    main()
