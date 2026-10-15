"""Read Pixiv Viewer's own settings out of the LevelDB it keeps them in, and write them back.

**Why this is the way in.** The app is a Tauri window over WebView2, and every route into its webview was measured and
is closed: `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` does not reach the renderer (Tauri overrides it -- tried through
`Start-Process`, through `cmd /c set` and through an explicit `ProcessStartInfo.EnvironmentVariables`, and the
renderer's own command line has no `--remote-debugging-port` in any of the three), so there is no CDP endpoint;
UI Automation enumerates the window down to `NonClientView` and stops, because Chromium does not build its
accessibility tree unless a screen reader asks, and sending `WM_GETOBJECT`/`OBJID_CLIENT` by hand did not wake it.

**What is not closed is the app's own state.** It keeps it in `%LOCALAPPDATA%\\org.eu.cocomi.pxvek\\EBWebView\\Default\\
Local Storage\\leveldb`, which is an ordinary LevelDB and holds `api`, `setting`, `search`, `token` and `refresh`
among its keys -- the API instance list and the login material, in a file format this can parse. **So the app becomes
a configuration surface rather than a thing to be driven**: a person points it at an API instance and logs in there,
and a script reads what they chose instead of pretending to click.

    python pxvek_store.py keys                       # what is in there, without printing secrets
    python pxvek_store.py dump [--show-secrets]     # every key and value
    python pxvek_store.py get <key>
    python pxvek_store.py set <key> <value>          # writes a new log record, the way LevelDB does
"""
import argparse
import json
import pathlib
import struct
import sys

STORE = pathlib.Path.home() / 'AppData' / 'Local' / 'org.eu.cocomi.pxvek' / 'EBWebView' / 'Default' / 'Local Storage' / 'leveldb'

#: **The keys this will print without being asked twice, and everything else is withheld.**
#:
#: An allowlist rather than a list of things to hide, and the reason is that a denylist failed three times in one
#: sitting: a live `"refreshToken":"7jNUhjcztDxDJh-8v..."` was printed from `PXV_CLIENT_CONFIG`, whose name contains no
#: secret word and whose value contains no secret word either; then `PXV_LOGIN_CODEV` was printed, and *login* was not
#: on the list. **The second miss was in the same session as the first, which is what a denylist does** -- each miss is
#: a new word to add, and the next secret will be called something else again.
#:
#: So the question is inverted: not "does this look secret" but "do I know what this is". These are the entries whose
#: meaning has actually been read and which are settings, history or cosmetics. Anything unnamed is withheld and
#: reported as withheld, so a new key shows up as a question rather than as a leak.
SAFE_KEYS = (
    'PIXIV_SEARCHHISTORY',
    'PXIMG_PROXY',
    'PXV_ACT_COLOR',
    'PXV_APP_SETTING',
    'PXV_CNT_SHOW',
    'PXV_HIDE_AP_SEL',
    'PXV_PXIMG_DIRECT',
    'PXV_VISUAL_THEME',
)


def is_safe(k):
    """Safe only if the name is on the list. **Prefix-matching on the piece after the NUL, not on the whole key**,
    because every key carries `_<origin>\\x00` in front of it."""
    name = short(k).split(' / ')[-1].upper()
    return name in SAFE_KEYS


