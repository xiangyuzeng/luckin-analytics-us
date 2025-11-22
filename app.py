import streamlit as st
import pandas as pd
import base64
from datetime import datetime
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="Luckin Coffee (US) - Operations Analytics",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&display=swap');
        body { font-family: 'Noto Sans SC', sans-serif; background-color: #F5F7FA; }
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

# --- Helper Functions ---

def clean_currency(x):
    """Cleans currency strings to floats."""
    if isinstance(x, str):
        try:
            return float(x.replace('$', '').replace(',', '').replace(' ', ''))
        except:
            return 0.0
    return float(x) if pd.notnull(x) else 0.0

# --- Data Parsers ---

def parse_uber(file):
    try:
        # Uber header is usually on row 1 (index 1)
        df = pd.read_csv(file, header=1)
        
        # Mapping specific to the Uber file provided
        col_map = {
            '订单下单时的当地日期': 'Date_Str', 
            '订单日期': 'Date_Str', # Fallback
            '销售额（含税）': 'Revenue_Raw',
            '订单状态': 'Status',
            '餐厅名称': 'Store_Name'
        }
        
        # Rename columns if they exist
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            st.error("Uber CSV: Could not find Date column. Expected '订单下单时的当地日期' or '订单日期'.")
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        df['Is_Completed'] = df['Status'] == '已完成'
        df['Is_Cancelled'] = df['Status'].isin(['已取消', '退款', '未完成'])
        
        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'Uber Eats'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Uber Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        # DoorDash mapping
        df['Date'] = pd.to_datetime(df['接单当地时间'], errors='coerce')
        df['Revenue'] = df['小计'].apply(clean_currency)
        
        df['Is_Completed'] = df['最终订单状态'] == 'Delivered'
        df['Is_Cancelled'] = df['最终订单状态'].isin(['Cancelled', 'Merchant Cancelled'])
        
        df['Store'] = df['店铺名称'].fillna('Unknown Store')
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"DoorDash Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        df = df.dropna(subset=['transaction_date'])
        
        df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        
        # Grubhub status logic
        df['Is_Cancelled'] = df['transaction_type'].astype(str).str.contains('Cancel|Refund', case=False, na=False)
        df['Is_Completed'] = ~df['Is_Cancelled']
        
        df['Store'] = df['store_name'].fillna('Unknown Store')
        df['Platform'] = 'Grubhub'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Grubhub Parse Error: {str(e)}")
        return pd.DataFrame()

# --- HTML Report Generator ---

def generate_html_report(df):
    # 1. Core Metrics Calculation
    completed_df = df[df['Is_Completed'] == True].copy()
    
    total_orders = len(completed_df)
    total_gmv = completed_df['Revenue'].sum()
    avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
    
    # Dates
    if not df.empty:
        min_date = df['Date'].min().strftime('%Y年%m月%d日')
        max_date = df['Date'].max().strftime('%m月%d日')
    else:
        min_date, max_date = "N/A", "N/A"
        
    report_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # Best Day
    best_day_date, best_day_val, best_day_orders = "N/A", 0, 0
    if not completed_df.empty:
        daily_sum = completed_df.groupby(completed_df['Date'].dt.date)['Revenue'].sum()
        if not daily_sum.empty:
            best_day_idx = daily_sum.idxmax()
            best_day_date = best_day_idx.strftime('%m月%d日')
            best_day_val = daily_sum.max()
            best_day_orders = completed_df[completed_df['Date'].dt.date == best_day_idx].shape[0]

    # Cancellation Rate
    total_attempts = len(df)
    cancel_count = len(df[df['Is_Cancelled'] == True])
    cancel_rate = (cancel_count / total_attempts * 100) if total_attempts > 0 else 0
    
    # 2. CHART DATA PREPARATION
    
    # A. Trend Chart Data
    # Group by Date and Platform
    daily_platform = completed_df.groupby([completed_df['Date'].dt.date, 'Platform']).size().unstack(fill_value=0)
    
    # Get list of dates for X-Axis
    dates_obj = daily_platform.index
    dates_list_js = json.dumps([d.strftime('%m/%d') for d in dates_obj])
    
    # Get data series for each platform (ensure they align with dates)
    def get_series_data(plat_name):
        if plat_name in daily_platform.columns:
            return json.dumps(daily_platform[plat_name].tolist())
        return json.dumps([0] * len(dates_obj))

    uber_data_js = get_series_data('Uber Eats')
    dd_data_js = get_series_data('DoorDash')
    gh_data_js = get_series_data('Grubhub')
    
    # B. Pie Chart Data
    plat_counts = completed_df['Platform'].value_counts()
    val_uber = plat_counts.get('Uber Eats', 0)
    val_dd = plat_counts.get('DoorDash', 0)
    val_gh = plat_counts.get('Grubhub', 0)
    
    # C. Store Chart Data
    store_perf = completed_df.groupby('Store')['Revenue'].sum().sort_values(ascending=True)
    store_names_js = json.dumps([s.replace('Luckin Coffee', '').strip() for s in store_perf.index.tolist()])
    store_vals_js = json.dumps([round(x, 2) for x in store_perf.values.tolist()])
    
    top_store = store_perf.index[-1].replace('Luckin Coffee', '').strip() if not store_perf.empty else "None"
    top_store_rev = store_perf.values[-1] if not store_perf.empty else 0
    
    # 3. Table Rows Construction
    table_rows = ""
    platforms = ['Uber Eats', 'DoorDash', 'Grubhub']
    colors = {'Uber Eats': '#06C167', 'DoorDash': '#FF3008', 'Grubhub': '#FF8000'} # Orange for GH
    
    for p in platforms:
        count = plat_counts.get(p, 0)
        # Calculate revenue share
        plat_rev = completed_df[completed_df['Platform']==p]['Revenue'].sum()
        rev_share = (plat_rev / total_gmv * 100) if total_gmv > 0 else 0
        
        table_rows += f"""
        <tr>
            <td>{p}</td>
            <td>{count}</td>
            <td><span class="badge" style="background-color: {colors[p]}20; color: {colors[p]};">{rev_share:.1f}%</span></td>
        </tr>
        """

    # 4. Risk HTML Logic
    if cancel_rate > 3.0:
        risk_html = f"""
            <div class="alert alert-danger">
                <h4>⚠️ 1. 异常/取消率预警 (High Cancellation Rate)</h4>
                <ul style="margin-left: 20px; margin-top: 10px; font-size: 14px;">
                    <li><strong>当前取消率：</strong> {cancel_rate:.1f}% (目标: < 2.0%)</li>
                    <li><strong>影响：</strong> 共 {cancel_count} 笔订单未完成。请检查库存同步或门店接单设备。</li>
                </ul>
            </div>
        """
    else:
        risk_html = f"""
            <div class="alert alert-info" style="background-color: #e6f4ea; border-color: #d2e3fc; color: #34A853;">
                <h4>✅ 订单状态正常 (Normal Operations)</h4>
                <p style="font-size: 14px; margin-top:5px;">当前取消率为 {cancel_rate:.1f}%，处于健康范围内。</p>
            </div>
        """

    # 5. HTML Template Construction
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        :root {{
            --luckin-blue: #232773;
            --luckin-gray: #F2F3F5;
            --text-main: #333333;
            --text-sub: #666666;
            --risk-red: #D93025;
            --warning-orange: #F9AB00;
            --success-green: #34A853;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "PingFang SC", "Microsoft YaHei", Helvetica, Arial, sans-serif; background-color: var(--luckin-gray); color: var(--text-main); line-height: 1.5; }}
        .header {{ background-color: var(--luckin-blue); color: white; padding: 15px 40px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .logo-area {{ display: flex; align-items: center; gap: 15px; }}
        .actual-logo {{ height: 55px; width: auto; background-color: white; padding: 2px; border-radius: 6px; border: 2px solid rgba(255,255,255,0.3); }}
        .report-title h1 {{ font-size: 24px; font-weight: 600; letter-spacing: 1px; margin: 0; }}
        .report-info {{ text-align: right; font-size: 12px; opacity: 0.9; }}
        .container {{ max-width: 1400px; margin: 30px auto; padding: 0 20px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .kpi-card {{ background: white; padding: 25px; border-radius: 8px; border-left: 5px solid var(--luckin-blue); box-shadow: 0 2px 6px rgba(0,0,0,0.05); transition: transform 0.2s; }}
        .kpi-card:hover {{ transform: translateY(-2px); }}
        .kpi-label {{ color: var(--text-sub); font-size: 14px; margin-bottom: 8px; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; color: var(--luckin-blue); }}
        .kpi-sub {{ font-size: 12px; color: var(--text-sub); margin-top: 5px; }}
        .section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
        .section-header {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }}
        .section-title {{ font-size: 18px; font-weight: bold; color: var(--luckin-blue); }}
        .chart-container {{ width: 100%; height: 400px; min-height: 400px; }}
        .styled-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        .styled-table th {{ background-color: #f8f9fa; color: var(--luckin-blue); font-weight: 600; text-align: left; padding: 12px 15px; border-bottom: 2px solid var(--luckin-blue); }}
        .styled-table td {{ padding: 12px 15px; border-bottom: 1px solid #eee; }}
        .styled-table tr:hover {{ background-color: #f1f7ff; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .alert {{ padding: 15px; border-radius: 6px; margin-top: 15px; border: 1px solid transparent; }}
        .alert-danger {{ background-color: #fce8e6; border-color: #fad2cf; color: #a50e0e; }}
        .alert-info {{ background-color: #e8f0fe; border-color: #d2e3fc; color: #174ea6; }}
        .footer {{ text-align: center; font-size: 12px; color: #999; margin-top: 40px; padding-bottom: 20px; }}
    </style>
</head>
<body>

    <header class="header">
        <div class="logo-area">
            <img src="luckin_logo.png" alt="Luckin Logo" class="actual-logo">
            <div class="report-title">
                <h1>瑞幸咖啡 (Luckin Coffee)</h1>
                <div style="font-size: 14px; font-weight: normal; opacity: 0.8;">美国市场运营中心 | US Operations</div>
            </div>
        </div>
        <div class="report-info">
            <div>报告周期: {min_date} - {max_date}</div>
            <div>生成时间: <span id="reportTime">{report_time}</span></div>
        </div>
    </header>

    <div class="container">
        
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">本月总订单量 (Orders)</div>
                <div class="kpi-value">{total_orders} <span style="font-size:14px; color:#999;">单</span></div>
                <div class="kpi-sub">日均: ~{int(total_orders/30) if total_orders else 0} 单</div>
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
                <div class="kpi-sub">⚠️ 需关注退款问题</div>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <div class="section-title">【一、全平台日订单趋势分析】</div>
            </div>
            <div class="chart-container" id="trendChart"></div>
        </div>

        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="section-header">
                    <div class="section-title">【二、渠道占比 (Market Share)】</div>
                </div>
                <div class="chart-container" id="channelChart" style="height: 300px; min-height: 300px;"></div>
                <table class="styled-table">
                    <thead>
                        <tr>
                            <th>渠道 (Platform)</th>
                            <th>订单数</th>
                            <th>营收占比</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>

            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="section-header">
                    <div class="section-title">【三、门店表现 (Store Performance)】</div>
                </div>
                <div class="chart-container" id="storeChart" style="height: 300px; min-height: 300px;"></div>
                <div class="alert alert-info" style="font-size: 13px;">
                    <strong>💡 洞察：</strong> {top_store} 贡献了最高营收 (${top_store_rev:,.0f})，是目前的核心主力店。
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <div class="section-title" style="color: var(--risk-red);">【四、异常检测与风险预警 (Risk & Anomaly)】</div>
            </div>
            {risk_html}
            <div class="alert alert-info" style="margin-top: 15px; border-color: #bee5eb; background-color: #e2e6ea; color: #333;">
                <h4>⚠️ 2. 平台费率提示</h4>
                <p style="font-size: 14px; margin-top: 5px;">
                    请定期核对 Grubhub 与 DoorDash 订单的 "Merchant Service Fee" 是否出现较大波动，以确保促销活动设置正确。
                </p>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <div class="section-title">【五、下阶段运营建议 (Recommendations)】</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">1. 运营优化 (Operations)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;">针对 <strong>Uber Eats</strong> (Top Channel) 优化出餐动线，确保骑手取餐等待时间 < 5分钟，提升平台排名权重。</li>
                        <li style="margin-bottom: 8px;">加强 {top_store} 店周末时段的人员配置，以应对突发的订单高峰。</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">2. 营销策略 (Marketing)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;"><strong>Grubhub 策略：</strong> 该渠道客单价较高。建议推出针对办公人群的 "多人咖啡套餐" (Group Bundle)。</li>
                        <li style="margin-bottom: 8px;"><strong>DoorDash 策略：</strong> 建议开启 "$0 Delivery Fee" 活动以稳定日均单量。</li>
                    </ul>
                </div>
            </div>
        </div>

    </div>

    <div class="footer">
        &copy; 2025 Luckin Coffee Inc. Internal Report | Confidential
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            
            if (typeof echarts === 'undefined') {{
                console.error("ECharts library failed to load.");
                return;
            }}

            // --- INJECTED DATA FROM PYTHON ---
            const dates = {dates_list_js};
            const uberData = {uber_data_js};
            const ddData = {dd_data_js};
            const ghData = {gh_data_js};
            
            const storeNames = {store_names_js};
            const storeVals = {store_vals_js};
            
            const valUber = {val_uber};
            const valDd = {val_dd};
            const valGh = {val_gh};

            // Chart 1: Trend
            const trendDom = document.getElementById('trendChart');
            if (trendDom) {{
                const trendChart = echarts.init(trendDom);
                trendChart.setOption({{
                    tooltip: {{ trigger: 'axis' }},
                    legend: {{ data: ['Uber Eats', 'DoorDash', 'Grubhub'], bottom: 0 }},
                    grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                    xAxis: {{ type: 'category', boundaryGap: false, data: dates }},
                    yAxis: {{ type: 'value', name: '订单量' }},
                    series: [
                        {{ name: 'Uber Eats', type: 'line', smooth: true, data: uberData, itemStyle: {{ color: '#06C167' }}, lineStyle: {{ width: 3 }} }}, 
                        {{ name: 'DoorDash', type: 'line', smooth: true, data: ddData, itemStyle: {{ color: '#FF3008' }}, lineStyle: {{ width: 3 }} }}, 
                        {{ name: 'Grubhub', type: 'line', smooth: true, data: ghData, itemStyle: {{ color: '#FF8000' }}, lineStyle: {{ width: 3, color: '#FF8000' }} }} 
                    ]
                }});
                window.addEventListener('resize', function() {{ trendChart.resize(); }});
            }}

            // Chart 2: Pie
            const channelDom = document.getElementById('channelChart');
            if (channelDom) {{
                const channelChart = echarts.init(channelDom);
                channelChart.setOption({{
                    tooltip: {{ trigger: 'item' }},
                    legend: {{ top: '5%', left: 'center' }},
                    series: [
                        {{
                            name: '订单来源',
                            type: 'pie',
                            radius: ['40%', '70%'],
                            avoidLabelOverlap: false,
                            itemStyle: {{ borderRadius: 10, borderColor: '#fff', borderWidth: 2 }},
                            label: {{ show: false, position: 'center' }},
                            emphasis: {{ label: {{ show: true, fontSize: 20, fontWeight: 'bold' }} }},
                            data: [
                                {{ value: valUber, name: 'Uber Eats', itemStyle: {{ color: '#06C167' }} }},
                                {{ value: valDd, name: 'DoorDash', itemStyle: {{ color: '#FF3008' }} }},
                                {{ value: valGh, name: 'Grubhub', itemStyle: {{ color: '#FF8000' }} }}
                            ]
                        }}
                    ]
                }});
                window.addEventListener('resize', function() {{ channelChart.resize(); }});
            }}

            // Chart 3: Store Performance (Bar)
            const storeDom = document.getElementById('storeChart');
            if (storeDom) {{
                const storeChart = echarts.init(storeDom);
                storeChart.setOption({{
                    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                    grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                    xAxis: {{ type: 'value', name: '营收 ($)' }},
                    yAxis: {{ type: 'category', data: storeNames }},
                    series: [
                        {{
                            name: '营收',
                            type: 'bar',
                            data: storeVals,
                            itemStyle: {{ color: '#232773' }}, 
                            label: {{ show: true, position: 'right', formatter: '${{c}}' }}
                        }}
                    ]
                }});
                window.addEventListener('resize', function() {{ storeChart.resize(); }});
            }}
        }});
    </script>
</body>
</html>
    """
    return html

# --- Main App Layout ---

# 1. Navbar
st.markdown(f"""
    <div class="luckin-navbar">
        <div style="display:flex; align-items:center;">
            <div style="font-size: 24px; font-weight: bold; letter-spacing: 1px;">Luckin Coffee</div>
            <div style="margin-left: 15px; opacity: 0.7; border-left: 1px solid rgba(255,255,255,0.3); padding-left: 15px;">
                美国市场运营分析系统 (US Operations)
            </div>
        </div>
        <div style="font-size: 14px;">
            {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>
""", unsafe_allow_html=True)

# 2. Sidebar
with st.sidebar:
    st.title("Control Panel")
    st.markdown("**Step 1: Upload Platform CSVs**")
    
    uber_upload = st.file_uploader("Uber Eats (CSV)", type='csv', key='uber')
    dd_upload = st.file_uploader("DoorDash (CSV)", type='csv', key='dd')
    gh_upload = st.file_uploader("Grubhub (CSV)", type='csv', key='gh')
    
    st.markdown("---")
    st.info("ℹ️ Reports auto-update upon file upload.")

# 3. Processing
data_frames = []

if uber_upload:
    uber_upload.seek(0)
    df_uber = parse_uber(uber_upload)
    if not df_uber.empty: data_frames.append(df_uber)

if dd_upload:
    dd_upload.seek(0)
    df_dd = parse_doordash(dd_upload)
    if not df_dd.empty: data_frames.append(df_dd)

if gh_upload:
    gh_upload.seek(0)
    df_gh = parse_grubhub(gh_upload)
    if not df_gh.empty: data_frames.append(df_gh)

# 4. Visualization
if data_frames:
    try:
        master_df = pd.concat(data_frames, ignore_index=True)
        master_df.sort_values('Date', inplace=True)
        
        # Generate HTML
        html_report = generate_html_report(master_df)
        
        st.subheader("📊 Report Preview")
        st.components.v1.html(html_report, height=1300, scrolling=True)
        
        # Download Button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                label="📥 Download HTML Report",
                data=html_report,
                file_name=f"Luckin_US_Report_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html",
                type="primary",
                use_container_width=True
            )
            
    except Exception as e:
        st.error(f"Processing Error: {str(e)}")
else:
    st.markdown("""
    <div style='text-align: center; padding: 60px; color: #666;'>
        <h1>👋 Welcome to Luckin Analytics</h1>
        <p style="font-size: 18px;">Upload CSV files from the sidebar to generate your report.</p>
    </div>
    """, unsafe_allow_html=True)
