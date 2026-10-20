"""Pull the rule-bearing sentences out of a batch of saved tutorial pages.

**Why a separate script.** Ninety-two pages at roughly six useful paragraphs each is more text than is worth reading line
by line; what matters is which sentences carry a rule, and a rule is recognisable by its wording rather than by its
position. So this ranks each paragraph by how many rule-shaped phrases it contains and keeps the best few per article.

**What counts as rule-shaped.** A sentence that tells the reader to do or not do something, or that carries a number,
or that names a proportion. The patterns below are the Chinese and the English forms the two sites actually use --
adding a pattern for a wording that never appears would make the ranking look thorough without making it better.
"""
import json
import pathlib
import re

TMP = pathlib.Path(r'E:\DaShaoHuo\cache\tmp')
OUT = pathlib.Path(r'E:\DaShaoHuo\cache\medibang_keylines.json')

#: Strong markers: the sentence is almost certainly a prescription.
STRONG = [
    '必須', '不要', '避免', '記得', '重點', '關鍵', '訣竅', '建議', '留意', '注意',
    '建議先', '原則', '絕對', '千萬', '一定', '正確', '錯誤', '常見', '初學者',
]
#: A number next to a body word means a proportion is being stated.
NUMBERED = re.compile(r'(\d+\s*(?:分之|倍|個|頭身|等分|公分|%))|'
                      r'(?:一|二|三|四|五|六|七|八|九|十)\s*(?:等分|分之|倍|頭身)')

BODY = ['臉', '頭', '眼', '鼻', '嘴', '耳', '手', '腳', '腿', '臂', '肩', '腰', '身體', '髮', '肌']
#: Paragraphs that are navigation, footers or JSON-LD rather than prose.
NOISE = re.compile(r'^\{"@|^&nbsp;$|^https?://|^[（(]?文字和圖片|立即免費下載|推薦的功能|'
                   r'^Twitter|^\s*$')


def sentences(html):
    ps = re.findall(r'(?s)<(?:p|h2|h3|li)[^>]*>(.*?)</(?:p|h2|h3|li)>', html)
    out = []
    for p in ps:
        t = re.sub(r'<[^>]+>', '', p).strip()
        t = t.replace('&nbsp;', ' ').replace('&#8220;', '"').replace('&#8221;', '"')
        t = re.sub(r'\s+', ' ', t)
        if len(t) >= 18 and not NOISE.search(t):
            out.append(t)
    return out


def score(s):
    n = sum(1 for w in STRONG if w in s)
    if NUMBERED.search(s):
        n += 2
    if any(b in s for b in BODY):
        n += 1
    # A long sentence that merely contains 注意 is usually a preamble; a short one is a rule.
    if len(s) > 110:
        n -= 1
    return n


def main():
    files = sorted(TMP.glob('art-*.html')) + sorted(TMP.glob('face-*.html')) + \
        sorted(TMP.glob('cs-*.html')) + sorted(TMP.glob('cs2-*.html')) + sorted(TMP.glob('cs3-*.html'))
    rows = []
    for f in files:
        html = f.read_text(encoding='utf-8', errors='replace')
        title = re.search(r'<title>(.*?)</title>', html)
        title = (title.group(1).split('|')[0].strip() if title else f.stem)
        if not title or len(title) < 4:
            continue
        cand = [(score(s), i, s) for i, s in enumerate(sentences(html))]
        cand = [c for c in cand if c[0] >= 2]
        cand.sort(key=lambda c: (-c[0], c[1]))
        picked, seen = [], set()
        for n, i, s in cand:
            key = s[:24]
            if key in seen:
                continue
            seen.add(key)
            picked.append(s[:300])
            if len(picked) >= 3:
                break
        if picked:
            rows.append({'file': f.name, 'title': title, 'lines': picked})

    rows.sort(key=lambda r: r['title'])
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('  %d articles with rule-bearing lines -> %s' % (len(rows), OUT))
    for r in rows:
        print()
        print('  == %s' % r['title'])
        for s in r['lines']:
            print('     - %s' % s)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
