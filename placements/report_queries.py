"""Load the Part 7 report statements from the project's SQL query bank."""

import re
from pathlib import Path

from django.conf import settings


_QUERY_HEADER = re.compile(r"^--\s*(Q\d+)\.\s*(.+?)\s*$", re.IGNORECASE)


def load_report_queries():
    """Return (display title, SELECT statement) pairs from database/queriesdb.sql."""
    query_file = Path(settings.BASE_DIR) / "database" / "queriesdb.sql"
    lines = query_file.read_text(encoding="utf-8-sig").splitlines()

    reports = []
    title = None
    statement_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        header = _QUERY_HEADER.match(line)
        if header:
            if statement_lines:
                raise ValueError(f"Query {title} is missing a terminating semicolon.")
            title = f"{header.group(1).upper()} · {header.group(2)}"
            continue

        if line.startswith("--") or line.upper().startswith("USE "):
            continue

        if title is None:
            continue

        statement_lines.append(line)
        if line.endswith(";"):
            statement = "\n".join(statement_lines).strip()
            reports.append((title, statement[:-1].rstrip()))
            title = None
            statement_lines = []

    if statement_lines:
        raise ValueError(f"Query {title} is missing a terminating semicolon.")

    return reports