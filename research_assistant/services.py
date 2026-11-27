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

    MIN_SIMILARITY = 0.30
    MIN_CHUNK_WORDS = 12
    GREETINGS = {
        "hi", "hello", "hlo", "hey", "hola", "greetings",
        "good morning", "good afternoon", "good evening", "howdy", "sup", "yo", "hai",
    }

    _GARBLED_REPLACEMENTS = {
        "Kau?ilya": "Kautilya",
        "Artha??stra": "Arthashastra",
        "Mah?bh?rata": "Mahabharata",
        "??bdabodha": "Sabdabodha",
        "P??inian": "Paninian",
        "Vi?vahit?ya": "Visvahitaya",
        "g?t?": "gita",
        "vyaktitvavikasanas?dhanam": "vyaktitvavikasanasadhanam",
        "Nirantarakarmakara?a?": "Nirantarakarmakarana",
        "San?tana": "Sanatana",
        "Bh?skar?c?rya": "Bhaskaracarya",
        "?ryabha?a": "Aryabhata",
        "?ryabha??ya": "Aryabhatiya",
        "L?l?vat?": "Lilavati",
        "Avadh?nam": "Avadhanam",
        "avadh?nam": "avadhanam",
        "avadh?nin": "avadhanin",
        "GRAHA?AMUKURA": "GRAHANAMUKURA",
        "Graha?amukura": "Grahanamukura",
        "Kanna?a": "Kannada",
        "Dema?a": "Demana",
        "?a?karan?r?ya?a": "Sankaranarayana",
        "?a?kara": "Sankara",
        "V?riyar": "Variyar",
        "dhruvat?r?": "dhruvatara",
        "t?r?": "tara",
        "Pur??as": "Puranas",
        "siddh?ntas": "siddhantas",
        "Sidd?ntic": "Siddhantic",
        "Jy?nayana": "Jyanayana",
        "s?taka": "sataka",
        "m?nava??stradi?da": "manavasastradinda",
        "ac?r?m?m??seya": "acaramimanseya",
        "ka?ege": "kanege",
        "?-linkers": "π-linkers",
        "?-linker": "π-linker",
        "?-Linkers": "π-Linkers",
        "?-electron": "π-electron",
    }

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
    def clean_garbled_text(cls, text: str) -> str:
        """Cleans garbled '?' diacritic replacement artifacts while preserving real question punctuation."""
        if not text:
            return ""
        for k, v in cls._GARBLED_REPLACEMENTS.items():
            text = text.replace(k, v)
        text = re.sub(r"(\d+)\?±\?(\d+)", r"\1 ± \2", text)
        text = re.sub(r"(\d+)\?%", r"\1%", text)
        text = re.sub(r"(\d+)\?s\b", r"\1 s", text)
        text = text.replace("cm?2", "cm²").replace("Cu3?xP", "Cu3-xP")
        text = text.replace("often?overlooked", "often-overlooked")
        text = text.replace("?ean-energy", "clean-energy").replace("or?-energy", "or bio-energy")
        text = re.sub(r"(?<=[a-zA-Z])\?+(?=[a-zA-Z])", "", text)
        text = re.sub(r"\?(?=[a-zA-Z])", "", text)
        text = re.sub(r"(?<=[a-zA-Z])\?(?=[,;:'\"])", "", text)
        return text

    @classmethod
    def _is_greeting_or_short(cls, query: str) -> bool:
        """Detects casual greetings or non-research inputs shorter than 4 characters."""
        if len(query) < 4:
            return True
        normalized = re.sub(r"[^\w\s]", "", query.lower()).strip()
        if not normalized or len(normalized) < 4:
            return True
        if normalized in cls.GREETINGS:
            return True
        return any(normalized.startswith(g + " ") and len(normalized.split()) <= 3 for g in cls.GREETINGS)

    @classmethod
    def _get_sample_questions(cls) -> List[str]:
        """Builds 3 sample research questions grounded in topics/papers in our database."""
        defaults = [
            "What are the applications of deep learning in healthcare?",
            "How do transformer architectures improve natural language processing?",
            "What are the current challenges in quantum computing?",
        ]
        try:
            titles = list(
                Paper.objects.filter(chunks__isnull=False)
                .distinct()
                .order_by("-pagerank_score")
                .values_list("title", flat=True)[:3]
            )
            if len(titles) == 3:
                return [
                    f"What are the key findings of {cls.clean_garbled_text(titles[0])}?",
                    defaults[0],
                    defaults[1],
                ]
        except Exception:
            pass
        return defaults

    @classmethod
    def ask(cls, question: str, top_k: int = 5, user: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes grounded retrieval and generation:
        1. Handles greetings / short non-research queries without vector search
        2. Encodes question into 384-d vector and retrieves distinct-paper chunks (>= 0.30 sim, >= 12 words)
        3. Invokes local Ollama LLM (llama3.2) with deterministic extractive fallback
        4. Returns answer, generation_mode, and structured source passages with citations
        """
        clean_question = question.strip()
        model_name = getattr(settings, "OLLAMA_MODEL", "llama3.2")

        if not clean_question:
            return {
                "question": "",
                "answer": "Please ask a research question.",
                "sources": [],
                "grounded": False,
                "generation_mode": "greeting",
                "model_name": model_name,
                "is_greeting": True,
                "sample_questions": cls._get_sample_questions(),
            }

        if cls._is_greeting_or_short(clean_question):
            return {
                "question": clean_question,
                "answer": (
                    "Hello! I am the Chanakya Academic Research Assistant. "
                    "Ask any research question and I will synthesize an evidence-backed answer "
                    "with inline citations [1], [2] from our university library.\n\n"
                    "Try one of these sample research questions:"
                ),
                "sources": [],
                "grounded": False,
                "generation_mode": "greeting",
                "model_name": model_name,
                "is_greeting": True,
                "sample_questions": cls._get_sample_questions(),
            }

        # Log Q&A event
        EventLogger.log_event(
            user=user,
            event_type="search",
            target_type="assistant_query",
            target_id=clean_question[:100],
            metadata={"question": clean_question},
        )

        query_emb = EmbeddingService.generate_embedding(clean_question)

        # 1. Retrieve candidate chunks and filter by similarity >= 0.30, word count >= 12, unique paper_id
        has_indexed_chunks = PaperChunk.objects.filter(embedding__isnull=False).exists()
        sources: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        if has_indexed_chunks:
            candidate_chunks = (
                PaperChunk.objects.select_related("paper")
                .filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", query_emb))
                .order_by("distance")[: top_k * 6]
            )
            seen_paper_ids = set()
            for chunk in candidate_chunks:
                sim = max(0.0, 1.0 - float(chunk.distance or 1.0))
                if sim < cls.MIN_SIMILARITY:
                    continue

                cleaned_passage = cls.clean_garbled_text(chunk.chunk_text).strip()
                if len(cleaned_passage.split()) < cls.MIN_CHUNK_WORDS:
                    continue

                paper = chunk.paper
                if paper.id in seen_paper_ids:
                    continue
                seen_paper_ids.add(paper.id)

                cid = len(sources) + 1
                clean_title = cls.clean_garbled_text(paper.title)
                sources.append({
                    "citation_id": cid,
                    "paper_id": paper.id,
                    "title": clean_title,
                    "authors": paper.authors_display,
                    "venue": paper.venue or "Scholarly Archive",
                    "year": paper.published_year or "Recent",
                    "url": paper.url or f"/papers/{paper.id}/",
                    "passage": cleaned_passage,
                    "similarity": round(sim, 3),
                })
                context_parts.append(
                    f"[{cid}] Title: {clean_title} ({paper.published_year or 'n.d.'})\n"
                    f"Authors: {paper.authors_display}\n"
                    f"Content: {cleaned_passage[:500]}"
                )
                if len(sources) >= top_k:
                    break

            if not sources:
                return {
                    "question": clean_question,
                    "answer": (
                        "I could not find any research passages in the Chanakya repository with sufficient "
                        f"semantic relevance (similarity ≥ {cls.MIN_SIMILARITY:.2f}) for that query. "
                        "Please try phrasing your question with specific academic keywords or explore the sample topics below."
                    ),
                    "sources": [],
                    "grounded": False,
                    "generation_mode": "extractive",
                    "model_name": model_name,
                    "is_greeting": False,
                    "sample_questions": cls._get_sample_questions(),
                }
        else:
            # Fallback to Paper titles and abstracts if chunks not yet populated
            papers = Paper.objects.all().order_by("-pagerank_score")[:top_k]
            for idx, paper in enumerate(papers, start=1):
                clean_title = cls.clean_garbled_text(paper.title)
                clean_abs = cls.clean_garbled_text(paper.abstract[:300] if paper.abstract else paper.title)
                sources.append({
                    "citation_id": idx,
                    "paper_id": paper.id,
                    "title": clean_title,
                    "authors": paper.authors_display,
                    "venue": paper.venue,
                    "year": paper.published_year,
                    "url": paper.url or f"/papers/{paper.id}/",
                    "passage": clean_abs,
                    "similarity": 0.5,
                })
                context_parts.append(f"[{idx}] Title: {clean_title}\nPassage: {clean_abs}")

        formatted_context = "\n\n".join(context_parts)
        prompt = cls.SYSTEM_PROMPT.format(context=formatted_context, question=clean_question)

        # 2. Attempt generation via Ollama
        answer = cls._call_ollama(prompt)
        if answer:
            generation_mode = "ollama"
        else:
            # 3. Fallback to deterministic extractive synthesis if Ollama is unreachable
            answer = cls._extractive_fallback(clean_question, sources)
            generation_mode = "extractive"

        return {
            "question": clean_question,
            "answer": answer,
            "sources": sources,
            "grounded": True,
            "generation_mode": generation_mode,
            "model_name": model_name,
            "is_greeting": False,
        }

    @classmethod
    def _call_ollama(cls, prompt: str) -> Optional[str]:
        """Calls Ollama HTTP API (e.g. llama3.2) with host fallback and explicit logging."""
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
        model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        candidate_urls = [f"{base_url}/api/generate"]
        if "host.docker.internal" in base_url:
            candidate_urls.append("http://localhost:11434/api/generate")

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 380},
        }

        for ollama_url in candidate_urls:
            try:
                resp = requests.post(ollama_url, json=payload, timeout=(3, 75))
                if resp.status_code == 200:
                    data = resp.json()
                    response_text = data.get("response", "").strip()
                    if response_text:
                        logger.info(
                            "Ollama (%s) succeeded via %s (%d chars).",
                            model, ollama_url, len(response_text),
                        )
                        return response_text
                    logger.warning("Ollama (%s) returned empty response from %s: %s", model, ollama_url, data)
                else:
                    logger.warning(
                        "Ollama (%s) HTTP %s from %s: %s",
                        model, resp.status_code, ollama_url, resp.text[:300],
                    )
            except Exception as e:
                logger.warning("Ollama (%s) call to %s failed: %s", model, ollama_url, e)
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

