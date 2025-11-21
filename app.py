import streamlit as st
import pandas as pd
import base64
import io

# --- PAGE SETUP ---
st.set_page_config(page_title="Luckin Coffee Analytics", layout="wide", page_icon="☕")

# --- HELPER: CONVERT IMAGE TO BASE64 FOR HTML REPORT ---
def get_image_base64(path):
    try:
        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except:
        return "" # Return empty if no logo found

# --- 1. DATA PARSING (Same logic as before) ---
@st.cache_data
def parse_uber(file):
    try:
        df = pd.read_csv(file)
        df.columns = [c.strip() for c in df.columns]
        if 'Order Status' in df.columns: df = df[df['Order Status'] == 'Completed']
        df['Date'] = pd.to_datetime(df['Order Date'])
        rev_col = next((c for c in df.columns if 'Sales' in c and 'tax' in c), 'Sales')
        df['Revenue'] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
        df['Store'] = df['Restaurant Name'] if 'Restaurant Name' in df.columns else 'Unknown Store'
        df['Platform'] = 'Uber Eats'
        return df[['Date', 'Revenue', 'Store', 'Platform']]
    except: return pd.DataFrame()

@st.cache_data
def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        date_col = 'TIMESTAMP_UTC' if 'TIMESTAMP_UTC' in df.columns else 'Created At'
        status_col = 'FINAL_ORDER_STATUS' if 'FINAL_ORDER_STATUS' in df.columns else 'Order Status'
        if status_col in df.columns: df = df[df[status_col] == 'Delivered']
        df['Date'] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
        rev_col = 'SUBTOTAL' if 'SUBTOTAL' in df.columns else 'Subtotal'
        df['Revenue'] = pd.to_numeric(df[rev_col], errors='coerce').fillna(0)
        df['Store'] = df['STORE_NAME'] if 'STORE_NAME' in df.columns else 'Luckin Coffee'
        df['Platform'] = 'DoorDash'
        return df[['Date', 'Revenue', 'Store', 'Platform']]
    except: return pd.DataFrame()

@st.cache_data
def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        df['Date'] = pd.to_datetime(df['transaction_date'])
        df['Revenue'] = pd.to_numeric(df['subtotal'], errors='coerce').fillna(0)
        df['Store'] = df['store_name'] if 'store_name' in df.columns else 'Luckin Coffee'
        df['Platform'] = 'Grubhub'
        return df[['Date', 'Revenue', 'Store', 'Platform']]
    except: return pd.DataFrame()

# --- 2. UI - SIDEBAR UPLOADS ---
st.sidebar.image("luckin_logo.png", width=100)
st.sidebar.title("数据上传 (Data Upload)")
st.sidebar.markdown("请上传三大平台的CSV文件:")

uber_file = st.sidebar.file_uploader("Uber Eats / Postmates", type=['csv'])
dd_file = st.sidebar.file_uploader("DoorDash", type=['csv'])
gh_file = st.sidebar.file_uploader("Grubhub", type=['csv'])

