import streamlit as st
from google import genai
import PyPDF2
import os
import random
import re
from dotenv import load_dotenv
from fpdf import FPDF

# Simple Password Protection
def check_password():
    if "password_correct" not in st.session_state:
        st.text_input("Enter Access Code", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

def password_entered():
    if st.session_state["password"] == "Railbot1702": # You can change this password
        st.session_state["password_correct"] = True
        del st.session_state["password"]
    else:
        st.error("Incorrect code")

if not check_password():
    st.stop()

# --- 1. Configuration & Security ---
load_dotenv()

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
3. Provide a brief 'Explanation' based purely on the text.
4. DO NOT invent information. Absolute technical accuracy is required.
5. Generate EXACTLY the number of questions requested. Do not stop early.
Formatting:
Question [Number]: [Question Text]
A) [Option]
B) [Option]
C) [Option]
D) [Option]
Correct Answer: [Letter]
Explanation: [Rationale]
"""

# --- 2. Hardcoded Table of Contents ---
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
        "CHAPTER IX - SWITCH EXPANSION JOIN TO (SEJ)", "CHAPTER X - TRACK TOOLS AND MISCELLANEOUS DRAWINGS",
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
if "quiz_questions" not in st.session_state: st.session_state.quiz_questions = []
if "quiz_user_answers" not in st.session_state: st.session_state.quiz_user_answers = {}
if "quiz_submitted" not in st.session_state: st.session_state.quiz_submitted = False
if "generated_text" not in st.session_state: st.session_state.generated_text = None

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
        st.error(f"Error reading PDF: {e}")
    return pages

def get_toc(filename):
    clean_fn = filename.strip()
    return PREDEFINED_TOCS.get(clean_fn, ["General Manual Content"])

def find_page_index(all_pages, title):
    search_term = re.sub(r'^(CHAPTER [A-Z0-9]+:?\s*-?\s*|\d+\.\s*|\d+\s+)', '', title, flags=re.IGNORECASE).strip().lower()
    for i, pg_text in enumerate(all_pages):
        if i > 2 and search_term in pg_text.lower()[:800]: 
            return i
    return -1

def get_dynamic_text(all_pages, toc_list, selected_title):
    if not all_pages: return ""
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
    
    # Extract the entire chapter text
    chapter_pages = all_pages[start_idx:end_idx]
    
    # Randomly slice a chunk of up to 15 pages from WITHIN the chapter to ensure variety every time
    if len(chapter_pages) > 15:
        max_start = len(chapter_pages) - 15
        rand_start = random.randint(0, max_start)
        chapter_pages = chapter_pages[rand_start : rand_start + 15]
        
    return "\n".join(chapter_pages)

def parse_questions(text):
    if not text: return []
    pattern = r"Question \d+: (.*?)\nA\) (.*?)\nB\) (.*?)\nC\) (.*?)\nD\) (.*?)\nCorrect Answer: ([A-D])\nExplanation: (.*?)(?=\nQuestion \d+:|$)"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"question": m[0].strip(), "options": [m[1].strip(), m[2].strip(), m[3].strip(), m[4].strip()], "correct": m[5].strip(), "explanation": m[6].strip()} for m in matches]

def create_pdf_report(questions, title="Railway MCQ Report"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title.encode('latin-1', 'replace').decode('latin-1'), ln=True, align='C')
    pdf.ln(10)
    
    for i, q in enumerate(questions):
        pdf.set_font("Helvetica", "B", 12)
        q_text = f"Q{i+1}: {q['question']}"
        pdf.multi_cell(0, 10, q_text.encode('latin-1', 'replace').decode('latin-1'))
        
        pdf.set_font("Helvetica", "", 12)
        for idx, char in enumerate(["A", "B", "C", "D"]):
            opt_text = f"  {char}) {q['options'][idx]}"
            pdf.cell(0, 8, opt_text.encode('latin-1', 'replace').decode('latin-1'), ln=True)
        
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, f"Correct Answer: {q['correct']}", ln=True)
        pdf.set_font("Helvetica", "I", 11)
        exp_text = f"Explanation: {q['explanation']}"
        pdf.multi_cell(0, 8, exp_text.encode('latin-1', 'replace').decode('latin-1'))
        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
    return pdf.output(dest='S').encode('latin-1', 'replace')

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
        num_q = c2.number_input("Questions", 1, 50, 5, key="gen_num") # Limit increased to 50
        diff = c3.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="gen_diff")
        
        if st.button("Generate Paper", key="gen_btn"):
            all_pgs = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, pdf_sel))
            context = get_dynamic_text(all_pgs, toc, topic_sel)
            
            # Dynamic prompt parameters to enforce variety
            seed = random.randint(1, 100000)
            prompt_content = f"Seed: {seed}. Topic: {topic_sel}. Generate exactly {num_q} unique questions. Ensure you cover completely different technical details than typical questions. Diff: {diff}. Context: {context}"
            
            with st.spinner(f"Generating {num_q} questions... (This might take a minute)"):
                resp = client.models.generate_content(
                    model="gemini-flash-lite-latest",
                    config={
                        'system_instruction': SYSTEM_INSTRUCTION,
                        'temperature': 0.7 # Increased temperature for variety
                    },
                    contents=prompt_content
                )
                st.session_state.generated_text = resp.text

        if st.session_state.generated_text:
            st.text_area("Results", st.session_state.generated_text, height=400)
            parsed_qs = parse_questions(st.session_state.generated_text)
            if parsed_qs:
                pdf_data = create_pdf_report(parsed_qs, f"Generated MCQs: {pdf_sel}")
                st.download_button(
                    label=f"📥 Download {len(parsed_qs)} Questions as PDF",
                    data=pdf_data,
                    file_name=f"MCQs_{topic_sel.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key="dl_btn_tab1"
                )
            else:
                st.error("Could not parse the generated questions. Please try generating again.")

# --- TAB 2: INTERACTIVE QUIZ ---
with tab2:
    if not available_pdfs: st.warning("Add PDFs to 'manuals' folder.")
    else:
        if not st.session_state.quiz_questions:
            q_pdf = st.selectbox("Select Manual", available_pdfs, key="qz_pdf")
            q_toc = get_toc(q_pdf)
            qc1, qc2, qc3 = st.columns(3)
            q_topic = qc1.selectbox("Topic", ["All Topics (Random)"] + q_toc, key="qz_top")
            q_num = qc2.number_input("Questions", 1, 50, 5, key="qz_num") # Limit increased to 50
            q_diff = qc3.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key="qz_diff")
            
            if st.button("🏁 Start Quiz"):
                all_pgs = index_local_pdf(os.path.join(KNOWLEDGE_FOLDER, q_pdf))
                context = get_dynamic_text(all_pgs, q_toc, q_topic)
                
                seed = random.randint(1, 100000)
                prompt_content = f"Seed: {seed}. Topic: {q_topic}. Generate exactly {q_num} unique questions. Ensure you cover completely different technical details than typical questions. Diff: {q_diff}. Context: {context}"
                
                with st.spinner(f"Preparing {q_num} Question Exam..."):
                    resp = client.models.generate_content(
                        model="gemini-flash-lite-latest",
                        config={
                            'system_instruction': SYSTEM_INSTRUCTION,
                            'temperature': 0.7
                        },
                        contents=prompt_content
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
                
                pdf_report = create_pdf_report(st.session_state.quiz_questions, f"Quiz Result: {score}/{len(st.session_state.quiz_questions)} ({pct:.1f}%)")
                st.download_button(
                    label="📥 Download Quiz Report as PDF",
                    data=pdf_report,
                    file_name="Quiz_Results.pdf",
                    mime="application/pdf",
                    key="dl_btn_tab2"
                )

                if st.button("New Test"):
                    st.session_state.quiz_questions = []
                    st.session_state.quiz_user_answers = {}
                    st.session_state.quiz_submitted = False
                    st.rerun()