"""batch_convert_to_gbk.py

Batch convert multiple *.zh-cn.txt UTF-8 files to GBK encoding with Translated By header insertion.

Usage examples:
	python batch_convert_to_gbk.py npc/re/guides/
	python batch_convert_to_gbk.py npc/re/ --recursive
	python batch_convert_to_gbk.py npc/re/guides/ --force

Behavior:
	- Automatically finds all *.zh-cn.txt files in given paths
	- Recursively processes directories when --recursive is specified
	- Creates <name>_gbk.txt for each file (or overwrites original with --force)
	- Inserts 'Translated By: dsc' header if not present
	- Prints summary of conversions (success/fail counts)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Import the core conversion logic
from convert_to_gbk import convert_file_to_gbk

# Use tqdm for progress UI if available; otherwise run silently until summary
try:
	from tqdm import tqdm
except Exception:
	tqdm = None


def find_files(paths: list[str], recursive: bool = False) -> list[str]:
	"""Find all *.zh-cn.txt files in the given paths."""
	files = []
	pattern = "*.zh-cn.txt"
	
	for path in paths:
		p = Path(path)
		if p.is_file():
			files.append(str(p.resolve()))
		elif p.is_dir():
			if recursive:
				files.extend(str(f.resolve()) for f in p.rglob(pattern) if f.is_file())
			else:
				files.extend(str(f.resolve()) for f in p.glob(pattern) if f.is_file())
	
	return files


def main(argv: list[str] | None = None) -> int:
	"""CLI entry point for batch conversion."""
	parser = argparse.ArgumentParser(
		description="Batch convert UTF-8 files to GBK encoding.",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
Examples:
  %(prog)s npc/re/guides/
  %(prog)s npc/re/ --recursive  %(prog)s npc/re/guides/ --force		"""
	)
	parser.add_argument("paths", nargs="+", help="Input file paths or directories")
	parser.add_argument("--recursive", "-r", action="store_true", help="Recursively process directories")
	parser.add_argument("--force", action="store_true", help="Overwrite original files instead of creating <name>_gbk variants")
	args = parser.parse_args(argv)

	# Find all files to process
	files = find_files(args.paths, args.recursive)

	if not files:
		print("No *.zh-cn.txt files found.", file=sys.stderr)
		return 1

	# Progress iterator: show tqdm progress bar if available; otherwise iterate silently
	iterator = tqdm(files, desc="Converting", unit="file") if tqdm else files

	success_count = 0
	fail_count = 0

	# Do not emit per-file prints; only update counts and let tqdm show progress.
	for file_path in iterator:
		output_path = file_path if args.force else None
		success, message = convert_file_to_gbk(file_path, output_path=output_path, insert_header=True)

		if success:
			success_count += 1
		else:
			fail_count += 1
	
	print(f"\nSummary: {success_count} succeeded, {fail_count} failed.")
	return 0 if fail_count == 0 else 1


if __name__ == "__main__":
	raise SystemExit(main())
