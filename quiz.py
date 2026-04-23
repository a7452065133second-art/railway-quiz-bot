import streamlit as st
from google import genai
import PyPDF2
import os
import random
import re
import json
from dotenv import load_dotenv

# --- 1. Configuration & Security ---
load_dotenv()

# Fixed Key Loading: Checks .env FIRST, then Streamlit Secrets. 
# This prevents the "StreamlitSecretNotFoundError" locally.
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    try:
        API_KEY = st.secrets["GOOGLE_API_KEY"]
    except:
        st.error("⚠️ API Key not found! Add GOOGLE_API_KEY to your .env file or Streamlit Secrets.")
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

# --- 2. Hardcoded Table of Contents for your 7 Manuals ---
PREDEFINED_TOCS = {
    "IRTMM.pdf": [
        "CHAPTER 1 ORGANISATIONAL STRUCTURE, DUTIES AND INSPECTIONS",
        "CHAPTER 2 TAMPING MACHINE AND DYNAMIC TRACK STABILIZER",
        "CHAPTER 3 BALLAST CLEANING AND HANDLING MACHINES",
        "CHAPTER 4 TRACK RELAYING MACHINES",
        "CHAPTER 5 SPECIAL PURPOSE MACHINES",
        "CHAPTER 6 PLANNING AND DEPLOYMENT",
        "CHAPTER 7 RULES FOR MOVEMENT AND BLOCK WORKING",
        "CHAPTER 8 PERIODICAL MAINTENANCE AND ASSOCIATED INFRASTRUCTURAL FACILITY",
        "CHAPTER 9 MANPOWER",
        "CHAPTER 10 STORES AND CONTRACTS",
        "CHAPTER 11 MONITORING"
    ],
    "IRPWM 2024 Corrected Up To ACS - 11 (26-02-2026).pdf": [
        "ABBREVIATIONS AND TERMINOLOGY",
        "CHAPTER 1 - DUTIES OF PERMANENT WAY OFFICIALS",
        "CHAPTER 2 - TRACK STRUCTURE AND COMPONENTS",
        "CHAPTER 3 - INSTALLATION AND MAINTENANCE OF WELDED RAILS",
        "CHAPTER 4 - CURVES & TURNOUTS",
        "CHAPTER 5 - TRACK MONITORING & TOLERANCES",
        "CHAPTER 6 - MAINTENANCE OF PERMANENT WAY",
        "CHAPTER 7 - PERMANENT WAY RENEWALS",
        "CHAPTER 8 - ENGINEERING RESTRICTIONS & INDICATORS",
        "CHAPTER 9 - LEVEL CROSSINGS AND GATEMAN",
        "CHAPTER 10 - PATROLLING OF THE RAILWAY LINE",
        "CHAPTER 11 - ACTION DURING ACCIDENTS",
        "CHAPTER 12 - CRS SANCTION",
        "CHAPTER 13 - TRACK MANAGEMENT SYSTEM",
        "CHAPTER 14 - TRAINING, COMPETENCY & REFERENCES",
        "CHAPTER 15 - EMERGING TRACK TECHNOLOGY ITEMS"
    ],
    "ATWeldManual-2022.pdf": [
        "1. Introduction", "2. Scope", "3. Selection of Rail to be welded",
        "4. Execution of joints at site", "5. Operations subsequent to welding",
        "6. Acceptance tests", "7. Sample test joint", "8. Other requirements",
        "9. Precautions", "10. Defects in A.T. welding", "11. Check list for inspection of A.T. welds"
    ],
    "IRS Track Manual Revised-2024.pdf": [
        "CHAPTER I - RAILS AND FISHPLATES (RF)", "CHAPTER II - SLEEPER FASTENINGS (SF)",
        "CHAPTER III - CAST IRON SLEEPERS (SC)", "CHAPTER IV - STEEL TROUGH SLEEPERS (SS)",
        "CHAPTER V - TURNOUTS, SWITCHES AND CROSSINGS (TSC)", "CHAPTER VI - DIAMONDS AND SLIPS (DS)",
        "CHAPTER VII - SCISSORS AND ORDINARY CROSSOVERS (SX)", "CHAPTER VIII - PRESTRESSED CONCRETE SLEEPERS (SPC)",
        "CHAPTER IX - SWITCH EXPANSION JOINTS (SEJ)", "CHAPTER X - TRACK TOOLS AND MISCELLANEOUS DRAWINGS",
        "CHAPTER XI - TRACK FORMULAE (TF)"
    ],
    "Manual for Glued Insulated Rail Joint  (Revised-2024).pdf": [
        "0. FOREWORD", "1. MATERIAL AND EQUIPMENT FOR FABRICATION",
        "2. FABRICATION / ASSEMBLY OF GLUED JOINTS", "3. TESTING AND INSPECTION OF GLUED JOINTS",
        "4. INSTALLATION AND MAINTENANCE OF GLUED JOINTS", "5. PROCEDURE FOR JOINT INSPECTION",
        "6. RE-FURBISHING OF EXISTING GLUED JOINTS", "7. ANNEXURE-A MATERIALS",
        "8. ANNEXURE-B SPECIFICATIONS", "9. ANNEXURE-C JOINT INSPECTION"
    ],
    "USFDMANUAL.pdf": [
        "1 Rail defects and their codification", "2 Ultrasonic testing of rails at manufacturer’s works",
        "3 Ultrasonic rail testing equipment and accessories", "4 Calibration and Maintenance of machines",
        "5 Procedure for undertaking ultrasonic testing", "6 Need based concept in USFD testing",
        "7 Limitations of ultrasonic flaw detection", "8 Testing of Alumino-thermic welded rail joints",
        "9 Testing of flash butt and gas pressure welded joints", "10 Testing of rails for fabrication",
        "11 Testing technique of worn out point", "13 Reporting and analysis of Rail/Weld failures"
    ],
    "FBW_Manual.pdf": [
        "1 Scope", "2 Selection of Rail to be welded", "3 Suitability of rails for welding",
        "4 Preparation of rails to be welded", "5 Procedure of welding of rails",
        "6 Record of welds", "7 Post-weld straightening", "8 Finishing", "9 Marking of joints",
        "10 Testing of weld", "11 Handling of high strength rails", "12 Check list for FBW plants"
    ]
}

