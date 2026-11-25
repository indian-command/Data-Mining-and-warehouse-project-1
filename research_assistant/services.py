import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from pgvector.django import CosineDistance

from papers.models import Paper, PaperChunk
from papers.services import EmbeddingService
from research_library.models import ResearchResource
from trends.services import EventLogger

logger = logging.getLogger(__name__)
User = get_user_model()


class ResearchAssistantService:
    """RAG-powered academic research assistant grounded in stored paper chunks with citations."""

    SYSTEM_PROMPT = """You are the Chanakya Research Assistant, an academic AI grounded strictly in verifiable university research.
Answer the user's research question clearly, objectively, and accurately using ONLY the context passages provided below.
Cite sources using bracketed numbers like [1], [2] immediately following every claim made.
If the provided passages do not contain sufficient evidence, state clearly what is supported by the passages and what cannot be determined without hallucinating.

CONTEXT PASSAGES:
{context}

QUESTION:
{question}

GROUNDED ANSWER (with citations [1], [2]):"""

    @classmethod
    def ask(cls, question: str, top_k: int = 5, user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes grounded retrieval and generation:
        1. Encodes question into 384-d vector
        2. Retrieves top-k paper chunks via pgvector CosineDistance
        3. Invokes local Ollama LLM (llama3.2) with deterministic extractive fallback
        4. Returns answer and structured source passages with citations
        """
        clean_question = question.strip()
        if not clean_question:
            return {"answer": "Please ask a research question.", "sources": [], "grounded": False}

        # Log Q&A event
        EventLogger.log_event(
            user=user,
            event_type="search",
            target_type="assistant_query",
            target_id=clean_question[:100],
            metadata={"question": clean_question},
        )

        query_emb = EmbeddingService.generate_embedding(clean_question)

        # 1. Retrieve top-k relevant chunks
        chunks = (
            PaperChunk.objects.select_related("paper")
            .filter(embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", query_emb))
            .order_by("distance")[:top_k]
        )

        sources: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        if chunks.exists():
            for idx, chunk in enumerate(chunks, start=1):
                paper = chunk.paper
                sim = max(0.0, 1.0 - float(chunk.distance or 1.0))
                sources.append({
                    "citation_id": idx,
                    "paper_id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors_display,
                    "venue": paper.venue or "Scholarly Archive",
                    "year": paper.published_year or "Recent",
                    "url": paper.url or f"/papers/{paper.id}/",
                    "passage": chunk.chunk_text,
                    "similarity": round(sim, 3),
                })
                context_parts.append(
                    f"[{idx}] Title: {paper.title} ({paper.published_year or 'n.d.'})\n"
                    f"Authors: {paper.authors_display}\n"
                    f"Content: {chunk.chunk_text}"
                )
        else:
            # Fallback to Paper titles and abstracts if chunks not yet populated
            papers = Paper.objects.all().order_by("-pagerank_score")[:top_k]
            for idx, paper in enumerate(papers, start=1):
                sources.append({
                    "citation_id": idx,
                    "paper_id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors_display,
                    "venue": paper.venue,
                    "year": paper.published_year,
                    "url": paper.url or f"/papers/{paper.id}/",
                    "passage": paper.abstract[:300] if paper.abstract else paper.title,
                    "similarity": 0.5,
                })
                context_parts.append(
                    f"[{idx}] Title: {paper.title}\nPassage: {paper.abstract[:300]}"
                )

        formatted_context = "\n\n".join(context_parts)
        prompt = cls.SYSTEM_PROMPT.format(context=formatted_context, question=clean_question)

        # 2. Attempt generation via Ollama
        answer = cls._call_ollama(prompt)

        # 3. Fallback to deterministic extractive synthesis if Ollama is unreachable
        if not answer:
            answer = cls._extractive_fallback(clean_question, sources)

        return {
            "question": clean_question,
            "answer": answer,
            "sources": sources,
            "grounded": True,
        }

    @classmethod
    def _call_ollama(cls, prompt: str) -> Optional[str]:
        """Calls Ollama HTTP API (e.g. llama3.2)."""
        ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "top_p": 0.9},
        }

        try:
            resp = requests.post(ollama_url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("response", "").strip()
                if response_text:
                    return response_text
        except Exception as e:
            logger.info(f"Ollama local LLM call bypassed ({e}). Using deterministic extractive synthesis.")
        return None

    @classmethod
    def _extractive_fallback(cls, question: str, sources: List[Dict[str, Any]]) -> str:
        """Deterministic, grounded extractive synthesis with inline citations [1], [2]."""
        if not sources:
            return (
                "No relevant research passages were found in the library for this query. "
                "Try searching for broader keywords in Unified Search."
            )

        q_terms = set(re.findall(r"\w+", question.lower()))
        paragraphs = []

        for src in sources[:3]:
            passage = src["passage"]
            cid = src["citation_id"]
            title = src["title"]

            # Select the sentence with highest query term overlap
            sentences = re.split(r"(?<=[.!?])\s+", passage)
            best_sentence = sentences[0]
            best_overlap = 0

            for s in sentences:
                s_terms = set(re.findall(r"\w+", s.lower()))
                overlap = len(q_terms & s_terms)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_sentence = s

            clean_sentence = best_sentence.strip()
            if not clean_sentence.endswith("."):
                clean_sentence += "."

            paragraphs.append(
                f"According to research in *{title}* [{cid}], {clean_sentence}"
            )

        combined_answer = (
            " ".join(paragraphs)
            + " These findings highlight key academic insights across the retrieved research literature."
        )
        return combined_answer