# --- 3. MAIN LOGIC ---
if uber_file or dd_file or gh_file:
    # Merge Data
    dfs = []
    if uber_file: dfs.append(parse_uber(uber_file))
    if dd_file: dfs.append(parse_doordash(dd_file))
    if gh_file: dfs.append(parse_grubhub(gh_file))
    
    if dfs:
        df = pd.concat(dfs, ignore_index=True)
        df.sort_values('Date', inplace=True)

        # --- CALCULATE METRICS ---
        total_orders = len(df)
        total_gmv = df['Revenue'].sum()
        avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
        
        # Peak Day
        daily_sum = df.groupby(df['Date'].dt.date)['Revenue'].sum()
        if not daily_sum.empty:
            peak_date = daily_sum.idxmax()
            peak_val = daily_sum.max()
        else:
            peak_date = "N/A"
            peak_val = 0

        # Trend Chart Data (JS Array format)
        daily_counts = df.groupby([df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
        all_dates = [str(d) for d in daily_counts.index]
        
        # Prepare lists for ECharts (safely handling missing platforms)
        def get_platform_data(plat):
            return daily_counts[plat].tolist() if plat in daily_counts.columns else [0]*len(all_dates)
        
        uber_data = get_platform_data('Uber Eats')
        dd_data = get_platform_data('DoorDash')
        gh_data = get_platform_data('Grubhub')

        # Store Performance Data
        store_perf = df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
        store_names = store_perf.index.tolist()
        store_values = store_perf.values.tolist()

        # Market Share Data
        platform_counts = df['Platform'].value_counts()
        pie_data = [{"value": int(v), "name": k} for k, v in platform_counts.items()]

        # Logo Base64
        logo_b64 = get_image_base64("luckin_logo.png")

        # --- 4. HTML TEMPLATE INJECTION ---
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
            <style>
                :root {{ --luckin-blue: #232773; --luckin-gray: #F2F3F5; --text-main: #333333; --risk-red: #D93025; --success-green: #34A853; }}
                body {{ font-family: "PingFang SC", sans-serif; background-color: var(--luckin-gray); margin: 0; padding: 0; }}
                .header {{ background-color: var(--luckin-blue); color: white; padding: 20px 40px; display: flex; align-items: center; justify-content: space-between; }}
                .logo-img {{ width: 55px; height: 55px; border-radius: 6px; background: white; padding: 2px; border: 2px solid rgba(255,255,255,0.3); }}
                .container {{ max-width: 1400px; margin: 30px auto; padding: 0 20px; }}
                .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
                .kpi-card {{ background: white; padding: 25px; border-radius: 8px; border-left: 5px solid var(--luckin-blue); box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
                .kpi-value {{ font-size: 28px; font-weight: bold; color: var(--luckin-blue); }}
                .chart-container {{ width: 100%; height: 400px; background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .section-title {{ font-size: 18px; font-weight: bold; color: var(--luckin-blue); margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div style="display:flex; align-items:center; gap:15px;">
                    <img src="{logo_b64}" class="logo-img">
                    <div>
                        <h1 style="margin:0; font-size:24px;">瑞幸咖啡 (Luckin Coffee)</h1>
                        <div style="font-size:14px; opacity:0.8;">美国市场运营中心 | US Operations</div>
                    </div>
                </div>
                <div style="text-align:right; font-size:12px;">Generated via Streamlit</div>
            </div>

            <div class="container">
                <!-- KPI CARDS -->
                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div style="color:#666; font-size:14px;">总订单量 (Orders)</div>
                        <div class="kpi-value">{total_orders}</div>
                    </div>
                    <div class="kpi-card">
                        <div style="color:#666; font-size:14px;">总营收 (GMV)</div>
                        <div class="kpi-value">${total_gmv:,.2f}</div>
                        <div style="font-size:12px; color:#999;">客单价: ${avg_ticket:.2f}</div>
                    </div>
                    <div class="kpi-card">
                        <div style="color:#666; font-size:14px;">销售峰值日</div>
                        <div class="kpi-value">{peak_date}</div>
                        <div style="font-size:12px; color:#999;">营收: ${peak_val:,.2f}</div>
                    </div>
                    <div class="kpi-card" style="border-left-color: var(--risk-red);">
                        <div style="color:#666; font-size:14px;">渠道分布</div>
                        <div class="kpi-value" style="font-size:20px;">Uber: {get_platform_data('Uber Eats') and sum(get_platform_data('Uber Eats'))} 单</div>
                    </div>
                </div>

                <!-- TREND CHART -->
                <div class="chart-container">
                    <div class="section-title">【一、全平台日订单趋势分析】</div>
                    <div id="trendChart" style="width: 100%; height: 320px;"></div>
                </div>

                <div style="display: flex; gap: 20px;">
                    <!-- PIE CHART -->
                    <div class="chart-container" style="flex:1;">
                        <div class="section-title">【二、渠道占比 (Market Share)】</div>
                        <div id="pieChart" style="width: 100%; height: 320px;"></div>
                    </div>
                    <!-- BAR CHART -->
                    <div class="chart-container" style="flex:1;">
                        <div class="section-title">【三、门店表现 (Revenue)】</div>
                        <div id="barChart" style="width: 100%; height: 320px;"></div>
                    </div>
                </div>
            </div>

            <script>
                // Trend Chart
                var trendChart = echarts.init(document.getElementById('trendChart'));
                trendChart.setOption({{
                    tooltip: {{ trigger: 'axis' }},
                    legend: {{ data: ['Uber Eats', 'DoorDash', 'Grubhub'], bottom: 0 }},
                    grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                    xAxis: {{ type: 'category', boundaryGap: false, data: {all_dates} }},
                    yAxis: {{ type: 'value' }},
                    series: [
                        {{ name: 'Uber Eats', type: 'line', smooth: true, data: {uber_data}, itemStyle: {{ color: '#06C167' }}, lineStyle: {{ width: 3 }} }},
                        {{ name: 'DoorDash', type: 'line', smooth: true, data: {dd_data}, itemStyle: {{ color: '#FF3008' }}, lineStyle: {{ width: 3 }} }},
                        {{ name: 'Grubhub', type: 'line', smooth: true, data: {gh_data}, itemStyle: {{ color: '#FF8000' }}, lineStyle: {{ width: 3 }} }}
                    ]
                }});

                // Pie Chart
                var pieChart = echarts.init(document.getElementById('pieChart'));
                pieChart.setOption({{
                    tooltip: {{ trigger: 'item' }},
                    legend: {{ bottom: 0 }},
                    series: [
                        {{
                            type: 'pie',
                            radius: ['40%', '70%'],
                            itemStyle: {{ borderRadius: 10, borderColor: '#fff', borderWidth: 2 }},
                            data: {pie_data}
                        }}
                    ]
                }});

                // Bar Chart
                var barChart = echarts.init(document.getElementById('barChart'));
                barChart.setOption({{
                    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                    grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                    xAxis: {{ type: 'value' }},
                    yAxis: {{ type: 'category', data: {store_names} }},
                    series: [
                        {{
                            type: 'bar',
                            data: {store_values},
                            itemStyle: {{ color: '#232773' }},
                            label: {{ show: true, position: 'right' }}
                        }}
                    ]
                }});
                
                window.onresize = function() {{
                    trendChart.resize();
                    pieChart.resize();
                    barChart.resize();
                }};
            </script>
        </body>
        </html>
        """

        # --- 5. DISPLAY HTML ---
        # This renders the HTML string as an iframe inside Streamlit
        st.components.v1.html(html_content, height=1000, scrolling=True)

        # --- 6. DOWNLOAD BUTTON ---
        st.download_button(
            label="📥 下载完整 HTML 报告 (Download Report)",
            data=html_content,
            file_name="luckin_us_report.html",
            mime="text/html"
        )
    else:
        st.error("Uploaded files empty or could not be parsed.")
else:
    # Empty State
    st.markdown("""
    <div style='text-align: center; padding: 50px;'>
        <h2>👋 请在左侧上传数据文件</h2>
        <p>Please upload CSV files from Uber/DoorDash/Grubhub to generate the report.</p>
    </div>
    """, unsafe_allow_html=True)