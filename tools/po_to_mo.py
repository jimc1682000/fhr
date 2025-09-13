#!/usr/bin/env python3
"""
Minimal .po -> .mo compiler (single-language, no plural forms).
Used in CI to compile locales without external gettext tools.
"""
from __future__ import annotations

import os
import struct
import sys
from typing import List, Tuple


def parse_po(path: str) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    msgid: List[str] = []
    msgstr: List[str] = []
    state = None  # 'id' or 'str'
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('#') or not line:
                continue
            if line.startswith('msgid '):
                if msgid or msgstr:
                    entries.append((''.join(msgid), ''.join(msgstr)))
                    msgid, msgstr = [], []
                state = 'id'
                msgid.append(_unquote(line[5:].strip()))
            elif line.startswith('msgstr '):
                state = 'str'
                msgstr.append(_unquote(line[6:].strip()))
            elif line.startswith('msgctxt '):
                # ignore context lines for this minimal compiler
                continue
            elif line.startswith('"'):
                if state == 'id':
                    msgid.append(_unquote(line.strip()))
                elif state == 'str':
                    msgstr.append(_unquote(line.strip()))
            else:
                # unsupported directive; ignore
                continue
        if msgid or msgstr:
            entries.append((''.join(msgid), ''.join(msgstr)))
    # Ensure header exists; if first entry has empty msgid, keep it
    return entries


def _unquote(s: str) -> str:
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.encode('utf-8').decode('unicode_escape')


def write_mo(entries: List[Tuple[str, str]], out_path: str) -> None:
    # Based on GNU MO file format
    entries = sorted(entries, key=lambda kv: kv[0])
    ids = [e[0].encode('utf-8') for e in entries]
    strs = [e[1].encode('utf-8') for e in entries]

    keystart = 7 * 4
    orig_tbl_offset = keystart
    trans_tbl_offset = orig_tbl_offset + len(ids) * 8
    orig_str_offset = trans_tbl_offset + len(strs) * 8

    orig_table = []
    off = orig_str_offset
    for i in ids:
        orig_table.append((len(i), off))
        off += len(i) + 1

    trans_table = []
    for s in strs:
        trans_table.append((len(s), off))
        off += len(s) + 1

    with open(out_path, 'wb') as f:
        # header
        f.write(struct.pack("Iiiiiii", 0x950412de, 0, len(ids), orig_tbl_offset, trans_tbl_offset, 0, 0))
        # tables
        for length, offset in orig_table:
            f.write(struct.pack("ii", length, offset))
        for length, offset in trans_table:
            f.write(struct.pack("ii", length, offset))
        # strings
        for i in ids:
            f.write(i + b"\0")
        for s in strs:
            f.write(s + b"\0")


def compile_po_to_mo(po_path: str, mo_path: str) -> None:
    entries = parse_po(po_path)
    os.makedirs(os.path.dirname(mo_path), exist_ok=True)
    write_mo(entries, mo_path)


def compile_all(root: str = 'locales') -> None:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith('.po'):
                po = os.path.join(dirpath, fn)
                mo = po[:-3] + '.mo'
                compile_po_to_mo(po, mo)
                print(f"Compiled {po} -> {mo}")


if __name__ == '__main__':
    compile_all()

