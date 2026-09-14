"""AFSL discipline: the repository never carries the banned vocabulary or an em-dash.

The banned list is assembled from fragments so this file passes its own check.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".yml", ".yaml", ".txt", ".cfg", ".lock", ""}

_PARTS = [
    ("adv", "ice"),
    ("recomm", "end"),
    ("guar", "antee"),
    ("optim", "al"),
    ("optim", "ise"),
    ("optim", "ize"),
    ("outperf", "orm"),
    ("should inv", "est"),
    ("returns ", "of"),
    ("best strat", "egy"),
    ("beat the ", "market"),
]
BANNED = ["".join(p) for p in _PARTS]
EM_DASH = "\u2014"


def repo_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def test_repository_is_free_of_banned_terms():
    offenders = []
    for path in repo_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in BANNED:
            for m in re.finditer(re.escape(word), text):
                line = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line}: {word!r}")
    assert not offenders, "\n".join(offenders)


def test_repository_is_free_of_em_dashes():
    offenders = [
        str(p.relative_to(ROOT))
        for p in repo_files()
        if p.name != "uv.lock" and EM_DASH in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, offenders


def test_banned_list_covers_the_brief():
    assert len(BANNED) == 11
