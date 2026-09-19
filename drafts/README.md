# drafts/ — articles the database refused

A file in here is a **finished, validated article** that could not be
inserted into D1 at the moment it was written, almost always because the
free tier's **daily row-READ limit** ran out (2026-09-16, and again on
2026-09-19 — that run had written 545 words, cleared `--check` with three
sources and three FAQ entries, and vetted an image, and all of it was
thrown away at the INSERT).

Nothing here is published yet. The next `Daily Article (AI)` run picks up
the oldest file before it goes looking for a new story:

```bash
python article_put.py --retry-pending
```

* published → the file is deleted and `data/articles.json` is regenerated
* the site covered the story meanwhile → the file is deleted
* older than `PENDING_MAX_H` (18h) → the file is deleted; it is news, not
  an archive
* D1 still refusing → the file stays exactly where it is

**Do not hand-edit `data/articles.json` to publish one of these.** That is
the race `article_put.py` exists to close: the id is allocated inside the
INSERT, and two runs rewriting the file both lose.

This directory is kept in git deliberately — an empty one still has to
exist, or the workflow's `git status --porcelain drafts` has no pathspec
to match.
