"""Query-classification schema (M2 ships the schema ONLY; M4 hardens in place).

M2 needs these types importable so ``AgentState.analytics: QueryClassification | None``
resolves at runtime (LangGraph evaluates every state annotation). The classifier
function, structured-output call, retries, and the enums' ``_missing_`` hooks
(out-of-enum -> "other") are M4's — do not add them here.
"""

from enum import Enum

from pydantic import BaseModel


class QuestionType(str, Enum):
    factual = "factual"
    how_to = "how_to"
    comparison = "comparison"
    opinion = "opinion"
    troubleshooting = "troubleshooting"
    other = "other"


class Category(str, Enum):
    technology = "technology"
    science = "science"
    health = "health"
    finance_business = "finance_business"
    travel_geography = "travel_geography"
    entertainment_sports = "entertainment_sports"
    history_politics = "history_politics"
    lifestyle = "lifestyle"
    other = "other"


class QueryClassification(BaseModel):
    topic: str            # free-form, 1-4 lowercase words ("redis vector search")
    category: Category    # closed enum
    question_type: QuestionType
    language: str         # ISO 639-1
    confidence: float     # 0..1
