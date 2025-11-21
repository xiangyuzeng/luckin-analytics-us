import streamlit as st
import pandas as pd
import base64
import io
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Luckin Coffee US - Operations Report",
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

        /* Luckin Header in Streamlit */
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
        
        .info-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #e0e0e0;
            box-shadow: 0 2px 5px rgba(0,0,0,0.03);
            margin-bottom: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def clean_currency(x):
    """Cleans currency strings to float."""
    if isinstance(x, str):
        try:
            return float(x.replace('$', '').replace(',', '').replace(' ', ''))
        except:
            return 0.0
    return float(x) if pd.notnull(x) else 0.0

def get_image_base64(uploaded_file):
    """Converts uploaded logo to base64."""
    if uploaded_file is not None:
        try:
            return base64.b64encode(uploaded_file.getvalue()).decode()
        except:
            return ""
    return ""

# --- DATA PARSERS ---

def parse_uber(file):
    try:
        # Uber CSV from your sample has metadata in row 1, headers in row 2
        df = pd.read_csv(file, header=1)
        
        # Standardization
        # Date: 订单下单时的当地日期 (10/1/2025) + 商家接受订单时的当地时间戳 (8:30)
        # We will just use Date for daily aggregation to be safe, or combine if needed
        df['Date_Str'] = df['订单下单时的当地日期'].astype(str)
        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        
        # Revenue: '销售额（含税）'
        df['Revenue'] = df['销售额（含税）'].apply(clean_currency)
        
        # Status: '订单状态' (已完成, 已取消, etc)
        df['Status_Raw'] = df['订单状态']
        df['Is_Completed'] = df['订单状态'] == '已完成'
        df['Is_Cancelled'] = df['订单状态'].isin(['已取消', '退款'])
        
        df['Store'] = df['餐厅名称'].fillna('Unknown Store')
        df['Platform'] = 'Uber Eats'
        
        # Select relevant columns
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
    except Exception as e:
        st.error(f"Error parsing Uber CSV: {e}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # DoorDash from sample
        # Date: '接单当地时间' (10/31/2025 15:34)
        df['Date'] = pd.to_datetime(df['接单当地时间'], errors='coerce')
        
        # Revenue: '小计' (Subtotal)
        df['Revenue'] = df['小计'].apply(clean_currency)
        
        # Status: '最终订单状态' (Delivered, Cancelled)
        df['Status_Raw'] = df['最终订单状态']
        df['Is_Completed'] = df['最终订单状态'] == 'Delivered'
        df['Is_Cancelled'] = df['最终订单状态'] == 'Cancelled' # Verify exact string in CSV
        
        df['Store'] = df['店铺名称'].fillna('Unknown Store')
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
    except Exception as e:
        st.error(f"Error parsing DoorDash CSV: {e}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        
        # Grubhub from sample
        # Date: 'transaction_date' (######## or date format) + 'transaction_time_local'
        # In the sample CSV provided in prompt, dates looked masked or formatted. 
        # Assuming standard CSV format available in the file upload.
        
        # Dropping rows with missing dates
        df = df.dropna(subset=['transaction_date'])
        
        # Combine date and time if available, else just date
        df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        
        # Revenue: 'subtotal' + 'tax'? Or just subtotal. Let's use 'subtotal' based on typical reporting.
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        
        # Status: Grubhub uses 'transaction_type'. 
        # 'Order' is standard. 'Cancellation' or 'Order Adjustment' implies issues.
        # Let's assume rows present are valid transactions unless type says Cancel.
        df['Status_Raw'] = df['transaction_type']
        df['Is_Completed'] = ~df['transaction_type'].astype(str).str.contains('Cancel', case=False, na=False)
        df['Is_Cancelled'] = df['transaction_type'].astype(str).str.contains('Cancel', case=False, na=False)
        
        df['Store'] = df['store_name'].fillna('Unknown Store')
        df['Platform'] = 'Grubhub'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
    except Exception as e:
        st.error(f"Error parsing Grubhub CSV: {e}")
        return pd.DataFrame()

# --- HTML GENERATOR ---
def generate_html_report(df, logo_b64):
    # 1. CALCULATE METRICS
    completed_df = df[df['Is_Completed'] == True].copy()
    
    total_orders = len(completed_df)
    total_gmv = completed_df['Revenue'].sum()
    avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
    
    # Date Range
    min_date = df['Date'].min().strftime('%Y年%m月%d日')
    max_date = df['Date'].max().strftime('%m月%d日')
    report_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # Highest Day
    if not completed_df.empty:
        daily_sum = completed_df.groupby(completed_df['Date'].dt.date)['Revenue'].sum()
        best_day_date = daily_sum.idxmax().strftime('%m月%d日')
        best_day_val = daily_sum.max()
        best_day_orders = completed_df[completed_df['Date'].dt.date == daily_sum.idxmax()].shape[0]
    else:
        best_day_date = "N/A"
        best_day_val = 0
        best_day_orders = 0

    # Cancellation Rate
    total_attempts = len(df)
    cancel_count = len(df[df['Is_Cancelled'] == True])
    cancel_rate = (cancel_count / total_attempts * 100) if total_attempts > 0 else 0
    
    # 2. PREPARE CHART DATA
    # Trend Data (Line Chart)
    daily_platform = completed_df.groupby([completed_df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
    dates_list = [str(d) for d in daily_platform.index]
    uber_data = daily_platform.get('Uber Eats', [0]*len(dates_list)).tolist()
    dd_data = daily_platform.get('DoorDash', [0]*len(dates_list)).tolist()
    gh_data = daily_platform.get('Grubhub', [0]*len(dates_list)).tolist()
    
    # Channel Mix Data (Pie Chart & Table)
    plat_counts = completed_df['Platform'].value_counts()
    plat_revenue = completed_df.groupby('Platform')['Revenue'].sum()
    
    # Store Performance (Bar Chart)
    store_perf = completed_df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
    store_names = store_perf.index.tolist()
    store_vals = [round(x, 2) for x in store_perf.values.tolist()]
    top_store = store_names[-1] if store_names else "None"
    top_store_rev = store_vals[-1] if store_vals else 0

    # Risk Detection (Simple Logic)
    risk_html = ""
    if cancel_rate > 3.0:
         risk_html += f"""
         <div class="alert alert-danger">
            <h4>⚠️ 1. 异常/取消率预警 (High Cancellation Rate)</h4>
            <ul style="margin-left: 20px; margin-top: 10px; font-size: 14px;">
                <li><strong>当前取消率：</strong> {cancel_rate:.1f}% (Target: < 2.0%)</li>
                <li><strong>影响：</strong> 共 {cancel_count} 笔订单未完成。请检查库存同步或门店接单设备。</li>
            </ul>
        </div>"""
    else:
        risk_html += f"""
         <div class="alert alert-info">
            <h4>✅ 订单状态正常 (Normal Operations)</h4>
            <p style="font-size: 14px;">当前取消率为 {cancel_rate:.1f}%，处于健康范围内。</p>
        </div>"""

    # Logo Styling
    logo_css = f"url('data:image/png;base64,{logo_b64}')" if logo_b64 else "none"
    logo_display_class = "actual-logo" if logo_b64 else "logo-placeholder"
    logo_html = f'<div class="logo-box" style="background-image: {logo_css};"></div>'

    # 3. GENERATE HTML
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        :root {{ --luckin-blue: #232773; --luckin-gray: #F2F3F5; --text-main: #333333; --risk-red: #D93025; --success-green: #34A853; --warning-orange: #F9AB00; }}
        body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background-color: var(--luckin-gray); margin: 0; padding: 0; color: #333; }}
        
        /* HEADER */
        .header {{ background-color: var(--luckin-blue); color: white; padding: 20px 40px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .logo-box {{ width: 60px; height: 60px; background-color: white; border-radius: 8px; background-size: contain; background-repeat: no-repeat; background-position: center; border: 2px solid rgba(255,255,255,0.2); }}
        .report-title h1 {{ font-size: 24px; font-weight: 600; letter-spacing: 1px; margin: 0; }}
        .report-info {{ text-align: right; font-size: 12px; opacity: 0.9; }}
        
        .container {{ max-width: 1300px; margin: 30px auto; padding: 0 20px; }}

        /* KPI CARDS */
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .kpi-card {{ background: white; padding: 25px; border-radius: 8px; border-left: 5px solid var(--luckin-blue); box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
        .kpi-label {{ color: #666; font-size: 14px; margin-bottom: 8px; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; color: var(--luckin-blue); }}
        .kpi-sub {{ font-size: 12px; color: #999; margin-top: 5px; }}

        /* SECTIONS */
        .section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
        .section-header {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 20px; }}
        .section-title {{ font-size: 18px; font-weight: bold; color: var(--luckin-blue); }}
        .chart-container {{ width: 100%; height: 350px; }}

        /* TABLES & ALERTS */
        .styled-table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 10px; }}
        .styled-table th {{ background-color: #f8f9fa; color: var(--luckin-blue); text-align: left; padding: 10px; border-bottom: 2px solid var(--luckin-blue); }}
        .styled-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
        
        .alert {{ padding: 15px; border-radius: 6px; margin-top: 10px; border: 1px solid transparent; }}
        .alert-danger {{ background-color: #fce8e6; border-color: #fad2cf; color: #a50e0e; }}
        .alert-info {{ background-color: #e8f0fe; border-color: #d2e3fc; color: #174ea6; }}
        
        .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .badge-success {{ background: #e6f4ea; color: #34A853; }}

        .footer {{ text-align: center; font-size: 12px; color: #999; margin: 40px 0 20px 0; }}
    </style>
</head>
<body>

    <div class="header">
        <div style="display:flex; align-items:center; gap:15px;">
            {logo_html}
            <div class="report-title">
                <h1>瑞幸咖啡 (Luckin Coffee)</h1>
                <div style="font-size: 14px; font-weight: normal; opacity: 0.8;">美国市场运营中心 | US Operations</div>
            </div>
        </div>
        <div class="report-info">
            <div>报告周期: {min_date} - {max_date}</div>
            <div>生成时间: {report_time}</div>
        </div>
    </div>

    <div class="container">
        <!-- KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">总订单量 (Orders)</div>
                <div class="kpi-value">{total_orders} <span style="font-size:14px; color:#999;">单</span></div>
                <div class="kpi-sub">All Platforms</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">总营收 (GMV)</div>
                <div class="kpi-value">${total_gmv:,.2f}</div>
                <div class="kpi-sub">平均客单价: ${avg_ticket:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">最高单日销量</div>
                <div class="kpi-value">{best_day_date}</div>
                <div class="kpi-sub">单日: {best_day_orders} 单 | 营收: ${best_day_val:,.0f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: var(--risk-red);">
                <div class="kpi-label">订单异常/取消率</div>
                <div class="kpi-value" style="color: var(--risk-red);">{cancel_rate:.1f}%</div>
                <div class="kpi-sub">Target: < 2.0%</div>
            </div>
        </div>

        <!-- Chart: Trend -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">【一、全平台日订单趋势 (Daily Trend)】</div>
            </div>
            <div id="trendChart" class="chart-container"></div>
        </div>

        <!-- Split Section -->
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <!-- Channel Mix -->
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="section-header"><div class="section-title">【二、渠道占比 (Platform Mix)】</div></div>
                <div id="channelChart" class="chart-container" style="height: 300px;"></div>
                <table class="styled-table">
                    <thead><tr><th>渠道</th><th>订单数</th><th>营收占比</th></tr></thead>
                    <tbody>
                        {''.join([f"<tr><td>{p}</td><td>{plat_counts.get(p,0)}</td><td><span class='badge badge-success'>{plat_revenue.get(p,0)/total_gmv*100:.1f}%</span></td></tr>" for p in ['Uber Eats', 'DoorDash', 'Grubhub'] if p in plat_counts])}
                    </tbody>
                </table>
            </div>

            <!-- Store Performance -->
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="section-header"><div class="section-title">【三、门店表现 (Store Performance)】</div></div>
                <div id="storeChart" class="chart-container" style="height: 300px;"></div>
                <div class="alert alert-info" style="font-size: 13px;">
                    <strong>💡 洞察：</strong> {top_store} 是目前营收最高的门店 (Contribution: ${top_store_rev:,.0f})。
                </div>
            </div>
        </div>

        <!-- Risks -->
        <div class="section">
            <div class="section-header"><div class="section-title" style="color: var(--risk-red);">【四、异常检测与风险预警 (Risk & Anomaly)】</div></div>
            {risk_html}
        </div>

        <!-- Recommendations -->
        <div class="section">
            <div class="section-header"><div class="section-title">【五、运营建议 (Recommendations)】</div></div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">1. 运营优化 (Operations)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;">针对 <strong>Uber Eats</strong> (Top Channel) 优化出餐动线，确保骑手取餐等待时间 < 5分钟。</li>
                        <li>{top_store} 订单量较大，建议检查周末时段的人员配置。</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">2. 营销策略 (Marketing)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;">建议针对客单价较低的渠道推出 "Group Bundle" 套餐以提升 AOV。</li>
                        <li>关注取消率较高的时段，必要时开启平台暂停接单功能。</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <div class="footer">
        &copy; 2025 Luckin Coffee Inc. US Operations | Confidential Report
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            // Trend Chart
            var trendChart = echarts.init(document.getElementById('trendChart'));
            trendChart.setOption({{
                tooltip: {{ trigger: 'axis' }},
                legend: {{ bottom: 0 }},
                grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                xAxis: {{ type: 'category', boundaryGap: false, data: {dates_list} }},
                yAxis: {{ type: 'value' }},
                series: [
                    {{ name: 'Uber Eats', type: 'line', smooth: true, data: {uber_data}, itemStyle: {{ color: '#06C167' }}, lineStyle: {{ width: 3 }} }},
                    {{ name: 'DoorDash', type: 'line', smooth: true, data: {dd_data}, itemStyle: {{ color: '#FF3008' }}, lineStyle: {{ width: 3 }} }},
                    {{ name: 'Grubhub', type: 'line', smooth: true, data: {gh_data}, itemStyle: {{ color: '#FF8000' }}, lineStyle: {{ width: 3 }} }}
                ]
            }});

            // Pie Chart
            var channelChart = echarts.init(document.getElementById('channelChart'));
            channelChart.setOption({{
                tooltip: {{ trigger: 'item' }},
                legend: {{ top: '5%', left: 'center' }},
                series: [{{
                    name: 'Revenue Source',
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: {{ borderRadius: 10, borderColor: '#fff', borderWidth: 2 }},
                    label: {{ show: false, position: 'center' }},
                    emphasis: {{ label: {{ show: true, fontSize: 20, fontWeight: 'bold' }} }},
                    data: [
                        {{ value: {plat_counts.get('Uber Eats', 0)}, name: 'Uber Eats', itemStyle: {{ color: '#06C167' }} }},
                        {{ value: {plat_counts.get('DoorDash', 0)}, name: 'DoorDash', itemStyle: {{ color: '#FF3008' }} }},
                        {{ value: {plat_counts.get('Grubhub', 0)}, name: 'Grubhub', itemStyle: {{ color: '#FF8000' }} }}
                    ]
                }}]
            }});

            // Store Bar Chart
            var storeChart = echarts.init(document.getElementById('storeChart'));
            storeChart.setOption({{
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                xAxis: {{ type: 'value' }},
                yAxis: {{ type: 'category', data: {store_names} }},
                series: [{{
                    name: 'Revenue',
                    type: 'bar',
                    data: {store_vals},
                    itemStyle: {{ color: '#232773' }},
                    label: {{ show: true, position: 'right', formatter: '${{c}}' }}
                }}]
            }});

            window.addEventListener('resize', function() {{
                trendChart.resize();
                channelChart.resize();
                storeChart.resize();
            }});
        }});
    </script>
</body>
</html>
    """
    return html

# --- MAIN UI LAYOUT ---

# 1. Top Navigation Bar
st.markdown(f"""
    <div class="luckin-navbar">
        <div style="display:flex; align-items:center;">
            <div style="font-size: 24px; font-weight: bold; letter-spacing: 1px;">Luckin Coffee</div>
            <div style="margin-left: 15px; opacity: 0.7; border-left: 1px solid rgba(255,255,255,0.3); padding-left: 15px;">
                US Operations Report Generator
            </div>
        </div>
        <div style="font-size: 14px;">
            {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>
""", unsafe_allow_html=True)

# 2. Sidebar Controls
with st.sidebar:
    st.title("Control Panel")
    st.markdown("**1. Upload Brand Logo**")
    logo_file = st.file_uploader("Upload Logo (Optional)", type=['png', 'jpg', 'jpeg'])
    
    st.markdown("---")
    st.markdown("**2. Upload Data Files (CSV)**")
    
    uber_upload = st.file_uploader("Uber Eats (CSV)", type='csv', key='uber')
    dd_upload = st.file_uploader("DoorDash (CSV)", type='csv', key='dd')
    gh_upload = st.file_uploader("Grubhub (CSV)", type='csv', key='gh')
    
    st.markdown("---")
    st.info("System will automatically merge new files and update the dashboard.")

# 3. Main Content Logic
data_frames = []

if uber_upload:
    df_uber = parse_uber(uber_upload)
    if not df_uber.empty: data_frames.append(df_uber)

if dd_upload:
    df_dd = parse_doordash(dd_upload)
    if not df_dd.empty: data_frames.append(df_dd)

if gh_upload:
    df_gh = parse_grubhub(gh_upload)
    if not df_gh.empty: data_frames.append(df_gh)

if data_frames:
    try:
        # Merge all data
        master_df = pd.concat(data_frames, ignore_index=True)
        master_df.sort_values('Date', inplace=True)
        
        # Get Logo
        logo_b64 = get_image_base64(logo_file)
        
        # Generate HTML
        html_report = generate_html_report(master_df, logo_b64)
        
        # Display
        st.subheader("📊 Report Preview")
        st.components.v1.html(html_report, height=1200, scrolling=True)
        
        # Download
        col_dl1, col_dl2, col_dl3 = st.columns([1,2,1])
        with col_dl2:
            st.download_button(
                label="📥 Download HTML Report (Luckin_Ops_Report.html)",
                data=html_report,
                file_name=f"Luckin_US_Report_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html",
                type="primary",
                use_container_width=True
            )
            
    except Exception as e:
        st.error(f"Error consolidating data: {str(e)}")
else:
    # Empty State
    st.markdown("""
    <div style='text-align: center; padding: 60px; color: #666;'>
        <h1>👋 Welcome to Luckin US Analytics</h1>
        <p style="font-size: 18px;">Upload Uber, DoorDash, and Grubhub CSV files to generate the weekly operations report.</p>
    </div>
    """, unsafe_allow_html=True)
