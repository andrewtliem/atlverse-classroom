import os
import json
import google.generativeai as genai
from typing import List, Dict, Tuple
import logging
from simple_vector import SimpleVectorSearch

class AIService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        # Configure Google Generative AI with the API key
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.vector_search = SimpleVectorSearch()
    
    def generate_study_guide(self, content: str, subject: str) -> str:
        """Generate a comprehensive study guide from the provided content"""
        prompt = f"""
        You are an AI tutor that ONLY uses the provided course materials. Do NOT use any external knowledge.

        Create a comprehensive study guide for "{subject}" based STRICTLY on the following uploaded course materials:

        {content}

            **Please output the study guide as clean, readable HTML using:**
        - Headings (`<h2>`, `<h3>`)
        - Lists (`<ul>`, `<li>`)
        - Tables if helpful (`<table>`)
        - Bold and italic for emphasis

        Organize as:
        1. Key Concepts and Definitions
        2. Important Topics Summary
        3. Learning Objectives
        4. Review Questions for Self-Assessment

        **Return ONLY the HTML, with no extra commentary or markdown.**
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Error generating study guide: {str(e)}")
    
    def generate_quiz(self, content: str, quiz_type: str, context: str = "") -> List[Dict]:
        """Generate quiz questions based on content and type"""
        
        if quiz_type == "mcq":
            prompt = f"""
            Create 20 higher-order thinking multiple choice questions based on the provided course material.

            MATERIAL CONTENT:
            {content}

            CONTEXT: {context}

            You MUST respond ONLY with a valid JSON array. No other text, no explanations, no markdown formatting.

            Example format:
            [
                {{
                    "question": "What is the main topic discussed?",
                    "options": ["A) Topic 1", "B) Topic 2", "C) Topic 3", "D) Topic 4"],
                    "correct_answer": "A",
                    "explanation": "The material clearly states..."
                }}
            ]

            Generate exactly 20 questions that require analysis, evaluation or application. Return ONLY the JSON array.
            """
        
        elif quiz_type == "true_false":
            prompt = f"""
            Create 20 higher-order thinking true/false questions based on the provided course material.

            MATERIAL CONTENT:
            {content}

            CONTEXT: {context}

            You MUST respond ONLY with a valid JSON array. No other text, no explanations, no markdown formatting.

            Example format:
            [
                {{
                    "question": "The material states that...",
                    "correct_answer": "True",
                    "explanation": "This is correct because..."
                }}
            ]

            Generate exactly 20 true/false questions that require analysis, evaluation or application. Return ONLY the JSON array.
            """
        
        elif quiz_type == "essay":
            prompt = f"""
            You are an AI tutor that ONLY uses the provided course materials. Do NOT use any external knowledge.

            Based STRICTLY on the following uploaded course materials, create 3 essay questions:

            {content}

            Context: {context}

            IMPORTANT RULES:
            - Use ONLY information from the provided materials above
            - Do NOT add any external knowledge or information
            - Questions must be answerable from the given content only
            - If the materials are insufficient for 3 questions, create fewer questions

            Format each question as JSON with this structure:
            {{
                "question": "Essay question that requires detailed analysis (based only on provided materials)",
                "key_points": ["Key point 1 from materials", "Key point 2 from materials", "Key point 3 from materials"],
                "suggested_length": "Number of paragraphs or words"
            }}

            Return only a JSON array of questions based strictly on the provided content.
            """
        
        else:
            raise ValueError(f"Unsupported quiz type: {quiz_type}")
        
        try:
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Clean up response text
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            # Try to find JSON array in the response
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']')
            
            if start_idx != -1 and end_idx != -1:
                response_text = response_text[start_idx:end_idx+1]
            
            questions = json.loads(response_text)
            return questions
        
        except json.JSONDecodeError as e:
            logging.error(f"JSON parse error. Response was: {response.text[:500]}...")
            raise Exception(f"AI response format error - please try generating the quiz again")
        except Exception as e:
            logging.error(f"Quiz generation error: {str(e)}")
            raise Exception(f"Error generating quiz: {str(e)}")
    
    def score_quiz(self, questions: List[Dict], answers: List[str], quiz_type: str) -> Tuple[float, List[Dict]]:
        """Score a quiz and provide feedback"""
        
        if quiz_type == "mcq":
            return self._score_mcq(questions, answers)
        elif quiz_type == "true_false":
            return self._score_true_false(questions, answers)
        elif quiz_type == "essay":
            return self._score_essay(questions, answers)
        else:
            raise ValueError(f"Unsupported quiz type: {quiz_type}")
    
    def _score_mcq(self, questions: List[Dict], answers: List[str]) -> Tuple[float, List[Dict]]:
        """Score multiple choice questions"""
        correct_count = 0
        feedback = []
        
        for i, (question, answer) in enumerate(zip(questions, answers)):
            is_correct = answer == question.get('correct_answer')
            if is_correct:
                correct_count += 1
            
            feedback.append({
                'question_index': i,
                'is_correct': is_correct,
                'correct_answer': question.get('correct_answer'),
                'explanation': question.get('explanation', ''),
                'user_answer': answer
            })
        
        score = (correct_count / len(questions)) * 100 if questions else 0
        return score, feedback
    
    def _score_true_false(self, questions: List[Dict], answers: List[str]) -> Tuple[float, List[Dict]]:
        """Score true/false questions"""
        correct_count = 0
        feedback = []
        
        for i, (question, answer) in enumerate(zip(questions, answers)):
            is_correct = answer == question.get('correct_answer')
            if is_correct:
                correct_count += 1
            
            feedback.append({
                'question_index': i,
                'is_correct': is_correct,
                'correct_answer': question.get('correct_answer'),
                'explanation': question.get('explanation', ''),
                'user_answer': answer
            })
        
        score = (correct_count / len(questions)) * 100 if questions else 0
        return score, feedback
    
    def _score_essay(self, questions: List[Dict], answers: List[str]) -> Tuple[float, List[Dict]]:
        """Score essay questions using AI"""
        feedback = []
        total_score = 0
        
        for i, (question, answer) in enumerate(zip(questions, answers)):
            if not answer or answer.strip() == "" or answer.strip().lower() in ["i dont know", "i don't know", "no idea", "not sure", "unknown"]:
                score = 0
                ai_feedback = "No valid answer provided."
            else:
                # Use AI to score the essay based only on provided materials
                prompt = f"""
                You are an AI tutor that ONLY evaluates based on the provided course materials. Do NOT use external knowledge.

                Score this essay answer on a scale of 0-100 based STRICTLY on how well it addresses the course materials:
                1. Relevance to the question (based on course materials only)
                2. Depth of understanding of the provided materials
                3. Use of key concepts from the uploaded materials only
                4. Quality of explanation using only the course content

                Question: {question.get('question', '')}
                Key points from course materials that should be covered: {', '.join(question.get('key_points', []))}
                
                Student's answer: {answer}

                IMPORTANT: Only evaluate based on how well the student demonstrates understanding of the specific course materials provided. Do not penalize for not including information outside the uploaded content.

                Provide your response in this JSON format:
                {{
                    "score": <number 0-100>,
                    "feedback": "Detailed feedback explaining the score based on course materials understanding and suggestions for improvement"
                }}
                """
                
                try:
                    response = self.model.generate_content(prompt)
                    result = json.loads(response.text)
                    score = result.get('score', 0)
                    ai_feedback = result.get('feedback', 'Unable to generate feedback.')
                except:
                    # Fallback scoring if AI fails - check for minimal effort
                    answer_lower = answer.strip().lower()
                    if len(answer.strip()) < 10 or answer_lower in ["i dont know", "i don't know", "no idea", "not sure", "unknown"]:
                        score = 0
                        ai_feedback = "Answer appears to be incomplete or invalid. Please provide a substantive response."
                    elif len(answer.strip()) > 100:
                        score = 70
                        ai_feedback = "Answer received. Consider providing more detailed analysis based on course materials."
                    else:
                        score = 30
                        ai_feedback = "Answer appears brief. Please elaborate using concepts from the course materials."
            
            feedback.append({
                'question_index': i,
                'score': score,
                'feedback': ai_feedback,
                'user_answer': answer
            })
            
            total_score += score
        
        average_score = total_score / len(questions) if questions else 0
        return average_score, feedback

    def get_daily_quote(self) -> str:
        """Return a short CS quote or fact using Gemini"""
        prompt = (
            "Provide a single short inspirational quote or interesting fact about "
            "computer science. Respond with only the quote or fact in one or two "
            "sentences."
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            raise Exception(f"Error getting daily quote: {str(e)}")
