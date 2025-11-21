import streamlit as st
import pandas as pd
import base64
import io
from datetime import datetime
import streamlit.components.v1 as components

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(
    page_title="Luckin Analytics Hub",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. STYLING & CSS (Enterprise Theme) ---
st.markdown("""
    <style>
        /* General Font & Layout */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', 'Microsoft YaHei', sans-serif;
            background-color: #F8F9FA; 
        }

        /* Hide Streamlit Default Elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stApp { margin-top: -60px; }
        
        /* Custom Header Styling */
        .luckin-header-container {
            background-color: #232773; /* Luckin Blue */
            padding: 1.5rem 2rem;
            border-bottom: 4px solid #003087;
            color: white;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .logo-img {
            height: 48px;
            width: auto;
            background: white;
            padding: 4px;
            border-radius: 6px;
            margin-right: 16px;
        }

        .header-title {
            font-size: 22px;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin: 0;
        }
        
        .header-subtitle {
            font-size: 13px;
            opacity: 0.8;
            margin-top: 2px;
            font-weight: 400;
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E5E7EB;
        }
        
        /* Empty State / Instructions Styling */
        .instruction-card {
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            color: #475569;
        }
        .instruction-icon {
            font-size: 48px;
            color: #CBD5E1;
            margin-bottom: 15px;
        }

    </style>
""", unsafe_allow_html=True)

# --- 3. HELPER FUNCTIONS ---

def get_image_base64(path):
    """Reads a local image file and converts it to base64 string."""
    try:
        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except FileNotFoundError:
        return None # Graceful fallback if logo is missing

def clean_currency(x):
    """Cleans currency strings to floats."""
    if isinstance(x, (int, float)): return x
    if isinstance(x, str):
        # Remove '$', ',', and empty spaces
        clean_str = x.replace('$', '').replace(',', '').replace(' ', '')
        # Check if it's enclosed in parentheses (negative accounting format)
        if '(' in clean_str and ')' in clean_str:
            clean_str = clean_str.replace('(', '').replace(')', '')
            return -float(clean_str)
        return float(clean_str)
    return 0.0

# --- 4. DATA PARSERS ---

@st.cache_data
def parse_uber(file):
    try:
        # Uber header often on row 2 (index 1)
        df = pd.read_csv(file, header=1)
        
        # Map Columns
        # Date: 订单日期
        # Revenue: 销售额（含税）
        # Status: 订单状态
        
        if '订单状态' in df.columns:
            df = df[df['订单状态'] == '已完成']
        elif 'Order Status' in df.columns:
            df = df[df['Order Status'] == 'Completed']
            
        date_col = '订单日期' if '订单日期' in df.columns else 'Order Date'
        rev_col = '销售额（含税）' if '销售额（含税）' in df.columns else 'Sales (tax incl)'
        store_col = '餐厅名称' if '餐厅名称' in df.columns else 'Restaurant Name'
        
        df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
        df['Revenue'] = df[rev_col].apply(clean_currency)
        df['Store'] = df[store_col]
        df['Platform'] = 'Uber Eats'
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except:
        return pd.DataFrame()

@st.cache_data
def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # Map Columns
        # Date: 接单当地时间 (Local Created Time)
        # Revenue: 小计 (Subtotal)
        # Status: 最终订单状态
        
        if '最终订单状态' in df.columns:
            df = df[df['最终订单状态'].astype(str).str.contains('Delivered|Picked Up|已送达', case=False, na=False)]
        
        df['Date'] = pd.to_datetime(df['接单当地时间'], errors='coerce')
        df['Revenue'] = df['小计'].apply(clean_currency)
        df['Store'] = df['店铺名称']
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except:
        return pd.DataFrame()

@st.cache_data
def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        # Drop metadata rows
        df = df.dropna(subset=['transaction_date'])
        
        df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        df['Store'] = df['store_name']
        df['Platform'] = 'Grubhub'
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except:
        return pd.DataFrame()

# --- 5. UI HEADER ---

logo_base64 = get_image_base64("luckin_logo.png")
logo_html = f'<img src="{logo_base64}" class="logo-img">' if logo_base64 else ""

st.markdown(f"""
    <div class="luckin-header-container">
        <div style="display:flex; align-items:center;">
            {logo_html}
            <div>
                <div class="header-title">Luckin Coffee (US)</div>
                <div class="header-subtitle">Operations & Financial Reconciliation System | 财务分析与对账系统</div>
            </div>
        </div>
        <div style="text-align:right; font-size:12px; opacity:0.9; font-family:monospace;">
            {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 6. SIDEBAR & LOGIC ---

st.sidebar.header("Data Import (数据导入)")
st.sidebar.markdown("Upload monthly transaction files:")

uber_file = st.sidebar.file_uploader("Uber Eats / Postmates", type=['csv'])
dd_file = st.sidebar.file_uploader("DoorDash", type=['csv'])
gh_file = st.sidebar.file_uploader("Grubhub", type=['csv'])

data_frames = []

if uber_file: data_frames.append(parse_uber(uber_file))
if dd_file: data_frames.append(parse_doordash(dd_file))
if gh_file: data_frames.append(parse_grubhub(gh_file))

# --- 7. MAIN CONTENT ---

if not data_frames:
    # Empty State - Waiting for input
    st.markdown("""
    <div class="instruction-card">
        <div class="instruction-icon">📥</div>
        <h3>Awaiting Data Source</h3>
        <p>Please upload CSV files from Uber Eats, DoorDash, or Grubhub in the left sidebar to generate the analysis report.</p>
        <p style="color:#999; font-size:14px;">请在左侧上传平台账单文件以生成报表</p>
    </div>
    """, unsafe_allow_html=True)

else:
    # Process Data
    try:
        master_df = pd.concat(data_frames, ignore_index=True)
        
        if master_df.empty:
             st.error("Error: Valid data could not be extracted. Please check if the CSV files have the correct headers.")
        else:
            master_df.sort_values('Date', inplace=True)
            
            # Metrics Calculation
            total_orders = len(master_df)
            total_gmv = master_df['Revenue'].sum()
            avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
            
            # Chart Data Preparation
            daily_counts = master_df.groupby([master_df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
            dates_js = [str(d) for d in daily_counts.index]
            
            def get_plat_data(p): 
                return daily_counts[p].tolist() if p in daily_counts.columns else [0]*len(dates_js)
            
            store_perf = master_df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
            store_names = store_perf.index.tolist()
            store_values = [round(x, 2) for x in store_perf.values.tolist()]
            
            pie_counts = master_df['Platform'].value_counts()
            pie_js_data = [{"value": int(v), "name": k} for k, v in pie_counts.items()]

            # Logo for HTML Report (Ensure it's embedded even if downloaded)
            # If logo loaded successfully above, use it.
            
            # --- GENERATE & EMBED HTML REPORT ---
            html_code = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
                <style>
                    :root {{ 
                        --luckin-blue: #232773; 
                        --luckin-gray: #F9FAFB; 
                        --text-main: #333333; 
                        --risk-red: #D93025; 
                        --success-green: #34A853; 
                    }}
                    body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background-color: var(--luckin-gray); margin: 0; padding: 0; }}
                    
                    .report-container {{ max-width: 100%; padding: 0 10px; }}
                    
                    /* KPI Grid */
                    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
                    .kpi-card {{ background: white; padding: 20px; border-radius: 8px; border-left: 4px solid var(--luckin-blue); box-shadow: 0 2px 5px rgba(0,0,0,0.03); }}
                    .kpi-label {{ color: #666; font-size: 13px; margin-bottom: 5px; }}
                    .kpi-value {{ font-size: 26px; font-weight: bold; color: var(--luckin-blue); }}
                    .kpi-sub {{ font-size: 12px; color: #999; }}
                    
                    /* Chart Sections */
                    .chart-section {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.03); }}
                    .section-header {{ font-size: 16px; font-weight: bold; color: var(--luckin-blue); border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px; }}
                    
                    .chart-div {{ width: 100%; height: 350px; }}
                    
                    /* Table Styles */
                    .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
                    .data-table th {{ text-align: left; padding: 10px; background: #f8f9fa; color: var(--luckin-blue); font-weight: 600; }}
                    .data-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
                </style>
            </head>
            <body>
                <div class="report-container">
                    
                    <!-- KPI Cards -->
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-label">Total Orders (总订单量)</div>
                            <div class="kpi-value">{total_orders}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">Total GMV (总营收)</div>
                            <div class="kpi-value">${total_gmv:,.2f}</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">Avg Ticket (客单价)</div>
                            <div class="kpi-value">${avg_ticket:.2f}</div>
                        </div>
                        <div class="kpi-card" style="border-left-color: #D93025;">
                            <div class="kpi-label">Peak Day (销售峰值日)</div>
                            <div class="kpi-value" style="color: #D93025; font-size: 22px;">{master_df.groupby(master_df['Date'].dt.date)['Revenue'].sum().idxmax()}</div>
                        </div>
                    </div>

                    <!-- Trend Chart -->
                    <div class="chart-section">
                        <div class="section-header">📈 Daily Order Trend (日订单趋势)</div>
                        <div id="trendChart" class="chart-div"></div>
                    </div>

                    <!-- Split Charts -->
                    <div style="display: flex; gap: 15px;">
                        <div class="chart-section" style="flex: 1;">
                            <div class="section-header">🍰 Market Share (渠道占比)</div>
                            <div id="pieChart" class="chart-div"></div>
                        </div>
                        <div class="chart-section" style="flex: 1;">
                            <div class="section-header">🏢 Store Performance (门店表现)</div>
                            <div id="barChart" class="chart-div"></div>
                        </div>
                    </div>
                </div>

                <script>
                    document.addEventListener("DOMContentLoaded", function() {{
                        // Trend Chart
                        var trendChart = echarts.init(document.getElementById('trendChart'));
                        trendChart.setOption({{
                            tooltip: {{ trigger: 'axis' }},
                            legend: {{ bottom: 0 }},
                            grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                            xAxis: {{ type: 'category', boundaryGap: false, data: {dates_js} }},
                            yAxis: {{ type: 'value' }},
                            series: [
                                {{ name: 'Uber Eats', type: 'line', smooth: true, showSymbol: false, data: {get_plat_data('Uber Eats')}, itemStyle: {{ color: '#06C167' }}, areaStyle: {{ opacity: 0.1 }} }},
                                {{ name: 'DoorDash', type: 'line', smooth: true, showSymbol: false, data: {get_plat_data('DoorDash')}, itemStyle: {{ color: '#FF3008' }}, areaStyle: {{ opacity: 0.1 }} }},
                                {{ name: 'Grubhub', type: 'line', smooth: true, showSymbol: false, data: {get_plat_data('Grubhub')}, itemStyle: {{ color: '#FF8000' }}, areaStyle: {{ opacity: 0.1 }} }}
                            ]
                        }});

                        // Pie Chart
                        var pieChart = echarts.init(document.getElementById('pieChart'));
                        pieChart.setOption({{
                            tooltip: {{ trigger: 'item' }},
                            legend: {{ top: '5%', left: 'center' }},
                            series: [{{
                                name: 'Orders',
                                type: 'pie',
                                radius: ['40%', '70%'],
                                avoidLabelOverlap: false,
                                itemStyle: {{ borderRadius: 5, borderColor: '#fff', borderWidth: 2 }},
                                label: {{ show: false, position: 'center' }},
                                emphasis: {{ label: {{ show: true, fontSize: 20, fontWeight: 'bold' }} }},
                                data: {pie_js_data}
                            }}]
                        }});

                        // Bar Chart
                        var barChart = echarts.init(document.getElementById('barChart'));
                        barChart.setOption({{
                            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                            grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                            xAxis: {{ type: 'value', name: 'USD' }},
                            yAxis: {{ type: 'category', data: {store_names} }},
                            series: [{{
                                name: 'Revenue',
                                type: 'bar',
                                data: {store_values},
                                itemStyle: {{ color: '#232773' }},
                                label: {{ show: true, position: 'right', formatter: '{{c}}' }}
                            }}]
                        }});

                        window.onresize = function() {{
                            trendChart.resize();
                            pieChart.resize();
                            barChart.resize();
                        }};
                    }});
                </script>
            </body>
            </html>
            """
            
            # Render HTML Preview
            components.html(html_code, height=1000, scrolling=True)
            
            # Sidebar Download
            st.sidebar.markdown("---")
            st.sidebar.download_button(
                label="📥 Download Report (下载报告)",
                data=html_code,
                file_name=f"Luckin_US_Analytics_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html"
            )

    except Exception as e:
        st.error(f"An error occurred processing the files: {e}")
        st.warning("Please ensure you are uploading the correct CSV files for Uber, DoorDash, and Grubhub.")
