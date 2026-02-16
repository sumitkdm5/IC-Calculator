import streamlit as st
import boto3
import json
import pandas as pd
import pdfplumber
import io

# ==========================================
# CONFIGURATION SECTION
# ==========================================
try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except FileNotFoundError:
    AWS_ACCESS_KEY = "PLACEHOLDER"
    AWS_SECRET_KEY = "PLACEHOLDER" 
    AWS_REGION = "us-east-1"

# ==========================================
# 1. THE ARCHITECT: BEDROCK CONNECTOR
# ==========================================
def extract_json(text):
    """
    Robust JSON extractor that handles messy AI output
    """
    try:
        # Strip markdown code blocks
        text = text.replace('```json', '').replace('```', '')
        
        # Find the outer-most brackets
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

    prompt = f"""
    You are an Expert Incentive Compensation Analyst.
    
    === DATA STRUCTURE ===
    The user has uploaded a file with these columns: {column_info}
    Map these columns logically to the query.
    
    === PLAN RULES ===
    {plan_rules_text}

    === SALES DATA ===
    {sales_context}

    === USER QUESTION ===
    {question}

    === RESPONSE FORMAT ===
    You must return a valid JSON object only. No intro text.
    {{
        "final_answer_summary": "Direct answer here.",
        "detailed_logic": "Step-by-step math explanation.",
        "chart_data": {{ "Label": 100 }} 
    }}
    If the data seems empty, explicitly state that in the summary.
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
                "final_answer_summary": "⚠️ AI Parsing Error. Raw output below.", 
                "detailed_logic": raw_text, 
                "chart_data": {}
            }
    except Exception as e:
        return {"final_answer_summary": "System Error", "detailed_logic": str(e), "chart_data": {}}

# ==========================================
# 2. DATA HANDLERS (ROBUST VERSION)
# ==========================================
def get_default_plan():
    return "Default Demo Plan: Consumables (50% wt) and Capital (30% wt)."

def get_demo_data_string():
    return """Date,Customer Name,Product Category,Sales Amount,Units
