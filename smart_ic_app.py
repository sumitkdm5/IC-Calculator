import streamlit as st
import boto3
import json
import pandas as pd
import pdfplumber
import io
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import traceback

# ==========================================
# CONFIGURATION & STYLING
# ==========================================
st.set_page_config(
    page_title="Smart Incentive Simulator", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    /* Main container styling */
    .main {
        padding: 0rem 1rem;
    }
    
    /* Query suggestion cards */
    .suggestion-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: transform 0.2s;
    }
    
    .suggestion-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* Response cards */
    .response-header {
        background: linear-gradient(90deg, #00a99d 0%, #0066cc 100%);
        padding: 1rem;
        border-radius: 8px 8px 0 0;
        color: white;
        font-weight: bold;
    }
    
    .metric-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #00a99d;
        margin: 0.5rem 0;
    }
    
    /* Rule citation boxes */
    .rule-box {
        background: #e3f2fd;
        padding: 0.8rem;
        border-left: 3px solid #2196f3;
        margin: 0.5rem 0;
        border-radius: 4px;
    }
    
    /* Status badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .status-success { background: #d4edda; color: #155724; }
    .status-warning { background: #fff3cd; color: #856404; }
    .status-danger { background: #f8d7da; color: #721c24; }
    
    /* Sidebar improvements */
    .sidebar .sidebar-content {
        background: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

try:
    AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
    AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
    AWS_REGION = st.secrets["AWS_REGION"]
except (FileNotFoundError, KeyError):
    AWS_ACCESS_KEY = "PLACEHOLDER"
    AWS_SECRET_KEY = "PLACEHOLDER" 
    AWS_REGION = "us-east-1"

# ==========================================
# AI ENGINE (ENHANCED)
# ==========================================
def extract_json(text):
    """Enhanced JSON extraction with better error handling"""
    try:
        text = text.replace('```json', '').replace('```', '')
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            json_str = text[start:end]
            return json.loads(json_str, strict=False)
        return None
    except json.JSONDecodeError as e:
        st.error(f"JSON Parse Error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Extraction Error: {str(e)}")
        return None

def ask_claude_json(sales_context, plan_rules_text, question, column_info="", response_format="detailed"):
    """
    Enhanced AI query with multiple response formats
    response_format: 'quick' | 'detailed' | 'comparison'
    """
    bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    # Enhanced prompt with better structure
    prompt = f"""
    You are an Expert Incentive Compensation Analyst with deep expertise in sales compensation calculations.
    
    === DATA STRUCTURE ===
    Available columns/sheets: {column_info}
    Use ALL relevant sheets and data provided.
    
    === COMPENSATION PLAN RULES ===
    {plan_rules_text}

    === SALES & PERFORMANCE DATA ===
    {sales_context}

    === USER QUESTION ===
    {question}

    === RESPONSE FORMAT ===
    Return a valid JSON object ONLY. No preamble, no markdown formatting.
    
    CRITICAL: For chart_config data, use SIMPLE numeric values only, NOT nested objects.
    
    CORRECT format:
    {{"chart_config": {{"data": {{"Jan": 4500, "Feb": 700, "Mar": 3500}}}}}}
    
    WRONG format (DO NOT USE):
    {{"chart_config": {{"data": {{"Jan": {{"Capital": 4500, "Consumables": 2800}}}}}}}}
    
    {{
        "final_answer_summary": "A clear, actionable 1-2 sentence answer to the user's question.",
        "confidence_level": "high|medium|low",
        "key_stats": [
            {{
                "label": "Total Payout", 
                "value": "$10,000", 
                "delta": "+5% vs Target",
                "status": "success|warning|danger"
            }},
            {{
                "label": "Attainment", 
                "value": "105%", 
                "delta": "Above Quota",
                "status": "success"
            }}
        ],
        "detailed_logic_markdown": "### Step-by-Step Calculation\\n\\nUse markdown tables for calculations:\\n\\n| Month | Sales ($) | MBO Score | Total Payout ($) |\\n|-------|-----------|-----------|------------------|\\n| Jan   | 7,000     | 4         | 8,500            |\\n\\nProvide clear explanations for each step.",
        "rule_citations": [
            "Rule 3: Payout Curve - April sales at 110% triggered 2.0x accelerator",
            "Rule 6: Force Majeure - March baseline adjusted due to cyclone impact"
        ],
        "data_sources": [
            "Sales_Transactions sheet (Jan-Apr data)",
            "MBO_Scores sheet (Manager ratings)"
        ],
        "chart_config": {{
            "type": "bar|line|combo|pie", 
            "title": "Monthly Sales Trend",
            "data": {{"Jan": 4500, "Feb": 700, "Mar": 3500, "Apr": 1200}},
            "x_label": "Month",
            "y_label": "Sales Amount ($)"
        }},
        "recommendations": [
            "Focus on institutional channel - CardioFix sales show 47% higher margins",
            "Target Q2 recovery - need 15 more CardioFix units to reach semester goal"
        ],
        "risk_factors": [
            "March cyclone impact reduced payout by $5,500",
            "NeuroCalm sales trending 12% below target"
        ]
    }}
    
    IMPORTANT:
    - Use actual numbers from the data provided
    - Show all calculation steps
    - Cite specific plan rules used
    - Provide actionable insights
    - For charts, use simple numeric values only (no nested objects in chart data)
    """

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 5000,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    })

    try:
        response = bedrock.invoke_model(
            body=body, 
            modelId="anthropic.claude-sonnet-4-6"
        )
        response_body = json.loads(response.get('body').read())
        raw_text = response_body['content'][0]['text']
        parsed_data = extract_json(raw_text)
        
        if parsed_data:
            return parsed_data
        else:
            return {
                "final_answer_summary": "⚠️ AI response could not be parsed. Raw output below.", 
                "confidence_level": "low",
                "detailed_logic_markdown": raw_text, 
                "key_stats": [],
                "rule_citations": [],
                "chart_config": {},
                "recommendations": [],
                "risk_factors": []
            }
    except Exception as e:
        # ENHANCED DEBUG LOGGING
        error_details = traceback.format_exc()
        error_type = type(e).__name__
        error_message = str(e)
        
        # Display errors in the app
        st.error(f"🔴 Error Type: {error_type}")
        st.error(f"🔴 Error Message: {error_message}")
        
        with st.expander("📋 Full Error Details (click to expand)"):
            st.code(error_details, language="python")
        
        # Log to console (appears in Streamlit Cloud logs)
        print("=" * 60)
        print("BEDROCK API ERROR")
        print("=" * 60)
        print(f"Error Type: {error_type}")
        print(f"Error Message: {error_message}")
        print(f"AWS Region: {AWS_REGION}")
        print(f"Model ID: anthropic.claude-3-5-sonnet-20240620-v1:0")
        print("Full Traceback:")
        print(error_details)
        print("=" * 60)
        
        return {
            "final_answer_summary": f"System Error - {error_type}: {error_message}", 
            "confidence_level": "low",
            "detailed_logic_markdown": f"## Error Details\n\n**Type:** {error_type}\n\n**Message:** {error_message}\n\n**Full Trace:**\n```\n{error_details}\n```", 
            "chart_config": {},
            "key_stats": [],
            "rule_citations": [],
            "recommendations": [],
            "risk_factors": []
        }

