"""Slugify a niche or subreddit name into a filesystem-safe identifier."""
import re


class SlugError(ValueError):
    """Raised when a name cannot produce a non-empty slug."""


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase ASCII slug: non-alphanumerics collapse to a single ``-``,
    leading/trailing ``-`` stripped. Raises ``SlugError`` if empty."""
    if not isinstance(name, str):
        raise SlugError(f"name must be str, got {type(name).__name__}")
    ascii_only = name.encode("ascii", errors="ignore").decode("ascii").lower()
    slug = _NON_ALNUM.sub("-", ascii_only).strip("-")
    if not slug:
        raise SlugError(f"name {name!r} produces empty slug after normalisation")
    return slug


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: slug.py <name>", file=sys.stderr)
        sys.exit(2)
    try:
        print(slugify(sys.argv[1]))
    except SlugError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
