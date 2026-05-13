"""
Memory Manager with Weighted Retrieval
Implements time decay and emotional weighting for memories.
"""
import asyncio
import json
import faiss
import numpy as np
import logging
from pathlib import Path
from collections import deque
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math

from settings import Settings
from utils import load_or_initialize_json, save_json
from llm_provider import MultiProviderManager


@dataclass
class MemoryConfig:
    """Configuration for memory management."""
    working_memory_size: int = 10
    short_term_limit: int = 20
    long_term_retrieval_k: int = 3
    style_exemplars_k: int = 2

    # Time decay parameters
    decay_half_life_days: float = 30.0  # 半衰期天数
    decay_base: float = 0.9  # 基础衰减系数

    # Emotional weighting
    emotional_boost_factor: float = 1.5  # 高情感记忆的权重提升
    emotional_decay_threshold: float = 0.3  # 情感衰减阈值

    # Retrieval scoring
    similarity_weight: float = 0.4
    recency_weight: float = 0.3
    emotional_weight: float = 0.3


@dataclass
class WeightedMemory:
    """记忆项，带有权重元数据"""
    content: str
    created_at: datetime
    last_accessed: datetime
    emotional_intensity: float  # 记录时的情感强度 (0-100)
    eii_snapshot: float  # 当时的 EII
    access_count: int = 0
    decayed_score: float = 1.0

    def __post_init__(self):
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if isinstance(self.last_accessed, str):
            self.last_accessed = datetime.fromisoformat(self.last_accessed)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "emotional_intensity": self.emotional_intensity,
            "eii_snapshot": self.eii_snapshot,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WeightedMemory":
        return cls(
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            emotional_intensity=data.get("emotional_intensity", 50.0),
            eii_snapshot=data.get("eii_snapshot", 50.0),
            access_count=data.get("access_count", 0),
        )


class EmbeddingCache:
    """LRU cache for embeddings."""

    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, List[float]] = {}
        self._max_size = max_size
        self._access_order: List[str] = []

    def get(self, text: str) -> Optional[List[float]]:
        text_hash = hash(text)
        key = str(text_hash)
        if key in self._cache:
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def put(self, text: str, embedding: List[float]):
        text_hash = hash(text)
        key = str(text_hash)

        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self._max_size:
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

        self._cache[key] = embedding
        self._access_order.append(key)

    def clear(self):
        self._cache.clear()
        self._access_order.clear()


class TimeDecayCalculator:
    """时间衰减计算器"""

    def __init__(self, half_life_days: float = 30.0, base: float = 0.9):
        self.half_life_days = half_life_days
        self.base = base
        self.lambda_decay = math.log(2) / half_life_days  # 指数衰减率

    def calculate_decay(self, age_days: float) -> float:
        """
        计算时间衰减系数

        Args:
            age_days: 记忆年龄（天）

        Returns:
            衰减系数 (0-1)，1 表示不衰减
        """
        # 指数衰减: e^(-lambda * t)
        decay = math.exp(-self.lambda_decay * age_days)
        return max(0.1, decay)  # 最低保留 10%

    def calculate_weighted_decay(
        self,
        created_at: datetime,
        last_accessed: datetime,
        now: Optional[datetime] = None
    ) -> float:
        """
        计算加权衰减（考虑创建时间和最后访问时间）

        Returns:
            综合衰减系数
        """
        now = now or datetime.now()

        # 基础年龄衰减
        age_days = (now - created_at).total_seconds() / 86400
        age_decay = self.calculate_decay(age_days)

        # 访问时间奖励（最近访问的记忆衰减更慢）
        time_since_access = (now - last_accessed).total_seconds() / 86400
        access_bonus = math.exp(-time_since_access / 7)  # 7天内的访问有奖励

        # 组合：基础衰减 + 访问奖励
        return age_decay * (0.7 + 0.3 * access_bonus)


