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
    is_meeting: bool = False
    calendar_event_id: Optional[str] = None
    calendar_event_link: Optional[str] = None
    calendar_account: Optional[str] = "mukesh"
    calendar_event_start: Optional[str] = None
    calendar_event_end: Optional[str] = None
    calendar_event_status: Optional[str] = None
    calendar_event_error: Optional[str] = None

    def to_frontmatter_dict(self) -> Dict[str, Any]:
        """Return dict suitable for YAML frontmatter serialization"""
        res = {
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
            "is_meeting": self.is_meeting,
        }
        if self.calendar_event_id:
            res["calendar_event_id"] = self.calendar_event_id
        if self.calendar_event_link:
            res["calendar_event_link"] = self.calendar_event_link
        if self.calendar_account:
            res["calendar_account"] = self.calendar_account
        if self.calendar_event_start:
            res["calendar_event_start"] = self.calendar_event_start
        if self.calendar_event_end:
            res["calendar_event_end"] = self.calendar_event_end
        if self.calendar_event_status:
            res["calendar_event_status"] = self.calendar_event_status
        if self.calendar_event_error:
            res["calendar_event_error"] = self.calendar_event_error
        return res

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
            is_meeting=bool(data.get("is_meeting", False)),
            calendar_event_id=data.get("calendar_event_id"),
            calendar_event_link=data.get("calendar_event_link"),
            calendar_account=data.get("calendar_account", "mukesh"),
            calendar_event_start=data.get("calendar_event_start"),
            calendar_event_end=data.get("calendar_event_end"),
            calendar_event_status=data.get("calendar_event_status"),
            calendar_event_error=data.get("calendar_event_error"),
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
    is_meeting: bool = False
    calendar_event_link: Optional[str] = None

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


@dataclass
class CalendarEvent:
    """Schema for Google Calendar Event representation."""
    id: str
    summary: str
    start_time: str
    end_time: str
    description: Optional[str] = ""
    location: Optional[str] = ""
    attendees: List[str] = field(default_factory=list)
    html_link: Optional[str] = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarEvent":
        start = data.get("start", {})
        end = data.get("end", {})
        start_str = start.get("dateTime", start.get("date", data.get("start_time", ""))) if isinstance(start, dict) else str(start)
        end_str = end.get("dateTime", end.get("date", data.get("end_time", ""))) if isinstance(end, dict) else str(end)

        attendees_raw = data.get("attendees", [])
        attendees_list = []
        if isinstance(attendees_raw, list):
            for a in attendees_raw:
                if isinstance(a, dict) and "email" in a:
                    attendees_list.append(a["email"])
                elif isinstance(a, str):
                    attendees_list.append(a)

        return cls(
            id=data.get("id", ""),
            summary=data.get("summary", "Untitled Event"),
            start_time=start_str,
            end_time=end_str,
            description=data.get("description", ""),
            location=data.get("location", ""),
            attendees=attendees_list,
            html_link=data.get("htmlLink", data.get("html_link", "")),
        )

