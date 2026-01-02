import streamlit as st
import boto3
import json
import pandas as pd
from fpdf import FPDF

# ==========================================
# CONFIGURATION SECTION (SECURE FOR CLOUD)
# ==========================================
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except FileNotFoundError:
    # Fallback for local testing if secrets.toml isn't set up
    AWS_ACCESS_KEY = "YOUR_ACCESS_KEY"
    AWS_SECRET_KEY = "YOUR_SECRET_KEY" 
    AWS_REGION = "us-east-1"

# ==========================================
# 1. THE ARCHITECT: BEDROCK CONNECTOR
# ==========================================
def ask_claude_json(context, question):
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    prompt = f"""
    You are an expert Incentive Compensation Analyst. 
    You have access to the Plan Rules and the Rep's Sales Data below.

    === PLAN RULES ===
    1. Consumables (Weight 50%): Formula: (Actual/Quota)*100 = Attainment%. Look up on Curve. 
       - Quota: $60k. Target Pay: $5k. Curve: 80%->80%, 100%->100%, 150%->180%.
    2. Capital (Weight 30%): Tiered Commission on UNITS. 
       - 50-75u: $100 | 76-100u: $250 | 101-125u: $500.
    3. MBO (Weight 20%): Avg: $1k | Good: $2.5k | Exc: $5k.
    4. GLOBAL ELIGIBILITY: May: 99% | June: 98% | July: 97%.

    === REP DATA ===
    {context}

    === USER QUESTION ===
    {question}

    === RESPONSE FORMAT (CRITICAL) ===
    You must respond in a valid JSON object format.
    
    IMPORTANT FORMATTING RULES FOR 'detailed_logic':
    - You MUST use Markdown formatting.
    - Use numbered lists (1., 2., 3.) for main steps.
    - Use bullet points (- ) for sub-calculations.
    - Use bolding (**text**) for final numbers in each step.
    - Add newlines (\\n) between every distinct step so it reads clearly.

    Structure:
    {{
        "final_answer_summary": "A short, punchy summary (max 2 sentences).",
        "detailed_logic": "1. **Step One:** Calc...\\n\\n2. **Step Two:** Calc...\\n  - Sub-step math...",
        "chart_data": {{
            "Baseline Payout": 1234.56,
            "Simulated Payout": 2345.67
        }}
    }}
    """

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2500,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    })

    try:
        response = bedrock.invoke_model(body=body, modelId="anthropic.claude-3-5-sonnet-20240620-v1:0")
        response_body = json.loads(response.get('body').read())
        return json.loads(response_body['content'][0]['text'])
    except Exception as e:
        return {"final_answer_summary": "Error", "detailed_logic": str(e), "chart_data": {}}

# ==========================================
# 2. DATA LAYER (NOW GENERIC)
# ==========================================
def load_data():
    return """
    REP: Jordan Doe | ID: REP-2024-X
    
    MONTH: MAY
    - Consumables Sales: $40,600 (Quota: $60,000)
    - Capital Units: 66 Units (Tier 1)
    - MBO Rating: Good ($2,500 base)
    - Eligibility: 99%
    
    MONTH: JUNE
    - Consumables Sales: $58,800
    - Capital Units: 65 Units
    - MBO Rating: Excellent
    - Eligibility: 98%
    
    MONTH: JULY
    - Consumables Sales: $23,100
    - Capital Units: 41 Units
    - MBO Rating: Average
    - Eligibility: 97%
    """

