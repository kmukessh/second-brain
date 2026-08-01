from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal, Dict, Any

PARACategory = Literal["Projects", "Areas", "Resources", "Archives"]
CaptureType = Literal["note", "link", "file"]


@dataclass
class CaptureMetadata:
    """Sidecar metadata for immutable raw captures in raw/*.meta.json"""
    id: str
    captured_at: str
    type: CaptureType
    source: str = "cli"
    original_filename: Optional[str] = None
    content_hash: Optional[str] = None
    processed: bool = False
    wiki_path: Optional[str] = None
    raw_file: Optional[str] = None
    author: Optional[str] = "Mukesh"
    author_github: Optional[str] = "https://github.com/kmukessh"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaptureMetadata":
        return cls(**data)


@dataclass
class WikiNote:
    """Processed markdown note schema living in wiki/ subfolders"""
    id: str
    title: str
    para_category: PARACategory
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    links: List[str] = field(default_factory=list)
    embedding_id: Optional[str] = None
    source_raw: Optional[str] = None
    body: str = ""

    def to_frontmatter_dict(self) -> Dict[str, Any]:
        """Return dict suitable for YAML frontmatter serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "para_category": self.para_category,
            "tags": self.tags,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "links": self.links,
            "embedding_id": self.embedding_id,
            "source_raw": self.source_raw,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], body: str = "") -> "WikiNote":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            para_category=data.get("para_category", "Resources"),
            tags=data.get("tags", []),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            links=data.get("links", []),
            embedding_id=data.get("embedding_id"),
            source_raw=data.get("source_raw"),
            body=body,
        )


@dataclass
class GraphNode:
    """Node schema for data/graph.json"""
    id: str
    label: str
    category: str
    tags: List[str] = field(default_factory=list)
    summary: str = ""
    wiki_path: str = ""
    size: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    """Edge schema for data/graph.json"""
    source: str
    target: str
    type: str = "semantic_similarity"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AskSource:
    """Source citation for RAG answers"""
    id: str
    title: str
    wiki_path: str
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AskResponse:
    """Response returned by ask.py RAG query"""
    answer: str
    sources: List[AskSource] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
        }
