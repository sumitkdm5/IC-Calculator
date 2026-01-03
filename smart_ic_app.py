import streamlit as st
import boto3
import json
import pandas as pd
import pdfplumber
from fpdf import FPDF
import re

# ==========================================
# CONFIGURATION SECTION (SECURE)
# ==========================================
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except FileNotFoundError:
    AWS_ACCESS_KEY = "PLACEHOLDER_DO_NOT_COMMIT"
    AWS_SECRET_KEY = "PLACEHOLDER_DO_NOT_COMMIT" 
    AWS_REGION = "us-east-1"

# ==========================================
# 1. THE ARCHITECT: BEDROCK CONNECTOR
# ==========================================
def extract_json(text):
    """
    Finds the first valid JSON object in a string and parses it.
    """
    try:
        # 1. Strip Markdown code blocks if present
        text = text.replace('```json', '').replace('```', '')
        
        # 2. Find start and end braces
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start != -1 and end != 0:
            json_str = text[start:end]
            # 3. Safe Load: 'strict=False' allows control characters like newlines inside strings
            return json.loads(json_str, strict=False)
        return None
    except Exception:
        return None

def ask_claude_json(sales_context, plan_rules_text, question, is_strict_mode=False):
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    if is_strict_mode:
        safety_instruction = """
        === AUDITOR MODE ACTIVE (STRICT) ===
        1. VALIDATE DATA: If the Plan requires a variable missing in Data, STOP.
           - Return JSON: {"final_answer_summary": "⚠️ Error: Missing Data [Variable Name].", "detailed_logic": "", "chart_data": {}}
        """
    else:
        safety_instruction = "=== DEMO MODE ===\nAssume standard defaults if minor details are missing."

    prompt = f"""
    You are an Expert Incentive Compensation Analyst.
    {safety_instruction}

    === PLAN RULES ===
    {plan_rules_text}

    === SALES DATA ===
    {sales_context}

    === USER QUESTION ===
    {question}

    === RESPONSE FORMAT (CRITICAL) ===
    You must respond in a valid JSON object format only. Do not add intro text.
    
    Structure:
    {{
        "final_answer_summary": "Your summary here.",
        "detailed_logic": "1. Step One...\\n2. Step Two...",
        "chart_data": {{ "Label": 100 }}
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
        raw_text = response_body['content'][0]['text']
        
        # Attempt Parse
        parsed_data = extract_json(raw_text)
        
        if parsed_data:
            return parsed_data
        else:
            # Fallback if parsing fails: Return text as simple error
            return {
                "final_answer_summary": "⚠️ Technical Parsing Error. Here is the raw AI response:", 
                "detailed_logic": raw_text, 
                "chart_data": {}
            }

    except Exception as e:
        return {"final_answer_summary": "System Error", "detailed_logic": f"Detail: {str(e)}", "chart_data": {}}

# ==========================================
# 2. DATA HANDLERS (UPGRADED DEMO DATA)
# ==========================================
def get_default_plan():
    return """
    1. Consumables (Weight 50%): Formula: (Actual/Quota)*100 = Attainment%.
       - Quota: $60k. Target Pay: $5k. Curve: 80%->80%, 100%->100%, 150%->180%.
    2. Capital (Weight 30%): Tiered Commission on UNITS. 
       - 50-75u: $100 | 76-100u: $250 | 101-125u: $500.
    3. MBO (Weight 20%): Avg: $1k | Good: $2.5k | Exc: $5k.
    """

def get_demo_data():
    # RICH CSV DATA instead of Summary
    return """
    Date,Customer Name,Product Category,Sales Amount,Units
    2024-05-15,Mercy Hospital,Consumables,15000,0
    2024-05-20,Dr. Smith Clinic,Capital,25000,30
    2024-05-25,General Health,Capital,20000,36
    2024-05-28,Mercy Hospital,Consumables,25600,0
    2024-06-10,Dr. Smith Clinic,Consumables,30000,0
    2024-06-15,General Health,Capital,28800,65
    2024-07-05,Mercy Hospital,Consumables,5000,0
    2024-07-10,Dr. Smith Clinic,Capital,18100,41
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
    return df.head(300).to_csv(index=False)

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
@st.dialog("Welcome to the Smart IC Navigator")
def show_about_dialog():
    st.markdown("""
    **👋 What is this app?**
    This is a technical prototype of an **AI-powered Incentive Compensation Calculator**.

    **🎯 Key Features:**
    * **Simulate:** "What if I sold 10 more units?"
    * **Analyze:** "Who is my Top Customer?" (New!)
    * **Predict:** "Who is at risk of Churning?"
    
    **Two Modes:**
    1. **Demo Sandbox:** Uses rich sample data (Mercy Hospital, Dr. Smith).
    2. **Custom Lab:** Upload your own Excel/PDF files.
    """)
    if st.button("Get Started 🚀"):
        st.rerun()

