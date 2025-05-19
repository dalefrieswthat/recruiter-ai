from typing import Dict, List, Any
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
import os

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        # Get Hugging Face token from environment
        hf_token = os.getenv('HUGGINGFACE_TOKEN')
        if not hf_token:
            logger.warning("No HUGGINGFACE_TOKEN found in environment variables")
            
        # Initialize the sentence transformer model with token
        self.model = SentenceTransformer('all-MiniLM-L6-v2', token=hf_token)  # Lightweight model good for semantic search
        self.embeddings_cache = {}  # In-memory cache for embeddings
        
    def generate_embeddings(self, text: str) -> np.ndarray:
        """Generate embeddings for a given text."""
        try:
            # Split text into chunks if it's too long (model has a max length)
            chunks = self._split_text(text)
            
            # Generate embeddings for each chunk
            chunk_embeddings = []
            for chunk in chunks:
                embedding = self.model.encode(chunk)
                chunk_embeddings.append(embedding)
            
            # Average the chunk embeddings to get a single embedding for the text
            return np.mean(chunk_embeddings, axis=0)
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            return None

    def store_embeddings(self, key: str, text: str) -> bool:
        """Store embeddings in memory cache."""
        try:
            embedding = self.generate_embeddings(text)
            if embedding is not None:
                self.embeddings_cache[key] = {
                    'embedding': embedding,
                    'text': text
                }
                return True
            return False
        except Exception as e:
            logger.error(f"Error storing embeddings: {str(e)}")
            return False

    def get_embeddings(self, key: str) -> Dict[str, Any]:
        """Retrieve embeddings from cache."""
        return self.embeddings_cache.get(key)

    def clear_embeddings(self, key: str = None):
        """Clear embeddings from cache."""
        if key:
            self.embeddings_cache.pop(key, None)
        else:
            self.embeddings_cache.clear()

    def _split_text(self, text: str, max_length: int = 512) -> List[str]:
        """Split text into chunks of maximum length."""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word.split())
            if current_length + word_length > max_length:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks 