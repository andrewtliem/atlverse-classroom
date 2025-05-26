import os
import json
import google.generativeai as genai
from typing import List, Dict, Tuple

class AIService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
    
    def generate_study_guide(self, content: str, subject: str) -> str:
        """Generate a comprehensive study guide from the provided content"""
        prompt = f"""
        Create a comprehensive study guide for the subject "{subject}" based on the following content:

        {content}

        Please structure the study guide with:
        1. Key concepts and definitions
        2. Important topics summary
        3. Learning objectives
        4. Study tips and strategies
        5. Review questions for self-assessment

        Make it clear, organized, and helpful for student learning.
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
            Based on the following content, create 5 multiple choice questions:

            {content}

            Context: {context}

            Format each question as JSON with this structure:
            {{
                "question": "Question text",
                "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                "correct_answer": "A",
                "explanation": "Why this answer is correct"
            }}

            Return only a JSON array of 5 questions.
            """
        
        elif quiz_type == "true_false":
            prompt = f"""
            Based on the following content, create 5 true/false questions:

            {content}

            Context: {context}

            Format each question as JSON with this structure:
            {{
                "question": "Statement to evaluate",
                "correct_answer": "True" or "False",
                "explanation": "Explanation of why this is true or false"
            }}

            Return only a JSON array of 5 questions.
            """
        
        elif quiz_type == "essay":
            prompt = f"""
            Based on the following content, create 3 essay questions:

            {content}

            Context: {context}

            Format each question as JSON with this structure:
            {{
                "question": "Essay question that requires detailed analysis",
                "key_points": ["Key point 1", "Key point 2", "Key point 3"],
                "suggested_length": "Number of paragraphs or words"
            }}

            Return only a JSON array of 3 questions.
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
                # Use AI to score the essay
                prompt = f"""
                Score this essay answer on a scale of 0-100 based on:
                1. Relevance to the question
                2. Depth of understanding
                3. Use of key concepts
                4. Quality of explanation

                Question: {question.get('question', '')}
                Key points that should be covered: {', '.join(question.get('key_points', []))}
                
                Student's answer: {answer}

                Provide your response in this JSON format:
                {{
                    "score": <number 0-100>,
                    "feedback": "Detailed feedback explaining the score and suggestions for improvement"
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
