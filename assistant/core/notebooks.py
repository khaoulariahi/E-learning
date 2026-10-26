"""Notebooks: a student's collection of sources for one course."""

import uuid

from pydantic import BaseModel

from assistant.core.db import connect, now


class Notebook(BaseModel):
    id: str
    name: str
    created_at: str


def create_notebook(name: str) -> Notebook:
    name = name.strip()
    if not name:
        raise ValueError("Notebook name is empty")
    nb = Notebook(id=uuid.uuid4().hex, name=name, created_at=now())
    connect().execute("INSERT INTO notebooks(id, name, created_at) VALUES (?, ?, ?)", (nb.id, nb.name, nb.created_at))
    return nb


def list_notebooks() -> list[Notebook]:
    rows = connect().execute("SELECT id, name, created_at FROM notebooks ORDER BY created_at DESC").fetchall()
    return [Notebook(**dict(r)) for r in rows]


def get_notebook(notebook_id: str) -> Notebook | None:
    row = connect().execute("SELECT id, name, created_at FROM notebooks WHERE id=?", (notebook_id,)).fetchone()
    return Notebook(**dict(row)) if row else None
