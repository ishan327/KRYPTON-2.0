"""In-memory NCERT library: catalogue, BM25 search and context building."""
import pickle
import random
from collections import Counter, defaultdict

from config import INDEX_DIR
from textutil import tokenize

K1, B = 1.4, 0.75


class Library:
    def __init__(self):
        self.chunks: list[dict] = []
        self.chapters: list[dict] = []
        self.index: dict = {"postings": {}, "lengths": [], "avgdl": 1, "idf": {}}
        self.by_chapter: dict[tuple, list[int]] = defaultdict(list)
        self.load()

    def load(self):
        path = INDEX_DIR / "library.pkl"
        if path.exists():
            with open(path, "rb") as f:
                data = pickle.load(f)
        elif (INDEX_DIR / "library.pkl.gz").exists():  # compressed copy used by the cloud version
            import gzip
            with gzip.open(INDEX_DIR / "library.pkl.gz", "rb") as f:
                data = pickle.load(f)
        else:
            return
        self.chunks, self.chapters, self.index = data["chunks"], data["chapters"], data["index"]
        self.by_chapter = defaultdict(list)
        for i, c in enumerate(self.chunks):
            self.by_chapter[(c["code"], c["ch"])].append(i)

    @property
    def ready(self) -> bool:
        return bool(self.chunks)

    def stats(self) -> dict:
        return {"chunks": len(self.chunks), "chapters": len(self.chapters),
                "books": len({c["code"] for c in self.chapters}),
                "classes": sorted({c["cls"] for c in self.chapters})}

    def catalog(self) -> dict:
        out: dict = {}
        for c in self.chapters:
            subj = out.setdefault(str(c["cls"]), {}).setdefault(c["subject"], {})
            book = subj.setdefault(c["code"], {"code": c["code"], "title": c["book"], "chapters": []})
            book["chapters"].append({"ch": c["ch"], "title": c["title"], "exercises": len(c["exercises"])})
        return {cls: {s: list(books.values()) for s, books in subs.items()} for cls, subs in out.items()}

    # ---------- selection ----------
    def chapter_info(self, code: str, ch: int) -> dict | None:
        return next((c for c in self.chapters if c["code"] == code and c["ch"] == ch), None)

    def selected_chapters(self, cls=None, subject=None, chapters=None) -> list[dict]:
        if chapters:
            keys = {(k.split(":")[0], int(k.split(":")[1])) for k in chapters if ":" in k}
            return [c for c in self.chapters if (c["code"], c["ch"]) in keys]
        return [c for c in self.chapters
                if (cls is None or c["cls"] == cls) and (not subject or c["subject"] == subject)]

    def _candidates(self, cls, subject, chapters) -> set[int] | None:
        if not (cls or subject or chapters):
            return None
        ids = set()
        for c in self.selected_chapters(cls, subject, chapters):
            ids.update(self.by_chapter[(c["code"], c["ch"])])
        return ids

    # ---------- search ----------
    def search(self, query: str, cls=None, subject=None, chapters=None, k: int = 8) -> list[tuple[float, dict]]:
        cand = self._candidates(cls, subject, chapters)
        q = tokenize(query)
        if not q:
            return []
        scores: Counter = Counter()
        post, lengths, avgdl, idf = (self.index[x] for x in ("postings", "lengths", "avgdl", "idf"))
        for term in set(q):
            for doc, tf in post.get(term, ()):
                if cand is not None and doc not in cand:
                    continue
                denom = tf + K1 * (1 - B + B * lengths[doc] / avgdl)
                scores[doc] += idf[term] * tf * (K1 + 1) / denom
        return [(s, self.chunks[d]) for d, s in scores.most_common(k)]

    def sample(self, cls=None, subject=None, chapters=None, k: int = 8, seed=None) -> list[dict]:
        """Spread chunks evenly across the selected chapters (used when no topic is typed)."""
        sel = self.selected_chapters(cls, subject, chapters)
        if not sel:
            return []
        rng = random.Random(seed)
        if len(sel) > k:
            sel = rng.sample(sel, k)
        per = max(1, k // len(sel))
        out = []
        for c in sel:
            ids = [i for i in self.by_chapter[(c["code"], c["ch"])] if len(self.chunks[i]["text"]) > 300]
            if not ids:
                ids = self.by_chapter[(c["code"], c["ch"])]
            step = max(1, len(ids) // per)
            out += [self.chunks[i] for i in ids[::step][:per]]
        return out[:k]

    def gather(self, query: str, cls=None, subject=None, chapters=None, k: int = 8) -> list[dict]:
        if query.strip():
            hits = [c for _, c in self.search(query, cls, subject, chapters, k)]
            if hits:
                return hits
            if cls or subject or chapters:  # topic not found in this subject: search everything in the class
                hits = [c for _, c in self.search(query, cls, None, None, k)]
                if hits:
                    return hits
        return self.sample(cls, subject, chapters, k)

    @staticmethod
    def to_context(chunks: list[dict], max_chars: int) -> tuple[str, list[dict]]:
        parts, sources, used = [], [], 0
        for i, c in enumerate(chunks, start=1):
            block = f"[S{i}] Class {c['cls']} {c['subject']} — {c['book']}, Ch {c['ch']} \"{c['ch_title']}\", page {c['page']}\n{c['text']}"
            if used + len(block) > max_chars and parts:
                break
            parts.append(block)
            used += len(block)
            sources.append({"id": f"S{i}", "label": f"Class {c['cls']} · {c['book']} · Ch {c['ch']}: {c['ch_title']}",
                            "page": c["page"], "code": c["code"], "ch": c["ch"]})
        return "\n\n".join(parts), sources


library = Library()
