"""Parse BibTeX content into readable text."""
import logging

logger = logging.getLogger(__name__)


def parse_bibtex(raw: str) -> str:
    """Parse BibTeX string and return human-readable formatted text."""
    if not raw.strip():
        return ""

    try:
        import bibtexparser
        from bibtexparser.bparser import BibTexParser

        parser = BibTexParser(common_strings=True)
        bib_db = bibtexparser.loads(raw, parser=parser)

        lines = []
        for entry in bib_db.entries:
            parts = []
            entry_type = entry.get("ENTRYTYPE", "article").upper()
            key = entry.get("ID", "")
            parts.append(f"[{entry_type}] {key}")

            for field in ("author", "title", "journal", "booktitle", "year",
                          "volume", "number", "pages", "doi", "url", "publisher"):
                val = entry.get(field, "").strip()
                if val:
                    parts.append(f"  {field}: {val}")

            lines.append("\n".join(parts))

        return "\n\n".join(lines)
    except Exception as exc:
        logger.warning("bibtex parse failed: %s", exc)
        # Fallback: return raw text
        return raw
