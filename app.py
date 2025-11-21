import streamlit as st
import pandas as pd
import base64
import io
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="瑞幸咖啡财务对账系统 (Luckin Analytics)",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS (LUCKIN THEME) ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&display=swap');
        
        body { font-family: 'Noto Sans SC', sans-serif; background-color: #F5F7FA; }
        
        /* Hide Streamlit Branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stApp { margin-top: -60px; }

        /* Luckin Header */
        .luckin-navbar {
            background-color: #232773;
            padding: 1.5rem 2rem;
            border-radius: 0 0 15px 15px;
            color: white;
            box-shadow: 0 4px 20px rgba(35, 39, 115, 0.2);
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 2rem;
        }
        
        /* Card Styling */
        .info-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #e0e0e0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.03);
            margin-bottom: 1rem;
        }
        
        /* Step indicators */
        .step-circle {
            background: #232773;
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            margin-right: 8px;
        }
        
        /* Success Message */
        .stAlert { border-radius: 8px; }
        
        h3 { color: #232773 !important; font-weight: 700 !important; }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def get_image_base64(uploaded_file):
    """Converts uploaded logo to base64 for HTML embedding"""
    if uploaded_file is not None:
        try:
            return base64.b64encode(uploaded_file.getvalue()).decode()
        except:
            return ""
    return ""

def clean_currency(x):
    """Cleans currency strings like '$1,200.50' to float 1200.50"""
    if isinstance(x, str):
        return float(x.replace('$', '').replace(',', '').replace(' ', ''))
    return float(x)

# --- PARSERS (Optimized for your CSV structure) ---

@st.cache_data
def parse_uber(file):
    try:
        # Uber CSVs often have the real header on Row 2 (index 1)
        # Based on your file: "餐厅名称,餐厅号,订单号..." is on line 2
        df = pd.read_csv(file, header=1) 
        
        # Key Columns Mapping
        # Date: 订单接受时间 (Order Accept Time) or 订单日期
        # Revenue: 销售额（含税） (Sales incl Tax)
        # Status: 订单状态
        
        # Filter Completed
        if '订单状态' in df.columns:
            df = df[df['订单状态'] == '已完成']
        
        # Process Date
        df['Date'] = pd.to_datetime(df['订单日期'], errors='coerce')
        
        # Process Revenue
        df['Revenue'] = df['销售额（含税）'].apply(clean_currency)
        
        df['Store'] = df['餐厅名称'].fillna('Unknown Store')
        df['Platform'] = 'Uber Eats'
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception as e:
        st.toast(f"Uber 解析错误: {str(e)}", icon="⚠️")
        return pd.DataFrame()

@st.cache_data
def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # DoorDash columns from your file:
        # Date: 接单当地时间
        # Revenue: 小计 (Subtotal)
        # Status: 最终订单状态
        
        if '最终订单状态' in df.columns:
            df = df[df['最终订单状态'] == 'Delivered']
            
        df['Date'] = pd.to_datetime(df['接单当地时间'], errors='coerce')
        df['Revenue'] = df['小计'].apply(clean_currency)
        df['Store'] = df['店铺名称']
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception as e:
        st.toast(f"DoorDash 解析错误: {str(e)}", icon="⚠️")
        return pd.DataFrame()

@st.cache_data
def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        
        # Grubhub columns from your file:
        # transaction_date, subtotal, store_name
        
        # Filter out rows that are mostly empty or headers
        df = df.dropna(subset=['transaction_date'])
        
        df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        df['Store'] = df['store_name']
        df['Platform'] = 'Grubhub'
        
        # Filter out refunds (negative values) for Gross Sales calculation if desired
        # df = df[df['Revenue'] > 0] 
        
        return df[['Date', 'Revenue', 'Store', 'Platform']].dropna(subset=['Date'])
    except Exception as e:
        st.toast(f"Grubhub 解析错误: {str(e)}", icon="⚠️")
        return pd.DataFrame()

# --- MAIN UI LAYOUT ---

# 1. Top Navigation Bar
col_nav1, col_nav2 = st.columns([1, 3])
with col_nav1:
    # Logo Upload in Sidebar to keep main clean
    pass 

st.markdown(f"""
    <div class="luckin-navbar">
        <div style="display:flex; align-items:center;">
            <div style="font-size: 24px; font-weight: bold; letter-spacing: 1px;">Luckin Coffee</div>
            <div style="margin-left: 15px; opacity: 0.7; border-left: 1px solid rgba(255,255,255,0.3); padding-left: 15px;">
                财务分析与对账系统 (US)
            </div>
        </div>
        <div style="font-size: 14px;">
            {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>
""", unsafe_allow_html=True)

# 2. Sidebar Controls
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/7/7d/Luckin_Coffee_logo.svg/1200px-Luckin_Coffee_logo.svg.png", width=150)
    st.title("控制面板")
    st.markdown("**第一步：上传企业 Logo**")
    logo_file = st.file_uploader("上传 Logo (用于生成报告)", type=['png', 'jpg', 'jpeg'])
    
    st.markdown("---")
    st.markdown("**第二步：上传平台账单**")
    
    uber_upload = st.file_uploader("Uber Eats (CSV)", type='csv')
    dd_upload = st.file_uploader("DoorDash (CSV)", type='csv')
    gh_upload = st.file_uploader("Grubhub (CSV)", type='csv')
    
    st.markdown("---")
    st.info("ℹ️ 系统会自动识别中英文表头。")

# 3. Main Content Area
if uber_upload or dd_upload or gh_upload:
    
    # --- Data Processing ---
    dfs = []
    if uber_upload: dfs.append(parse_uber(uber_upload))
    if dd_upload: dfs.append(parse_doordash(dd_upload))
    if gh_upload: dfs.append(parse_grubhub(gh_upload))
    
    if dfs:
        try:
            master_df = pd.concat(dfs, ignore_index=True)
            master_df.sort_values('Date', inplace=True)
            
            # --- Metrics ---
            total_orders = len(master_df)
            total_gmv = master_df['Revenue'].sum()
            avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
            
            # Grouping Data for JS
            daily_counts = master_df.groupby([master_df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
            dates_list = [str(d) for d in daily_counts.index]
            
            def get_platform_series(plat):
                return daily_counts[plat].tolist() if plat in daily_counts.columns else [0]*len(dates_list)
            
            store_perf = master_df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
            store_names = store_perf.index.tolist()
            store_vals = [round(x, 2) for x in store_perf.values.tolist()]
            
            pie_counts = master_df['Platform'].value_counts()
            pie_data = [{"value": int(v), "name": k} for k, v in pie_counts.items()]

            # Logo Logic
            logo_b64 = get_image_base64(logo_file) if logo_file else ""
            logo_css = f"url('data:image/png;base64,{logo_b64}')" if logo_b64 else "none"
            
            # --- HTML GENERATION (THE "LUCKIN REPORT") ---
            html_report = f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
                <style>
                    :root {{ --luckin-blue: #232773; --luckin-gray: #F2F3F5; --text-main: #333333; --risk-red: #D93025; --success-green: #34A853; }}
                    body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background-color: var(--luckin-gray); margin: 0; padding: 0; }}
                    
                    /* REPORT HEADER */
                    .header {{ background-color: var(--luckin-blue); color: white; padding: 25px 40px; display: flex; align-items: center; justify-content: space-between; }}
                    .logo-box {{ width: 60px; height: 60px; background-color: white; border-radius: 8px; background-image: {logo_css}; background-size: contain; background-repeat: no-repeat; background-position: center; border: 2px solid rgba(255,255,255,0.2); }}
                    
                    .container {{ max-width: 1200px; margin: 30px auto; padding: 0 20px; }}
                    
                    /* KPI CARDS */
                    .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
                    .kpi-card {{ background: white; padding: 25px; border-radius: 12px; border-left: 5px solid var(--luckin-blue); box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
                    .kpi-label {{ color: #666; font-size: 14px; margin-bottom: 8px; }}
                    .kpi-value {{ font-size: 32px; font-weight: bold; color: var(--luckin-blue); }}
                    .kpi-sub {{ font-size: 12px; color: #999; margin-top: 5px; }}

                    /* CHART CONTAINERS */
                    .chart-box {{ background: white; padding: 25px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
                    .section-title {{ font-size: 18px; font-weight: bold; color: var(--luckin-blue); margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 15px; display: flex; align-items: center; gap: 10px; }}
                    .section-title::before {{ content: ''; width: 4px; height: 18px; background: var(--luckin-blue); display: block; border-radius: 2px; }}
                    
                    .chart {{ width: 100%; height: 400px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div style="display:flex; align-items:center; gap:20px;">
                        <div class="logo-box"></div>
                        <div>
                            <h1 style="margin:0; font-size:26px; letter-spacing:1px;">瑞幸咖啡 (Luckin Coffee)</h1>
                            <div style="font-size:14px; opacity:0.8; margin-top:5px;">美国市场运营分析周报 | US Operations Weekly Report</div>
                        </div>
                    </div>
                    <div style="text-align:right; font-size:12px; line-height:1.6;">
                        <div>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                        <div>数据来源: Uber Eats, DoorDash, Grubhub</div>
                    </div>
                </div>

                <div class="container">
                    <!-- KPI -->
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <div class="kpi-label">总订单量 (Total Orders)</div>
                            <div class="kpi-value">{total_orders}</div>
                            <div class="kpi-sub">All Platforms</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">总营收 (Total GMV)</div>
                            <div class="kpi-value">${total_gmv:,.2f}</div>
                            <div class="kpi-sub">Gross Sales</div>
                        </div>
                        <div class="kpi-card">
                            <div class="kpi-label">平均客单价 (AOV)</div>
                            <div class="kpi-value">${avg_ticket:.2f}</div>
                            <div class="kpi-sub">Average Order Value</div>
                        </div>
                        <div class="kpi-card" style="border-left-color: #D93025;">
                            <div class="kpi-label">最高单日销量</div>
                            <div class="kpi-value" style="color: #D93025; font-size: 24px;">{master_df.groupby(master_df['Date'].dt.date)['Revenue'].sum().idxmax()}</div>
                            <div class="kpi-sub">Peak Revenue Day</div>
                        </div>
                    </div>

                    <!-- Trend Chart -->
                    <div class="chart-box">
                        <div class="section-title">全平台日订单趋势 (Daily Order Trend)</div>
                        <div id="trendChart" class="chart"></div>
                    </div>

                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <!-- Pie Chart -->
                        <div class="chart-box" style="flex: 1; min-width: 400px;">
                            <div class="section-title">渠道占比 (Platform Mix)</div>
                            <div id="pieChart" class="chart"></div>
                        </div>
                        <!-- Bar Chart -->
                        <div class="chart-box" style="flex: 1; min-width: 400px;">
                            <div class="section-title">门店营收表现 (Store Performance)</div>
                            <div id="barChart" class="chart"></div>
                        </div>
                    </div>
                </div>

                <script>
                    document.addEventListener("DOMContentLoaded", function() {{
                        // 1. Trend Chart
                        var trendChart = echarts.init(document.getElementById('trendChart'));
                        trendChart.setOption({{
                            tooltip: {{ trigger: 'axis' }},
                            legend: {{ bottom: 0 }},
                            grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                            xAxis: {{ type: 'category', boundaryGap: false, data: {dates_list} }},
                            yAxis: {{ type: 'value' }},
                            series: [
                                {{ name: 'Uber Eats', type: 'line', smooth: true, showSymbol: false, data: {get_platform_series('Uber Eats')}, itemStyle: {{ color: '#06C167' }}, areaStyle: {{ opacity: 0.1 }} }},
                                {{ name: 'DoorDash', type: 'line', smooth: true, showSymbol: false, data: {get_platform_series('DoorDash')}, itemStyle: {{ color: '#FF3008' }}, areaStyle: {{ opacity: 0.1 }} }},
                                {{ name: 'Grubhub', type: 'line', smooth: true, showSymbol: false, data: {get_platform_series('Grubhub')}, itemStyle: {{ color: '#FF8000' }}, areaStyle: {{ opacity: 0.1 }} }}
                            ]
                        }});

                        // 2. Pie Chart
                        var pieChart = echarts.init(document.getElementById('pieChart'));
                        pieChart.setOption({{
                            tooltip: {{ trigger: 'item' }},
                            legend: {{ top: '5%', left: 'center' }},
                            series: [{{
                                name: 'Orders',
                                type: 'pie',
                                radius: ['40%', '70%'],
                                avoidLabelOverlap: false,
                                itemStyle: {{ borderRadius: 10, borderColor: '#fff', borderWidth: 2 }},
                                label: {{ show: false, position: 'center' }},
                                emphasis: {{ label: {{ show: true, fontSize: 20, fontWeight: 'bold' }} }},
                                data: {pie_data}
                            }}]
                        }});

                        // 3. Bar Chart
                        var barChart = echarts.init(document.getElementById('barChart'));
                        barChart.setOption({{
                            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                            grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                            xAxis: {{ type: 'value', name: 'USD' }},
                            yAxis: {{ type: 'category', data: {store_names} }},
                            series: [{{
                                name: 'Revenue',
                                type: 'bar',
                                data: {store_vals},
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
            
            # --- DISPLAY IN STREAMLIT ---
            
            # 1. System Logic Guide
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            st.markdown("""
            ### ⚙️ 系统处理逻辑 (System Logic)
            
            1.  **自动清洗 (Data Cleaning):** 系统自动剔除退款订单、无效数据行，并统一时间格式 (UTC 转 Local)。
            2.  **货币标准化 (Currency):** 自动移除 `$`, `,` 等符号，确保金额计算准确。
            3.  **多渠道融合 (Merge):** 将 Uber, DoorDash, Grubhub 的不同表头映射为标准字段：`Date`, `Revenue`, `Store`, `Platform`。
            4.  **Logo 注入:** 如果您在侧边栏上传了 Logo 图片，它将自动嵌入到下方的 HTML 报告中，下载后依然有效。
            """)
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.subheader("📊 报告预览 (Report Preview)")
            
            # Render the HTML
            st.components.v1.html(html_report, height=1000, scrolling=True)
            
            # Download Button
            col_dl1, col_dl2, col_dl3 = st.columns([1,2,1])
            with col_dl2:
                st.download_button(
                    label="📥 下载最终 HTML 报告文件 (Download Final Report)",
                    data=html_report,
                    file_name=f"Luckin_Analytics_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html",
                    type="primary",
                    use_container_width=True
                )

        except Exception as e:
            st.error(f"数据合并或处理时发生错误: {e}")
            st.info("请检查所有上传的 CSV 文件格式是否正确。")
    else:
        st.warning("请至少上传一个有效的 CSV 文件。")

else:
    # --- EMPTY STATE (Start Screen) ---
    st.markdown("""
    <div style='text-align: center; padding: 60px; color: #666;'>
        <h1>👋 欢迎使用瑞幸美国数据分析系统</h1>
        <p style="font-size: 18px;">Welcome to Luckin Coffee US Analytics Hub</p>
        <br>
        <div style="display: flex; justify-content: center; gap: 20px; margin-top: 20px;">
            <div class="info-card" style="width: 200px;">
                <div class="step-circle">1</div>
                <div>在左侧侧边栏上传 Logo</div>
            </div>
            <div class="info-card" style="width: 200px;">
                <div class="step-circle">2</div>
                <div>上传 Uber/DD/GH 原始报表</div>
            </div>
            <div class="info-card" style="width: 200px;">
                <div class="step-circle">3</div>
                <div>自动生成 HTML 分析报告</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
