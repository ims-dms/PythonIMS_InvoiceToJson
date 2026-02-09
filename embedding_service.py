"""
Embedding Service for Vector Search
====================================

Generates high-dimensional text embeddings using Google's Gemini API.
Uses text-embedding-005 model for 1024-dimensional embeddings (best accuracy).

This service handles:
- Single text embedding generation
- Batch embedding for efficiency
- Text preprocessing and normalization
- Caching to reduce API calls
- Retry logic for reliability
"""

import logging
import time
import re
import hashlib
from typing import List, Dict, Optional, Tuple, Union
from threading import Lock
import json

import google.generativeai as genai

from vector_config import (
    get_vector_config, 
    EmbeddingConfig, 
    EmbeddingModel
)

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """
    Thread-safe LRU cache for embeddings to reduce API calls.
    Uses MD5 hash of normalized text as key.
    """
    
    def __init__(self, max_size: int = 10000, ttl: int = 3600):
        self._cache: Dict[str, Tuple[List[float], float]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
    
    def _hash_text(self, text: str) -> str:
        """Generate cache key from text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def get(self, text: str) -> Optional[List[float]]:
        """Get embedding from cache if exists and not expired."""
        key = self._hash_text(text)
        with self._lock:
            if key in self._cache:
                embedding, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    self._hits += 1
                    return embedding
                else:
                    del self._cache[key]
            self._misses += 1
            return None
    
    def set(self, text: str, embedding: List[float]):
        """Store embedding in cache."""
        key = self._hash_text(text)
        with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            
            self._cache[key] = (embedding, time.time())
    
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%"
            }
    
    def clear(self):
        """Clear all cached embeddings."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


class EmbeddingService:
    """
    High-performance embedding service using Google's Gemini API.
    
    Features:
    - 1024-dimensional embeddings (text-embedding-005)
    - Batch processing for efficiency
    - Automatic retry with exponential backoff
    - Caching to reduce API costs
    - Text preprocessing for better matching
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Singleton pattern for global embedding service."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config: Optional[EmbeddingConfig] = None
        self._api_key: Optional[str] = None
        self._model_name: str = ""
        self._dimensions: int = 0
        self._cache = EmbeddingCache(max_size=50000, ttl=3600)
        self._initialized = True
        self._configured = False
        
        logger.info("EmbeddingService initialized (singleton)")
    
    def configure(self, api_key: str, config: EmbeddingConfig = None):
        """
        Configure the embedding service with API credentials.
        
        Args:
            api_key: Gemini API key (from TokenManager or appSetting.txt)
            config: Optional EmbeddingConfig override
        """
        self._api_key = api_key
        self._config = config or get_vector_config().embedding
        self._model_name = self._config.model.model_name
        self._dimensions = self._config.model.dimensions
        
        # Configure the Gemini SDK
        genai.configure(api_key=api_key)
        
        self._configured = True
        logger.info(
            f"EmbeddingService configured: model={self._model_name}, "
            f"dimensions={self._dimensions}"
        )
    
    def _ensure_configured(self):
        """Ensure service is configured before use."""
        if not self._configured:
            raise RuntimeError(
                "EmbeddingService not configured. Call configure(api_key) first."
            )
    
    def preprocess_text(self, text: str) -> str:
        """
        Normalize text for better embedding quality.
        
        Preprocessing steps:
        1. Convert to lowercase
        2. Remove special characters (keep alphanumeric and spaces)
        3. Normalize whitespace
        4. Truncate to max length
        
        Args:
            text: Raw input text
            
        Returns:
            Normalized text ready for embedding
        """
        if not text:
            return ""
        
        # Convert to uppercase for consistency with existing fuzzy matcher
        text = text.upper()
        
        # Remove special characters but keep alphanumeric, spaces, and common units
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Truncate if too long
        if self._config and len(text) > self._config.max_text_length:
            text = text[:self._config.max_text_length]
        
        return text
    
    def embed_text(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            use_cache: Whether to use/update cache
            
        Returns:
            List of floats representing the embedding vector
        """
        self._ensure_configured()
        
        # Preprocess
        processed = self.preprocess_text(text)
        if not processed:
            # Return zero vector for empty text
            return [0.0] * self._dimensions
        
        # Check cache
        if use_cache:
            cached = self._cache.get(processed)
            if cached is not None:
                return cached
        
        # Generate embedding
        try:
            result = genai.embed_content(
                model=self._model_name,
                content=processed,
                task_type="SEMANTIC_SIMILARITY"
            )
            
            embedding = result['embedding']
            
            # Cache the result
            if use_cache:
                self._cache.set(processed, embedding)
            
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation failed for text '{text[:50]}...': {e}")
            raise
    
    def embed_batch(
        self, 
        texts: List[str], 
        use_cache: bool = True,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            use_cache: Whether to use/update cache
            show_progress: Log progress for large batches
            
        Returns:
            List of embedding vectors (same order as input)
        """
        self._ensure_configured()
        
        if not texts:
            return []
        
        embeddings = [None] * len(texts)
        texts_to_embed = []
        indices_to_embed = []
        
        # Check cache first
        for i, text in enumerate(texts):
            processed = self.preprocess_text(text)
            if not processed:
                embeddings[i] = [0.0] * self._dimensions
            elif use_cache:
                cached = self._cache.get(processed)
                if cached is not None:
                    embeddings[i] = cached
                else:
                    texts_to_embed.append(processed)
                    indices_to_embed.append(i)
            else:
                texts_to_embed.append(processed)
                indices_to_embed.append(i)
        
        if not texts_to_embed:
            return embeddings
        
        # Batch process uncached texts
        batch_size = self._config.batch_size if self._config else 100
        total_batches = (len(texts_to_embed) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(texts_to_embed))
            batch_texts = texts_to_embed[start:end]
            batch_indices = indices_to_embed[start:end]
            
            if show_progress:
                logger.info(
                    f"Embedding batch {batch_idx + 1}/{total_batches} "
                    f"({len(batch_texts)} texts)"
                )
            
            # Retry logic
            max_retries = self._config.max_retries if self._config else 3
            retry_delay = self._config.retry_delay if self._config else 1.0
            
            for attempt in range(max_retries):
                try:
                    # Use batch embedding API
                    result = genai.embed_content(
                        model=self._model_name,
                        content=batch_texts,
                        task_type="SEMANTIC_SIMILARITY"
                    )
                    
                    # Extract embeddings
                    batch_embeddings = result['embedding']
                    
                    # Handle single vs multiple embeddings
                    if len(batch_texts) == 1:
                        batch_embeddings = [batch_embeddings]
                    
                    # Store results
                    for j, (idx, emb) in enumerate(zip(batch_indices, batch_embeddings)):
                        embeddings[idx] = emb
                        if use_cache:
                            self._cache.set(batch_texts[j], emb)
                    
                    break  # Success
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"Embedding batch failed (attempt {attempt + 1}), "
                            f"retrying in {wait_time}s: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Embedding batch failed after {max_retries} attempts: {e}")
                        raise
        
        return embeddings
    
    def embed_menu_item(self, item: Dict) -> List[float]:
        """
        Generate embedding for a menu item.
        
        Creates a rich text representation combining:
        - Product description (desca)
        - Unit information
        - Category/brand if available
        
        Args:
            item: Menu item dictionary with at least 'desca' key
            
        Returns:
            Embedding vector for the menu item
        """
        # Build rich text representation
        parts = []
        
        # Primary: description
        if item.get('desca'):
            parts.append(str(item['desca']))
        
        # Add unit context if available
        if item.get('baseunit'):
            parts.append(f"UNIT {item['baseunit']}")
        if item.get('altunit'):
            parts.append(f"ALT {item['altunit']}")
        
        # Extract brand from description (first word typically)
        if item.get('desca'):
            words = str(item['desca']).split()
            if words:
                parts.append(f"BRAND {words[0]}")
        
        text = ' '.join(parts)
        return self.embed_text(text)
    
    def compute_similarity(
        self, 
        embedding1: List[float], 
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0 to 1)
        """
        if not embedding1 or not embedding2:
            return 0.0
        
        # Compute dot product and magnitudes
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        magnitude1 = sum(a * a for a in embedding1) ** 0.5
        magnitude2 = sum(b * b for b in embedding2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def get_cache_stats(self) -> Dict:
        """Get embedding cache statistics."""
        return self._cache.get_stats()
    
    def clear_cache(self):
        """Clear embedding cache."""
        self._cache.clear()
        logger.info("Embedding cache cleared")
    
    @property
    def dimensions(self) -> int:
        """Get embedding dimensions."""
        return self._dimensions
    
    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name


# Global instance accessor
def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance."""
    return EmbeddingService()


def configure_embedding_service(api_key: str, config: EmbeddingConfig = None):
    """
    Configure the global embedding service.
    
    Args:
        api_key: Gemini API key
        config: Optional configuration override
    """
    service = get_embedding_service()
    service.configure(api_key, config)
    return service
