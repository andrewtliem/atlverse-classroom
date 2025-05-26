import os
import json
import re
from typing import List, Dict, Tuple
import google.generativeai as genai
from app import db
from models import Material
from sqlalchemy import text
import numpy as np

class VectorService:
    def __init__(self):
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
        self.model = genai.GenerativeModel('gemini-2.0-flash')
    
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks for better context preservation"""
        if not text or len(text.strip()) == 0:
            return []
        
        # Clean and normalize text
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Split by sentences first to maintain semantic boundaries
        sentences = re.split(r'[.!?]+', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # If adding this sentence would exceed chunk size, save current chunk
            if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap from end of previous chunk
                if overlap > 0:
                    overlap_text = current_chunk[-overlap:].strip()
                    current_chunk = overlap_text + " " + sentence
                else:
                    current_chunk = sentence
            else:
                current_chunk += (" " + sentence if current_chunk else sentence)
        
        # Add the last chunk if it exists
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using Gemini's text representation"""
        try:
            # Use Gemini to create a consistent numerical representation
            prompt = f"""Create a numerical representation for this text by analyzing its semantic content.
            Convert the following text into exactly 384 numbers between -1 and 1 that represent its meaning:
            
            Text: {text[:1000]}...
            
            Return only a JSON array of exactly 384 float numbers between -1 and 1."""
            
            response = self.model.generate_content(prompt)
            
            # Parse the response to extract numbers
            try:
                embedding = json.loads(response.text)
                if isinstance(embedding, list) and len(embedding) == 384:
                    return embedding
            except:
                pass
            
            # Fallback: create embedding based on text characteristics
            return self._create_fallback_embedding(text)
            
        except Exception as e:
            print(f"Error generating embedding: {str(e)}")
            return self._create_fallback_embedding(text)
    
    def _create_fallback_embedding(self, text: str) -> List[float]:
        """Create a simple embedding based on text characteristics"""
        # Use text properties to create a consistent 384-dimensional vector
        embedding = [0.0] * 384
        
        if not text:
            return embedding
        
        # Simple hash-based embedding for consistency
        text_lower = text.lower()
        for i, char in enumerate(text_lower[:384]):
            embedding[i] = (ord(char) - 97) / 25.0 if 'a' <= char <= 'z' else 0.0
        
        # Normalize to [-1, 1] range
        max_val = max(abs(x) for x in embedding) or 1.0
        embedding = [x / max_val for x in embedding]
        
        return embedding
    
    def process_material(self, material_id: int):
        """Process a material and store its chunks with embeddings"""
        try:
            # Get material
            material = Material.query.get(material_id)
            if not material or not material.content:
                return False
            
            # Delete existing chunks for this material
            db.session.execute(text("DELETE FROM document_chunks WHERE material_id = :material_id"), 
                             {"material_id": material_id})
            
            # Create chunks
            chunks = self.chunk_text(material.content)
            
            if not chunks:
                return False
            
            # Process each chunk
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 10:  # Skip very short chunks
                    continue
                    
                # Generate embedding
                embedding = self.generate_embedding(chunk)
                
                # Store in database
                db.session.execute(text("""
                    INSERT INTO document_chunks (material_id, chunk_text, chunk_index, embedding)
                    VALUES (:material_id, :chunk_text, :chunk_index, :embedding)
                """), {
                    "material_id": material_id,
                    "chunk_text": chunk,
                    "chunk_index": i,
                    "embedding": embedding
                })
            
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"Error processing material {material_id}: {str(e)}")
            return False
    
    def find_relevant_chunks(self, query: str, classroom_id: int, material_id: int = None, top_k: int = 5) -> List[Dict]:
        """Find most relevant chunks for a query using cosine similarity"""
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            
            # Build SQL query
            sql = """
                SELECT dc.chunk_text, dc.material_id, m.title,
                       dc.embedding,
                       dc.chunk_index
                FROM document_chunks dc
                JOIN material m ON dc.material_id = m.id
                WHERE m.classroom_id = :classroom_id
            """
            
            params = {"classroom_id": classroom_id}
            
            if material_id:
                sql += " AND dc.material_id = :material_id"
                params["material_id"] = material_id
            
            # Execute query
            result = db.session.execute(text(sql), params)
            chunks = result.fetchall()
            
            if not chunks:
                return []
            
            # Calculate similarities
            chunk_scores = []
            for chunk in chunks:
                chunk_embedding = chunk.embedding
                if isinstance(chunk_embedding, list) and len(chunk_embedding) == 384:
                    similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                    chunk_scores.append({
                        'text': chunk.chunk_text,
                        'material_id': chunk.material_id,
                        'material_title': chunk.title,
                        'similarity': similarity,
                        'chunk_index': chunk.chunk_index
                    })
            
            # Sort by similarity and return top k
            chunk_scores.sort(key=lambda x: x['similarity'], reverse=True)
            return chunk_scores[:top_k]
            
        except Exception as e:
            print(f"Error finding relevant chunks: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
        except:
            return 0.0
    
    def get_relevant_context(self, query: str, classroom_id: int, material_id: int = None) -> str:
        """Get relevant context for AI generation"""
        relevant_chunks = self.find_relevant_chunks(query, classroom_id, material_id)
        
        if not relevant_chunks:
            return "No relevant content found in uploaded materials."
        
        context_parts = []
        for chunk in relevant_chunks:
            context_parts.append(f"From {chunk['material_title']}:\n{chunk['text']}\n")
        
        return "\n".join(context_parts)