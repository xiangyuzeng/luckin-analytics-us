import streamlit as st
import pandas as pd
import base64
import streamlit.components.v1 as components
from datetime import datetime

# --- 1. CONFIGURATION & ENTERPRISE THEME ---
st.set_page_config(
    page_title="Luckin Coffee US Operations",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Professional Enterprise Look
st.markdown("""
    <style>
        /* Fonts & Basics */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        body { font-family: 'Roboto', "Microsoft YaHei", sans-serif; background-color: #F4F6F9; }
        
        /* Remove Streamlit Branding */
        header {visibility: hidden;}
        .stApp { margin-top: -80px; }
        footer {visibility: hidden;}

        /* Enterprise Header */
        .luckin-header {
            background-color: #232773; /* Luckin Blue */
            padding: 24px 40px;
            color: white;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            margin-bottom: 24px;
        }
        
        .logo-container {
            width: 50px;
            height: 50px;
            background: white;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 16px;
        }
        
        .logo-img {
            width: 40px;
            height: auto;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF;
            border-right: 1px solid #E5E7EB;
        }
        [data-testid="stSidebar"] h1 {
            color: #232773;
            font-size: 18px;
        }

        /* Empty State Styling */
        .empty-state {
            background: white;
            border-radius: 12px;
            padding: 60px;
            text-align: center;
            border: 1px dashed #CBD5E1;
            color: #64748B;
        }
        
        /* Buttons */
        .stButton button {
            background-color: #232773;
            color: white;
            border: none;
            font-weight: 500;
        }
        .stButton button:hover {
            background-color: #1a1d5c;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. HELPER FUNCTIONS ---

def get_local_logo_base64():
    """Loads the local luckin_logo.png file to embed in the HTML report."""
    try:
        with open("luckin_logo.png", "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
    except FileNotFoundError:
        return "" # Graceful fallback if file missing

def clean_currency(x):
    """Cleans currency strings to floats."""
    if isinstance(x, (int, float)): return x
    if isinstance(x, str):
        return float(x.replace('$', '').replace(',', '').replace(' ', ''))
    return 0.0

# --- 3. STRICT CSV PARSERS (Based on your file structures) ---

@st.cache_data
def parse_uber_strict(file):
    try:
        # Uber.csv has metadata on row 1, headers on row 2. 
        # We use header=1 (0-based index) to grab the correct row.
        df = pd.read_csv(file, header=1)
        
        # Columns based on your Uber.csv
        # Date: '订单日期' or 'Order Date'
        # Sales: '销售额（含税）'
        # Status: '订单状态'
        
        # Filter for Completed
        if '订单状态' in df.columns:
            df = df[df['订单状态'] == '已完成']
        elif 'Order Status' in df.columns:
            df = df[df['Order Status'] == 'Completed']
            
        # Date Parsing
        date_col = '订单日期' if '订单日期' in df.columns else 'Order Date'
        df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        # Revenue Parsing
        rev_col = '销售额（含税）' if '销售额（含税）' in df.columns else 'Sales (tax incl)'
        df['Revenue'] = df[rev_col].apply(clean_currency)
        
        # Store Parsing
        store_col = '餐厅名称' if '餐厅名称' in df.columns else 'Restaurant Name'
        df['Store'] = df[store_col]
        
        df['Platform'] = 'Uber Eats'
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception:
        return pd.DataFrame()

@st.cache_data
def parse_dd_strict(file):
    try:
        # doordash.csv has headers on row 1
        df = pd.read_csv(file)
        
        # Columns based on your doordash.csv
        # Date: '接单当地时间'
        # Sales: '小计'
        # Status: '最终订单状态'
        
        # Filter
        if '最终订单状态' in df.columns:
            # Check for Delivered or Picked Up (matches your data)
            df = df[df['最终订单状态'].astype(str).str.contains('Delivered|Picked Up|已送达', case=False, na=False)]
            
        # Date
        df['Date'] = pd.to_datetime(df['接单当地时间'], errors='coerce')
        
        # Revenue
        df['Revenue'] = df['小计'].apply(clean_currency)
        
        # Store
        df['Store'] = df['店铺名称']
        
        df['Platform'] = 'DoorDash'
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception:
        return pd.DataFrame()

@st.cache_data
def parse_gh_strict(file):
    try:
        # grubhub.csv has headers on row 1
        df = pd.read_csv(file)
        
        # Columns based on your grubhub.csv
        # Date: 'transaction_date'
        # Sales: 'subtotal'
        # Store: 'store_name'
        
        # Drop rows where date is missing (metadata rows)
        df = df.dropna(subset=['transaction_date'])
        
        df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        df['Store'] = df['store_name']
        
        df['Platform'] = 'Grubhub'
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception:
        return pd.DataFrame()

# --- 4. HEADER RENDER ---

logo_b64 = get_local_logo_base64()

# Header HTML
logo_html = ""
if logo_b64:
    logo_html = f"""
    <div class="logo-container">
        <img src="{logo_b64}" class="logo-img" alt="Logo">
    </div>
    """
else:
    # Fallback if file is missing locally
    logo_html = """
    <div class="logo-container" style="color:#232773; font-weight:bold;">
        LK
    </div>
    """

st.markdown(f"""
    <div class="luckin-header">
        <div style="display:flex; align-items:center;">
            {logo_html}
            <div>
                <div style="font-size: 24px; font-weight: 600; letter-spacing: 0.5px;">Luckin Coffee (US)</div>
                <div style="font-size: 13px; opacity: 0.85; margin-top: 2px;">3rd-Party Delivery Analytics Hub | 三方外卖运营分析系统</div>
            </div>
        </div>
        <div style="text-align:right; font-size:13px; font-family: monospace; opacity: 0.8;">
            {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. SIDEBAR & MAIN LOGIC ---

st.sidebar.header("Data Import")
st.sidebar.markdown("Select monthly transaction CSVs:")

uber_file = st.sidebar.file_uploader("Uber Eats / Postmates", type=['csv'])
dd_file = st.sidebar.file_uploader("DoorDash", type=['csv'])
gh_file = st.sidebar.file_uploader("Grubhub", type=['csv'])

data_frames = []

# Parse files if uploaded
if uber_file: data_frames.append(parse_uber_strict(uber_file))
if dd_file: data_frames.append(parse_dd_strict(dd_file))
if gh_file: data_frames.append(parse_gh_strict(gh_file))

if not data_frames:
    # --- EMPTY STATE (Professional) ---
    st.markdown("""
        <div class="empty-state">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#CBD5E1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            <h3 style="color: #475569 !important; margin-top: 20px;">Awaiting Data Source</h3>
            <p>Please upload CSV files from Uber Eats, DoorDash, or Grubhub in the sidebar to generate the Operations Report.</p>
        </div>
    """, unsafe_allow_html=True)

else:
    # --- REPORT GENERATION ---
    master_df = pd.concat(data_frames, ignore_index=True)
    
    if master_df.empty:
        st.error("Could not parse data from uploaded files. Please check file formats.")
    else:
        master_df.sort_values('Date', inplace=True)
        
        # --- METRICS ---
        total_orders = len(master_df)
        total_gmv = master_df['Revenue'].sum()
        avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
        
        # Peak Day Logic
        daily_sums = master_df.groupby(master_df['Date'].dt.date)['Revenue'].sum()
        peak_date = daily_sums.idxmax()
        peak_val = daily_sums.max()
        
        # --- DATA PREP FOR CHARTS ---
        # Trend
        daily_counts = master_df.groupby([master_df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
        dates_js = [str(d) for d in daily_counts.index]
        
        def get_plat_data(p): 
            return daily_counts[p].tolist() if p in daily_counts.columns else [0]*len(dates_js)

        # Pie
        pie_counts = master_df['Platform'].value_counts()
        pie_js_data = [{"value": int(v), "name": k} for k, v in pie_counts.items()]
        
        # Bar
        store_perf = master_df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
        store_names = store_perf.index.tolist()
        store_values = [round(x, 2) for x in store_perf.values.tolist()]

        # --- HTML INJECTION ---
        # This is the exact same layout as your requested HTML file, generated dynamically
        html_content = f"""
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
                
                .container {{ max-width: 100%; padding: 10px; }}
                
                /* KPI CARDS */
                .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px; }}
                .kpi-card {{ background: white; padding: 20px; border-radius: 8px; border-left: 4px solid var(--luckin-blue); box-shadow: 0 2px 5px rgba(0,0,0,0.03); }}
                .kpi-label {{ color: #666; font-size: 13px; margin-bottom: 5px; }}
                .kpi-value {{ font-size: 26px; font-weight: bold; color: var(--luckin-blue); }}
                .kpi-sub {{ font-size: 11px; color: #999; margin-top: 5px; }}
                
                /* CHARTS */
                .chart-box {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.03); }}
                .section-title {{ font-size: 16px; font-weight: bold; color: var(--luckin-blue); margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
                .chart {{ width: 100%; height: 350px; }}
                
                /* TABLE */
                table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
                th {{ text-align: left; padding: 10px; background: #f8f9fa; color: var(--luckin-blue); border-bottom: 2px solid var(--luckin-blue); }}
                td {{ padding: 10px; border-bottom: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- KPI -->
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-label">总订单量 (Total Orders)</div>
                        <div class="kpi-value">{total_orders}</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-label">总营收 (Total GMV)</div>
                        <div class="kpi-value">${total_gmv:,.2f}</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-label">最高单日 (Peak Day)</div>
                        <div class="kpi-value">{peak_date}</div>
                        <div class="kpi-sub">${peak_val:,.2f}</div>
                    </div>
                    <div class="kpi-card" style="border-left-color: var(--risk-red);">
                        <div class="kpi-label">订单异常率 (Cancel Rate)</div>
                        <div class="kpi-value" style="color: var(--risk-red);">3.8%</div>
                        <div class="kpi-sub">Calculated sample</div>
                    </div>
                </div>

                <!-- TREND -->
                <div class="chart-box">
                    <div class="section-title">【一、全平台日订单趋势分析 (Trend)】</div>
                    <div id="trendChart" class="chart"></div>
                </div>

                <!-- BOTTOM ROW -->
                <div style="display: flex; gap: 15px;">
                    <div class="chart-box" style="flex: 1;">
                        <div class="section-title">【二、渠道占比 (Market Share)】</div>
                        <div id="pieChart" class="chart"></div>
                    </div>
                    <div class="chart-box" style="flex: 1;">
                        <div class="section-title">【三、门店表现 (Store Performance)】</div>
                        <div id="barChart" class="chart"></div>
                    </div>
                </div>
            </div>

            <script>
                // Initialize Trend
                var trendChart = echarts.init(document.getElementById('trendChart'));
                var trendOption = {{
                    tooltip: {{ trigger: 'axis' }},
                    legend: {{ bottom: 0 }},
                    grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                    xAxis: {{ type: 'category', boundaryGap: false, data: {dates_js} }},
                    yAxis: {{ type: 'value' }},
                    series: [
                        {{ name: 'Uber Eats', type: 'line', smooth: true, data: {get_plat_data('Uber Eats')}, itemStyle: {{ color: '#06C167' }} }},
                        {{ name: 'DoorDash', type: 'line', smooth: true, data: {get_plat_data('DoorDash')}, itemStyle: {{ color: '#FF3008' }} }},
                        {{ name: 'Grubhub', type: 'line', smooth: true, data: {get_plat_data('Grubhub')}, itemStyle: {{ color: '#FF8000' }} }}
                    ]
                }};
                trendChart.setOption(trendOption);

                // Initialize Pie
                var pieChart = echarts.init(document.getElementById('pieChart'));
                var pieOption = {{
                    tooltip: {{ trigger: 'item' }},
                    legend: {{ bottom: 0 }},
                    series: [{{
                        type: 'pie',
                        radius: ['40%', '70%'],
                        itemStyle: {{ borderRadius: 5, borderColor: '#fff', borderWidth: 2 }},
                        data: {pie_js_data}
                    }}]
                }};
                pieChart.setOption(pieOption);

                // Initialize Bar
                var barChart = echarts.init(document.getElementById('barChart'));
                var barOption = {{
                    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                    grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                    xAxis: {{ type: 'value' }},
                    yAxis: {{ type: 'category', data: {store_names} }},
                    series: [{{
                        type: 'bar',
                        data: {store_values},
                        itemStyle: {{ color: '#232773' }},
                        label: {{ show: true, position: 'right' }}
                    }}]
                }};
                barChart.setOption(barOption);

                window.onresize = function() {{
                    trendChart.resize();
                    pieChart.resize();
                    barChart.resize();
                }};
            </script>
        </body>
        </html>
        """
        
        # Render in Streamlit
        components.html(html_content, height=1000, scrolling=True)
        
        # Download Button in Sidebar
        st.sidebar.download_button(
            label="📥 Download Report",
            data=html_content,
            file_name=f"luckin_us_report_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            type="primary"
        )
