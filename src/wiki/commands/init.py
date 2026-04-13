"""wiki init — create wiki workspace."""

from __future__ import annotations

from pathlib import Path

from wiki.config import WIKI_DIRS


def run_init() -> None:
    cwd = Path.cwd()
    missing = [d for d in WIKI_DIRS if not (cwd / d).is_dir()]

    if not missing:
        print("Already a wiki directory. Nothing to do.")
        return

    for d in WIKI_DIRS:
        (cwd / d).mkdir(parents=True, exist_ok=True)

    # Scaffold index.md
    index_path = cwd / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text(
            "# Wiki Index\n\n"
            "## Entities\n\n"
            "## Concepts\n\n"
            "## Sources\n\n"
            "## Syntheses\n\n"
            "## Meta\n\n"
        )

    # Scaffold log.md
    log_path = cwd / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text("# Wiki Log\n\n")

    # .gitignore
    gitignore_path = cwd / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".obsidian/\nwiki/.chroma/\n.wiki/\n")

    # git init if needed
    import subprocess

    git_dir = cwd / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=cwd, check=True, capture_output=True)

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "bootstrap: initial workspace"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )

    print("Wiki workspace initialized.")
