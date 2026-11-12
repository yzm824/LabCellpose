"""Print what a compiled library says about how it was built: FFmpeg's configuration and license strings.

    python windows/binary_facts.py FILE

Used when the notices for the Windows package are written: the license of the FFmpeg library inside the OpenCV wheel
depends on how that copy was configured, and the library records it.
"""
import re, sys

PATTERN = re.compile(rb'(--enable-[a-z0-9-]+|--disable-gpl|GPL version [0-9a-z. ]+|LGPL version [0-9a-z. ]+|'
                     rb'FFmpeg version [\x20-\x7e]{0,40}|libavcodec license: [\x20-\x7e]{0,60}|x264 - core [0-9]+|x265 \(build [0-9]+\))')

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    found = sorted({match.group(0).decode('latin-1') for match in PATTERN.finditer(data)})
    print('\n'.join(found) if found else 'no configuration or license strings found')
