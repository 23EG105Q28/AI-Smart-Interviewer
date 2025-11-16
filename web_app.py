"""
AI Soft Skill Evaluator - Web Application
Flask backend with real-time video processing and speech analysis
"""

from flask import Flask, render_template, Response, jsonify, request, send_file, session
import cv2
import numpy as np
import speech_recognition as sr
from textblob import TextBlob
import threading
import time
import json
import base64
from datetime import datetime
import os
from io import BytesIO
import wave
from werkzeug.utils import secure_filename
import pyttsx3
from queue import Queue
import google.generativeai as genai
import random
import PyPDF2
from docx import Document

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads/resumes'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

# Global variables - English Practice
camera = None
is_recording = False
recording_start_time = None
all_transcripts = []
all_scores = []
video_frames = []
audio_frames = []
current_feedback = {}
scroll_text = ""
scroll_speed = 3

# Sample prompts for reading
SAMPLE_TEXTS = [
    "The quick brown fox jumps over the lazy dog with remarkable agility and grace",
    "Technology has revolutionized the way we communicate and interact with the world around us",
    "Effective communication is the cornerstone of professional success in any field",
    "Innovation and creativity drive progress in today's rapidly changing world",
    "Leadership requires both confidence and the ability to inspire others",
    "The journey of a thousand miles begins with a single step and unwavering determination",
    "Collaboration and teamwork are essential ingredients for achieving extraordinary results"
]

# Speech recognition
recognizer = sr.Recognizer()
speech_thread = None
audio_thread = None

# Configure Google Gemini AI for dynamic conversations (Optional - works with fallback)
GEMINI_API_KEY = "YOUR_API_KEY_HERE"  # Get free key from: https://makersuite.google.com/app/apikey
try:
    if GEMINI_API_KEY != "YOUR_API_KEY_HERE":
        genai.configure(api_key=GEMINI_API_KEY)
        ai_model = genai.GenerativeModel('gemini-pro')
        print("✅ Google Gemini AI initialized")
    else:
        ai_model = None
        print("ℹ️ Using fallback conversation mode (no API key)")
except Exception as e:
    print(f"⚠️ Could not initialize Gemini AI: {e}")
    ai_model = None

# Global variables - Interview Practice
interview_active = False
interview_questions = []
current_question_index = 0
interview_responses = []
interview_messages = []
interview_start_time = None
interview_thread = None
tts_engine = None
ai_speaking = False
user_listening = False
message_queue = Queue()
conversation_history = []  # Store entire conversation for context

# --- Resume Parsing Functions ---
def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        print(f"✅ Extracted {len(text)} characters from PDF")
        return text.strip()
    except Exception as e:
        print(f"⚠️ Error extracting PDF: {e}")
        return ""