# ==========================================
# DATA HANDLERS (ENHANCED)
# ==========================================
@st.cache_data(ttl=3600)
def get_default_plan():
    return """
    DEMO PLAN RULES:
    - Products: Consumables (50% weight), Capital Equipment (30% weight)
    - Payout Structure: 70% Sales Volume, 30% MBO
    - Accelerator: 2.0x multiplier for sales > 100% quota
    - Cliff: 0% payout if < 85% attainment
    """

@st.cache_data(ttl=3600)
def get_demo_data_string():
    return """
=== SHEET: Sales_Transactions ===
Date,Customer Name,Product Category,Sales Amount,Units
2024-01-15,KENTUCKY CLINIC,Consumables,2800,4
2024-01-15,DUKE UNIVERSITY HOSPITAL,Capital,4500,5
2024-02-15,PADUCAH OUTPATIENT,Consumables,700,1
2024-03-15,NORTHWESTERN MEMORIAL,Consumables,3500,5
2024-04-15,KENTUCKY CLINIC,Consumables,1200,2
"""

def extract_text_from_pdf(uploaded_file):
    """Enhanced PDF extraction"""
    uploaded_file.seek(0)
    text = ""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text if text else "No text extracted from PDF"
    except Exception as e:
        st.error(f"PDF Read Error: {str(e)}")
        return f"Error reading PDF: {str(e)}"