# ==========================================
# 4. MAIN UI
# ==========================================
st.set_page_config(page_title="Smart Incentive Calculator", layout="wide")
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.title("🤖 Smart Incentive Calculator")
with col_btn:
    if st.button("ℹ️ About App"):
        show_about_dialog()

if "first_visit" not in st.session_state:
    st.session_state.first_visit = True
    show_about_dialog()

if 'history' not in st.session_state:
    st.session_state.history = []

mode = st.radio("Select Mode:", ["Demo Sandbox", "Custom Lab (Upload Data)"], horizontal=True)

if mode == "Demo Sandbox":
    current_sales_data = get_demo_data()
    current_plan_rules = get_default_plan()
    is_strict = False
    st.info("🟢 **Demo Mode:** Using sample data (Mercy Hospital, Dr. Smith, etc.)")

else: 
    st.warning("🟠 **Custom Lab:** Data is stateless. Files disappear on refresh.")
    c1, c2 = st.columns(2)
    with c1:
        sales_file = st.file_uploader("1. Upload Sales Data (Excel/CSV)", type=['xlsx', 'csv'])
    with c2:
        plan_file = st.file_uploader("2. Upload Plan Rules (PDF) - Optional", type=['pdf'])
    
    if sales_file:
        current_sales_data = process_sales_file(sales_file)
        st.success("✅ Sales Data Loaded")
    else:
        current_sales_data = None
        st.error("⚠️ Please upload Sales Data to proceed.")

    if plan_file:
        current_plan_rules = extract_text_from_pdf(plan_file)
        st.success("✅ Custom Plan Rules Extracted")
    else:
        current_plan_rules = get_default_plan()
        st.info("ℹ️ Using Default Plan Rules (Upload PDF to override)")
    
    is_strict = True

# --- INTERFACE ---
tab1, tab2 = st.tabs(["📈 Smart Simulator", "📄 Data Inspector"])

with tab1:
    if current_sales_data:
        st.markdown("### ⚡ Quick Actions")
        
        c1, c2, c3 = st.columns(3)
        if c1.button("🚀 Simulate: +10 Capital Units"):
            st.session_state.prompt = "Simulate if I sold 10 more Capital Units in May. How does this impact my payout?"
        if c2.button("🎯 Goal: Reach $5k Payout"):
            st.session_state.prompt = "I want to earn $5,000 in Consumables Commission next month. How much do I need to sell?"
        if c3.button("📉 Analyze: Low Performance"):
            st.session_state.prompt = "Analyze the data. Which month had the lowest sales and why?"

        c4, c5 = st.columns(2)
        if c4.button("🏆 Top Prescriber"):
            st.session_state.prompt = "Analyze the data. Who is the Top Customer by total sales amount? Show the number."
        if c5.button("🔮 Churn Prediction"):
            st.session_state.prompt = "Look at the data month-by-month. Which customer has stopped buying or decreased significantly?"

        user_input = st.chat_input("Type your own scenario...")
        if user_input:
            st.session_state.prompt = user_input

        if 'prompt' in st.session_state:
            with st.spinner("🤖 Analyzing..."):
                result = ask_claude_json(current_sales_data, current_plan_rules, st.session_state.prompt, is_strict)
                st.session_state.history.insert(0, {"q": st.session_state.prompt, "a": result})
            del st.session_state.prompt

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