2024-05-15,KENTUCKY CLINIC,Consumables,2800,4
2024-05-15,DUKE UNIVERSITY HOSPITAL,Capital,4500,5
2024-05-15,PADUCAH OUTPATIENT SURGERY CENTER,Consumables,700,1
2024-05-15,NORTHWESTERN MEMORIAL HOSPITAL,Consumables,3500,5
2024-05-15,HOUSTON METHODIST HOSPITAL,Capital,8100,9
2024-06-15,KENTUCKY CLINIC,Consumables,1200,2
2024-06-15,DUKE UNIVERSITY HOSPITAL,Capital,9000,10"""

def extract_text_from_pdf(uploaded_file):
    uploaded_file.seek(0)
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def process_sales_file(uploaded_file):
    """
    Robust file reader that handles multi-tab Excels and resets pointers.
    """
    uploaded_file.seek(0)
    df = pd.DataFrame()
    
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            # Read ALL sheets to find the one with data
            xls = pd.read_excel(uploaded_file, sheet_name=None, engine='openpyxl')
            
            # Find the sheet with the most rows
            max_rows = 0
            best_sheet = None
            for sheet_name, sheet_df in xls.items():
                if len(sheet_df) > max_rows:
                    max_rows = len(sheet_df)
                    best_sheet = sheet_name
            
            if best_sheet:
                df = xls[best_sheet]
            else:
                # Fallback if all empty
                df = pd.DataFrame()

        # Clean Data
        df = df.fillna(0)
        
        # Guard clause for empty files
        if len(df) == 0:
            return None, "", ""

        columns = ", ".join(list(df.columns))
        # Limit rows for AI context window
        csv_string = df.head(400).to_csv(index=False)
        
        return df, csv_string, columns

    except Exception as e:
        st.error(f"Critical File Read Error: {str(e)}")
        return None, "", ""

def generate_quick_insights(df_input):
    """
    Generates prompt suggestions without API calls.
    Uses a copy to prevent modifying the original display DF.
    """
    insights = []
    if df_input is None or len(df_input) == 0:
        return []
        
    try:
        # Work on a copy to be safe
        df = df_input.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # 1. Top Customer
        cust_col = next((c for c in df.columns if 'customer' in c or 'name' in c), None)
        sales_col = next((c for c in df.columns if 'sales' in c or 'amount' in c or 'total' in c), None)
        
        if cust_col and sales_col:
            # Sum sales by customer
            top_cust = df.groupby(cust_col)[sales_col].sum().idxmax()
            insights.append(f"💡 Insight: Analyze Top Performer ({top_cust})")
            
        # 2. Product Trends
        prod_col = next((c for c in df.columns if 'product' in c or 'item' in c), None)
        if prod_col and sales_col:
            top_prod = df.groupby(prod_col)[sales_col].sum().idxmax()
            insights.append(f"📦 Insight: Product Mix Strategy ({top_prod})")
            
    except Exception:
        # Fail silently on insights if columns don't match, to allow main app to run
        pass
    
    return insights

# ==========================================
# 3. UI & STATE MANAGEMENT
# ==========================================
st.set_page_config(page_title="Smart Incentive Simulator", layout="wide")

def reset_history():
    st.session_state.history = []

if 'history' not in st.session_state:
    st.session_state.history = []

col_title, col_btn = st.columns([6, 1])
with col_title:
    st.title("🤖 Smart Incentive Simulator")
with col_btn:
    st.button("Clear Chat", on_click=reset_history)

mode = st.radio(
    "Select Mode:", 
    ["Demo Sandbox", "Custom Lab (Upload Data)"], 
    horizontal=True,
    on_change=reset_history 
)

current_sales_data_str = ""
current_sales_df = None
current_plan_rules = ""
current_columns = ""

if mode == "Demo Sandbox":
    # Load Default Data
    current_sales_data_str = get_demo_data_string()
    current_sales_df = pd.read_csv(io.StringIO(current_sales_data_str))
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
        current_sales_df, current_sales_data_str, current_columns = process_sales_file(sales_file)
        
        if current_sales_df is not None and len(current_sales_df) > 0:
            st.success(f"✅ Sales Data Loaded ({len(current_sales_df)} rows)")
        else:
            st.error("❌ Error: loaded file has 0 rows. Please check if data is in the first sheet or unhidden.")
            
    if plan_file:
        try:
            current_plan_rules = extract_text_from_pdf(plan_file)
            st.success("✅ Plan Rules Extracted")
        except Exception as e:
            st.error(f"Error reading PDF: {e}")
    else:
        current_plan_rules = "No specific plan uploaded. Infer rules from data columns."

# ==========================================
# 4. INTERFACE
# ==========================================
tab1, tab2 = st.tabs(["📈 Smart Simulator", "📄 Data Inspector"])

with tab1:
    # Main Logic: Only run if we have a valid dataframe
    if current_sales_df is not None and len(current_sales_df) > 0:
        
        # --- DYNAMIC INSIGHTS ENGINE ---
        st.markdown("### 🔍 Auto-Detected Insights")
        detected_prompts = generate_quick_insights(current_sales_df)
        
        if detected_prompts:
            cols = st.columns(len(detected_prompts))
            for i, prompt_text in enumerate(detected_prompts):
                if cols[i].button(prompt_text, key=f"insight_{i}"):
                    st.session_state.prompt = f"{prompt_text}. Analyze the data to explain the drivers behind this."

        st.markdown("---")
        
        # --- SCENARIO BUTTONS ---
        st.markdown("### ⚡ Simulation Scenarios")
        if mode == "Demo Sandbox":
            xc1, xc2, xc3 = st.columns(3)
            if xc1.button("🚀 Simulate: +10 Capital Units"):
                st.session_state.prompt = "Simulate if I sold 10 more Capital Units in May. How does this impact my payout?"
            if xc2.button("🏆 Top Prescriber"):
                st.session_state.prompt = "Analyze the data. Who is the Top Customer by total sales amount?"
            if xc3.button("📉 Analyze Low Perf"):
                st.session_state.prompt = "Which month had the lowest sales and why?"
        else:
            # GOTHAM BUTTONS
            yc1, yc2, yc3 = st.columns(3)
            if yc1.button("🌪️ Analyze: Cyclone Impact"):
                st.session_state.prompt = "Analyze my March Payout. How did the Cyclone affect my check? Look for adjustments."
            if yc2.button("📉 Identify: Churn Risk"):
                st.session_state.prompt = "Analyze the transaction history. Who is my biggest Churn Risk in Retail and why?"
            if yc3.button("🎯 Goal: Course Correction"):
                st.session_state.prompt = "I am behind on my Semester Target of $60,000. How many units of CardioFix do I need to sell in May/June to catch up?"

        # --- CHAT ---
        user_input = st.chat_input("Type your question here...")
        if user_input:
            st.session_state.prompt = user_input

        # Execute AI Call
        if 'prompt' in st.session_state:
            with st.spinner("🤖 Analyzing Scenario..."):
                result = ask_claude_json(current_sales_data_str, current_plan_rules, st.session_state.prompt, current_columns)
                st.session_state.history.insert(0, {"q": st.session_state.prompt, "a": result})
            del st.session_state.prompt

        # Render History
        for item in st.session_state.history:
            st.write("---")
            st.markdown(f"**Q:** {item['q']}")
            res = item['a']
            
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
        st.text(current_sales_data_str[:2000] if current_sales_data_str else "Empty")