@st.cache_data
def process_sales_file(uploaded_file_bytes, file_name):
    """Enhanced data processing with caching"""
    combined_context = ""
    all_columns = []
    main_df = pd.DataFrame()
    max_rows = 0
    sheet_info = {}

    try:
        file_io = io.BytesIO(uploaded_file_bytes)
        
        if file_name.endswith('.csv'):
            df = pd.read_csv(file_io)
            df = df.fillna(0)
            combined_context = df.head(500).to_csv(index=False)
            all_columns = list(df.columns)
            main_df = df
            sheet_info['csv_data'] = {'rows': len(df), 'columns': len(df.columns)}
            
        else:  # Excel
            xls = pd.read_excel(file_io, sheet_name=None, engine='openpyxl')
            for sheet_name, sheet_df in xls.items():
                sheet_df = sheet_df.fillna(0)
                combined_context += f"\n\n=== SHEET: {sheet_name} ===\n"
                combined_context += sheet_df.head(300).to_csv(index=False)
                all_columns.extend([f"{sheet_name}.{c}" for c in sheet_df.columns])
                sheet_info[sheet_name] = {'rows': len(sheet_df), 'columns': len(sheet_df.columns)}
                
                if len(sheet_df) > max_rows:
                    max_rows = len(sheet_df)
                    main_df = sheet_df

        columns_str = ", ".join([str(c) for c in all_columns[:50]])
        if len(all_columns) > 50:
            columns_str += f" ... and {len(all_columns) - 50} more"
            
        return main_df, combined_context, columns_str, sheet_info

    except Exception as e:
        st.error(f"File Processing Error: {str(e)}")
        return None, "", "", {}

def generate_smart_suggestions(df_input, plan_rules=""):
    """Enhanced smart query suggestions based on data analysis"""
    suggestions = []
    
    if df_input is None or len(df_input) == 0:
        return [
            "💰 Calculate my total compensation for Q1",
            "📊 Show me my attainment vs quota",
            "🎯 What do I need to hit my target?",
            "📈 Analyze my monthly sales trend"
        ]
    
    try:
        df = df_input.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        cust_col = next((c for c in df.columns if 'customer' in c or 'name' in c), None)
        sales_col = next((c for c in df.columns if 'sales' in c or 'amount' in c or 'total' in c), None)
        
        if cust_col and sales_col:
            top_cust = df.groupby(cust_col)[sales_col].sum().idxmax()
            suggestions.append(f"👤 Why is {top_cust} my top account?")
            suggestions.append("⚠️ Which customers are at churn risk?")
            
        prod_col = next((c for c in df.columns if 'product' in c or 'item' in c or 'category' in c), None)
        if prod_col and sales_col:
            top_prod = df.groupby(prod_col)[sales_col].sum().idxmax()
            suggestions.append(f"📦 Analyze my {top_prod} performance")
            suggestions.append("🔄 What's my optimal product mix?")
        
        date_col = next((c for c in df.columns if 'date' in c or 'month' in c), None)
        if date_col:
            suggestions.append("📅 Show my monthly trend analysis")
            suggestions.append("🎯 Am I on track for quarterly goals?")
            
        suggestions.append("🚀 Simulate: +10 units of top product")
        suggestions.append("💡 What if I doubled institutional sales?")
        
    except Exception:
        pass
    
    return suggestions[:8]

