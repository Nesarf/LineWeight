# The learning library

**What this is, and why it is inside the repository.** Everything learned about drawing from the fifteen reference books
lives here rather than in a downloads folder or a research log, because a library that is not part of the tool is a
library the tool cannot use. `TODO.md` records what was tried and what went wrong; **this records what is known.**

**Three parts, and they are deliberately separate:**

- `sources.md` -- what the books are, who wrote them, where they are on this machine, and whether their text could be
  read or only their pictures. **A source with OCR noise and a source with clean text are different kinds of evidence
  and are marked as such.**
- `facts.json` -- **the countable lists.** Eight parts of the body, three kinds of line, seven types of folds, six
  parameters of a face. **These are the things a drawing can be checked against without measuring anything**, which is
  the one property every one of these books has in common and the one this project kept missing.
- `extracts/` -- the pages that carry a list or a rule, rendered out of the PDFs at a legible size. **A page kept as an
  image is a page that can be looked at again**, which is the whole point of the exercise that produced this library.

**A rule for what belongs in `facts.json`.** Only entries that are **finite and nameable** go in: a list that can be
counted to the end, with a name per item. Anything that is a proportion or a measurement stays in the prose, **because
this stretch established at length that a measured quantity is the thing that keeps being misread** -- and a countable
list is the thing that kept being right.