# --- 3. Session State Initializer ---
for key in ["quiz_questions", "quiz_user_answers", "quiz_submitted", "current_toc"]:
    if key not in st.session_state:
        st.session_state[key] = [] if "questions" in key or "toc" in key else {}
st.session_state.quiz_submitted = st.session_state.get("quiz_submitted", False)

# --- 4. Helper Functions ---
@st.cache_data
def index_local_pdf(filepath):
    pages = []
    try:
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text: pages.append(text)
    except Exception as e:
        st.error(f"Error: {e}")
    return pages

def get_toc(filename):
    """Checks dictionary first, then falls back to AI."""
    # Clean filename for match
    clean_fn = filename.strip()
    if clean_fn in PREDEFINED_TOCS:
        return PREDEFINED_TOCS[clean_fn]
    return ["General Manual Content"]

def find_page_index(all_pages, title):
    # Search for the core text of the chapter title
    search_term = re.sub(r'^(CHAPTER [A-Z0-9]+:?\s*-?\s*|\d+\.\s*|\d+\s+)', '', title, flags=re.IGNORECASE).strip().lower()
    for i, pg_text in enumerate(all_pages):
        if i > 2 and search_term in pg_text.lower()[:800]: 
            return i
    return -1

def get_dynamic_text(all_pages, toc_list, selected_title):
    if selected_title == "All Topics (Random)": return random.choice(all_pages)
    start_idx = find_page_index(all_pages, selected_title)
    if start_idx == -1: return random.choice(all_pages)
    
    end_idx = len(all_pages)
    try:
        curr_pos = toc_list.index(selected_title)
        if curr_pos < len(toc_list) - 1:
            nxt = find_page_index(all_pages, toc_list[curr_pos + 1])
            if nxt != -1 and nxt > start_idx: end_idx = nxt
    except: pass
    
    # Take a representative 10-page chunk if chapter is huge
    if (end_idx - start_idx) > 10: end_idx = start_idx + 10
    return "\n".join(all_pages[start_idx:end_idx])

def parse_questions(text):
    pattern = r"Question \d+: (.*?)\nA\) (.*?)\nB\) (.*?)\nC\) (.*?)\nD\) (.*?)\nCorrect Answer: ([A-D])\nExplanation: (.*?)(?=\nQuestion|$)"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"question": m[0].strip(), "options": [m[1], m[2], m[3], m[4]], "correct": m[5], "explanation": m[6]} for m in matches]

# --- 5. UI Layout ---
st.set_page_config(page_title="Railway Examiner", page_icon="🚆", layout="wide")
st.title("🚆 IR Technical Manual Portal")

