import streamlit as st
from google import genai
import PyPDF2
import os
import random
import time
import re
from dotenv import load_dotenv

# --- 1. Configuration & Security ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    st.error("⚠️ API Key not found! Create a '.env' file with GOOGLE_API_KEY=your_key")
    st.stop()

client = genai.Client(api_key=API_KEY)
KNOWLEDGE_FOLDER = "manuals"

SYSTEM_INSTRUCTION = """
You are an expert Indian Railways Technical Examiner. Generate high-quality MCQs based ONLY on the provided manual text.

RULES:
1. Provide exactly 4 options (A, B, C, D).
2. Mark the correct answer (Letter).
3. Provide a brief 'Explanation'.

Formatting:
Question [Number]: [Question Text]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
Correct Answer: [Letter]
Explanation: [Rationale]
"""

# --- 2. Session State for Quiz Tab ---
if "quiz_questions" not in st.session_state:
    st.session_state.quiz_questions = []
if "quiz_user_answers" not in st.session_state:
    st.session_state.quiz_user_answers = {}
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False

# --- 3. Helper Functions ---
@st.cache_data
def index_local_pdf(filepath):
    chunks = []
    try:
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text and len(text.strip()) > 150:
                    chunks.append(text)
    except Exception as e:
        st.error(f"Error reading file: {e}")
    return chunks

def parse_questions(text):
    pattern = r"Question \d+: (.*?)\nA\) (.*?)\nB\) (.*?)\nC\) (.*?)\nD\) (.*?)\nCorrect Answer: ([A-D])\nExplanation: (.*?)(?=\nQuestion|$)"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{
        "question": m[0].strip(),
        "options": [m[1].strip(), m[2].strip(), m[3].strip(), m[4].strip()],
        "correct": m[5].strip(),
        "explanation": m[6].strip()
    } for m in matches]

def get_motivation(score_pct):
    quotes = {
        "low": ["Keep learning! Every mistake is a step toward safety.", "Review the manual. Technical precision saves lives."],
        "mid": ["Good job! You're building a solid technical foundation.", "Well done! Aim for 100% in the next attempt."],
        "high": ["Excellent! You have a master-level grasp of these manuals.", "Perfect! The Railways need experts like you."]
    }
    if score_pct < 50: return random.choice(quotes["low"])
    if score_pct < 85: return random.choice(quotes["mid"])
    return random.choice(quotes["high"])

# --- 4. Main UI ---
st.set_page_config(page_title="Railway Examiner", page_icon="🚆", layout="wide")
st.title("🚆 Indian Railways Knowledge Portal")

tab1, tab2 = st.tabs(["📄 MCQ Document Generator", "📝 Interactive Quiz Center"])

# --- TAB 1: GENERATE ONLY ---
with tab1:
    st.header("Generate MCQ Document")
    st.write("Use this tab to create question papers to copy-paste or download.")
    
    available_pdfs = sorted([f for f in os.listdir(KNOWLEDGE_FOLDER) if f.endswith('.pdf')]) if os.path.exists(KNOWLEDGE_FOLDER) else []
    
    if not available_pdfs:
        st.warning("Please add PDF manuals to the 'manuals' folder.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1: selected_pdf = st.selectbox("Select Manual", available_pdfs, key="t1_pdf")
        with c2: t1_num = st.number_input("How many questions?", 1, 50, 10, key="t1_num")
        with c3: t1_diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="t1_diff")
        
        if st.button("Generate Paper", key="t1_btn"):
            pages = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, selected_pdf))
            full_text = ""
            with st.spinner("Writing questions..."):
                for i in range(0, t1_num, 5):
                    batch = min(5, t1_num - i)
                    response = client.models.generate_content(
                        model="gemini-flash-lite-latest",
                        config={'system_instruction': SYSTEM_INSTRUCTION},
                        contents=f"Generate {batch} questions from Question {i+1}. Difficulty: {t1_diff}. Source: {random.choice(pages)}"
                    )
                    full_text += response.text + "\n\n"
            
            st.text_area("Generated Content (Copy from here)", full_text, height=400)
            st.download_button("📩 Download as .txt", full_text, file_name="Railway_MCQs.txt")

# --- TAB 2: TAKE A QUIZ ---
with tab2:
    st.header("Interactive Technical Quiz")
    
    if not available_pdfs:
        st.warning("Please add PDF manuals to start a quiz.")
    else:
        # Quiz Settings
        if not st.session_state.quiz_questions:
            qc1, qc2, qc3 = st.columns(3)
            with qc1: q_pdf = st.selectbox("Select Manual", available_pdfs, key="q_pdf")
            with qc2: q_num = st.number_input("Questions", 1, 20, 5, key="q_num")
            with qc3: q_diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="q_diff")
            
            if st.button("🏁 Start Fresh Quiz"):
                pages = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, q_pdf))
                raw_quiz = ""
                with st.status("Preparing your exam paper...") as s:
                    for i in range(0, q_num, 5):
                        batch = min(5, q_num - i)
                        resp = client.models.generate_content(
                            model="gemini-flash-lite-latest",
                            config={'system_instruction': SYSTEM_INSTRUCTION},
                            contents=f"Generate {batch} questions starting at {i+1}. Difficulty: {q_diff}. Source: {random.choice(pages)}"
                        )
                        raw_quiz += resp.text + "\n"
                    
                    st.session_state.quiz_questions = parse_questions(raw_quiz)
                    st.session_state.quiz_submitted = False
                    st.session_state.quiz_user_answers = {}
                    s.update(label="Exam Ready!", state="complete")
                st.rerun()
        
        # Quiz Interface
        else:
            if not st.session_state.quiz_submitted:
                st.info(f"Answer the questions below. Questions are based on your selected manual.")
                for i, q in enumerate(st.session_state.quiz_questions):
                    st.markdown(f"**Q{i+1}: {q['question']}**")
                    u_choice = st.radio("Pick one:", ["-", "A", "B", "C", "D"], 
                                       format_func=lambda x: x if x == "-" else f"{x}) {q['options'][ord(x)-65]}",
                                       key=f"quiz_radio_{i}")
                    st.session_state.quiz_user_answers[i] = u_choice
                    st.write("---")
                
                if st.button("📤 Submit for Evaluation"):
                    st.session_state.quiz_submitted = True
                    st.rerun()
            
            # Result Interface
            else:
                score = 0
                st.subheader("📊 Your Evaluation Report")
                for i, q in enumerate(st.session_state.quiz_questions):
                    u_ans = st.session_state.quiz_user_answers.get(i)
                    correct = q["correct"]
                    is_right = u_ans == correct
                    if is_right: score += 1
                    
                    with st.expander(f"Question {i+1}: {'✅ Correct' if is_right else '❌ Incorrect'}", expanded=not is_right):
                        st.write(f"**Your Answer:** {u_ans}")
                        st.write(f"**Correct Answer:** {correct}) {q['options'][ord(correct)-65]}")
                        st.info(f"**Technical Explanation:** {q['explanation']}")
                
                pct = (score / len(st.session_state.quiz_questions)) * 100
                st.divider()
                c_res1, c_res2 = st.columns(2)
                c_res1.metric("Final Score", f"{pct:.1f}%", f"{score}/{len(st.session_state.quiz_questions)}")
                c_res2.info(f"**Motivation:** {get_motivation(pct)}")
                
                if st.button("🔄 Retake or Change Manual"):
                    st.session_state.quiz_questions = []
                    st.rerun()