def create_pdf(text_content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    clean_text = text_content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, clean_text)
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. THE POP-UP DIALOG FUNCTION
# ==========================================
@st.dialog("Welcome to the Smart IC Navigator")
def show_about_dialog():
    st.markdown("""
    **👋 What is this app?**
    This is a technical prototype of an **AI-powered Incentive Compensation Calculator**. It demonstrates how Generative AI can sit on top of complex structured data to provide human-like explanations.

    **🎯 Why was this created?**
    To showcase the "Art of the Possible" in modern Product Management—specifically how LLMs (like Claude 3.5) can be used to interpret compensation plans dynamically.

    **⚙️ How does it function?**
    1.  **Input:** Takes raw sales data (CSV) and Plan Rules (Text).
    2.  **Process:** Uses AWS Bedrock to calculate math and generate logic.
    3.  **Output:** Visualizes the "Baseline" vs. "Simulated" payout differences.

    **✅ What can this app do?**
    * Simulate "What-If" scenarios (e.g., "What if I sold 10 more units?").
    * Explain complex math in simple English.
    * Visualize payout gaps with dynamic charts.

    **❌ What can this app NOT do?**
    * **No Live Data:** This demo uses static, synthetic data (Jordan Doe). It does not connect to real production databases.
    * **No Write-Back:** Changes made here are for simulation only; they do not update actual payroll records.
    """)
    if st.button("Get Started 🚀"):
        st.rerun()

# ==========================================
# 4. THE UI: MAIN APP
# ==========================================
st.set_page_config(page_title="Smart Incentive Calculator", layout="wide")

# --- HEADER SECTION ---
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.title("🤖 Smart Incentive Calculator")
with col_btn:
    if st.button("ℹ️ About App"):
        show_about_dialog()

# --- FIRST LOAD LOGIC ---
if "first_visit" not in st.session_state:
    st.session_state.first_visit = True
    show_about_dialog()

# Initialize Session History
if 'history' not in st.session_state:
    st.session_state.history = []

tab1, tab2 = st.tabs(["📈 Smart Simulator", "📄 Context & Data"])

with tab1:
    st.info("Ask me to simulate payouts, explain gaps, or suggest strategies.")
    
    # --- INPUT SECTION ---
    c1, c2, c3 = st.columns(3)
    if c1.button("🚀 Simulate: +10 Capital Units (May)"):
        st.session_state.current_prompt = "Simulate if I sold 10 more Capital Units in May."
    if c2.button("🎯 Goal: Reach $5k Payout (July)"):
        st.session_state.current_prompt = "I want to earn $5,000 in July. Suggest a strategy."
    if c3.button("📉 Analyze: Why was July low?"):
        st.session_state.current_prompt = "Why was July payout lower than June? Show the gap."

    user_input = st.chat_input("Type your own scenario...")
    if user_input:
        st.session_state.current_prompt = user_input

    # --- PROCESSING LOGIC ---
    if 'current_prompt' in st.session_state:
        prompt_text = st.session_state.current_prompt
        
        with st.spinner("🤖 AI is thinking..."):
            data_context = load_data()
            result = ask_claude_json(data_context, prompt_text)
            
            st.session_state.history.insert(0, {
                "question": prompt_text,
                "result": result
            })
        
        del st.session_state.current_prompt

    # --- HISTORY DISPLAY LOOP ---
    if len(st.session_state.history) > 0:
        st.write("---")
        st.subheader("📜 Session History")
        
        for i, item in enumerate(st.session_state.history):
            result = item['result']
            question = item['question']
            
            with st.container():
                st.markdown(f"### Q: {question}")
                st.success(f"**Answer:** {result.get('final_answer_summary')}")
                
                col_chart, col_logic = st.columns([1, 1])
                
                with col_chart:
                    chart_data = result.get('chart_data')
                    if chart_data and len(chart_data) > 0:
                        df = pd.DataFrame(list(chart_data.items()), columns=["Scenario", "Payout ($)"])
                        st.bar_chart(df.set_index("Scenario"))
                
                with col_logic:
                    with st.expander("🧐 See Mathematical Proof"):
                        st.markdown(result.get('detailed_logic'))
                st.markdown("---")

with tab2:
    st.header("Admin Context")
    raw_text = load_data()
    st.code(raw_text, language="yaml")
    pdf_bytes = create_pdf(raw_text)
    st.download_button("Download Data as PDF", pdf_bytes, "IC_Context.pdf", "application/pdf")