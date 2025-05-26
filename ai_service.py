import os
import json
import google.generativeai as genai
from typing import List, Dict, Tuple
from simple_vector import SimpleVectorSearch

class AIService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.vector_search = SimpleVectorSearch()
    
    def generate_study_guide(self, content: str, subject: str) -> str:
        """Generate a comprehensive study guide from the provided content"""
        prompt = f"""
        You are an AI tutor that ONLY uses the provided course materials. Do NOT use any external knowledge.

        Create a comprehensive study guide for "{subject}" based STRICTLY on the following uploaded course materials:

        {content}

        IMPORTANT RULES:
        - Use ONLY information from the provided materials above
        - Do NOT add any external knowledge or information
        - If the materials are insufficient, state what's missing rather than filling gaps with outside knowledge
        - Stay strictly within the scope of the uploaded content

        Please structure the study guide with:
        1. Key concepts and definitions (from the materials only)
        2. Important topics summary (from the materials only)
        3. Learning objectives (based on the materials only)
        4. Review questions for self-assessment (based on the materials only)

        Make it clear, organized, and helpful for student learning using ONLY the provided course content.
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
            You are an AI tutor that ONLY uses the provided course materials. Do NOT use any external knowledge.

            Based STRICTLY on the following uploaded course materials, create 5 multiple choice questions:

            {content}

            Context: {context}

            IMPORTANT RULES:
            - Use ONLY information from the provided materials above
            - Do NOT add any external knowledge or information
            - Questions must be answerable from the given content only
            - If the materials are insufficient for 5 questions, create fewer questions

            Format each question as JSON with this structure:
            {{
                "question": "Question text (based only on provided materials)",
                "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                "correct_answer": "A",
                "explanation": "Why this answer is correct (referencing only the provided materials)"
            }}

            Return only a JSON array of questions based strictly on the provided content.
            """
        
        elif quiz_type == "true_false":
            prompt = f"""
            You are an AI tutor that ONLY uses the provided course materials. Do NOT use any external knowledge.

            Based STRICTLY on the following uploaded course materials, create 5 true/false questions:

            {content}

            Context: {context}

            IMPORTANT RULES:
            - Use ONLY information from the provided materials above
            - Do NOT add any external knowledge or information
            - Questions must be answerable from the given content only
            - If the materials are insufficient for 5 questions, create fewer questions

            Format each question as JSON with this structure:
            {{
                "question": "Statement to evaluate (based only on provided materials)",
                "correct_answer": "True" or "False",
                "explanation": "Explanation of why this is true or false (referencing only the provided materials)"
            }}

            Return only a JSON array of questions based strictly on the provided content.
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
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            questions = json.loads(response_text)
            return questions
        
        except json.JSONDecodeError as e:
            raise Exception(f"Error parsing AI response as JSON: {str(e)}")
        except Exception as e:
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
            if not answer or answer.strip() == "":
                score = 0
                ai_feedback = "No answer provided."
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
                    # Fallback scoring if AI fails
                    score = 70 if len(answer.strip()) > 100 else 50
                    ai_feedback = "Answer received. Consider providing more detailed analysis."
            
            feedback.append({
                'question_index': i,
                'score': score,
                'feedback': ai_feedback,
                'user_answer': answer
            })
            
            total_score += score
        
        average_score = total_score / len(questions) if questions else 0
        return average_score, feedback
