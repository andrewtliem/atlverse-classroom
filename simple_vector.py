import re
from typing import List, Dict
from models import Material
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging

class SimpleVectorSearch:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
    
    def chunk_text(self, text: str, chunk_size: int = 300) -> List[str]:
        """Split text into manageable chunks"""
        if not text or len(text.strip()) == 0:
            return []
        
        # Clean text
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Split by sentences
        sentences = re.split(r'[.!?]+', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += (" " + sentence if current_chunk else sentence)
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def get_relevant_content(self, query: str, classroom_id: int, material_id: int = None) -> str:
        """Get relevant content using TF-IDF similarity"""
        try:
            # Get materials
            if material_id:
                materials = Material.query.filter_by(id=material_id).all()
            else:
                materials = Material.query.filter_by(classroom_id=classroom_id).all()
            
            if not materials:
                return "No materials found."
            
            # Collect all chunks with metadata
            all_chunks = []
            chunk_metadata = []
            
            for material in materials:
                if material.content:
                    chunks = self.chunk_text(material.content)
                    for chunk in chunks:
                        if len(chunk.strip()) > 20:  # Skip very short chunks
                            all_chunks.append(chunk)
                            chunk_metadata.append({
                                'material_title': material.title,
                                'material_id': material.id
                            })
            
            if not all_chunks:
                return "No content found in materials."
            
            # Create TF-IDF vectors
            documents = [query] + all_chunks
            tfidf_matrix = self.vectorizer.fit_transform(documents)
            
            # Calculate similarities
            query_vector = tfidf_matrix[0:1]
            chunk_vectors = tfidf_matrix[1:]
            
            similarities = cosine_similarity(query_vector, chunk_vectors).flatten()
            
            # Get top 5 most relevant chunks
            top_indices = np.argsort(similarities)[-5:][::-1]
            
            relevant_chunks = []
            for idx in top_indices:
                if similarities[idx] > 0.1:  # Minimum similarity threshold
                    chunk_info = chunk_metadata[idx]
                    relevant_chunks.append({
                        'text': all_chunks[idx],
                        'title': chunk_info['material_title'],
                        'similarity': similarities[idx]
                    })
            
            if not relevant_chunks:
                # Fallback: return first few chunks if no good matches
                for i, chunk in enumerate(all_chunks[:3]):
                    relevant_chunks.append({
                        'text': chunk,
                        'title': chunk_metadata[i]['material_title'],
                        'similarity': 0.0
                    })
            
            # Format response
            context_parts = []
            for chunk in relevant_chunks:
                context_parts.append(f"From {chunk['title']}:\n{chunk['text']}\n")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logging.error(f"Error in content retrieval: {str(e)}")
            # Fallback: return all content concatenated
            content_parts = []
            for material in materials:
                if material.content:
                    content_parts.append(f"From {material.title}:\n{material.content[:1000]}...\n")
            return "\n".join(content_parts) if content_parts else "No content available."