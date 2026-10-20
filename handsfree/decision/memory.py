"""Persistent episodic memory and fast semantic cache for HandsFreeOS."""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from handsfree.domain.models import MemoryEntry

logger = logging.getLogger(__name__)


class EpisodicMemoryStore:
    """Persists learned command associations and provides sub-5ms cached dispatch."""

    DEFAULT_PATH = os.path.expanduser("~/.config/handsfree/memory.json")

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or self.DEFAULT_PATH
        self._cache: Dict[str, MemoryEntry] = {}
        self.load()

    def _normalize_key(self, phrase: str) -> str:
        """Normalizes phrase into a deterministic lookup key."""
        cleaned = phrase.lower().strip()
        cleaned = re.sub(r"^(hey\s+)?bit[,\s!]*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"[\.\?!,]+$", "", cleaned).strip()
        return cleaned

    def load(self) -> None:
        """Loads cached memory entries from disk."""
        if not os.path.isfile(self.storage_path):
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    self._cache[k] = MemoryEntry(
                        phrase=v.get("phrase", k),
                        intent=v.get("intent", "noop"),
                        target=v.get("target"),
                        speech=v.get("speech", ""),
                        hit_count=v.get("hit_count", 1),
                        last_updated=v.get("last_updated", time.time()),
                    )
            logger.debug(f"Loaded {len(self._cache)} memory entries from {self.storage_path}")
        except Exception as e:
            logger.warning(f"Failed to load memory store from {self.storage_path}: {e}")

    def save(self) -> None:
        """Flushes memory entries to disk."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            serializable = {k: v.model_dump() for k, v in self._cache.items()}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save memory store to {self.storage_path}: {e}")

    def lookup(self, phrase: str) -> Optional[Dict[str, Any]]:
        """Fast-path lookup returning cached intent and target in <2ms."""
        key = self._normalize_key(phrase)
        if not key:
            return None

        entry = self._cache.get(key)
        if entry:
            entry.hit_count += 1
            entry.last_updated = time.time()
            return {
                "intent": entry.intent,
                "target": entry.target,
                "speech": entry.speech,
                "hit_count": entry.hit_count,
                "from_cache": True,
            }
        return None

    def record(self, phrase: str, intent: str, target: Any, speech: str = "") -> None:
        """Records a successfully executed natural command association."""
        key = self._normalize_key(phrase)
        if not key or intent in {"noop", "answer_user"}:
            # Do not cache questions or noops
            return

        if key in self._cache:
            entry = self._cache[key]
            entry.intent = intent
            entry.target = target
            entry.speech = speech
            entry.hit_count += 1
            entry.last_updated = time.time()
        else:
            self._cache[key] = MemoryEntry(
                phrase=phrase,
                intent=intent,
                target=target,
                speech=speech,
                hit_count=1,
            )

        self.save()

    def invalidate(self, phrase: str) -> bool:
        """Removes a key from cache (used on user correction)."""
        key = self._normalize_key(phrase)
        if key in self._cache:
            del self._cache[key]
            self.save()
            return True
        return False

    def list_entries(self) -> List[MemoryEntry]:
        """Returns all cached memory entries."""
        return list(self._cache.values())

    def clear(self) -> None:
        """Clears memory store."""
        self._cache.clear()
        if os.path.exists(self.storage_path):
            try:
                os.remove(self.storage_path)
            except Exception:
                pass
