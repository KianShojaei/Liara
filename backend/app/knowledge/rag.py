"""KnowledgeBase: the limitations registry (YAML) plus a small RAG over Liara docs.

Docs: Markdown/MDX files under app/knowledge/docs (clone github.com/liara-cloud/docs and
copy the folders paas, cli, domains, dns-management-system, references). Chunked by heading,
embedded with text-embedding-3-small when an LLM key exists, otherwise keyword scoring.
Index lives in a .npz next to the docs; answers cite the source file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from app.config import Settings

log = logging.getLogger("copilot.knowledge")

DOCS_DIR = Path(__file__).parent / "docs"
LIMITATIONS_FILE = Path(__file__).parent / "limitations.yaml"
INDEX_FILE = DOCS_DIR / ".index.npz"
CHUNK_MAX_CHARS = 1800


def chunk_markdown(text: str, source: str) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    heading, buffer = "", []
    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                chunks.append(
                    {
                        "source": source,
                        "heading": heading,
                        "text": "\n".join(buffer)[:CHUNK_MAX_CHARS],
                    }
                )
            heading, buffer = line.strip("# ").strip(), []
        else:
            buffer.append(line)
    if buffer:
        chunks.append(
            {"source": source, "heading": heading, "text": "\n".join(buffer)[:CHUNK_MAX_CHARS]}
        )
    return [c for c in chunks if len(c["text"].strip()) > 40]


class KnowledgeBase:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._limitations: list[dict[str, Any]] = (
            yaml.safe_load(LIMITATIONS_FILE.read_text(encoding="utf-8")) or []
        )
        self._chunks: list[dict[str, str]] = []
        self._vectors: np.ndarray | None = None
        self._load_docs()

    # ------------------------------------------------------- limitations

    def limitations(self) -> list[dict[str, Any]]:
        return self._limitations

    def limitation(self, limitation_id: str) -> dict[str, Any] | None:
        return next((item for item in self._limitations if item["id"] == limitation_id), None)

    # --------------------------------------------------------------- docs

    def _load_docs(self) -> None:
        if not DOCS_DIR.exists():
            return
        for file in sorted(DOCS_DIR.rglob("*.md*")):
            if file.name.startswith("."):
                continue
            rel = str(file.relative_to(DOCS_DIR))
            self._chunks.extend(
                chunk_markdown(file.read_text(encoding="utf-8", errors="ignore"), rel)
            )
        if INDEX_FILE.exists() and self._chunks:
            data = np.load(INDEX_FILE, allow_pickle=False)
            if int(data["count"]) == len(self._chunks):
                self._vectors = data["vectors"]

    @property
    def doc_count(self) -> int:
        return len(self._chunks)

    async def build_index(self, embed: Any) -> int:
        """embed(list[str]) -> list[list[float]]. Builds and persists the vector index."""
        if not self._chunks:
            return 0
        vectors: list[list[float]] = []
        for i in range(0, len(self._chunks), 64):
            vectors.extend(await embed([c["text"] for c in self._chunks[i : i + 64]]))
        self._vectors = np.asarray(vectors, dtype=np.float32)
        np.savez(INDEX_FILE, vectors=self._vectors, count=len(self._chunks))
        return len(self._chunks)

    async def search(self, query: str, *, k: int = 4, embed: Any = None) -> list[dict[str, Any]]:
        if not self._chunks:
            return []
        if self._vectors is not None and embed is not None:
            try:
                qvec = np.asarray((await embed([query]))[0], dtype=np.float32)
                scores = (
                    self._vectors
                    @ qvec
                    / (np.linalg.norm(self._vectors, axis=1) * np.linalg.norm(qvec) + 1e-9)
                )
                order = np.argsort(-scores)[:k]
                return [
                    {
                        **self._chunks[i],
                        "score": float(scores[i]),
                        "url": self._url(self._chunks[i]["source"]),
                    }
                    for i in order
                ]
            except Exception as exc:  # noqa: BLE001
                log.warning("embedding search failed, falling back to keywords: %s", exc)
        return await asyncio.to_thread(self._keyword_search, query, k)

    def _keyword_search(self, query: str, k: int) -> list[dict[str, Any]]:
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
        scored = []
        for chunk in self._chunks:
            hay = (chunk["heading"] + " " + chunk["text"]).lower()
            score = sum(hay.count(t) for t in terms)
            if score:
                scored.append((score, chunk))
        scored.sort(key=lambda s: -s[0])
        return [{**c, "score": float(s), "url": self._url(c["source"])} for s, c in scored[:k]]

    @staticmethod
    def _url(source: str) -> str:
        return (
            "https://docs.liara.ir/"
            + re.sub(r"\.(md|mdx)$", "", source).replace("index", "").rstrip("/")
            + "/"
        )

    def to_json(self) -> str:
        return json.dumps({"docs": self.doc_count, "limitations": len(self._limitations)})
