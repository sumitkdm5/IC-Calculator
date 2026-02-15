import streamlit as st
import boto3
import json
import pandas as pd
import pdfplumber
from fpdf import FPDF
import io

# ==========================================
# CONFIGURATION SECTION
# ==========================================
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except FileNotFoundError:
    # Fallback for local testing without secrets.toml
    AWS_ACCESS_KEY = "PLACEHOLDER"
    AWS_SECRET_KEY = "PLACEHOLDER" 
    AWS_REGION = "us-east-1"

# ==========================================
# 1. THE ARCHITECT: BEDROCK CONNECTOR
# ==========================================
def extract_json(text):
    try:
        # Clean markdown code blocks if present
        text = text.replace('```json', '').replace('```', '')
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            json_str = text[start:end]
            return json.loads(json_str, strict=False)
        return None
    except Exception:
        return None

def ask_claude_json(sales_context, plan_rules_text, question, column_info=""):
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    # We explicitly tell Claude about the columns to fix the 'Missing Data' error
    prompt = f"""
    You are an Expert Incentive Compensation Analyst.
    
    === DATA STRUCTURE ===
    The user has uploaded a file with these columns: {column_info}
    Please map these columns to the Plan Rules logically (e.g., 'NeuroCalm' in data = 'Product A' in plan).
    
    === PLAN RULES ===
    {plan_rules_text}

    === SALES DATA ===
    {sales_context}

    === USER QUESTION ===
    {question}

    === RESPONSE FORMAT ===
    Return a valid JSON object only. Do not add conversational filler.
    {{
        "final_answer_summary": "Direct answer here.",
        "detailed_logic": "Step-by-step math explanation.",
        "chart_data": {{ "Label": 100, "Label2": 200 }} 
    }}
    If data is missing for a specific calculation, estimate based on available trends but mention the assumption.
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
        parsed_data = extract_json(raw_text)
        
        if parsed_data:
            return parsed_data
        else:
            return {
                "final_answer_summary": "⚠️ AI Parsing Error (Try Again)", 
                "detailed_logic": raw_text, 
                "chart_data": {}
            }
    except Exception as e:
        return {"final_answer_summary": "System Error", "detailed_logic": str(e), "chart_data": {}}

# ==========================================
# 2. DATA HANDLERS
# ==========================================
def get_default_plan():
    # Only used if no PDF is uploaded
    return "Default Demo Plan: Consumables (50% wt) and Capital (30% wt)."

def get_demo_data():
    return """
Date,Customer Name,Product Category,Sales Amount,Units
2024-05-15,KENTUCKY CLINIC,Consumables,2800,4
2024-05-15,DUKE UNIVERSITY HOSPITAL,Capital,4500,5
2024-05-15,PADUCAH OUTPATIENT SURGERY CENTER,Consumables,700,1
2024-05-15,NORTHWESTERN MEMORIAL HOSPITAL,Consumables,3500,5
2024-05-15,HOUSTON METHODIST HOSPITAL,Capital,8100,9
2024-05-15,UCSF MEDICAL CENTER,Capital,900,1
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
    
    # Extract column names to help the AI map fields dynamically
    columns = ", ".join(list(df.columns))
    # Convert to CSV string (limit to 400 rows to fit context window)
    csv_string = df.head(400).to_csv(index=False)
    return csv_string, columns

# ==========================================
# 3. UI & STATE MANAGEMENT
# ==========================================
st.set_page_config(page_title="Smart Incentive Calculator", layout="wide")

# -- Reset History on Mode Change to avoid Ghost Data --
def reset_history():
    st.session_state.history = []

if 'history' not in st.session_state:
    st.session_state.history = []

col_title, col_btn = st.columns([6, 1])
with col_title:
    st.title("🤖 Smart Incentive Navigator")
with col_btn:
    st.button("Clear Chat", on_click=reset_history)

# -- Mode Selection --
mode = st.radio(
    "Select Mode:", 
    ["Demo Sandbox", "Custom Lab (Upload Data)"], 
    horizontal=True,
    on_change=reset_history # Wipes chat when you switch!
)

current_sales_data = ""
current_plan_rules = ""
current_columns = ""