# ==========================================
# VISUALIZATION ENGINE (ENHANCED)
# ==========================================
def create_plotly_chart(chart_config):
    """Create enhanced interactive Plotly charts with better error handling"""
    chart_type = chart_config.get('type', 'bar')
    title = chart_config.get('title', 'Analysis')
    data = chart_config.get('data', {})
    x_label = chart_config.get('x_label', 'Category')
    y_label = chart_config.get('y_label', 'Value')
    
    if not data:
        return None
    
    # Clean data - handle nested objects
    cleaned_data = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # If value is a dict, sum all values or take first value
            cleaned_data[key] = sum(value.values()) if value else 0
        else:
            cleaned_data[key] = value
    
    # Convert to dataframe
    try:
        df = pd.DataFrame(list(cleaned_data.items()), columns=[x_label, y_label])
    except Exception as e:
        st.error(f"Chart data error: {str(e)}")
        return None
    
    if chart_type == 'line':
        fig = px.line(df, x=x_label, y=y_label, title=title, markers=True)
        fig.update_traces(line_color='#0066cc', line_width=3, marker_size=8)
        
    elif chart_type == 'bar':
        fig = px.bar(df, x=x_label, y=y_label, title=title)
        fig.update_traces(marker_color='#00a99d')
        
    elif chart_type == 'combo':
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df[x_label], y=df[y_label], name='Actual', marker_color='#00a99d'))
        fig.add_trace(go.Scatter(x=df[x_label], y=df[y_label], mode='lines+markers', name='Trend', line=dict(color='#ff6c0e', width=2)))
        fig.update_layout(title=title)
        
    elif chart_type == 'pie':
        fig = px.pie(df, values=y_label, names=x_label, title=title)
        
    else:  # default to bar
        fig = px.bar(df, x=x_label, y=y_label, title=title)
        fig.update_traces(marker_color='#00a99d')
    
    fig.update_layout(
        template='plotly_white',
        height=400,
        font=dict(family="Arial, sans-serif", size=12),
        title_font_size=16,
        title_font_color='#333333',
        xaxis_title_font_size=14,
        yaxis_title_font_size=14
    )
    
    return fig

# ==========================================
# SESSION STATE MANAGEMENT
# ==========================================
def initialize_session_state():
    """Initialize all session state variables"""
    if 'history' not in st.session_state:
        st.session_state.history = []
    if 'favorites' not in st.session_state:
        st.session_state.favorites = []
    if 'current_query' not in st.session_state:
        st.session_state.current_query = ""
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'current_mode' not in st.session_state:
        st.session_state.current_mode = "🎮 Demo Sandbox"
    if 'execute_query' not in st.session_state:
        st.session_state.execute_query = False

def reset_history():
    st.session_state.history = []
    st.session_state.current_query = ""

def add_to_favorites(query, result):
    st.session_state.favorites.append({
        'query': query,
        'result': result,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M")
    })

# ==========================================
# UI COMPONENTS
# ==========================================
def render_metric_card(label, value, delta=None, status="success"):
    """Render enhanced metric card"""
    status_class = f"status-{status}"
    delta_html = f'<div class="status-badge {status_class}">{delta}</div>' if delta else ""
    
    st.markdown(f"""
    <div class="metric-card">
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 0.3rem;">{label}</div>
        <div style="font-size: 1.8rem; font-weight: bold; color: #333;">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

def render_rule_citation(rule_text):
    """Render rule citation box"""
    st.markdown(f"""
    <div class="rule-box">
        📋 {rule_text}
    </div>
    """, unsafe_allow_html=True)

def render_response_header(query_text, timestamp=None):
    """Render response header"""
    time_str = timestamp if timestamp else datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
    <div class="response-header">
        <div style="font-size: 0.85rem; opacity: 0.9;">🕐 {time_str}</div>
        <div style="font-size: 1.1rem; margin-top: 0.3rem;">Q: {query_text}</div>
    </div>
    """, unsafe_allow_html=True)

def export_analysis_to_json(query, result):
    """Export analysis as JSON"""
    export_data = {
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'analysis': result
    }
    return json.dumps(export_data, indent=2)

# ==========================================
# MAIN APPLICATION
# ==========================================
initialize_session_state()

