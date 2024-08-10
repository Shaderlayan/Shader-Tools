#!/usr/bin/env python3

import shpkstruct
import sys

def crc32(name: str, prefixed_calc = None) -> int:
    name_b = bytes(name, 'utf-8')
    hash = shpkstruct.crc32(name_b) if prefixed_calc is None else prefixed_calc.checksum(name_b)
    print('0x%08X  %s%s' % (hash, '' if prefixed_calc is None else '…', name))
    return hash

for arg in sys.argv[1:]:
    crc32(arg)
