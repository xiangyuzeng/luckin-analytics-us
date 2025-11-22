import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import numpy as np

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
        body { font-family: 'Noto Sans SC', sans-serif; background-color: #F2F3F5; }
        .luckin-navbar {
            background-color: #232773;
            padding: 1.5rem 2rem;
            border-radius: 0 0 10px 10px;
            color: white;
            box-shadow: 0 4px 12px rgba(35, 39, 115, 0.15);
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 2rem;
        }
        .stButton>button {
            width: 100%;
            background-color: #232773;
            color: white;
            border: none;
            height: 3rem;
        }
        .stButton>button:hover {
            background-color: #1a1d5c;
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def clean_currency(x):
    """Cleans currency strings to floats."""
    if pd.isna(x) or str(x).strip() == '':
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    x = str(x).strip()
    if '(' in x and ')' in x: x = '-' + x.replace('(', '').replace(')', '') 
    x = x.replace('$', '').replace(',', '').replace(' ', '')
    try:
        return float(x)
    except:
        return 0.0

# --- Data Parsers ---

def parse_uber(file):
    try:
        content = file.getvalue().decode('utf-8', errors='replace')
        lines = content.splitlines()
        
        # Dynamic Header Finder
        header_row = 0
        for i, line in enumerate(lines[:60]):
            if '餐厅名称' in line or 'Restaurant Name' in line:
                header_row = i
                break
        
        file.seek(0)
        df = pd.read_csv(file, header=header_row)

        # Column Mapping
        col_map = {
            '订单下单时的当地日期': 'Date_Str', '订单日期': 'Date_Str',
            '销售额（含税）': 'Revenue_Raw', 'Gross Sales': 'Revenue_Raw',
            '订单状态': 'Status', 'Order Status': 'Status',
            '餐厅名称': 'Store_Name', 'Restaurant Name': 'Store_Name',
            '订单号': 'Order_ID', 'Order ID': 'Order_ID'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        df['Is_Completed'] = df['Status'].astype(str).str.contains('Completed|已完成', case=False, na=False)
        df['Is_Cancelled'] = df['Status'].astype(str).str.contains('Cancelled|Refund|已取消|退款', case=False, na=False)
        
        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'Uber Eats'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Uber Error: {str(e)}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        col_map = {
            '接单当地时间': 'Date_Str', 'Created Time': 'Date_Str',
            '小计': 'Revenue_Raw', 'Subtotal': 'Revenue_Raw',
            '最终订单状态': 'Status', 'Order Status': 'Status',
            '店铺名称': 'Store_Name', 'Store Name': 'Store_Name',
            'DoorDash 订单 ID': 'Order_ID', 'Order ID': 'Order_ID'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        df['Is_Completed'] = df['Status'].isin(['Delivered', '已送达'])
        df['Is_Cancelled'] = df['Status'].isin(['Cancelled', 'Merchant Cancelled', '已取消'])
        
        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"DoorDash Error: {str(e)}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        col_map = {
            'transaction_date': 'Date_Str',
            'subtotal': 'Revenue_Raw',
            'store_name': 'Store_Name',
            'transaction_type': 'Type',
            'order_number': 'Order_ID'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})

        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        # 1. Handle Date: Grubhub CSVs from Excel often have "########"
        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        
        # CRITICAL FIX: If Date is missing (Excel error), verify valid order rows and assign a Fallback Date
        # so they are counted in Totals, even if the exact day is lost.
        valid_rows_mask = df['Order_ID'].notna()
        if df.loc[valid_rows_mask, 'Date'].isna().all():
            # Fallback: Assign all to a default date (e.g. Oct 1st) to ensure count is correct
            # Or distribute them if we want a pretty chart (Synthetic distribution)
            # For accuracy of totals, we just need valid entries.
            current_month = datetime.now().replace(day=1)
            df.loc[valid_rows_mask & df['Date'].isna(), 'Date'] = current_month

        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        df['Type'] = df['Type'].astype(str).fillna('')
        
        # Logic: Positive 'Order' rows are completed sales.
        df['Is_Cancelled_Row'] = df['Type'].str.contains('Cancel|Refund|Adjustment', case=False)
        df['Is_Order_Row'] = (df['Type'] == 'Prepaid Order') | (df['Type'] == 'Marketplace')
        
        # Mark Completed
        df['Is_Completed'] = df['Is_Order_Row'] & ~df['Is_Cancelled_Row']
        df['Is_Cancelled'] = df['Is_Cancelled_Row']

        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'Grubhub'

        # Drop rows that are not orders or cancels (e.g. header garbage) ONLY if date is also missing
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Order_ID'])
    except Exception as e:
        st.error(f"Grubhub Error: {str(e)}")
        return pd.DataFrame()

# --- HTML Generation ---

def generate_html_report(df):
    if df.empty: return "<div>No Data</div>"
    
    # Ensure we look at a specific window (e.g., Oct 2025 based on files)
    # If dates are mixed (some valid, some synthetic), sort by date
    df = df.sort_values('Date')
    
    # 1. Calculate KPI - COMPLETED ORDERS
    # Filter completed lines
    completed = df[df['Is_Completed'] == True].copy()
    
    # Grubhub needs UNQIUE ID counting due to multi-row structure
    # Uber/DD are single row usually, but unique ID is safer
    u_orders = completed[completed['Platform'] == 'Uber Eats']['Order_ID'].nunique()
    d_orders = completed[completed['Platform'] == 'DoorDash']['Order_ID'].nunique()
    g_orders = completed[completed['Platform'] == 'Grubhub']['Order_ID'].nunique()
    
    total_orders = u_orders + d_orders + g_orders
    
    # KPI - GMV
    # For Grubhub, we sum the 'Revenue' column of Completed Order Rows
    u_gmv = completed[completed['Platform'] == 'Uber Eats']['Revenue'].sum()
    d_gmv = completed[completed['Platform'] == 'DoorDash']['Revenue'].sum()
    g_gmv = completed[completed['Platform'] == 'Grubhub']['Revenue'].sum()
    
    total_gmv = u_gmv + d_gmv + g_gmv
    avg_ticket = total_gmv / total_orders if total_orders else 0
    
    # KPI - Peak Day
    # We need a common timeline. 
    if not completed.empty:
        # Remove synthetic NaT if any remain
        valid_dates = completed.dropna(subset=['Date'])
        if not valid_dates.empty:
            daily_sum = valid_dates.groupby(valid_dates['Date'].dt.date)['Revenue'].sum()
            peak_date = daily_sum.idxmax()
            peak_rev = daily_sum.max()
            
            # Count orders on peak day
            p_day_df = valid_dates[valid_dates['Date'].dt.date == peak_date]
            peak_orders = p_day_df[p_day_df['Platform']=='Uber Eats']['Order_ID'].nunique() + \
                          p_day_df[p_day_df['Platform']=='DoorDash']['Order_ID'].nunique() + \
                          p_day_df[p_day_df['Platform']=='Grubhub']['Order_ID'].nunique()
            
            peak_str = peak_date.strftime('%m月%d日')
        else:
            peak_str, peak_rev, peak_orders = "N/A", 0, 0
    else:
        peak_str, peak_rev, peak_orders = "N/A", 0, 0
        
    # KPI - Cancel Rate
    # (Unique IDs with Cancel Flag) / (Total Unique IDs)
    cancel_ids_u = df[(df['Platform']=='Uber Eats') & df['Is_Cancelled']]['Order_ID'].unique()
    cancel_ids_d = df[(df['Platform']=='DoorDash') & df['Is_Cancelled']]['Order_ID'].unique()
    cancel_ids_g = df[(df['Platform']=='Grubhub') & df['Is_Cancelled']]['Order_ID'].unique()
    total_cancels = len(cancel_ids_u) + len(cancel_ids_d) + len(cancel_ids_g)
    
    total_unique_ids = df[df['Platform']=='Uber Eats']['Order_ID'].nunique() + \
                       df[df['Platform']=='DoorDash']['Order_ID'].nunique() + \
                       df[df['Platform']=='Grubhub']['Order_ID'].nunique()
                       
    cancel_rate = (total_cancels / total_unique_ids * 100) if total_unique_ids else 0
    
    # 2. Chart Data Preparation
    # Create standard date range from min to max valid dates
    valid_dates_df = df.dropna(subset=['Date'])
    if not valid_dates_df.empty:
        min_d, max_d = valid_dates_df['Date'].min().date(), valid_dates_df['Date'].max().date()
        all_dates = pd.date_range(min_d, max_d).date
        dates_js = [d.strftime('%-m/%-d') for d in all_dates]
    else:
        dates_js = []
        all_dates = []

    def get_trend_data(plat):
        plat_df = valid_dates_df[(valid_dates_df['Platform'] == plat) & (valid_dates_df['Is_Completed'])]
        # If Grubhub dates were corrupted/fixed by assigning to 1st of month, the chart will spike. 
        # To match the HTML provided, let's assume valid dates exist or distribute them?
        # For accuracy, we plot what we have.
        daily = plat_df.groupby(plat_df['Date'].dt.date)['Order_ID'].nunique()
        return [int(daily.get(d, 0)) for d in all_dates]

    uber_data = get_trend_data('Uber Eats')
    dd_data = get_trend_data('DoorDash')
    gh_data = get_trend_data('Grubhub')
    
    # 3. Store Data
    valid_dates_df['Clean_Store'] = valid_dates_df['Store'].str.replace('Luckin Coffee', '').str.replace('US\d+', '', regex=True).str.replace('-', '').str.strip()
    valid_dates_df.loc[valid_dates_df['Clean_Store']=='', 'Clean_Store'] = 'Unknown'
    
    # Calculate Store Revenue (Completed only)
    store_stats = valid_dates_df[valid_dates_df['Is_Completed']].groupby('Clean_Store')['Revenue'].sum().sort_values()
    store_names = store_stats.index.tolist()
    store_vals = [round(x, 2) for x in store_stats.values]
    
    top_store = store_names[-1] if store_names else "N/A"
    
    # Shares
    s_u = (u_gmv / total_gmv * 100) if total_gmv else 0
    s_d = (d_gmv / total_gmv * 100) if total_gmv else 0
    s_g = (g_gmv / total_gmv * 100) if total_gmv else 0

    # Time string
    r_start = min_d.strftime('%Y年%m月%d日') if dates_js else ""
    r_end = max_d.strftime('%m月%d日') if dates_js else ""
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # --- INJECT INTO HTML ---
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Luckin Report</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        :root {{ --luckin-blue: #232773; --luckin-gray: #F2F3F5; --text-main: #333; --risk-red: #D93025; --success-green: #34A853; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--luckin-gray); color: var(--text-main); }}
        .header {{ background: var(--luckin-blue); color: white; padding: 15px 40px; display: flex; justify-content: space-between; align-items: center; }}
        .logo-box {{ border: 2px solid rgba(255,255,255,0.3); padding: 2px; border-radius: 6px; background: white; height: 55px; display: flex; align-items: center; }}
        .logo-box img {{ height: 45px; }}
        .container {{ max-width: 1400px; margin: 30px auto; padding: 0 20px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .kpi-card {{ background: white; padding: 25px; border-radius: 8px; border-left: 5px solid var(--luckin-blue); box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
        .kpi-val {{ font-size: 28px; font-weight: bold; color: var(--luckin-blue); }}
        .section {{ background: white; padding: 25px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }}
        .sec-title {{ font-size: 18px; font-weight: bold; color: var(--luckin-blue); border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 20px; }}
        .chart-box {{ width: 100%; height: 400px; }}
        .tbl {{ width: 100%; border-collapse: collapse; }}
        .tbl th {{ background: #f8f9fa; color: var(--luckin-blue); padding: 12px; text-align: left; border-bottom: 2px solid var(--luckin-blue); }}
        .tbl td {{ padding: 12px; border-bottom: 1px solid #eee; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
        .bg-green {{ background: #e6f4ea; color: var(--success-green); }}
        .alert {{ padding: 15px; border-radius: 6px; margin-top: 15px; border: 1px solid transparent; }}
        .alert-red {{ background: #fce8e6; color: #a50e0e; border-color: #fad2cf; }}
        .alert-blue {{ background: #e8f0fe; color: #174ea6; border-color: #d2e3fc; }}
    </style>
</head>
<body>
    <div class="header">
        <div style="display:flex; gap:15px; align-items:center;">
            <div class="logo-box"><img src="luckin_logo.png" alt="Logo" onerror="this.style.display='none'"></div>
            <div>
                <h1 style="margin:0; font-size:24px;">瑞幸咖啡 (Luckin Coffee)</h1>
                <div style="font-size:14px; opacity:0.8;">美国市场运营中心 | US Operations</div>
            </div>
        </div>
        <div style="text-align:right; font-size:12px;">
            <div>报告周期: {r_start} - {r_end}</div>
            <div>生成时间: {gen_time}</div>
        </div>
    </div>

    <div class="container">
        <div class="kpi-grid">
            <div class="kpi-card">
                <div style="color:#666; margin-bottom:8px;">本月总订单量 (Orders)</div>
                <div class="kpi-val">{total_orders} <span style="font-size:14px; color:#999;">单</span></div>
                <div style="font-size:12px; color:#666; margin-top:5px;">日均: ~{int(total_orders/30)} 单</div>
            </div>
            <div class="kpi-card">
                <div style="color:#666; margin-bottom:8px;">总营收 (GMV)</div>
                <div class="kpi-val">${total_gmv:,.2f}</div>
                <div style="font-size:12px; color:#666; margin-top:5px;">平均客单价: ${avg_ticket:.2f}</div>
            </div>
            <div class="kpi-card">
                <div style="color:#666; margin-bottom:8px;">最高单日销量</div>
                <div class="kpi-val">{peak_str}</div>
                <div style="font-size:12px; color:#666; margin-top:5px;">单日: {peak_orders} 单 | 营收: ${peak_rev:,.0f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: var(--risk-red);">
                <div style="color:#666; margin-bottom:8px;">订单异常/取消率</div>
                <div class="kpi-val" style="color: var(--risk-red);">{cancel_rate:.1f}%</div>
                <div style="font-size:12px; color:#666; margin-top:5px;">⚠️ 需关注退款问题</div>
            </div>
        </div>

        <div class="section">
            <div class="sec-title">【一、全平台日订单趋势分析】</div>
            <div id="trendChart" class="chart-box"></div>
        </div>

        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="sec-title">【二、渠道占比 (Market Share)】</div>
                <div id="channelChart" class="chart-box" style="height:300px;"></div>
                <table class="tbl">
                    <thead><tr><th>渠道</th><th>订单数</th><th>营收占比</th></tr></thead>
                    <tbody>
                        <tr><td>Uber Eats</td><td>{u_orders}</td><td><span class="badge bg-green">{s_u:.1f}%</span></td></tr>
                        <tr><td>DoorDash</td><td>{d_orders}</td><td>{s_d:.1f}%</td></tr>
                        <tr><td>Grubhub</td><td>{g_orders}</td><td>{s_g:.1f}%</td></tr>
                    </tbody>
                </table>
            </div>
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="sec-title">【三、门店表现 (Store Performance)】</div>
                <div id="storeChart" class="chart-box" style="height:300px;"></div>
                <div class="alert alert-blue" style="font-size:13px; margin-top:10px;">
                    <strong>💡 洞察：</strong> {top_store} 是目前的核心主力店。
                </div>
            </div>
        </div>

        <div class="section">
            <div class="sec-title" style="color: var(--risk-red);">【四、异常检测与风险预警】</div>
            <div class="alert alert-red">
                <h4>⚠️ 1. 退款/取消率分析</h4>
                <ul style="margin-left: 20px; font-size: 14px;">
                    <li>当前取消率：{cancel_rate:.1f}%</li>
                    <li>影响：共 {total_cancels} 笔订单涉及异常/取消。</li>
                    <li>建议：检查门店接单设备连接状态。</li>
                </ul>
            </div>
            <div class="alert alert-blue">
                <h4>⚠️ 2. 平台费率波动</h4>
                <p style="font-size:14px;">Grubhub 订单费率存在波动，建议核对促销活动。</p>
            </div>
        </div>
        
        <div class="section">
            <div class="sec-title">【五、下阶段运营建议】</div>
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
                <div>
                    <h4 style="color:var(--luckin-blue);">1. 运营优化</h4>
                    <ul style="font-size:14px; color:#555;">
                        <li>针对 Uber Eats 优化出餐动线。</li>
                        <li>加强 {top_store} 周末时段配置。</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color:var(--luckin-blue);">2. 营销策略</h4>
                    <ul style="font-size:14px; color:#555;">
                        <li>Grubhub: 推出多人咖啡套餐。</li>
                        <li>DoorDash: 建议开启免运费活动。</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <div style="text-align:center; color:#999; font-size:12px; margin-top:40px; padding-bottom:20px;">
        &copy; 2025 Luckin Coffee Inc. Internal Report
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            const dates = {json.dumps(dates_js)};
            const uberData = {json.dumps(uber_data)};
            const ddData = {json.dumps(dd_data)};
            const ghData = {json.dumps(gh_data)};
            const storeNames = {json.dumps(store_names)};
            const storeVals = {json.dumps(store_vals)};

            if (typeof echarts === 'undefined') return;

            const tChart = echarts.init(document.getElementById('trendChart'));
            tChart.setOption({{
                tooltip: {{ trigger: 'axis' }},
                legend: {{ bottom: 0 }},
                grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
                xAxis: {{ type: 'category', boundaryGap: false, data: dates }},
                yAxis: {{ type: 'value' }},
                series: [
                    {{ name: 'Uber Eats', type: 'line', smooth: true, data: uberData, itemStyle: {{ color: '#06C167' }}, lineStyle: {{ width: 3 }} }},
                    {{ name: 'DoorDash', type: 'line', smooth: true, data: ddData, itemStyle: {{ color: '#FF3008' }}, lineStyle: {{ width: 3 }} }},
                    {{ name: 'Grubhub', type: 'line', smooth: true, data: ghData, itemStyle: {{ color: '#FF8000' }}, lineStyle: {{ width: 3 }} }}
                ]
            }});

            const cChart = echarts.init(document.getElementById('channelChart'));
            cChart.setOption({{
                tooltip: {{ trigger: 'item' }},
                legend: {{ top: '5%', left: 'center' }},
                series: [
                    {{
                        type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: false,
                        itemStyle: {{ borderRadius: 10, borderColor: '#fff', borderWidth: 2 }},
                        label: {{ show: false }},
                        data: [
                            {{ value: {u_orders}, name: 'Uber Eats', itemStyle: {{ color: '#06C167' }} }},
                            {{ value: {d_orders}, name: 'DoorDash', itemStyle: {{ color: '#FF3008' }} }},
                            {{ value: {g_orders}, name: 'Grubhub', itemStyle: {{ color: '#FF8000' }} }}
                        ]
                    }}
                ]
            }});

            const sChart = echarts.init(document.getElementById('storeChart'));
            sChart.setOption({{
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                grid: {{ left: '3%', right: '10%', bottom: '3%', containLabel: true }},
                xAxis: {{ type: 'value' }},
                yAxis: {{ type: 'category', data: storeNames }},
                series: [
                    {{ name: '营收', type: 'bar', data: storeVals, itemStyle: {{ color: '#232773' }}, label: {{ show: true, position: 'right', formatter: '${{c}}' }} }}
                ]
            }});

            window.onresize = function() {{
                tChart.resize(); cChart.resize(); sChart.resize();
            }};
        }});
    </script>
</body>
</html>
    """
    return html

# --- Main Execution ---

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

with st.sidebar:
    st.title("Control Panel")
    st.markdown("**Step 1: Upload Platform CSVs**")
    uber_file = st.file_uploader("Uber Eats (CSV)", type='csv', key='uber')
    dd_file = st.file_uploader("DoorDash (CSV)", type='csv', key='dd')
    gh_file = st.file_uploader("Grubhub (CSV)", type='csv', key='gh')
    st.markdown("---")
    st.info("Reports auto-update upon file upload.")

data_frames = []

if uber_file:
    uber_file.seek(0)
    df_u = parse_uber(uber_file)
    if not df_u.empty: data_frames.append(df_u)

if dd_file:
    dd_file.seek(0)
    df_d = parse_doordash(dd_file)
    if not df_d.empty: data_frames.append(df_d)

if gh_file:
    gh_file.seek(0)
    df_g = parse_grubhub(gh_file)
    if not df_g.empty: data_frames.append(df_g)

if data_frames:
    master_df = pd.concat(data_frames, ignore_index=True)
    html_report = generate_html_report(master_df)
    st.subheader("📊 Report Preview")
    st.components.v1.html(html_report, height=1500, scrolling=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.download_button("📥 Download HTML Report", html_report, file_name="Luckin_Report.html", mime="text/html", type="primary")
else:
    st.markdown("<div style='text-align:center; padding:50px; color:#666;'><h3>👋 Welcome</h3><p>Please upload CSV files to generate the report.</p></div>", unsafe_allow_html=True)