tab1, tab2 = st.tabs(["📄 MCQ Generator", "📝 Interactive Quiz"])
available_pdfs = [f for f in os.listdir(KNOWLEDGE_FOLDER) if f.endswith('.pdf')] if os.path.exists(KNOWLEDGE_FOLDER) else []

# --- TAB 1: MCQ GENERATOR ---
with tab1:
    if not available_pdfs: st.warning("Add PDFs to 'manuals' folder.")
    else:
        pdf_sel = st.selectbox("Select Manual", available_pdfs, key="gen_pdf")
        toc = get_toc(pdf_sel)
        c1, c2, c3 = st.columns(3)
        topic_sel = c1.selectbox("Topic", ["All Topics (Random)"] + toc, key="gen_top")
        num_q = c2.number_input("Questions", 1, 30, 5)
        diff = c3.selectbox("Difficulty", ["Easy", "Medium", "Hard"])
        
        if st.button("Generate Paper"):
            all_pgs = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, pdf_sel))
            context = get_dynamic_text(all_pgs, toc, topic_sel)
            with st.spinner("Generating..."):
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    config={'system_instruction': SYSTEM_INSTRUCTION},
                    contents=f"Topic: {topic_sel}. Num: {num_q}. Diff: {diff}. Context: {context}"
                )
                st.text_area("Results", resp.text, height=400)

# --- TAB 2: INTERACTIVE QUIZ ---
with tab2:
    if not available_pdfs: st.warning("Add PDFs to 'manuals' folder.")
    else:
        if not st.session_state.quiz_questions:
            q_pdf = st.selectbox("Select Manual", available_pdfs, key="qz_pdf")
            q_toc = get_toc(q_pdf)
            qc1, qc2, qc3 = st.columns(3)
            q_topic = qc1.selectbox("Topic", ["All Topics (Random)"] + q_toc, key="qz_top")
            q_num = qc2.number_input("Questions", 1, 20, 5, key="qz_num")
            q_diff = qc3.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="qz_diff")
            
            if st.button("🏁 Start Quiz"):
                all_pgs = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, q_pdf))
                context = get_dynamic_text(all_pgs, q_toc, q_topic)
                with st.spinner("Preparing Exam..."):
                    resp = client.models.generate_content(
                        model="gemini-flash-lite-latest",
                        config={'system_instruction': SYSTEM_INSTRUCTION},
                        contents=f"Topic: {q_topic}. Num: {q_num}. Diff: {q_diff}. Context: {context}"
                    )
                    st.session_state.quiz_questions = parse_questions(resp.text)
                    st.session_state.quiz_submitted = False
                    st.rerun()
        else:
            if not st.session_state.quiz_submitted:
                for i, q in enumerate(st.session_state.quiz_questions):
                    st.markdown(f"**Q{i+1}:** {q['question']}")
                    st.session_state.quiz_user_answers[i] = st.radio(f"Select Answer for Q{i+1}:", 
                                                                    ["A", "B", "C", "D"], 
                                                                    index=None, key=f"r_{i}",
                                                                    format_func=lambda x: f"{x}) {q['options'][ord(x)-65]}")
                    st.divider()
                if st.button("Submit Test"):
                    st.session_state.quiz_submitted = True
                    st.rerun()
            else:
                # --- RESULTS EVALUATION ---
                score = 0
                st.header("📊 Results & Review")
                for i, q in enumerate(st.session_state.quiz_questions):
                    u_ans = st.session_state.quiz_user_answers.get(i)
                    correct = q["correct"]
                    is_right = (u_ans == correct)
                    if is_right: score += 1
                    
                    with st.container(border=True):
                        st.markdown(f"**Q{i+1}: {q['question']}**")
                        for idx, L in enumerate(["A", "B", "C", "D"]):
                            txt = f"{L}) {q['options'][idx]}"
                            if L == correct: st.success(f"✅ {txt}")
                            elif L == u_ans: st.error(f"❌ {txt} (Your Choice)")
                            else: st.write(txt)
                        st.info(f"**Explanation:** {q['explanation']}")
                
                pct = (score/len(st.session_state.quiz_questions))*100
                st.metric("Final Score", f"{pct:.1f}%", f"{score}/{len(st.session_state.quiz_questions)}")
                if st.button("New Test"):
                    st.session_state.quiz_questions = []
                    st.rerun()