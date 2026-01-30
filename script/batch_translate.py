#!/usr/bin/env python3
"""
Batch translate utility (basic testing)

Usage:
    python -m script.batch_translate DIR [--run] [--target zh-cn]

By default this script lists all .txt files (recursively). Use `--run` to invoke
`TranslateEngine.process_file` and actually produce `.zh-cn.txt` outputs. This
keeps a safe dry-run default for initial testing.
"""
import os
import argparse
from script.translate import TranslateEngine


def find_txt_files(root, recursive=True):
    files = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                # Skip already-translated files like '*.zh-cn.txt'
                low = fn.lower()
                if low.endswith('.zh-cn.txt'):
                    continue
                if low.endswith('.txt'):
                    files.append(os.path.join(dirpath, fn))
    else:
        for fn in os.listdir(root):
            low = fn.lower()
            if low.endswith('.zh-cn.txt'):
                continue
            if low.endswith('.txt') and os.path.isfile(os.path.join(root, fn)):
                files.append(os.path.join(root, fn))
    return files


def main():
    ap = argparse.ArgumentParser(description='Batch find .txt files and optionally translate (basic test)')
    ap.add_argument('root', help='Root folder to scan for .txt files')
    ap.add_argument('--no-recursive', dest='recursive', action='store_false', help='Do not recurse into subfolders')
    ap.add_argument('--force', action='store_true', help='Force retranslation: include files even if .zh-cn.txt exists')
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(root):
        print(f'Not a directory: {root}')
        return

    files = find_txt_files(root, recursive=args.recursive)
    print(f'Found {len(files)} .txt files under {root} (recursive={args.recursive})')
    for p in files:
        print(' -', p)

    # Identify which files do NOT yet have a .zh-cn.txt translation
    if args.force:
        # force mode: include all candidate files regardless of existing outputs
        untranslated = list(files)
    else:
        untranslated = []
        for p in files:
            outp = os.path.splitext(p)[0] + '.zh-cn.txt'
            if not os.path.exists(outp):
                untranslated.append(p)

    print('\nFiles missing .zh-cn.txt:')
    if not untranslated:
        print(' - (none)')
    else:
        for p in untranslated:
            print(' -', p)

    # Perform translations for the missing files using TranslateEngine
    engine = TranslateEngine(target='zh-cn')
    succeeded = []
    failed = []
    for p in untranslated:
        outp = os.path.splitext(p)[0] + '.zh-cn.txt'
        print(f'Processing: {p} -> {outp}')
        try:
            engine.process_file(p, outfile=outp, force=args.force)
            succeeded.append(p)
        except Exception as e:
            print(f'Failed to translate {p}: {e}')
            failed.append((p, str(e)))

    print(f"\nCompleted: {len(succeeded)} succeeded, {len(failed)} failed.")


if __name__ == '__main__':
    main()