class EmotionalWeightCalculator:
    """情感权重计算器"""

    def __init__(
        self,
        boost_factor: float = 1.5,
        threshold: float = 0.3
    ):
        self.boost_factor = boost_factor
        self.threshold = threshold

    def calculate_weight(
        self,
        memory_eii: float,
        current_eii: float,
        emotional_intensity: float
    ) -> float:
        """
        计算情感权重

        Args:
            memory_eii: 记忆创建时的 EII
            current_eii: 当前 EII
            emotional_intensity: 记忆的情感强度 (0-100)

        Returns:
            情感权重系数
        """
        # 1. 高情感强度记忆的基础权重
        intensity_weight = 1.0 + (emotional_intensity / 100) * (self.boost_factor - 1.0)

        # 2. 情感状态匹配度
        # 如果当前情绪和记忆时的情绪相近，记忆更相关
        eii_diff = abs(current_eii - memory_eii) / 100  # 归一化差异
        mood_match = 1.0 - (eii_diff * self.threshold)  # 情绪匹配度

        # 3. 极端情绪增强
        # 在极端情绪下创建的记忆更容易被唤起
        extremity_bonus = 1.0
        if emotional_intensity > 70 or memory_eii > 70 or memory_eii < 30:
            extremity_bonus = 1.2

        return intensity_weight * mood_match * extremity_bonus


