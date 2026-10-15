"""Wire --against into the command line.

    python patch_cli.py
"""
import pathlib

P = pathlib.Path(r'E:\lineweight\lineweight\core.py')

EDITS = [
    ("    parser.add_argument('--fit', default='', metavar='IMAGE',",
     "    parser.add_argument('--against', default='corpus', choices=('corpus', 'linework'),\n"
     "                        help='which checked-in summary to compare against: the pooled corpus, or the design '\n"
     "                             'sheets. They record different things -- the design-sheet summary knows how much '\n"
     "                             'of each drawing the 2..16 px window drops, and the corpus does not.')\n"
     "    parser.add_argument('--fit', default='', metavar='IMAGE',"),
    ('        return fit_report(args.fit)', '        return fit_report(args.fit, against=args.against)'),
    ('        return fit_directory(args.fit_dir)', '        return fit_directory(args.fit_dir, against=args.against)'),
]


def main():
    s = P.read_text(encoding='utf-8')
    for i, (old, new) in enumerate(EDITS, 1):
        n = s.count(old)
        if n != 1:
            raise SystemExit('anchor %d matched %d times:\n%r' % (i, n, old[:80]))
        s = s.replace(old, new)
        print('  anchor %d applied' % i)
    P.write_text(s, encoding='utf-8')
    print('  the flag is wired')


if __name__ == '__main__':
    main()