def read_log(path):
    """The logical records of a LevelDB write-ahead log.

    The format is a sequence of 32 KiB blocks; each record starts with a 7-byte header -- crc32, length, type -- and a
    record may be split across blocks, in which case the pieces carry FIRST/MIDDLE/LAST types. **A parser that ignores
    the block boundaries reads garbage past the first 32 KiB**, which is the mistake this function exists to not make.
    """
    raw = path.read_bytes()
    BLOCK = 32768
    HEADER = 7
    out, pending = [], b''
    pos = 0
    while pos + HEADER <= len(raw):
        crc, length, rtype = struct.unpack('<IHB', raw[pos:pos + HEADER])
        pos += HEADER
        if length == 0 and rtype == 0:
            pos = (pos // BLOCK + 1) * BLOCK          # zero-filled trailer: skip to the next block
            continue
        if length > BLOCK:
            break
        chunk = raw[pos:pos + length]
        pos += length
        if rtype == 1:                                # FULL
            out.append(chunk)
        elif rtype == 2:                              # FIRST
            pending = chunk
        elif rtype == 3:                              # MIDDLE
            pending += chunk
        elif rtype == 4:                              # LAST
            out.append(pending + chunk)
            pending = b''
    return out


def read_varint(buf, pos):
    """A LevelDB varint32, which is what the record lengths actually are.

    **The bug this fixes was not a decode problem and showed up as one.** The first version read the key length as a
    single byte and the value length as a fixed four -- so every value came out shifted by one or two bytes, and the
    symptoms were all of the form "this looks like it should decode and does not": a JSON blob whose first character
    was missing, a UTF-16 blob whose byte pairs were misaligned into `∀搀愀 ...`, a value reported as undecoded when
    only its offset was wrong. **Nothing was encrypted.** The lengths are varints and reading them wrong moves
    everything after them.
    """
    shift = 0
    result = 0
    while True:
        if pos >= len(buf):
            raise ValueError('varint ran off the end')
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 35:
            raise ValueError('varint too long')


def parse_batch(record):
    """The key/value pairs inside one write batch."""
    if len(record) < 12:
        return []
    count, pos = struct.unpack('<I', record[8:12])[0], 12
    pairs = []
    for _ in range(count):
        if pos >= len(record):
            break
        kind = record[pos]
        pos += 1
        try:
            klen, pos = read_varint(record, pos)
            pair_key = record[pos:pos + klen]
            pos += klen
            if kind == 1:                             # kTypeValue
                vlen, pos = read_varint(record, pos)
                value = record[pos:pos + vlen]
                pos += vlen
            elif kind == 0:                           # kTypeDeletion
                value = None
            else:
                break
        except (ValueError, IndexError):
            break
        pairs.append((pair_key, value))
    return pairs


def load():
    """Every pair the store holds, newest last, so a later write wins the way LevelDB's own ordering would."""
    pairs = []
    for f in sorted(STORE.glob('*.log')):
        for rec in read_log(f):
            pairs.extend(parse_batch(rec))
    return pairs


def text(b):
    """Chromium's local-storage encoding, decoded. **The tag byte decides, and nothing else does.**

    Three attempts got this wrong in three different ways, which is worth writing down because each failure looked
    like a different problem:

      * decoding everything as UTF-8 turned the tagged values into `<911 binary bytes>`, which reads as encryption
        rather than as a missing decode step;
      * then stripping the first byte unconditionally took the opening quote off a plain JSON value and left the
        next character as the first -- so a readable blob looked unreadable;
      * then guarding with `str.isprintable()` rejected every *key*, because a Chromium local-storage key is
        `_<origin>\\x00<key>` and the NUL is not printable. The keys had been decoding correctly all along.

    The rule is only this: `0x00` in front means the rest is UTF-16LE, `0x01` means Latin-1, anything else is the
    string itself. A NUL is not a printable character and that has nothing to do with whether a string decoded.
    """
    if b is None:
        return None
    if not b:
        return ''
    if b[0] == 0:
        try:
            return b[1:].decode('utf-16-le')
        except UnicodeDecodeError:
            pass
    elif b[0] == 1:
        try:
            return b[1:].decode('latin-1')
        except UnicodeDecodeError:
            pass
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return '<%d bytes, undecoded, first byte 0x%02x>' % (len(b), b[0])


def short(k):
    """A key as a person reads it: `_<origin>\\x00\\x01<name>` shown as `<origin> / <name>`.

    **The second control byte is not decoration.** Chromium writes `_<origin>`, a NUL, then `\\x01`, then the key --
    the `\\x01` marking that the value is a string rather than a number. Splitting on the NUL alone leaves it attached
    to the name, so every comparison against a list of names fails while the printed form looks perfectly correct.
    That is what the allowlist did: it withheld everything, including the eight entries it exists to allow, and the
    output gave no sign of why.
    """
    if k is None:
        return ''
    parts = [p.strip('\x00\x01\x02\x03\x04') for p in k.split('\x00')]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        return '%s / %s' % (parts[0].lstrip('_'), ' / '.join(parts[1:]))
    return parts[0].lstrip('_') if parts else k


def looks_secret(key):
    k = key.lower()
    return any(word in k for word in SECRETISH)


def cmd_keys(_):
    pairs = load()
    newest = {}
    for k, v in pairs:
        newest[text(k)] = v
    print('  %d records, %d distinct keys' % (len(pairs), len(newest)))
    print('  ** only the keys named in SAFE_KEYS print their value; everything else reports its size. **')
    for k in sorted(newest):
        v = newest[k]
        if is_safe(k):
            s = text(v) or ''
            print('    %-34s  %s' % (short(k), s[:88] + ('...' if len(s) > 88 else '')))
        else:
            print('    %-34s  %s  (withheld: not on the list of known settings)'
                  % (short(k), ('%d bytes' % len(v)) if v else 'deleted'))
    return 0


def cmd_dump(args):
    newest = {}
    for k, v in load():
        newest[text(k)] = v
    for k in sorted(newest):
        v = newest[k]
        s = text(v)
        # **One test, and it is an allowlist.** Everything not on `SAFE_KEYS` is withheld and says so, which means a
        # key this tool has never seen arrives as a question rather than as a value in the scrollback.
        if not is_safe(k) and not args.show_secrets:
            print('  %s = <%d bytes, withheld -- not on SAFE_KEYS; --show-secrets to print>'
                  % (short(k), len(v) if v else 0))
            continue
        try:
            print('  %s = %s' % (short(k), json.dumps(json.loads(s), ensure_ascii=False, indent=2)))
        except (TypeError, ValueError):
            print('  %s = %r' % (short(k), s))
    return 0


def cmd_get(args):
    newest = {}
    for k, v in load():
        newest[text(k)] = v
    hit = [k for k in newest if args.key.lower() in k.lower()]
    if not hit:
        print('  no key matching %r' % args.key)
        return 1
    for k in hit:
        v = newest[k]
        print('  %s = %s' % (k, text(v)))
    return 0


def cmd_set(args):
    """Append a new value, which is what LevelDB itself would do.

    **A fresh record rather than an edit in place.** LevelDB's own ordering is by the log sequence, so the newest
    record for a key wins and rewriting the file in place would risk corrupting the store the app also reads. This
    appends one FULL record to a new `.log`, so it can be removed by deleting that file.
    """
    import binascii
    import time
    key = args.key.encode('utf-8')
    value = args.value.encode('utf-8')
    payload = struct.pack('<I', 1) + bytes([1, len(key)]) + key + struct.pack('<I', len(value)) + value
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    record = struct.pack('<IHB', crc, len(payload), 1) + payload
    out = STORE / ('%06d.log' % int(time.time()))
    out.write_bytes(record)
    print('  wrote %s (%d bytes): %s = %s' % (out.name, len(record), args.key, args.value))
    print('  ** close the app before and after: WebView2 keeps the store open and will not see this until restart. **')
    return 0


def main():
    if not STORE.exists():
        print('  no store at %s -- has the app been run?' % STORE)
        return 1
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('keys').set_defaults(fn=cmd_keys)
    p = sub.add_parser('dump'); p.add_argument('--show-secrets', action='store_true'); p.set_defaults(fn=cmd_dump)
    p = sub.add_parser('get'); p.add_argument('key'); p.set_defaults(fn=cmd_get)
    p = sub.add_parser('set'); p.add_argument('key'); p.add_argument('value'); p.set_defaults(fn=cmd_set)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == '__main__':
    raise SystemExit(main())
