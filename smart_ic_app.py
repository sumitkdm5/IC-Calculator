import streamlit as st
import boto3
import json
import pandas as pd
import pdfplumber
from fpdf import FPDF

# ==========================================
# CONFIGURATION SECTION (SECURE FOR CLOUD)
# ==========================================
try:
    # 1. ATTEMPT TO LOAD KEYS FROM CLOUD SECRETS (THIS RUNS ONLINE)
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except FileNotFoundError:
    # 2. FALLBACK FOR LOCAL TESTING (THIS RUNS ON LAPTOP ONLY)
    # ⚠️ DO NOT PASTE REAL KEYS HERE FOR GITHUB ⚠️
    AWS_ACCESS_KEY = "PLACEHOLDER_DO_NOT_COMMIT" 
    AWS_SECRET_KEY = "PLACEHOLDER_DO_NOT_COMMIT" 
    AWS_REGION = "us-east-1"

# ==========================================
# 1. THE ARCHITECT: BEDROCK CONNECTOR
# ==========================================
def ask_claude_json(sales_context, plan_rules_text, question, is_strict_mode=False):
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    # DYNAMIC PROMPT: Adjusts based on whether we are in "Demo" or "Strict" mode
    if is_strict_mode:
        safety_instruction = """
        === AUDITOR MODE ACTIVE (STRICT) ===
        1. VALIDATE DATA: Scan the 'Sales Data' and 'Plan Rules'.
        2. MISSING DATA CHECK: If the Plan requires a variable (e.g., 'Eligibility') and it is missing in the Sales Data, STOP.
           - Return a JSON error: {"final_answer_summary": "⚠️ CRITICAL ERROR: Missing Data. I cannot find [Variable Name]."}
        3. DO NOT HALLUCINATE: Do not guess numbers.
        """
    else:
        safety_instruction = "=== DEMO MODE ===\nAssume standard defaults if minor details are missing."

    prompt = f"""
    You are an Expert Incentive Compensation Analyst.
    
    {safety_instruction}

    === PLAN RULES (SOURCE OF TRUTH) ===
    {plan_rules_text}

    === SALES DATA ===
    {sales_context}

    === USER QUESTION ===
    {question}

    === INSTRUCTIONS ===
    - Perform the calculation or analysis requested.
    - If asked for "Predictions", look for trends in the data rows.
    
    === RESPONSE FORMAT (JSON) ===
    Structure:
    {{
        "final_answer_summary": "Summary text.",
        "detailed_logic": "Markdown formatted step-by-step logic.",
        "chart_data": {{ "Label": Value }}
    }}
    """

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    })

    try:
        response = bedrock.invoke_model(body=body, modelId="anthropic.claude-3-5-sonnet-20240620-v1:0")
        response_body = json.loads(response.get('body').read())
        return json.loads(response_body['content'][0]['text'])
    except Exception as e:
        return {"final_answer_summary": "System Error", "detailed_logic": str(e), "chart_data": {}}

# ==========================================
# 2. DATA HANDLERS
# ==========================================
def get_default_plan():
    return """
    1. Consumables (Weight 50%): Formula: (Actual/Quota)*100 = Attainment%.
       - Quota: $60k. Target Pay: $5k. Curve: 80%->80%, 100%->100%, 150%->180%.
    2. Capital (Weight 30%): Tiered Commission on UNITS. 
       - 50-75u: $100 | 76-100u: $250 | 101-125u: $500.
    3. MBO (Weight 20%): Avg: $1k | Good: $2.5k | Exc: $5k.
    4. GLOBAL ELIGIBILITY: May: 99% | June: 98% | July: 97%.
    """

def get_demo_data():
    return """
    REP: Jordan Doe | ID: REP-2024-X
    MONTH: MAY | Consumables: $40,600 | Capital: 66 Units | MBO: Good
    MONTH: JUNE | Consumables: $58,800 | Capital: 65 Units | MBO: Excellent
    MONTH: JULY | Consumables: $23,100 | Capital: 41 Units | MBO: Average
    """

def extract_text_from_pdf(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def process_sales_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    return df.head(300).to_csv(index=False) # Limit rows for token safety

def create_pdf(text_content):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    clean_text = text_content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, clean_text[:2000]) 
    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# 3. POP-UP WELCOME
