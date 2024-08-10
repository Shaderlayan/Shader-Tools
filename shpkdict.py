from os import path
from shpkstruct import crc32

data_dir = path.dirname(__file__)

dictionary = {}
suffix_dictionary = set()

def resolve(crc: int) -> str | None:
    return dictionary.get(crc)

try:
    with open(path.join(data_dir, "shpk_dictionary.txt"), "rt") as fd:
        for line in fd:
            line = line.strip()
            dictionary[crc32(line.encode('utf-8'))] = line
except:
    pass

try:
    with open(path.join(data_dir, "shpk_suffix_dictionary.txt"), "rt") as fd:
        for line in fd:
            suffix_dictionary.add(line.strip())
except:
    pass