def extract_text_from_docx(docx_path):
    """Extract text from Word document"""
    try:
        doc = Document(docx_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        print(f"✅ Extracted {len(text)} characters from DOCX")
        return text.strip()
    except Exception as e:
        print(f"⚠️ Error extracting DOCX: {e}")
        return ""

def parse_resume(file_path):
    """Parse resume and extract text based on file type"""
    if file_path.lower().endswith('.pdf'):
        return extract_text_from_pdf(file_path)
    elif file_path.lower().endswith(('.docx', '.doc')):
        return extract_text_from_docx(file_path)
    else:
        print("⚠️ Unsupported file format")
        return ""

# --- AI Interview Question Generation ---
def generate_interview_questions_from_resume(resume_text):
    """Generate personalized interview questions from resume using AI"""
    
    if not resume_text or len(resume_text) < 50:
        print("⚠️ Resume text too short, using default questions")
        return generate_default_questions()
    
    # Try to use AI to generate questions
    if ai_model is not None:
        try:
            prompt = f"""You are an experienced HR interviewer. Based on the following resume, generate exactly 6 interview questions that:
1. Are specific to the candidate's experience and skills mentioned in their resume
2. Test both technical knowledge and soft skills
3. Are conversational and professional
4. Start easy and progressively get more detailed
5. Include behavioral questions (e.g., "Tell me about a time when...")

Resume:
{resume_text[:2000]}

Generate exactly 6 questions, one per line. Just the questions, no numbering or extra text."""

            response = ai_model.generate_content(prompt)
            questions = [q.strip() for q in response.text.strip().split('\n') if q.strip() and len(q.strip()) > 10]
            
            # Filter out any numbering
            questions = [q.lstrip('0123456789.-) ') for q in questions]
            
            if len(questions) >= 4:
                print(f"✅ Generated {len(questions)} AI questions from resume")
                return questions[:6]  # Return max 6 questions
            else:
                print("⚠️ AI generated too few questions, using enhanced default")
                return generate_enhanced_questions_from_keywords(resume_text)
                
        except Exception as e:
            print(f"⚠️ AI question generation error: {e}")
            return generate_enhanced_questions_from_keywords(resume_text)
    else:
        # Fallback: Generate questions based on keywords
        return generate_enhanced_questions_from_keywords(resume_text)

def generate_enhanced_questions_from_keywords(resume_text):
    """Generate questions based on keywords found in resume"""
    text_lower = resume_text.lower()
    questions = []
    
    # Always start with introduction
    questions.append("Thank you for joining today. Let's start - can you walk me through your professional background?")
    
    # Check for specific technologies/skills
    if any(word in text_lower for word in ['python', 'java', 'javascript', 'c++', 'programming']):
        questions.append("I see you have programming experience. Can you describe a challenging technical problem you solved and your approach?")
    
    if any(word in text_lower for word in ['ai', 'machine learning', 'deep learning', 'neural network']):
        questions.append("You've worked with AI and machine learning. Can you tell me about a specific ML project and the impact it had?")
    
    if any(word in text_lower for word in ['team', 'lead', 'manage', 'collaboration']):
        questions.append("Tell me about a time when you had to work with a difficult team member. How did you handle it?")
    
    if any(word in text_lower for word in ['project', 'developed', 'built', 'created']):
        questions.append("Walk me through your most successful project from start to finish. What made it successful?")
    
    # Generic but important questions
    questions.append("What motivates you in your professional life, and how do you handle setbacks?")
    questions.append("Where do you see yourself in 3-5 years, and why is this role the right next step?")
    
    return questions[:6]

def generate_default_questions():
    """Default interview questions when resume parsing fails"""
    return [
        "Hello! Thank you for joining today. Let's start with an introduction - can you tell me about yourself?",
        "What are your key strengths and how have you demonstrated them in your previous roles?",
        "Describe a challenging project you worked on and how you overcame the obstacles.",
        "How do you handle feedback and continuous learning in your career?",
        "Where do you see yourself in the next 5 years, and how does this position align with your goals?",
        "Why are you interested in this role, and what unique value can you bring to our team?"
    ]

def generate_interview_questions(resume_text=""):
    """Legacy function - redirects to new implementation"""
    if resume_text:
        return generate_interview_questions_from_resume(resume_text)
    return generate_default_questions()

def init_tts_engine():
    """Initialize text-to-speech engine with more human-like voice"""
    global tts_engine
    if tts_engine is None:
        try:
            tts_engine = pyttsx3.init()
            
            # Get available voices
            voices = tts_engine.getProperty('voices')
            
            # Try to find a better quality voice (prefer female, English)
            selected_voice = None
            for voice in voices:
                voice_name = voice.name.lower()
                # Prefer Microsoft voices (better quality)
                if 'zira' in voice_name or 'hazel' in voice_name:  # Female voices
                    selected_voice = voice.id
                    break
                elif 'david' in voice_name:  # Male voice as backup
                    selected_voice = voice.id
            
            if selected_voice:
                tts_engine.setProperty('voice', selected_voice)
            elif len(voices) > 1:
                tts_engine.setProperty('voice', voices[1].id)
            
            # Optimize for more natural speech
            tts_engine.setProperty('rate', 170)  # Slightly faster, more natural
            tts_engine.setProperty('volume', 1.0)  # Full volume
            
            print(f"✅ TTS initialized with voice: {tts_engine.getProperty('voice')}")
        except Exception as e:
            print(f"⚠️ TTS engine initialization failed: {e}")
            tts_engine = None
    return tts_engine

def speak_text_sync(text):
    """Speak text synchronously (blocking) - Creates fresh engine each time to avoid blocking"""
    global ai_speaking
    import time
    
    try:
        ai_speaking = True
        print(f"🗣️ 🔊 AI SPEAKING OUT LOUD: {text[:80]}...")
        print(f"🔊 FULL TEXT: {text}")
        print("🎤 >>> CHECK YOUR SPEAKERS - VOICE SHOULD BE PLAYING NOW <<<")
        
        # Create a fresh engine instance for each speak call (prevents blocking issues)
        engine = pyttsx3.init()
        
        # Set voice properties
        voices = engine.getProperty('voices')
        if len(voices) > 1:
            # Try to use a better voice
            for voice in voices:
                if 'david' in voice.name.lower() or 'zira' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
        
        engine.setProperty('rate', 170)  # Speech rate
        engine.setProperty('volume', 1.0)  # Maximum volume
        
        # Speak and wait
        engine.say(text)
        engine.runAndWait()
        
        # CRITICAL: Add delay after speaking to prevent audio cutoff
        time.sleep(0.3)  # 300ms delay to ensure audio completes
        
        # Clean up
        try:
            engine.stop()
            del engine  # Force garbage collection
        except Exception:
            pass
        
        # Additional small delay before next operation
        time.sleep(0.2)
        
        ai_speaking = False
        print("✅ ✅ ✅ FINISHED SPEAKING - DID YOU HEAR IT? ✅ ✅ ✅")
        print("-" * 80)
        return True
        
    except Exception as e:
        print(f"⚠️ TTS error: {e}")
        import traceback
        traceback.print_exc()
        ai_speaking = False
        return False

def get_follow_up_response(_user_answer):
    """Generate natural follow-up responses based on user's answer"""
    responses = [
        "That's interesting. ",
        "I see. ",
        "Great point. ",
        "Excellent. ",
        "Thank you for sharing that. ",
        "That makes sense. ",
        "Good to know. ",
        "I appreciate that insight. "
    ]
    return random.choice(responses)

def generate_ai_response(user_answer, conversation_context):
    """
    Generate dynamic AI response based on user's answer using Gemini AI
    This creates natural, contextual follow-up questions or comments
    """
    global ai_model
    
    # Enhanced fallback system with pattern matching
    answer_lower = user_answer.lower()
    
    # Analyze the answer for keywords and generate appropriate follow-ups
    follow_up_questions = []
    
    # Career/job related
    if any(word in answer_lower for word in ['job', 'work', 'career', 'company', 'position']):
        follow_up_questions.extend([
            "That's great to hear. What specific skills do you think make you a strong fit for this role?",
            "Interesting. Can you tell me about a project or achievement you're particularly proud of in your career?",
            "I see. What are you looking for in your next career opportunity?"
        ])
    
    # Skills/technical related
    if any(word in answer_lower for word in ['skill', 'learn', 'experience', 'technology', 'develop']):
        follow_up_questions.extend([
            "That's impressive. How do you stay updated with new developments in your field?",
            "Great. Can you share an example where you applied those skills to solve a real problem?",
            "Excellent. What new skills are you currently working on developing?"
        ])
    
    # Team/collaboration related
    if any(word in answer_lower for word in ['team', 'collaborate', 'together', 'group', 'people']):
        follow_up_questions.extend([
            "Teamwork is important. How do you handle conflicts or disagreements within a team?",
            "That's good. Can you describe your ideal team environment?",
            "I appreciate that. What role do you typically take in team projects?"
        ])
    
    # Challenge/problem solving
    if any(word in answer_lower for word in ['challenge', 'problem', 'difficult', 'obstacle', 'issue']):
        follow_up_questions.extend([
            "That sounds challenging. Walk me through your approach to solving complex problems.",
            "Interesting. What did you learn from that experience?",
            "Thank you for sharing. How do you handle pressure or tight deadlines?"
        ])
    
    # Leadership/management
    if any(word in answer_lower for word in ['lead', 'manage', 'mentor', 'guide', 'responsibility']):
        follow_up_questions.extend([
            "Leadership is key. What's your management or leadership style?",
            "That's valuable. How do you motivate and inspire your team members?",
            "Good to know. Can you share an example of when you had to make a tough decision?"
        ])
    
    # Motivation/goals
    if any(word in answer_lower for word in ['motivate', 'goal', 'passion', 'drive', 'inspire']):
        follow_up_questions.extend([
            "That's inspiring. Where do you see yourself professionally in the next few years?",
            "Excellent. What drives you to excel in your work every day?",
            "I appreciate that. How do you measure success in your career?"
        ])
    
    # AI/Technology specific (since resume mentions AI)
    if any(word in answer_lower for word in ['ai', 'artificial', 'intelligence', 'machine learning', 'data']):
        follow_up_questions.extend([
            "AI is fascinating. What excites you most about working in this field?",
            "That's cutting-edge. How do you think AI will transform the industry in the coming years?",
            "Great insight. Can you describe a challenging AI project you've worked on?"
        ])
    
    # Generic acknowledgments if no patterns match
    if not follow_up_questions:
        follow_up_questions = [
            "Thank you for sharing that. Can you tell me more about your professional background?",
            "That's interesting. What would you say is your greatest professional strength?",
            "I appreciate your answer. How would your colleagues describe working with you?",
            "Good to know. What's a recent accomplishment you're proud of?",
            "That makes sense. What kind of work environment helps you thrive?",
            "Excellent. Can you walk me through your decision-making process?",
            "I see. What feedback have you received that helped you grow professionally?"
        ]
    
    # Try Gemini AI if available
    if ai_model is not None:
        try:
            # Build conversation context
            context = "You are a professional HR interviewer conducting a job interview. "
            context += "Your goal is to have a natural, engaging conversation and understand the candidate better.\n\n"
            context += "Interview conversation so far:\n"
            
            for msg in conversation_context[-6:]:  # Last 3 exchanges
                role = "Interviewer" if msg['type'] == 'ai' else "Candidate"
                context += f"{role}: {msg['content']}\n"
            
            context += f"\nCandidate's latest answer: {user_answer}\n\n"
            context += "Generate a brief, natural response that:\n"
            context += "1. Acknowledges their answer (1 sentence)\n"
            context += "2. Asks a relevant follow-up question based on what they said\n"
            context += "3. Keep it conversational and friendly (2-3 sentences max)\n"
            context += "4. Don't repeat questions already asked\n\n"
            context += "Your response:"
            
            # Generate AI response
            response = ai_model.generate_content(context)
            ai_response = response.text.strip()
            
            print(f"🤖 AI Generated Response: {ai_response[:100]}...")
            return ai_response
            
        except Exception as e:
            print(f"⚠️ AI generation error: {e}")
            # Fall through to use pattern-based questions
    
    # Use intelligent fallback
    return random.choice(follow_up_questions)

def generate_improvement_report(resume_text, interview_responses, conversation_history):
    """Generate a comprehensive improvement report based on interview performance"""
    
    print("📊 Generating improvement report...")
    
    # (user answers previously collected here are not used in this function)
    
    if ai_model is not None:
        try:
            prompt = f"""You are an expert career coach and interview trainer. Analyze the following interview performance and provide a comprehensive improvement report.

RESUME SUMMARY:
{resume_text[:1500]}

INTERVIEW QUESTIONS & ANSWERS:
"""
            for i, resp in enumerate(interview_responses, 1):
                prompt += f"\nQ{i}: {resp.get('question', 'N/A')}\n"
                prompt += f"A{i}: {resp.get('answer', 'N/A')}\n"
            
            prompt += """

Generate a detailed improvement report with the following sections:

1. OVERALL PERFORMANCE (Rate 1-10 and explain)
   - Communication clarity
   - Confidence level
   - Answer completeness
   - Professional demeanor

2. STRENGTHS (What they did well)
   - List 3-4 specific strengths with examples from their answers

3. AREAS FOR IMPROVEMENT
   - Resume improvements (specific suggestions)
   - Interview technique improvements (with examples)
   - Answer quality improvements (be specific)

4. SPECIFIC RECOMMENDATIONS
   - For resume enhancement
   - For interview preparation
   - For skill development

5. SAMPLE IMPROVED ANSWERS
   - Pick 2 questions where they could improve
   - Show how to answer them better

Keep the tone constructive, encouraging, and actionable. Be specific with examples."""

            response = ai_model.generate_content(prompt)
            report = response.text.strip()
            print("✅ AI improvement report generated")
            return report
            
        except Exception as e:
            print(f"⚠️ AI report generation error: {e}")
            return generate_fallback_report(interview_responses)
    else:
        return generate_fallback_report(interview_responses)

def generate_fallback_report(interview_responses):
    """Generate a basic improvement report without AI"""
    
    report = """
# INTERVIEW PERFORMANCE REPORT

## Overview
Thank you for completing the interview! Here's your personalized improvement report.

## Performance Analysis

### Communication Assessment
"""
    
    # Analyze answer lengths
    avg_length = sum(len(r.get('answer', '')) for r in interview_responses) / max(len(interview_responses), 1)
    
    if avg_length < 30:
        report += "- **Answer Length**: Your answers were quite brief. Try to elaborate more with specific examples.\n"
    elif avg_length < 100:
        report += "- **Answer Length**: Good balance, but could add more specific examples and details.\n"
    else:
        report += "- **Answer Length**: Excellent! You provided detailed, comprehensive answers.\n"
    
    report += "\n- **Total Questions Answered**: {}\n".format(len(interview_responses))
    report += "- **Engagement Level**: You completed the interview, showing good commitment.\n"
    
    report += """

## Key Strengths
- **Participated actively** in the interview process
- **Showed willingness** to answer all questions
- **Maintained engagement** throughout the session

## Areas for Improvement

### Resume Enhancement
1. **Quantify achievements**: Add specific numbers and metrics to your accomplishments
2. **Action verbs**: Start bullet points with strong action verbs (led, developed, achieved)
3. **Tailor content**: Customize your resume for each specific role
4. **Skills section**: Keep it updated with relevant, in-demand skills

### Interview Technique
1. **STAR Method**: Structure answers using Situation, Task, Action, Result
2. **Specific Examples**: Always back up claims with concrete examples
3. **Ask Questions**: Prepare thoughtful questions for the interviewer
4. **Practice**: Do mock interviews to build confidence

### Answer Quality
1. **Be Specific**: Replace general statements with specific achievements
2. **Show Impact**: Explain the results and impact of your work
3. **Tell Stories**: Make answers memorable with brief, relevant stories
4. **Stay Positive**: Frame challenges as learning opportunities

## Recommended Next Steps

### Immediate Actions
- [ ] Review your resume and add 2-3 quantifiable achievements
- [ ] Prepare 5 STAR-method examples from your experience
- [ ] Research the company and role thoroughly
- [ ] Practice common interview questions out loud

### Skill Development
- [ ] Identify 2-3 skills gaps and create a learning plan
- [ ] Take online courses or certifications in your field
- [ ] Build portfolio projects to showcase your abilities
- [ ] Network with professionals in your target industry

### Interview Preparation
- [ ] Record yourself answering questions and review
- [ ] Prepare questions to ask the interviewer
- [ ] Research the company's culture and values
- [ ] Plan your interview day logistics in advance

## Final Tips
1. **Confidence**: Believe in your abilities and communicate them clearly
2. **Authenticity**: Be genuine - it's better than trying to give "perfect" answers
3. **Energy**: Show enthusiasm for the role and company
4. **Follow-up**: Always send a thank-you email after interviews

Good luck with your job search! Keep practicing and refining your approach.
"""
    
    return report

def interview_conversation_thread():
    """
    Conduct structured interview with pre-generated questions from resume.
    CRITICAL PATTERN: SPEAK → Close Audio → LISTEN → Close Mic → Repeat
    This ensures TTS and microphone never compete for audio device.
    """
    global interview_active, current_question_index, ai_speaking, user_listening
    global interview_questions, interview_responses, interview_messages, conversation_history
    
    print("🎬 Starting structured interview with resume-based questions")
    print(f"📋 Total questions to ask: {len(interview_questions)}")
    
    # Initialize recognizer
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    
    # Speak initial greeting (OUTSIDE any mic context)
    greeting = "Hello and welcome! I've reviewed your resume and prepared some questions for you. Let's begin!"
    
    interview_messages.append({
        'type': 'ai',
        'content': greeting,
        'timestamp': time.time()
    })
    conversation_history.append({
        'type': 'ai',
        'content': greeting,
        'timestamp': time.time()
    })
    message_queue.put({'type': 'ai', 'content': greeting})
    
    print(f"🤖 AI: {greeting}")
    speak_text_sync(greeting)
    time.sleep(3.0)  # Longer pause after greeting to ensure audio device is released
    
    current_question_index = 0
    retry_count = 0
    max_retries = 2
    
    # ========================================
    # MAIN INTERVIEW LOOP
    # ========================================
    while interview_active and current_question_index < len(interview_questions):
        try:
            question = interview_questions[current_question_index]
            print(f"\n{'='*80}")
            print(f"🎙️ Question {current_question_index + 1}/{len(interview_questions)}")
            print(f"{'='*80}")
            
            # ========================================
            # STEP 1: SPEAK THE QUESTION (Outside mic context)
            # ========================================
            interview_messages.append({
                'type': 'ai',
                'content': question,
                'timestamp': time.time()
            })
            conversation_history.append({
                'type': 'ai',
                'content': question,
                'timestamp': time.time()
            })
            message_queue.put({'type': 'ai', 'content': question})
            
            print(f"🤖 AI: {question}")
            ai_speaking = True
            speak_text_sync(question)
            ai_speaking = False
            print("✅ Question spoken successfully!")
            
            # CRITICAL: Wait for audio device to be fully released
            time.sleep(3.0)
            
            # ========================================
            # STEP 2: LISTEN FOR ANSWER (Inside mic context)
            # ========================================
            print("🎧 Listening for your answer...")
            user_listening = True
            answer = None
            listen_success = False
            
            try:
                with sr.Microphone() as source:
                    print("🎤 Adjusting for ambient noise...")
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    print("🎤 Microphone ready - Please speak now!")
                    
                    try:
                        audio = recognizer.listen(source, timeout=60, phrase_time_limit=120)
                        user_listening = False
                        print("🎤 Audio captured, processing...")
                        
                        if not interview_active:
                            break
                        
                        # Recognize speech using Google
                        answer = recognizer.recognize_google(audio)
                        listen_success = True
                        print(f"👤 User said: {answer}")
                        
                    except sr.WaitTimeoutError:
                        user_listening = False
                        print("⚠️ Timeout - No speech detected")
                        
                        if retry_count < max_retries:
                            retry_count += 1
                            # Mic context closes here automatically
                            time.sleep(1.0)
                            
                            prompt = "I'm still here listening. Please take your time and answer when ready."
                            print(f"🤖 AI: {prompt}")
                            
                            interview_messages.append({
                                'type': 'ai',
                                'content': prompt,
                                'timestamp': time.time()
                            })
                            message_queue.put({'type': 'ai', 'content': prompt})
                            
                            speak_text_sync(prompt)
                            time.sleep(3.0)
                            continue  # Retry same question
                        else:
                            # Max retries reached, skip question
                            retry_count = 0
                            current_question_index += 1
                            
                            time.sleep(1.0)
                            skip_msg = "Let's move on to the next question."
                            print(f"🤖 AI: {skip_msg}")
                            
                            interview_messages.append({
                                'type': 'ai',
                                'content': skip_msg,
                                'timestamp': time.time()
                            })
                            message_queue.put({'type': 'ai', 'content': skip_msg})
                            
                            speak_text_sync(skip_msg)
                            time.sleep(3.0)
                            continue
                    
                    except sr.UnknownValueError:
                        user_listening = False
                        print("⚠️ Could not understand audio")
                        
                        if retry_count < max_retries:
                            retry_count += 1
                            time.sleep(1.0)
                            
                            retry_msg = "I'm sorry, I didn't quite catch that. Could you please repeat your answer?"
                            print(f"🤖 AI: {retry_msg}")
                            
                            interview_messages.append({
                                'type': 'ai',
                                'content': retry_msg,
                                'timestamp': time.time()
                            })
                            message_queue.put({'type': 'ai', 'content': retry_msg})
                            
                            speak_text_sync(retry_msg)
                            time.sleep(3.0)
                            continue
                        else:
                            retry_count = 0
                            current_question_index += 1
                            
                            time.sleep(1.0)
                            skip_msg = "Let's move to the next question."
                            speak_text_sync(skip_msg)
                            time.sleep(3.0)
                            continue
                    
                    except sr.RequestError as e:
                        user_listening = False
                        print(f"⚠️ Speech recognition error: {e}")
                        
                        time.sleep(1.0)
                        error_msg = "I'm having technical difficulties with speech recognition. Let's try the next question."
                        
                        interview_messages.append({
                            'type': 'ai',
                            'content': error_msg,
                            'timestamp': time.time()
                        })
                        message_queue.put({'type': 'ai', 'content': error_msg})
                        
                        speak_text_sync(error_msg)
                        time.sleep(3.0)
                        current_question_index += 1
                        continue
                
                # Microphone is now closed - safe to speak
                
            except Exception as mic_error:
                user_listening = False
                print(f"⚠️ Microphone error: {mic_error}")
                time.sleep(1.0)
                continue
            
            # ========================================
            # STEP 3: PROCESS THE ANSWER (Outside mic context)
            # ========================================
            if listen_success and answer:
                retry_count = 0  # Reset retry counter on success
                
                # Check if answer is too short
                if len(answer.strip()) < 5:
                    time.sleep(1.0)
                    prompt = "I'd love to hear more details. Could you elaborate on your answer?"
                    print(f"🤖 AI: {prompt}")
                    
                    interview_messages.append({
                        'type': 'ai',
                        'content': prompt,
                        'timestamp': time.time()
                    })
                    message_queue.put({'type': 'ai', 'content': prompt})
                    
                    speak_text_sync(prompt)
                    time.sleep(3.0)
                    continue  # Ask same question again
                
                # Valid answer - store it
                interview_messages.append({
                    'type': 'user',
                    'content': answer,
                    'timestamp': time.time()
                })
                conversation_history.append({
                    'type': 'user',
                    'content': answer,
                    'timestamp': time.time()
                })
                message_queue.put({'type': 'user', 'content': answer})
                
                interview_responses.append({
                    'question': question,
                    'question_number': current_question_index + 1,
                    'answer': answer,
                    'timestamp': time.time()
                })
                
                # Move to next question
                current_question_index += 1
                
                # ========================================
                # STEP 4: ACKNOWLEDGE OR FINISH (Outside mic context)
                # ========================================
                time.sleep(1.0)  # Brief pause before speaking
                
                if current_question_index >= len(interview_questions):
                    # All questions completed - generate report
                    closing = "Thank you so much for your time! You've provided some great answers. Let me prepare your personalized improvement report now."
                    print(f"🤖 AI: {closing}")
                    
                    interview_messages.append({
                        'type': 'ai',
                        'content': closing,
                        'timestamp': time.time()
                    })
                    conversation_history.append({
                        'type': 'ai',
                        'content': closing,
                        'timestamp': time.time()
                    })
                    message_queue.put({'type': 'ai', 'content': closing})
                    
                    speak_text_sync(closing)
                    time.sleep(2.0)
                    
                    # Generate improvement report
                    print("📊 Generating improvement report...")
                    resume_text = session.get('resume_text', '')
                    improvement_report = generate_improvement_report(resume_text, interview_responses, conversation_history)
                    session['improvement_report'] = improvement_report
                    
                    report_msg = "Your improvement report is ready! You can view and download it now."
                    print(f"🤖 AI: {report_msg}")
                    
                    interview_messages.append({
                        'type': 'ai',
                        'content': report_msg,
                        'timestamp': time.time()
                    })
                    message_queue.put({'type': 'ai', 'content': report_msg})
                    
                    speak_text_sync(report_msg)
                    break
                    
                else:
                    # More questions remaining - acknowledge and continue
                    acknowledgments = [
                        "Great answer! ",
                        "Thank you for sharing that. ",
                        "That's very helpful. ",
                        "Excellent response. ",
                        "I appreciate that insight. "
                    ]
                    ack = random.choice(acknowledgments) + "Let's continue to the next question."
                    print(f"🤖 AI: {ack}")
                    
                    interview_messages.append({
                        'type': 'ai',
                        'content': ack,
                        'timestamp': time.time()
                    })
                    message_queue.put({'type': 'ai', 'content': ack})
                    
                    speak_text_sync(ack)
                    time.sleep(3.0)
        
        except Exception as e:
            print(f"⚠️ Error in interview loop: {e}")
            import traceback
            traceback.print_exc()
            
            user_listening = False
            ai_speaking = False
            
            if interview_active:
                time.sleep(1.0)
                error_msg = "I encountered an issue. Let's try to continue."
                speak_text_sync(error_msg)
                time.sleep(2.0)
                current_question_index += 1
    
    # ========================================
    # CLEANUP
    # ========================================
    print("🏁 Interview completed!")
    interview_active = False
    user_listening = False
    ai_speaking = False

# --- Text-based soft skill analysis ---
def analyze_text_softskills(text):
    """Analyze text for confidence, clarity, and fluency"""
    feedback = {}

    # Sentiment as confidence (0-30 points) using TextBlob
    blob = TextBlob(text)
    sentiment_polarity = blob.sentiment.polarity  # Returns -1 to 1
    confidence_score = ((sentiment_polarity + 1) / 2) * 30
    feedback["confidence"] = round(confidence_score, 1)

    # Clarity (grammar)
    try:
        corrected = blob.correct()
        errors = len(str(corrected).split()) - len(str(blob).split())
        clarity_score = max(0, 30 - abs(errors) * 5)
    except Exception as e:
        print(f"⚠️ Error computing clarity score: {e}")
        clarity_score = 25
    feedback["clarity"] = round(clarity_score, 1)

    # Fluency
    sentences = text.split(".")
    avg_sentence_length = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    filler_words = sum(text.lower().count(w) for w in ["um", "uh", "like", "you know"])
    fluency_score = min(max(avg_sentence_length * 3 - filler_words * 5, 0), 20)
    feedback["fluency"] = round(fluency_score, 1)

    # Overall score
    feedback["score"] = round(feedback["confidence"] + feedback["clarity"] + feedback["fluency"], 1)
    
    return feedback

# --- Generate comprehensive improvement report ---
def generate_improvement_report(transcripts, scores, duration):
    """Generate detailed report with improvement suggestions"""
    
    report = {
        "session_summary": {},
        "performance_metrics": {},
        "strengths": [],
        "areas_for_improvement": [],
        "detailed_recommendations": [],
        "general_tips": [],
        "transcript": " ".join(transcripts) if transcripts else "No speech detected"
    }
    
    if not scores:
        report["session_summary"] = {
            "status": "No speech detected",
            "message": "No analysis could be performed. Please speak clearly into the microphone."
        }
        return report
    
    # Calculate averages
    avg_confidence = sum(s["confidence"] for s in scores) / len(scores)
    avg_clarity = sum(s["clarity"] for s in scores) / len(scores)
    avg_fluency = sum(s["fluency"] for s in scores) / len(scores)
    avg_total = sum(s["score"] for s in scores) / len(scores)
    
    # Session summary
    report["session_summary"] = {
        "duration_seconds": round(duration, 1),
        "total_segments": len(transcripts),
        "total_words": sum(len(t.split()) for t in transcripts),
        "average_words_per_segment": round(sum(len(t.split()) for t in transcripts) / len(transcripts), 1) if transcripts else 0,
        "overall_score": round(avg_total, 1)
    }
    
    # Performance metrics
    report["performance_metrics"] = {
        "confidence": round(avg_confidence, 1),
        "clarity": round(avg_clarity, 1),
        "fluency": round(avg_fluency, 1),
        "consistency": round(100 - (np.std([s["score"] for s in scores]) * 5), 1)
    }
    
    # Identify strengths
    if avg_confidence >= 20:
        report["strengths"].append("✅ Strong confidence and positive tone")
    if avg_clarity >= 20:
        report["strengths"].append("✅ Excellent grammar and clarity")
    if avg_fluency >= 15:
        report["strengths"].append("✅ Good fluency and sentence structure")
    
    # Areas for improvement
    if avg_confidence < 20:
        report["areas_for_improvement"].append("⚠️ Confidence - Work on maintaining a positive and assured tone")
    if avg_clarity < 20:
        report["areas_for_improvement"].append("⚠️ Clarity - Focus on grammar and clear articulation")
    if avg_fluency < 15:
        report["areas_for_improvement"].append("⚠️ Fluency - Reduce filler words and improve sentence structure")
    
    # Detailed recommendations
    if avg_confidence < 20:
        report["detailed_recommendations"].append({
            "skill": "Confidence & Tone",
            "current_score": round(avg_confidence, 1),
            "target_score": "20-30",
            "suggestions": [
                "Practice speaking with conviction and enthusiasm",
                "Use positive language and avoid hesitant phrases",
                "Smile while speaking to naturally improve tone",
                "Record yourself and listen to identify areas lacking confidence"
            ]
        })
    
    if avg_clarity < 20:
        report["detailed_recommendations"].append({
            "skill": "Clarity & Grammar",
            "current_score": round(avg_clarity, 1),
            "target_score": "25-30",
            "suggestions": [
                "Review basic grammar rules and sentence construction",
                "Speak slower to ensure proper word choice",
                "Practice pronouncing words clearly",
                "Read your transcript and identify grammatical errors to avoid"
            ]
        })
    
    if avg_fluency < 15:
        report["detailed_recommendations"].append({
            "skill": "Fluency & Flow",
            "current_score": round(avg_fluency, 1),
            "target_score": "15-20",
            "suggestions": [
                "Eliminate filler words (um, uh, like, you know)",
                "Practice pausing instead of using fillers",
                "Structure your thoughts before speaking",
                "Use varied sentence lengths for better flow",
                "Practice with the scrolling text at different speeds"
            ]
        })
    
    # Overall improvement tips
    report["general_tips"] = [
        "🎯 Practice regularly with this tool to track improvement",
        "📚 Read the scrolling text aloud multiple times to build fluency",
        "🎥 Review your recorded sessions to identify patterns",
        "⏱️ Time yourself - aim to maintain quality over longer durations",
        "👥 Practice with real interviews or presentations scenarios",
        "🔄 Iterate - each session should show measurable improvement"
    ]
    
    # Score interpretation
    if avg_total >= 60:
        report["interpretation"] = "Excellent! You demonstrate strong communication skills."
    elif avg_total >= 40:
        report["interpretation"] = "Good performance with room for targeted improvement."
    elif avg_total >= 20:
        report["interpretation"] = "Fair - Focus on the recommended areas to improve significantly."
    else:
        report["interpretation"] = "Needs improvement - Practice regularly and focus on fundamentals."
    
    return report

# --- Speech recognition thread ---
def listen_speech():
    """Continuously listen for speech when recording"""
    global current_feedback, all_transcripts, all_scores, is_recording
    
    with sr.Microphone() as source:
        print("🎤 Speech recognition initialized")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        
        while True:
            if not is_recording:
                time.sleep(0.5)
                continue
            
            try:
                print("🎙 Listening...")
                audio = recognizer.listen(source, phrase_time_limit=6)
                
                if not is_recording:
                    break
                
                text = recognizer.recognize_google(audio)
                print(f"🗣 Detected: {text}")
                
                # Analyze the text
                analysis = analyze_text_softskills(text)
                print(f"📊 Analysis: Conf={analysis['confidence']}, Clar={analysis['clarity']}, Flu={analysis['fluency']}, Total={analysis['score']}")
                
                current_feedback = {
                    "text": text,
                    "analysis": analysis,
                    "timestamp": time.time()
                }
                
                # Store for final report
                all_transcripts.append(text)
                all_scores.append(analysis)
                
            except sr.UnknownValueError:
                pass  # Could not understand
            except sr.RequestError as e:
                print(f"⚠ Speech recognition error: {e}")
            except Exception as e:
                print(f"⚠ Error: {e}")
                time.sleep(1)

# --- Video feed generator ---
def generate_frames():
    """Generate video frames with overlays"""
    global camera, is_recording, scroll_text, video_frames
    
    if camera is None or not camera.isOpened():
        camera = cv2.VideoCapture(0)
    
    scroll_x = 0
    
    while True:
        success, frame = camera.read()
        if not success:
            break
        
        frame = cv2.flip(frame, 1)
        
        # Record frame if active
        if is_recording:
            video_frames.append(frame.copy())
        
        # Add scrolling text if recording
        if is_recording and scroll_text:
            scroll_x -= scroll_speed
            if scroll_x < -len(scroll_text) * 15:
                scroll_x = frame.shape[1]
            
            # Add semi-transparent background
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 10), (frame.shape[1], 60), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
            
            cv2.putText(frame, scroll_text, (int(scroll_x), 45), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Add feedback overlay
        if current_feedback:
            y_offset = 80
            feedback_lines = [
                f"Confidence: {current_feedback['analysis']['confidence']:.1f}/30",
                f"Clarity: {current_feedback['analysis']['clarity']:.1f}/30",
                f"Fluency: {current_feedback['analysis']['fluency']:.1f}/20",
                f"Total: {current_feedback['analysis']['score']:.1f}/80"
            ]
            
            for line in feedback_lines:
                cv2.putText(frame, line, (10, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                y_offset += 30
        
        # Add recording indicator
        if is_recording:
            cv2.circle(frame, (frame.shape[1] - 30, 30), 10, (0, 0, 255), -1)
            cv2.putText(frame, "REC", (frame.shape[1] - 80, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Encode frame
        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# --- Routes ---
@app.route('/')
def home():
    """Home page with options"""
    return render_template('home.html')

@app.route('/english_practice')
def english_practice():
    """English practice page"""
    return render_template('index.html')

@app.route('/interview_practice')
def interview_practice():
    """Interview practice - upload resume page"""
    return render_template('interview_upload.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_recording', methods=['POST'])
def start_recording():
    """Start recording session"""
    global is_recording, recording_start_time, all_transcripts, all_scores
    global video_frames, scroll_text, speech_thread, current_feedback
    
    if not is_recording:
        is_recording = True
        recording_start_time = time.time()
        all_transcripts = []
        all_scores = []
        video_frames = []
        current_feedback = {}  # Clear old feedback
        rng = np.random.default_rng()
        scroll_text = rng.choice(SAMPLE_TEXTS)

        print("🎬 Starting new recording session")

        # Start speech recognition thread if not running
        if speech_thread is None or not speech_thread.is_alive():
            speech_thread = threading.Thread(target=listen_speech, daemon=True)
            speech_thread.start()

        return jsonify({"status": "started", "text": scroll_text})
    
    return jsonify({"status": "already_recording"})

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    """Stop recording and generate report"""
    global is_recording, recording_start_time, all_transcripts, all_scores
    
    if is_recording:
        is_recording = False
        duration = time.time() - recording_start_time
        
        # Generate report
        report = generate_improvement_report(all_transcripts, all_scores, duration)
        
        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"reports/report_{timestamp}.json"
        
        os.makedirs("reports", exist_ok=True)
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            "status": "stopped",
            "report": report,
            "filename": report_filename
        })
    
    return jsonify({"status": "not_recording"})

@app.route('/get_feedback')
def get_feedback():
    """Get current feedback"""
    global current_feedback, is_recording
    
    if is_recording and current_feedback and 'analysis' in current_feedback:
        feedback_copy = current_feedback.copy()
        print(f"📊 Sending feedback: {feedback_copy['analysis']}")
        return jsonify(feedback_copy)
    
    # Return empty scores if recording but no speech yet
    if is_recording:
        return jsonify({
            "status": "listening",
            "analysis": {
                "confidence": 0,
                "clarity": 0,
                "fluency": 0,
                "score": 0
            },
            "text": ""
        })
    
    return jsonify({"status": "not_recording", "analysis": None})

@app.route('/set_speed', methods=['POST'])
def set_speed():
    """Set scrolling text speed"""
    global scroll_speed
    data = request.json
    speed = data.get('speed', 3)
    
    if 1 <= speed <= 20:
        scroll_speed = speed
        return jsonify({"status": "success", "speed": scroll_speed})
    
    return jsonify({"status": "error", "message": "Speed must be between 1 and 20"})

@app.route('/download_report/<path:filename>')
def download_report(filename):
    """Download report file"""
    try:
        # Get the full path to the file
        file_path = os.path.join(os.getcwd(), filename)
        
        if not os.path.exists(file_path):
            return jsonify({"error": f"File not found: {filename}"}), 404
        
        return send_file(file_path, 
                        as_attachment=True,
                        download_name=os.path.basename(filename),
                        mimetype='application/json')
    except Exception as e:
        print(f"❌ Error downloading report: {e}")
        return jsonify({"error": str(e)}), 404

# --- Interview Practice Routes ---
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """Handle resume upload"""
    try:
        # Check if file was uploaded
        if 'resume' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['resume']
        
        # Check if file was selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type. Please upload PDF, DOC, or DOCX"}), 400
        
        # Create upload directory if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save file with secure filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(filepath)
        
        # Store resume info in session
        session['resume_filename'] = unique_filename
        session['resume_path'] = filepath
        session['original_filename'] = filename
        
        print(f"✅ Resume uploaded: {filename} -> {unique_filename}")
        
        return jsonify({
            "status": "success",
            "message": "Resume uploaded successfully",
            "filename": unique_filename
        }), 200
        
    except Exception as e:
        print(f"❌ Error uploading resume: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/interview_session')
def interview_session():
    """Interview session page"""
    # Check if resume was uploaded
    if 'resume_filename' not in session:
        return render_template('interview_upload.html')
    
    return render_template('interview_session.html')

@app.route('/get_resume_info')
def get_resume_info():
    """Get uploaded resume information"""
    if 'original_filename' in session:
        return jsonify({
            'filename': session['original_filename'],
            'upload_time': session.get('upload_time', 'Unknown')
        })
    return jsonify({'filename': None})

@app.route('/start_interview', methods=['POST'])
def start_interview():
    """Start AI interview session with resume-based questions"""
    global interview_active, interview_questions, current_question_index
    global interview_responses, interview_messages, interview_start_time, interview_thread
    global conversation_history
    
    if not interview_active:
        interview_active = True
        interview_start_time = time.time()
        current_question_index = 0
        interview_responses = []
        interview_messages = []
        conversation_history = []  # Clear conversation history for new interview
        
        # Parse uploaded resume and generate questions
        resume_filename = session.get('resume_filename', '')
        resume_path = session.get('resume_path', '')
        
        print(f"📄 Resume file: {resume_filename}")
        print(f"📂 Resume path: {resume_path}")
        
        # Extract text from resume
        resume_text = ""
        if resume_path and os.path.exists(resume_path):
            resume_text = parse_resume(resume_path)
            session['resume_text'] = resume_text  # Store for report generation
            print(f"✅ Extracted {len(resume_text)} characters from resume")
        else:
            print("⚠️ No resume found, using default questions")
        
        # Generate questions from resume
        interview_questions = generate_interview_questions_from_resume(resume_text)
        print(f"📋 Generated {len(interview_questions)} questions")
        
        print("🎬 Starting resume-based AI interview session")
        
        # Start interview conversation thread
        if interview_thread is None or not interview_thread.is_alive():
            interview_thread = threading.Thread(target=interview_conversation_thread, daemon=True)
            interview_thread.start()
        
        # The greeting will be spoken by the thread
        greeting = "Starting your personalized interview..."
        
        return jsonify({
            'status': 'success',
            'greeting_text': greeting,
            'total_questions': len(interview_questions)
        })
    
    return jsonify({'status': 'already_active'})


@app.route('/end_interview', methods=['POST'])
def end_interview():
    """End AI interview session"""
    global interview_active
    
    interview_active = False
    duration = time.time() - interview_start_time if interview_start_time else 0
    
    # Save interview data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    interview_data = {
        'timestamp': timestamp,
        'duration': duration,
        'questions': interview_questions,
        'responses': interview_responses,
        'messages': interview_messages,
        'resume_filename': session.get('original_filename', 'Unknown')
    }
    
    # Save to file
    os.makedirs('reports/interviews', exist_ok=True)
    report_file = f'reports/interviews/interview_{timestamp}.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(interview_data, f, indent=2, ensure_ascii=False)
    
    session['last_interview_report'] = report_file
    
    print(f"✅ Interview ended - Report saved: {report_file}")
    
    return jsonify({
        'status': 'success',
        'report_file': report_file,
        'questions_answered': len(interview_responses)
    })

@app.route('/get_interview_state')
def get_interview_state():
    """Get current interview state"""
    global ai_speaking, user_listening, current_question_index
    
    # Get new messages from queue
    new_messages = []
    while not message_queue.empty():
        try:
            new_messages.append(message_queue.get_nowait())
        except Exception:
            break
    
    current_q = None
    if current_question_index < len(interview_questions):
        current_q = {
            'number': current_question_index + 1,
            'text': interview_questions[current_question_index]
        }
    
    return jsonify({
        'ai_speaking': ai_speaking,
        'listening': user_listening,
        'current_question': current_q,
        'questions_answered': len(interview_responses),
        'interview_complete': current_question_index >= len(interview_questions),
        'new_messages': new_messages
    })

@app.route('/get_improvement_report', methods=['GET'])
def get_improvement_report():
    """Get the improvement report generated after interview"""
    report = session.get('improvement_report', '')
    
    if report:
        return jsonify({
            'status': 'success',
            'report': report
        })
    else:
        return jsonify({
            'status': 'not_ready',
            'message': 'Report not yet generated'
        })

@app.route('/interview_report')
def interview_report():
    """Display interview report"""
    if 'last_interview_report' in session:
        report_file = session['last_interview_report']
        if os.path.exists(report_file):
            with open(report_file, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
            return jsonify(report_data)
    return jsonify({'error': 'No interview report available'})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎤 AI SOFT SKILL EVALUATOR - WEB VERSION")
    print("="*60)
    print("Starting server...")
    print("Access the application at: http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