# ==========================================
@st.dialog("Welcome to Smart IC Calculator")
def show_welcome():
    st.markdown("""
    **👋 Welcome!**
    This AI-powered tool demonstrates the future of Incentive Compensation.
    
    **Choose your Mode:**
    1. **Demo Sandbox:** Instant simulation with pre-loaded data (Jordan Doe).
    2. **Custom Lab:** Upload your own Sales Data & Plan Documents to test real scenarios.
    """)
    if st.button("Enter Sandbox 🚀"):
        st.rerun()

# ==========================================
# 4. MAIN UI
# ==========================================
st.set_page_config(page_title="Smart Incentive Calculator", layout="wide")
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.title("🤖 Smart Incentive Calculator")
with col_btn:
    if st.button("ℹ️ About"):
        show_welcome()

if "first_visit" not in st.session_state:
    st.session_state.first_visit = True
    show_welcome()

if 'history' not in st.session_state:
    st.session_state.history = []

# --- MODE SELECTION ---
mode = st.radio("Select Mode:", ["Demo Sandbox (Jordan Doe)", "Custom Lab (Upload Data)"], horizontal=True)

# --- CONTEXT SETUP ---
if mode == "Demo Sandbox (Jordan Doe)":
    current_sales_data = get_demo_data()
    current_plan_rules = get_default_plan()
    is_strict = False
    st.info("🟢 **Demo Mode Active:** Using pre-loaded logic for instant simulation.")

else: # CUSTOM LAB MODE
    st.warning("🟠 **Custom Lab Active:** Data is stateless. Files disappear on refresh.")
    c1, c2 = st.columns(2)
    with c1:
        sales_file = st.file_uploader("1. Upload Sales Data (Excel/CSV)", type=['xlsx', 'csv'])
    with c2:
        plan_file = st.file_uploader("2. Upload Plan Rules (PDF) - Optional", type=['pdf'])
    
    # Logic for Custom Data
    if sales_file:
        current_sales_data = process_sales_file(sales_file)
        st.success("✅ Sales Data Loaded")
    else:
        current_sales_data = None
        st.error("⚠️ Please upload Sales Data to proceed.")

    # Logic for Custom Plan
    if plan_file:
        current_plan_rules = extract_text_from_pdf(plan_file)
        st.success("✅ Custom Plan Rules Extracted")
    else:
        current_plan_rules = get_default_plan()
        st.info("ℹ️ Using Default Plan Rules (Upload PDF to override)")
    
    is_strict = True # Turn on Auditor Mode

# --- INTERFACE ---
tab1, tab2 = st.tabs(["💬 AI Analyst", "📄 Data Inspector"])

with tab1:
    if current_sales_data:
        # Pre-defined buttons for Analyst
        c1, c2, c3 = st.columns(3)
        if c1.button("🏆 Top Performer Analysis"):
            st.session_state.prompt = "Analyze the data. Identify top performing Customers or Products. Show values."
        if c2.button("🔮 Churn Prediction"):
            st.session_state.prompt = "Look for customers with declining sales month-over-month. Who is at risk?"
        if c3.button("💰 Calculate Payout"):
            st.session_state.prompt = "Based on the Plan Rules and Sales Data, calculate the total payout. Show math."

        user_input = st.chat_input("Ask a question about your data...")
        if user_input:
            st.session_state.prompt = user_input

        # Processing Loop
        if 'prompt' in st.session_state:
            with st.spinner("🤖 Analyzing..."):
                result = ask_claude_json(current_sales_data, current_plan_rules, st.session_state.prompt, is_strict)
                st.session_state.history.insert(0, {"q": st.session_state.prompt, "a": result})
            del st.session_state.prompt

        # History Display
        for item in st.session_state.history:
            st.write("---")
            st.markdown(f"**Q:** {item['q']}")
            res = item['a']
            st.success(f"**A:** {res.get('final_answer_summary')}")
            
            with st.expander("See Logic & Charts"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(res.get('detailed_logic'))
                with col_b:
                    if res.get('chart_data'):
                        st.bar_chart(pd.DataFrame(list(res['chart_data'].items()), columns=["K", "V"]).set_index("K"))
    else:
        st.write("Waiting for data upload...")

with tab2:
    st.subheader("Current Context")
    st.text_area("Sales Data Payload", current_sales_data if current_sales_data else "No Data", height=200)
    st.text_area("Plan Rules Payload", current_plan_rules, height=200)