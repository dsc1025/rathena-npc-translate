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


def write_gbk_atomic(text: str, out_path: str) -> None:
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


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Convert a single file to GBK encoding.")
	parser.add_argument("input", help="Input file path")
	parser.add_argument("--force", action="store_true", help="Overwrite the original file instead of creating <name>_gbk")
	args = parser.parse_args(argv)

	inp = args.input

	if not os.path.isfile(inp):
		print(f"Input file not found: {inp}", file=sys.stderr)
		return 2

	try:
		text, used_enc = read_text(inp)
	except UnicodeDecodeError:
		print("Source file must be UTF-8 (utf-8 or utf-8-sig).", file=sys.stderr)
		return 3
	except Exception as e:
		print(f"Failed to read input file: {e}", file=sys.stderr)
		return 3

	# Insert "Translated By" block into the header before conversion, if not present.
	if "Translated By" not in text:
		lines = text.splitlines(True)  # preserve line endings
		# detect newline style
		nl = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
		header_end = None
		for i, ln in enumerate(lines):
			if not ln.lstrip().startswith("//"):
				break
			if "=" in ln:
				header_end = i
		if header_end is not None:
			insert_at = header_end + 1
		# detect newline style from the file (prefer CRLF when present)
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
		text = "".join(lines)

	if args.force:
		out = inp
	else:
		base, ext = os.path.splitext(inp)
		out = f"{base}_gbk{ext}"

	try:
		write_gbk_atomic(text, out)
	except UnicodeEncodeError:
		print(
			"Encoding to GBK failed: some characters are not representable in GBK.",
			file=sys.stderr,
		)
		return 4
	except Exception as e:
		print(f"Failed to write output file: {e}", file=sys.stderr)
		return 5

	print(f"Converted `{inp}` ({used_enc}) -> `{out}` (GBK)")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
