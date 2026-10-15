"""Three routes to one pixiv image, compared by the bytes rather than by the status code.

**What is being asked.** The viewer's own store says it proxies images through `i.pixiv.re` and has
`PXV_PXIMG_DIRECT` set true, which together look like a route that needs no session and maybe no proxy. The route
already in use here is `i.pximg.net` with a `Referer`, through mihomo. So: same artwork, three ways, and the question
is which of them returns **the same file** -- a 200 with a placeholder, a login wall or a resized copy all look like
success to a status check, and only the bytes settle it.

    python pixiv_routes.py
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

PROXY = 'http://127.0.0.1:10090'
TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp\pixiv-routes')
TMP.mkdir(parents=True, exist_ok=True)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/131.0 Safari/537.36')
SEARCH = ('https://www.pixiv.net/ajax/search/artworks/%s?word=%s&order=date_d&mode=all&p=1'
          '&s_mode=s_tag&type=all&lang=ja')


def curl(url, out, proxy=None, referer=None, timeout=45):
    """One request, reported as the things that can actually be checked.

    **The fields are separated by a pipe and not by a space**, because curl's `content_type` carries its own space:
    `application/json; charset=utf-8`. Splitting on spaces put "charset=utf-8" where the byte count belonged and the
    parse died on it -- a separator has to be something the data cannot contain.
    """
    cmd = ['curl', '-s', '--max-time', str(timeout), '-o', str(out),
           '-w', '%{http_code}|%{content_type}|%{size_download}']
    if proxy:
        cmd += ['-x', proxy]
    cmd += ['-H', 'User-Agent: ' + UA]
    if referer:
        cmd += ['-H', 'Referer: ' + referer]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    parts = r.stdout.strip().split('|')
    code = parts[0] if parts else ''
    ctype = parts[1] if len(parts) > 1 else ''
    size = parts[2] if len(parts) > 2 else '0'
    path = pathlib.Path(out)
    digest = None
    if path.exists() and path.stat().st_size:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return {'http': code.strip(), 'type': ctype.strip(), 'bytes': int(size or 0), 'sha': digest,
            'url': url}


def main():
    import urllib.parse
    tag = 'アニメ塗り'
    q = urllib.parse.quote(tag)
    found = TMP / 'search.json'
    r = curl(SEARCH % (q, q), found, proxy=PROXY, referer='https://www.pixiv.net/')
    print('  search: HTTP %s, %d bytes' % (r['http'], r['bytes']))
    try:
        data = json.loads(found.read_text(encoding='utf-8'))
        items = data['body']['illustManga']['data']
    except Exception as exc:
        print('  could not read the search: %s' % exc)
        return 1

    # one work, and its own thumbnail URL -- which is where the full path comes from
    pick = None
    for it in items:
        if it.get('id') and it.get('url') and not it.get('xRestrict') and it.get('illustType') in (0, None):
            pick = it
            break
    if not pick:
        print('  no usable work in the results')
        return 1

    master = re.sub(r'/c/[\d]+x[\d]+(_\d+)?(_a\d+)?/', '/', pick['url'])
    master = re.sub(r'_square1200\.', '_master1200.', master)
    print('  work %s  %s' % (pick['id'], pick.get('title', '')[:50]))
    print('  full path on i.pximg.net: %s' % master)

    host, _, path = master.partition('i.pximg.net')
    mirror = 'https://i.pixiv.re' + path
    print('  same path on the mirror : %s' % mirror)
    print()

    routes = [
        ('i.pximg.net + Referer + mihomo', master, PROXY, 'https://www.pixiv.net/', 'pximg'),
        ('i.pixiv.re  no Referer, direct', mirror, None, None, 'mirror-direct'),
        ('i.pixiv.re  no Referer, mihomo', mirror, PROXY, None, 'mirror-proxy'),
        ('i.pixiv.re  WITH Referer, direct', mirror, None, 'https://www.pixiv.net/', 'mirror-ref'),
        ('i.pximg.net direct (no proxy)', master, None, 'https://www.pixiv.net/', 'pximg-direct'),
    ]
    results = []
    print('  %-32s %-6s %-18s %9s  %s' % ('route', 'http', 'content-type', 'bytes', 'sha256[:16]'))
    for label, url, proxy, referer, tag_ in routes:
        out = TMP / (tag_ + '.bin')
        if out.exists():
            out.unlink()
        r = curl(url, out, proxy=proxy, referer=referer)
        results.append((label, r))
        print('  %-32s %-6s %-18s %9d  %s'
              % (label, r['http'], r['type'] or '-', r['bytes'], r['sha'] or '-'))

    print()
    good = [r for _, r in results if r['http'] == '200' and 'image' in (r['type'] or '')]
    if not good:
        print('  nothing returned an image')
        return 1
    reference = good[0]['sha']
    print('  %d of %d routes returned an image' % (len(good), len(results)))
    for label, r in results:
        if r['http'] == '200' and 'image' in (r['type'] or ''):
            same = 'the same bytes' if r['sha'] == reference else 'DIFFERENT bytes'
            print('    %-32s %s' % (label, same))
        else:
            print('    %-32s no image (HTTP %s)' % (label, r['http']))
    print()
    print('  ** "the same bytes" is the only comparison that means anything here: a resized copy, a placeholder and')
    print('     the original are all HTTP 200 with an image content type. **')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