# Sidebar Configuration
with st.sidebar:
    # Logo section - using ZS colors as placeholder
    st.markdown("""
    <div style='background: linear-gradient(90deg, #00a99d 0%, #0066cc 100%); 
                padding: 20px; 
                border-radius: 10px; 
                text-align: center; 
                color: white; 
                font-size: 20px; 
                font-weight: bold;
                margin-bottom: 20px;'>
        Smart Incentive<br/>Simulator
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### ⚙️ Configuration")
    
    mode = st.radio(
        "Select Mode:", 
        ["🎮 Demo Sandbox", "🔬 Custom Lab"], 
        key="mode_selector"
    )
    
    # FIX: Chinese Wall - Clear history when mode changes
    if mode != st.session_state.current_mode:
        reset_history()
        st.session_state.current_mode = mode
    
    st.markdown("---")
    st.markdown("### 📊 Quick Actions")
    
    if st.button("🗑️ Clear History", use_container_width=True):
        reset_history()
        st.rerun()
    
    if st.button("📥 Export Current Session", use_container_width=True):
        if st.session_state.history:
            export_data = json.dumps(st.session_state.history, indent=2)
            st.download_button(
                "Download JSON",
                export_data,
                "analysis_export.json",
                "application/json"
            )
    
    if st.session_state.favorites:
        st.markdown("---")
        st.markdown("### ⭐ Saved Queries")
        for idx, fav in enumerate(st.session_state.favorites[-5:]):
            if st.button(f"📌 {fav['query'][:30]}...", key=f"fav_{idx}"):
                st.session_state.current_query = fav['query']
                st.session_state.execute_query = True
                st.rerun()

# Main Content Area
st.title("🤖 Smart Incentive Simulator")
st.markdown("##### AI-powered compensation simulator with explainable calculations")

# Data Loading Section
current_sales_data_str = ""
current_sales_df = None
current_plan_rules = ""
current_columns = ""
sheet_info = {}

if mode == "🎮 Demo Sandbox":
    current_sales_data_str = get_demo_data_string()
    current_sales_df = pd.read_csv(io.StringIO("""Date,Customer Name,Product Category,Sales Amount,Units
2024-01-15,KENTUCKY CLINIC,Consumables,2800,4
2024-01-15,DUKE UNIVERSITY HOSPITAL,Capital,4500,5
2024-02-15,PADUCAH OUTPATIENT,Consumables,700,1
2024-03-15,NORTHWESTERN MEMORIAL,Consumables,3500,5
2024-04-15,KENTUCKY CLINIC,Consumables,1200,2"""))
    current_plan_rules = get_default_plan()
    current_columns = "Date, Customer Name, Product Category, Sales Amount, Units"
    st.session_state.data_loaded = True
    
    st.success("✅ **Demo Mode Active** | Pre-loaded Medical Device Sales Data")

else:  # Custom Lab
    st.info("📤 **Custom Lab Mode** | Upload your sales data and plan rules")
    
    col1, col2 = st.columns(2)
    
    with col1:
        sales_file = st.file_uploader(
            "📊 Upload Sales Data", 
            type=['xlsx', 'csv'],
            help="Upload Excel file (multiple sheets supported) or CSV"
        )
    
    with col2:
        plan_file = st.file_uploader(
            "📄 Upload Plan Rules", 
            type=['pdf'],
            help="Upload compensation plan document (PDF)"
        )
    
    if sales_file:
        file_bytes = sales_file.read()
        current_sales_df, current_sales_data_str, current_columns, sheet_info = process_sales_file(
            file_bytes, 
            sales_file.name
        )
        
        if current_sales_df is not None:
            st.session_state.data_loaded = True
            
            with st.expander("📋 Data Summary", expanded=False):
                st.write(f"**File:** {sales_file.name}")
                st.write(f"**Sheets/Tables:** {len(sheet_info)}")
                for sheet_name, info in sheet_info.items():
                    st.write(f"  - {sheet_name}: {info['rows']} rows × {info['columns']} columns")
                st.write(f"**Total Columns:** {len(current_columns.split(','))}")
    
    if plan_file:
        current_plan_rules = extract_text_from_pdf(plan_file)
        st.success(f"✅ Plan rules extracted ({len(current_plan_rules)} characters)")
    else:
        current_plan_rules = "No specific plan document uploaded. AI will infer rules from data structure and column names."

st.markdown("---")

# Main Interface
if st.session_state.data_loaded:
    
    # Smart Suggestions Section
    st.markdown("### 💡 Suggested Queries")
    suggestions = generate_smart_suggestions(current_sales_df, current_plan_rules)
    
    cols = st.columns(4)
    for idx, suggestion in enumerate(suggestions[:8]):
        col_idx = idx % 4
        # FIX: Auto-execute on suggestion click
        if cols[col_idx].button(suggestion, key=f"sugg_{idx}", use_container_width=True):
            st.session_state.current_query = suggestion.split(': ', 1)[-1] if ': ' in suggestion else suggestion
            st.session_state.execute_query = True
            st.rerun()
    
    st.markdown("---")
    
    # Query Input Section
    st.markdown("### 💬 Ask a Question")
    
    query_col1, query_col2 = st.columns([4, 1])
    
    with query_col1:
        # FIX: Support Enter key submission
        user_input = st.text_input(
            "Type your question or select from suggestions above",
            value=st.session_state.current_query,
            placeholder="e.g., Am I on track to hit my Q2 target?",
            label_visibility="collapsed",
            key="query_input",
            on_change=lambda: setattr(st.session_state, 'execute_query', True) if st.session_state.query_input else None
        )
    
    with query_col2:
        submit_clicked = st.button("🔍 Analyze", type="primary", use_container_width=True)
    
    # Process query (either from button click or Enter key)
    if (submit_clicked or st.session_state.execute_query) and (user_input or st.session_state.current_query):
        query_to_process = user_input or st.session_state.current_query
        
        with st.spinner("🤖 Analyzing your question..."):
            result = ask_claude_json(
                current_sales_data_str, 
                current_plan_rules, 
                query_to_process, 
                current_columns
            )
            
            st.session_state.history.insert(0, {
                "query": query_to_process,
                "result": result,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            st.session_state.current_query = ""
            st.session_state.execute_query = False
            st.rerun()
    
    # Display Results
    if st.session_state.history:
        st.markdown("---")
        st.markdown("## 📊 Analysis Results")
        
        for idx, item in enumerate(st.session_state.history):
            query = item['query']
            result = item['result']
            timestamp = item.get('timestamp', '')
            
            with st.container():
                render_response_header(query, timestamp)
                
                # Executive Summary
                summary = result.get('final_answer_summary', 'Processing...')
                confidence = result.get('confidence_level', 'medium')
                
                if confidence == 'low' or "Error" in summary:
                    st.error(f"**Answer:** {summary}")
                elif confidence == 'medium':
                    st.warning(f"**Answer:** {summary}")
                else:
                    st.success(f"**Answer:** {summary}")
                
                # Key Metrics Row
                stats = result.get('key_stats', [])
                if stats:
                    metric_cols = st.columns(min(len(stats), 4))
                    for idx_stat, stat in enumerate(stats[:4]):
                        with metric_cols[idx_stat]:
                            render_metric_card(
                                stat.get('label', 'Metric'),
                                stat.get('value', '0'),
                                stat.get('delta'),
                                stat.get('status', 'success')
                            )
                
                # Tabbed Detail View
                tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualization", "🧮 Calculation Details", "📋 Rules & Sources", "💡 Insights"])
                
                with tab1:
                    chart_conf = result.get('chart_config', {})
                    if chart_conf and chart_conf.get('data'):
                        fig = create_plotly_chart(chart_conf)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                            
                            with st.expander("📋 View Data Table"):
                                chart_data = chart_conf['data']
                                # FIX: Handle JSON values in table
                                clean_data = {}
                                for k, v in chart_data.items():
                                    if isinstance(v, dict):
                                        clean_data[k] = sum(v.values()) if v else 0
                                    else:
                                        clean_data[k] = v
                                
                                df_display = pd.DataFrame(
                                    list(clean_data.items()),
                                    columns=['Category', 'Value']
                                )
                                st.dataframe(df_display, use_container_width=True)
                    else:
                        st.info("No visualization available for this query")
                
                with tab2:
                    logic = result.get('detailed_logic_markdown', 'No calculation details provided.')
                    st.markdown(logic)
                
                with tab3:
                    rules = result.get('rule_citations', [])
                    if rules:
                        st.markdown("#### 📜 Plan Rules Applied")
                        for rule in rules:
                            render_rule_citation(rule)
                    
                    sources = result.get('data_sources', [])
                    if sources:
                        st.markdown("#### 📂 Data Sources Used")
                        for source in sources:
                            st.markdown(f"- {source}")
                
                with tab4:
                    recommendations = result.get('recommendations', [])
                    if recommendations:
                        st.markdown("#### ✅ Recommendations")
                        for rec in recommendations:
                            st.success(rec)
                    
                    risks = result.get('risk_factors', [])
                    if risks:
                        st.markdown("#### ⚠️ Risk Factors")
                        for risk in risks:
                            st.warning(risk)
                
                # Action Buttons Row
                action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                
                with action_col1:
                    if st.button("⭐ Save to Favorites", key=f"save_{idx}"):
                        add_to_favorites(query, result)
                        st.success("Saved!")
                
                with action_col2:
                    export_json = export_analysis_to_json(query, result)
                    st.download_button(
                        "📥 Export JSON",
                        export_json,
                        f"analysis_{idx}.json",
                        "application/json",
                        key=f"export_{idx}"
                    )
                
                # FIX: Follow-up query box next to response
                with action_col3:
                    follow_up_key = f"followup_input_{idx}"
                    follow_up_text = st.text_input(
                        "Follow-up question",
                        placeholder="Ask a follow-up...",
                        key=follow_up_key,
                        label_visibility="collapsed"
                    )
                
                with action_col4:
                    if st.button("🔄 Submit Follow-up", key=f"followup_btn_{idx}"):
                        if follow_up_text:
                            st.session_state.current_query = f"Based on the previous analysis about '{query}', {follow_up_text}"
                            st.session_state.execute_query = True
                            st.rerun()
                
                st.markdown("---")
    
    # Data Inspector
    with st.expander("🔍 Data Inspector", expanded=False):
        if current_sales_df is not None and len(current_sales_df) > 0:
            st.markdown("### 📊 Sample Data Preview")
            st.dataframe(current_sales_df.head(20), use_container_width=True)
            
            st.markdown("### 📈 Quick Stats")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Rows", len(current_sales_df))
            with col2:
                st.metric("Total Columns", len(current_sales_df.columns))
            with col3:
                numeric_cols = current_sales_df.select_dtypes(include=['number']).columns
                st.metric("Numeric Columns", len(numeric_cols))
        
        st.markdown("### 📄 Raw Context")
        st.text_area(
            "Combined Sales Payload",
            current_sales_data_str[:3000],
            height=200
        )

else:
    # Empty State
    st.info("👋 **Welcome!** Please upload your sales data to get started, or switch to Demo Sandbox mode to explore with sample data.")
    
    st.markdown("""
    ### 🚀 Quick Start Guide
    
    1. **Demo Mode**: Try it instantly with pre-loaded medical device sales data
    2. **Custom Lab**: Upload your own Excel/CSV sales data + PDF plan rules
    3. **Ask Questions**: Use natural language to explore your compensation
    4. **Get Insights**: Receive detailed calculations with visual explanations
    
    #### Example Questions:
    - "Am I on track to hit my quarterly target?"
    - "Which customers are my top performers?"
    - "Simulate: What if I sell 10 more units of Product X?"
    - "Why was my March payout lower than expected?"
    """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.85rem;'>
    <p>Smart Incentive Simulator v2.0 | Powered by AWS Bedrock & Claude 3.5 Sonnet</p>
    <p>🔒 Your data is processed securely and never stored permanently</p>
</div>
""", unsafe_allow_html=True)