class WeightedMemoryManager:
    """
    Three-tier memory system with weighted retrieval:
    - Working Memory: In-memory deque (unweighted, immediate context)
    - Short-term Memory: Recent events with basic metadata
    - Long-term Memory: FAISS index + weighted metadata
    """

    def __init__(
        self,
        settings: Settings,
        api_manager: MultiProviderManager,
        config: Optional[MemoryConfig] = None
    ):
        self.settings = settings
        self.api_manager = api_manager
        self.config = config or MemoryConfig()

        # 初始化计算器
        self.decay_calculator = TimeDecayCalculator(
            half_life_days=self.config.decay_half_life_days,
            base=self.config.decay_base
        )
        self.emotional_calculator = EmotionalWeightCalculator(
            boost_factor=self.config.emotional_boost_factor,
            threshold=self.config.emotional_decay_threshold
        )

        self.embedding_cache = EmbeddingCache()

        # 工作记忆
        self.working_memory: deque = deque(maxlen=self.config.working_memory_size)

        # 短期记忆
        self.short_term_memory = load_or_initialize_json(
            self.settings.SHORT_TERM_MEMORY_FILE,
            {"recent_events": []}
        )

        # 长期记忆（带权重）
        self.long_term_memories: Dict[str, WeightedMemory] = {}
        self.long_term_chunks: List[str] = []
        self.long_term_index: Optional[faiss.IndexFlatL2] = None
        self._memory_id_map: Dict[int, str] = {}  # FAISS索引 -> 内存ID

        # 风格库
        self.style_exemplars: List[Dict[str, str]] = []
        self.style_index: Optional[faiss.IndexFlatL2] = None

        # 初始化
        self._init_long_term_memory()
        self._init_style_library()

    def _init_long_term_memory(self):
        """初始化长期记忆"""
        logging.info("Initializing weighted long-term memory...")
        try:
            self._load_weighted_memories()
            self._rebuild_index()
            logging.info(f"Long-term memory: {len(self.long_term_memories)} items")
        except Exception as e:
            logging.error(f"Failed to initialize long-term memory: {e}", exc_info=True)

    def _init_style_library(self):
        """Initialize style exemplars library for personality matching"""
        logging.info("Initializing style library...")
        try:
            # Load style exemplars if they exist
            style_data = load_or_initialize_json(
                Path("json/style_exemplars.json"),
                {"exemplars": []}
            )
            self.style_exemplars = style_data.get("exemplars", [])
            logging.info(f"Style library: {len(self.style_exemplars)} exemplars")
        except Exception as e:
            logging.warning(f"Failed to load style library: {e}")
            self.style_exemplars = []

    def _load_weighted_memories(self):
        """加载带权重的记忆数据"""
        data = load_or_initialize_json(
            Path("json/weighted_memories.json"),
            {"memories": {}}
        )

        for mem_id, mem_data in data.get("memories", {}).items():
            try:
                self.long_term_memories[mem_id] = WeightedMemory.from_dict(mem_data)
            except Exception as e:
                logging.warning(f"Failed to load memory {mem_id}: {e}")

    def _save_weighted_memories(self):
        """保存带权重的记忆"""
        data = {
            "memories": {
                mem_id: mem.to_dict()
                for mem_id, mem in self.long_term_memories.items()
            }
        }
        save_json(Path("json/weighted_memories.json"), data)

    def _build_memory_chunks(self) -> List[str]:
        """构建记忆文本块"""
        chunks = []

        # 世界观
        if self.settings.LAPWING_WORLD_LORE:
            lore_chunks = [
                p.strip()
                for p in self.settings.LAPWING_WORLD_LORE.split('\n\n')
                if p.strip()
            ]
            chunks.extend(lore_chunks)

        # 用户资料
        memory_data = load_or_initialize_json(self.settings.MEMORY_FILE, {})
        user_profile = memory_data.get("user_profile", {})
        prefs = user_profile.get("preferences", [])
        dislikes = user_profile.get("dislikes", [])

        if prefs:
            chunks.append(f"Master likes these things: {', '.join(prefs)}.")
        if dislikes:
            chunks.append(f"Master dislikes: {', '.join(dislikes)}.")

        # 共享记忆（带权重）
        for mem_id, mem in self.long_term_memories.items():
            chunks.append(mem.content)

        return chunks

    def _rebuild_index(self):
        """重建 FAISS 索引 - 同步版本（用于初始化）"""
        self.long_term_chunks = list(self.long_term_memories.values())

        if not self.long_term_chunks:
            self.long_term_index = None
            self._memory_id_map = {}
            return

        try:
            # 使用 asyncio.run 来获取嵌入（初始化时同步）
            import asyncio
            embeddings = asyncio.run(self._get_embeddings_async(
                [mem.content for mem in self.long_term_chunks]
            ))

            if embeddings:
                dimension = len(embeddings[0])
                self.long_term_index = faiss.IndexFlatL2(dimension)
                self.long_term_index.add(np.array(embeddings, dtype=np.float32))

                # 建立索引映射
                self._memory_id_map = {
                    i: mem_id for i, mem_id in enumerate(self.long_term_memories.keys())
                }

                logging.info(f"FAISS index rebuilt: {len(embeddings)} vectors, dim={dimension}")

        except Exception as e:
            logging.error(f"Failed to rebuild FAISS index: {e}")
            self.long_term_index = None

    async def _rebuild_index_async(self):
        """异步重建 FAISS 索引 - 用于运行时更新"""
        self.long_term_chunks = list(self.long_term_memories.values())

        if not self.long_term_chunks:
            self.long_term_index = None
            self._memory_id_map = {}
            return

        try:
            # 在线程池中执行 CPU 密集型操作
            import asyncio
            embeddings = await self._get_embeddings_async(
                [mem.content for mem in self.long_term_chunks]
            )

            if embeddings:
                dimension = len(embeddings[0])

                # FAISS 操作在单独的线程中执行，避免阻塞事件循环
                def build_index():
                    index = faiss.IndexFlatL2(dimension)
                    index.add(np.array(embeddings, dtype=np.float32))
                    return index

                loop = asyncio.get_event_loop()
                self.long_term_index = await loop.run_in_executor(None, build_index)

                # 建立索引映射
                self._memory_id_map = {
                    i: mem_id for i, mem_id in enumerate(self.long_term_memories.keys())
                }

                logging.info(f"FAISS index rebuilt async: {len(embeddings)} vectors, dim={dimension}")

        except Exception as e:
            logging.error(f"Failed to rebuild FAISS index async: {e}")
            self.long_term_index = None

    async def _get_embeddings_async(self, texts: List[str]) -> List[List[float]]:
        """异步获取嵌入"""
        return await self.api_manager.embedding_client.get_embeddings(texts)

    def _calculate_memory_score(
        self,
        memory: WeightedMemory,
        query: str,
        similarity: float,
        current_eii: float
    ) -> float:
        """
        计算记忆的综合检索分数

        Score = similarity_weight * similarity
              + recency_weight * decay_score
              + emotional_weight * emotional_score
        """
        now = datetime.now()

        # 1. 相似度分数 (已归一化到 0-1)
        sim_score = 1.0 / (1.0 + similarity)  # L2距离转相似度

        # 2. 时间衰减分数
        decay_score = self.decay_calculator.calculate_weighted_decay(
            memory.created_at,
            memory.last_accessed,
            now
        )

        # 3. 情感权重分数
        emotional_score = self.emotional_calculator.calculate_weight(
            memory.eii_snapshot,
            current_eii,
            memory.emotional_intensity
        )

        # 综合分数
        total_score = (
            self.config.similarity_weight * sim_score +
            self.config.recency_weight * decay_score +
            self.config.emotional_weight * emotional_score
        )

        # 访问计数加成（频繁访问的记忆稍微提升）
        access_bonus = min(0.1, memory.access_count * 0.01)

        return total_score + access_bonus

    async def retrieve_long_term_memories(
        self,
        query: str,
        k: int = None,
        current_eii: float = 50.0
    ) -> List[Tuple[str, float]]:
        """
        检索长期记忆，按加权分数排序

        Args:
            query: 查询文本
            k: 返回数量
            current_eii: 当前 EII，用于情感加权

        Returns:
            [(memory_content, score), ...]
        """
        k = k or self.config.long_term_retrieval_k

        if not self.long_term_index or not self.long_term_chunks:
            return []

        try:
            # 获取查询嵌入
            query_embedding = self.embedding_cache.get(query)
            if query_embedding is None:
                embeddings = await self._get_embeddings_async([query])
                if not embeddings:
                    return []
                query_embedding = embeddings[0]
                self.embedding_cache.put(query, query_embedding)

            # FAISS 检索（获取更多用于重新排序）
            query_np = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.long_term_index.search(query_np, min(k * 3, len(self.long_term_chunks)))

            # 计算加权分数
            scored_memories = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < 0 or idx >= len(self.long_term_chunks):
                    continue

                mem_id = self._memory_id_map.get(idx)
                if mem_id and mem_id in self.long_term_memories:
                    memory = self.long_term_memories[mem_id]
                    score = self._calculate_memory_score(
                        memory, query, dist, current_eii
                    )
                    scored_memories.append((memory, score))

            # 按分数排序
            scored_memories.sort(key=lambda x: x[1], reverse=True)

            # 更新访问记录
            results = []
            for memory, score in scored_memories[:k]:
                memory.access_count += 1
                memory.last_accessed = datetime.now()
                results.append((memory.content, score))

            # 异步保存（不阻塞）
            self._save_weighted_memories()

            return results

        except Exception as e:
            logging.error(f"Failed to retrieve weighted memories: {e}")
            return []

    def add_to_working_memory(self, user_input: str, lapwing_response: str):
        """添加对话到工作记忆"""
        self.working_memory.append({
            "user": user_input,
            "lapwing": lapwing_response,
        })

    def get_formatted_working_memory(self) -> str:
        """格式化工作记忆"""
        if not self.working_memory:
            return "We just started talking."
        return "\n".join([
            f"Master: {turn['user']}\nLapwing: {turn['lapwing']}"
            for turn in self.working_memory
        ])

    def add_weighted_memory(
        self,
        content: str,
        eii_snapshot: float,
        emotional_intensity: float = 50.0
    ) -> str:
        """
        添加带权重的长期记忆

        Args:
            content: 记忆内容
            eii_snapshot: 当时的 EII
            emotional_intensity: 情感强度 (0-100)

        Returns:
            记忆 ID
        """
        now = datetime.now()
        mem_id = f"mem_{now.timestamp()}"

        memory = WeightedMemory(
            content=content,
            created_at=now,
            last_accessed=now,
            emotional_intensity=emotional_intensity,
            eii_snapshot=eii_snapshot
        )

        self.long_term_memories[mem_id] = memory
        self._save_weighted_memories()

        # 异步重建索引（不阻塞）
        import asyncio
        asyncio.create_task(self._rebuild_index_async())

        logging.info(f"Added weighted memory: {mem_id}")
        return mem_id

    def get_formatted_short_term_memory(self, k: int = 5) -> str:
        """格式化短期记忆"""
        if not self.short_term_memory.get("recent_events"):
            return "Nothing special has happened recently."
        recent = self.short_term_memory["recent_events"][-k:]
        return "\n".join(f"- {event}" for event in recent)

    def clear_working_memory(self):
        """清空工作记忆"""
        self.working_memory.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        now = datetime.now()

        # 计算记忆年龄分布
        age_distribution = {"recent": 0, "medium": 0, "old": 0}
        avg_access = 0

        for mem in self.long_term_memories.values():
            age_days = (now - mem.created_at).total_seconds() / 86400
            if age_days < 7:
                age_distribution["recent"] += 1
            elif age_days < 30:
                age_distribution["medium"] += 1
            else:
                age_distribution["old"] += 1
            avg_access += mem.access_count

        if self.long_term_memories:
            avg_access /= len(self.long_term_memories)

        return {
            "working_memory_size": len(self.working_memory),
            "short_term_events": len(self.short_term_memory.get("recent_events", [])),
            "long_term_memories": len(self.long_term_memories),
            "memory_age_distribution": age_distribution,
            "avg_access_count": round(avg_access, 2),
            "embedding_cache_size": len(self.embedding_cache._cache),
        }

    # 保持向后兼容
    async def retrieve_long_term_memories_simple(
        self,
        query: str,
        k: int = None
    ) -> str:
        """简单版本（向后兼容）"""
        results = await self.retrieve_long_term_memories(query, k, current_eii=50.0)
        return " ".join([content for content, _ in results]) if results else ""

    async def build_style_index_async(self):
        """异步构建风格索引"""
        try:
            if not self.style_exemplars:
                logging.info("No style exemplars to build index from")
                return

            # 获取所有exemplar文本的嵌入
            texts = [ex.get("text", "") for ex in self.style_exemplars if ex.get("text")]
            if not texts:
                return

            embeddings = await self._get_embeddings_async(texts)
            if embeddings:
                dimension = len(embeddings[0])

                def build_index():
                    index = faiss.IndexFlatL2(dimension)
                    index.add(np.array(embeddings, dtype=np.float32))
                    return index

                loop = asyncio.get_event_loop()
                self.style_index = await loop.run_in_executor(None, build_index)
                logging.info(f"Style index built: {len(embeddings)} exemplars")

        except Exception as e:
            logging.warning(f"Failed to build style index: {e}")

    async def retrieve_style_exemplars(self, query: str, k: int = None) -> List[Dict[str, str]]:
        """
        检索相似的风格示例

        Args:
            query: 查询文本
            k: 返回数量

        Returns:
            风格示例列表
        """
        k = k or self.config.style_exemplars_k

        if not self.style_index or not self.style_exemplars:
            return []

        try:
            # 获取查询嵌入
            query_embedding = self.embedding_cache.get(query)
            if query_embedding is None:
                embeddings = await self._get_embeddings_async([query])
                if not embeddings:
                    return []
                query_embedding = embeddings[0]
                self.embedding_cache.put(query, query_embedding)

            # FAISS检索
            query_np = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.style_index.search(query_np, min(k, len(self.style_exemplars)))

            results = []
            for idx in indices[0]:
                if 0 <= idx < len(self.style_exemplars):
                    results.append(self.style_exemplars[idx])

            return results

        except Exception as e:
            logging.error(f"Failed to retrieve style exemplars: {e}")
            return []


# 别名，保持向后兼容
MemoryManager = WeightedMemoryManager
