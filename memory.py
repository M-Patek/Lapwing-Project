import google.generativeai as genai
import faiss
import json
import numpy as np
import logging
from pathlib import Path
from collections import deque
from settings import Settings
from utils import load_or_initialize_json, save_json


class MemoryManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedding_model = genai.GenerativeModel("models/embedding-001")
        self.working_memory = deque(maxlen=self.settings.WORKING_MEMORY_MAXLEN)
        self.short_term_memory = load_or_initialize_json(
            self.settings.SHORT_TERM_MEMORY_FILE, {"recent_events": []}
        )
        self.long_term_index = None
        self.long_term_chunks = []
        self.style_index = None
        self.style_exemplars = []
        self.rebuild_long_term_index()
        self._initialize_style_library()

    def rebuild_long_term_index(self):
        logging.info("Initializing and vectorizing long-term memory...")
        try:
            world_lore = self.settings.LAPWING_WORLD_LORE or ""
            memory_data = self._load_json_memory()
            self.long_term_chunks = self._chunk_data(world_lore, memory_data)
            if self.long_term_chunks:
                memory_embeddings = self.embedding_model.embed_contents(
                    content=self.long_term_chunks, task_type="RETRIEVAL_DOCUMENT"
                )["embedding"]
                dimension = len(memory_embeddings[0])
                self.long_term_index = faiss.IndexFlatL2(dimension)
                self.long_term_index.add(np.array(memory_embeddings))
                logging.info(
                    f"Long-term memory vectorized. Index contains {self.long_term_index.ntotal} chunks."
                )
            else:
                self.long_term_index = None  # Ensure index is None if no data
                logging.warning("No long-term memory chunks found to vectorize.")
        except Exception as e:
            logging.critical(f"Failed to initialize memory manager: {e}", exc_info=True)

    def _initialize_style_library(self):
        logging.info("Initializing and vectorizing style library...")
        try:
            style_file = Path("json/style_exemplars.json")
            if style_file.exists() and style_file.stat().st_size > 0:
                with open(style_file, "r", encoding="utf-8") as f:
                    self.style_exemplars = json.load(f)
                if self.style_exemplars:
                    style_questions = [ex["user"] for ex in self.style_exemplars]
                    style_embeddings = self.embedding_model.embed_contents(
                        content=style_questions, task_type="RETRIEVAL_DOCUMENT"
                    )["embedding"]
                    dimension = len(style_embeddings[0])
                    self.style_index = faiss.IndexFlatL2(dimension)
                    self.style_index.add(np.array(style_embeddings))
                    logging.info(
                        f"Style library vectorized. Index contains {self.style_index.ntotal} exemplars."
                    )
        except Exception as e:
            logging.critical(f"Failed to initialize style library: {e}", exc_info=True)

    def _load_json_memory(self):
        return load_or_initialize_json(self.settings.MEMORY_FILE, {})

    def _chunk_data(self, world_lore, memory_data):
        chunks = [p.strip() for p in world_lore.split("\n\n") if p.strip()]
        prefs = memory_data.get("user_profile", {}).get("preferences", [])
        dislikes = memory_data.get("user_profile", {}).get("dislikes", [])
        mems = memory_data.get("shared_memories", [])
        if prefs:
            chunks.append(f"Master likes these things: {', '.join(prefs)}.")
        if dislikes:
            chunks.append(f"Master dislikes: {', '.join(dislikes)}.")
        if mems:
            chunks.extend(mems)
        return chunks

    def add_to_working_memory(self, user_input: str, lapwing_response: str):
        self.working_memory.append({"user": user_input, "lapwing": lapwing_response})

    def add_to_short_term_memory(self, event: str):
        """Adds a new event to short-term memory and saves it."""
        self.short_term_memory.setdefault("recent_events", []).append(event)
        save_json(self.settings.SHORT_TERM_MEMORY_FILE, self.short_term_memory)
        logging.info("event_added_to_stm", event=event)

    def get_formatted_working_memory(self) -> str:
        if not self.working_memory:
            return "We just started talking."
        return "\n".join(
            [
                f"Master: {turn['user']}\nLapwing: {turn['lapwing']}"
                for turn in self.working_memory
            ]
        )

    def get_formatted_short_term_memory(self) -> str:
        if not self.short_term_memory.get("recent_events"):
            return "Nothing special has happened recently."
        recent_events = self.short_term_memory["recent_events"][
            -self.settings.STM_RETRIEVAL_K :
        ]
        return "\n".join(f"- {event}" for event in recent_events)

    def _get_emotional_context_embedding(self, pad_state: dict):
        """Converts PAD state to a descriptive string and returns its embedding."""
        p, a, d = (
            pad_state.get("p", 0.5),
            pad_state.get("a", 0.5),
            pad_state.get("d", 0.5),
        )
        pleasure_desc = (
            "high pleasure"
            if p > 0.6
            else "low pleasure"
            if p < 0.4
            else "neutral pleasure"
        )
        arousal_desc = (
            "high arousal"
            if a > 0.6
            else "low arousal"
            if a < 0.4
            else "neutral arousal"
        )
        dominance_desc = (
            "high dominance"
            if d > 0.6
            else "low dominance"
            if d < 0.4
            else "neutral dominance"
        )
        context_str = f"Recalling a memory while feeling a sense of {pleasure_desc}, {arousal_desc}, and {dominance_desc}."
        return self.embedding_model.embed_contents(
            content=[context_str], task_type="RETRIEVAL_QUERY"
        )["embedding"][0]

    def retrieve_long_term_memories(self, query: str, pad_state: dict) -> str:
        if not self.long_term_index or not self.long_term_chunks:
            return "I don't have any long-term memories of Master yet."
        try:
            query_embedding = np.array(
                self.embedding_model.embed_contents(
                    content=[query], task_type="RETRIEVAL_QUERY"
                )["embedding"][0]
            )
            emotional_embedding = np.array(
                self._get_emotional_context_embedding(pad_state)
            )

            # Blend the embeddings
            bias_weight = self.settings.EMOTIONAL_BIAS_WEIGHT
            biased_embedding = (
                1 - bias_weight
            ) * query_embedding + bias_weight * emotional_embedding
            biased_embedding = biased_embedding.reshape(
                1, -1
            )  # Reshape for FAISS search

            distances, indices = self.long_term_index.search(
                biased_embedding, self.settings.LTM_RETRIEVAL_K
            )
            retrieved_chunks = [self.long_term_chunks[i] for i in indices[0]]

            logging.info(
                f"Retrieved emotionally-biased long-term memories for query '{query}': {retrieved_chunks}"
            )
            return " ".join(retrieved_chunks)
        except Exception as e:
            logging.error(f"Failed to retrieve long-term memories: {e}")
            return "I had a little trouble remembering..."

    def retrieve_style_exemplars(self, query: str) -> list[dict]:
        if not self.style_index or not self.style_exemplars:
            return []
        try:
            query_embedding = self.embedding_model.embed_contents(
                content=[query], task_type="RETRIEVAL_QUERY"
            )["embedding"]
            distances, indices = self.style_index.search(
                np.array(query_embedding), self.settings.STYLE_RETRIEVAL_K
            )
            retrieved_exemplars = [self.style_exemplars[i] for i in indices[0]]
            logging.info(
                f"Retrieved style exemplars for query '{query}': {retrieved_exemplars}"
            )
            return retrieved_exemplars
        except Exception as e:
            logging.error(f"Failed to retrieve style exemplars: {e}")
            return []