if mode == "Demo Sandbox":
    # Load Default Data
    current_sales_data = get_demo_data()
    current_plan_rules = get_default_plan()
    current_columns = "Date, Customer Name, Product Category, Sales Amount, Units"
    st.info("🟢 **Demo Mode:** Using Pre-loaded Medical Device Data.")

else:
    # Custom Lab Logic
    st.warning("🟠 **Custom Lab:** Upload your Hackathon Data (Excel/PDF).")
    c1, c2 = st.columns(2)
    with c1:
        sales_file = st.file_uploader("1. Upload Sales Data (Excel/CSV)", type=['xlsx', 'csv'])
    with c2:
        plan_file = st.file_uploader("2. Upload Plan Rules (PDF)", type=['pdf'])
    
    if sales_file:
        current_sales_data, current_columns = process_sales_file(sales_file)
        st.success(f"✅ Sales Data Loaded ({len(current_sales_data.splitlines())} rows)")
    else:
        st.info("Waiting for Sales Data...")

    if plan_file:
        current_plan_rules = extract_text_from_pdf(plan_file)
        st.success("✅ Plan Rules Extracted")
    else:
        current_plan_rules = "No specific plan uploaded. Infer rules from data columns."

# ==========================================
# 4. INTERFACE
# ==========================================
tab1, tab2 = st.tabs(["📈 Smart Simulator", "📄 Data Inspector"])

with tab1:
    if current_sales_data:
        st.markdown("### ⚡ Quick Actions")
        
        # DYNAMIC BUTTONS BASED ON MODE
        if mode == "Demo Sandbox":
            # Original Medical Device Buttons
            xc1, xc2, xc3 = st.columns(3)
            if xc1.button("🚀 Simulate: +10 Capital Units"):
                st.session_state.prompt = "Simulate if I sold 10 more Capital Units in May. How does this impact my payout?"
            if xc2.button("🏆 Top Prescriber"):
                st.session_state.prompt = "Analyze the data. Who is the Top Customer by total sales amount?"
            if xc3.button("📉 Analyze Low Perf"):
                st.session_state.prompt = "Which month had the lowest sales and why?"
        else:
            # GOTHAM / HACKATHON BUTTONS (Bruce Wayne Scenario)
            yc1, yc2, yc3 = st.columns(3)
            if yc1.button("🌪️ Analyze: Cyclone Impact"):
                st.session_state.prompt = "Analyze my March Payout. How did the Cyclone affect my check? Look for adjustments."
            if yc2.button("📉 Identify: Churn Risk"):
                st.session_state.prompt = "Analyze the transaction history. Who is my biggest Churn Risk in Retail and why?"
            if yc3.button("🎯 Goal: Course Correction"):
                st.session_state.prompt = "I am behind on my Semester Target of $60,000. How many units of CardioFix do I need to sell in May/June to catch up?"

        # Chat Input
        user_input = st.chat_input("Type your question here...")
        if user_input:
            st.session_state.prompt = user_input

        # Processing
        if 'prompt' in st.session_state:
            with st.spinner("🤖 Analyzing Scenario..."):
                # Pass the 'current_columns' to help AI map the fields
                result = ask_claude_json(current_sales_data, current_plan_rules, st.session_state.prompt, current_columns)
                st.session_state.history.insert(0, {"q": st.session_state.prompt, "a": result})
            del st.session_state.prompt

        # Display History
        for item in st.session_state.history:
            st.write("---")
            st.markdown(f"**Q:** {item['q']}")
            res = item['a']
            
            # Error Handling in UI
            summary = res.get('final_answer_summary', 'Error processing request.')
            if "Error" in summary:
                st.error(summary)
            else:
                st.success(f"**A:** {summary}")
            
            with st.expander("See Logic & Charts"):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(res.get('detailed_logic', 'No logic provided.'))
                with col_b:
                    if res.get('chart_data'):
                        st.bar_chart(pd.DataFrame(list(res['chart_data'].items()), columns=["K", "V"]).set_index("K"))
    else:
        if mode == "Custom Lab (Upload Data)":
             st.info("👋 Please upload your 'Bruce Wayne' Sales Data above to activate the Simulator.")

with tab2:
    st.subheader("Debug Context")
    st.text(f"Detected Columns: {current_columns}")
    with st.expander("View Raw Sales Data Payload"):
        st.text(current_sales_data[:2000] if current_sales_data else "Empty")