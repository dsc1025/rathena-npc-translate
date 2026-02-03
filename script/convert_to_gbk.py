"""convert_to_gbk.py

Convert a single file to GBK (CP936) encoding.

Usage examples:
	python convert_to_gbk.py input.txt

Behavior:
	- Source file MUST be UTF-8 (utf-8 or utf-8-sig). If decoding fails the script exits with an error.
	- If `--force` is omitted, the script creates a new file named <basename>_gbk<ext>.
	- If `--force` is supplied, the original file is overwritten atomically.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

def read_text(path: str) -> tuple[str, str]:
	with open(path, "rb") as fh:
		b = fh.read()

	# Only accept UTF-8 (with optional BOM) as source. Fail otherwise.
	for enc in ("utf-8-sig", "utf-8"):
		try:
			return b.decode(enc), enc
		except UnicodeDecodeError:
			continue

	# If we reach here, decoding failed — caller should handle and report that source must be UTF-8.
	raise UnicodeDecodeError("utf-8", b, 0, 1, "source file is not valid UTF-8")


def insert_translated_by_header(text: str) -> str:
	"""Insert 'Translated By: dsc' header block if not already present."""
	if "Translated By" in text:
		return text
	
	lines = text.splitlines(True)  # preserve line endings
	nl = "\r\n" if "\r\n" in text else "\n"
	
	# Try to find the header separator line to insert before it
	insert_at = None
	for i, ln in enumerate(lines):
		if ln.strip() == "//============================================================":
			insert_at = i
			break

	# Fallback: if separator not found, insert after initial header comment block
	if insert_at is None:
		header_end = None
		for i, ln in enumerate(lines):
			if not ln.lstrip().startswith("//"):
				break
			if "=" in ln:
				header_end = i
		insert_at = (header_end + 1) if header_end is not None else 0

	# Build header block matching other header lines (not the separator)
	# Find a reference header line to match length (strip all trailing whitespace)
	ref_line = None
	for ln in lines[:insert_at]:
		stripped = ln.rstrip()
		if stripped.startswith("//===== ") and ":" in stripped:
			ref_line = stripped
			break
	
	if ref_line:
		total_len = len(ref_line)
	else:
		total_len = 60  # fallback
	
	prefix = "//===== "
	title = "Translated By:"
	equals_count = total_len - len(prefix) - len(title) - 1
	first = prefix + title + " " + ("=" * equals_count)
	second = "//= dsc"
	block = [first + nl, second + nl]

	lines[insert_at:insert_at] = block
	return "".join(lines)


def write_gbk_atomic(text: str, out_path: str) -> None:
	"""Write text to file in GBK encoding atomically."""
	dirn = os.path.dirname(out_path) or "."
	fd, tmppath = tempfile.mkstemp(dir=dirn)
	os.close(fd)
	try:
		with open(tmppath, "w", encoding="gbk", errors="strict", newline="") as f:
			f.write(text)
		os.replace(tmppath, out_path)
	finally:
		if os.path.exists(tmppath):
			try:
				os.remove(tmppath)
			except Exception:
				pass


def convert_file_to_gbk(input_path: str, output_path: str | None = None, insert_header: bool = True) -> tuple[bool, str]:
	"""
	Convert a single UTF-8 file to GBK encoding.
	
	Args:
		input_path: Path to input UTF-8 file
		output_path: Path to output file (if None, creates <name>_gbk variant)
		insert_header: Whether to insert 'Translated By' header
	
	Returns:
		(success: bool, message: str)
	"""
	if not os.path.isfile(input_path):
		return False, f"Input file not found: {input_path}"

	try:
		text, used_enc = read_text(input_path)
	except UnicodeDecodeError:
		return False, "Source file must be UTF-8 (utf-8 or utf-8-sig)."
	except Exception as e:
		return False, f"Failed to read input file: {e}"

	if insert_header:
		text = insert_translated_by_header(text)

	if output_path is None:
		base, ext = os.path.splitext(input_path)
		output_path = f"{base}_gbk{ext}"

	try:
		write_gbk_atomic(text, output_path)
	except UnicodeEncodeError:
		return False, "Encoding to GBK failed: some characters are not representable in GBK."
	except Exception as e:
		return False, f"Failed to write output file: {e}"

	return True, f"Converted `{input_path}` ({used_enc}) -> `{output_path}` (GBK)"


def main(argv: list[str] | None = None) -> int:
	"""CLI entry point for single file conversion."""
	parser = argparse.ArgumentParser(description="Convert a single file to GBK encoding.")
	parser.add_argument("input", help="Input file path")
	parser.add_argument("--force", action="store_true", help="Overwrite the original file instead of creating <name>_gbk")
	args = parser.parse_args(argv)

	output_path = args.input if args.force else None
	success, message = convert_file_to_gbk(args.input, output_path, insert_header=True)
	
	if success:
		print(message)
		return 0
	else:
		print(message, file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
