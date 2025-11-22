import streamlit as st
import pandas as pd
import json
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(
    page_title="Luckin Coffee (US) - Operations Analytics",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Streamlit UI (Not the Report) ---
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
        .stButton>button {
            width: 100%;
            background-color: #232773;
            color: white;
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def clean_currency(x):
    """Cleans currency strings to floats, handling $, commas, and parenthesis for negatives."""
    if pd.isna(x) or x == '':
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    
    x = str(x).strip()
    # Handle negative numbers in parenthesis (e.g., "(5.00)")
    if '(' in x and ')' in x:
        x = '-' + x.replace('(', '').replace(')', '')
    
    x = x.replace('$', '').replace(',', '').replace(' ', '')
    
    try:
        return float(x)
    except:
        return 0.0

# --- Data Parsers ---

def parse_uber(file):
    try:
        # Uber CSVs often have the header on the 2nd row (index 1)
        df = pd.read_csv(file, header=1)
        
        # Map Columns based on standard Uber CSV exports
        # We look for specific Chinese headers found in your csv
        col_map = {
            '订单下单时的当地日期': 'Date_Str', 
            '餐点销售额总计（含税费）': 'Revenue_Raw', # Using Gross with Tax for GMV
            '订单状态': 'Status',
            '餐厅名称': 'Store_Name',
            'Uber Eats 优食管理工具中显示的餐厅名称': 'Store_Name_Alt'
        }
        
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        # Fallback if header row was actually 0
        if 'Date_Str' not in df.columns:
             # Try checking if columns suggest header was 0
             if '订单下单时的当地日期' in pd.read_csv(file, header=0).columns:
                 df = pd.read_csv(file, header=0)
                 df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        # Status Logic
        df['Is_Completed'] = df['Status'] == '已完成'
        # Is_Cancelled captures cancellations AND refunds
        df['Is_Cancelled'] = df['Status'].isin(['已取消', '退款', '未完成'])
        
        # Store Name Logic
        if 'Store_Name' in df.columns:
            df['Store'] = df['Store_Name'].fillna('Unknown')
        elif 'Store_Name_Alt' in df.columns:
            df['Store'] = df['Store_Name_Alt'].fillna('Unknown')
        else:
            df['Store'] = 'Luckin Coffee'

        df['Platform'] = 'Uber Eats'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Uber Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # DoorDash usually has header at row 0
        col_map = {
            '接单当地时间': 'Date_Str',
            '小计': 'Revenue_Raw', # Subtotal
            '最终订单状态': 'Status',
            '店铺名称': 'Store_Name'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})

        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        df['Is_Completed'] = df['Status'] == 'Delivered'
        df['Is_Cancelled'] = df['Status'].isin(['Cancelled', 'Merchant Cancelled'])
        
        df['Store'] = df['Store_Name'].fillna('Luckin Coffee')
        df['Platform'] = 'DoorDash'
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"DoorDash Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        
        # Standard Grubhub export mapping
        col_map = {
            'transaction_date': 'Date_Str',
            'subtotal': 'Revenue_Raw',
            'store_name': 'Store_Name',
            'transaction_type': 'Type'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})

        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        # Fix for ######## or Excel errors: attempt to parse, coerce errors to NaT
        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        
        # Fallback: If CSV dates are corrupted (#######), we might need to rely on 'transaction_time_local' if available
        if df['Date'].isnull().all() and 'transaction_time_local' in df.columns:
             df['Date'] = pd.to_datetime(df['transaction_time_local'], errors='coerce')

        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        # Grubhub Logic: Rows with 'Refund' or 'Cancel' in type are cancellations
        # Grubhub often has a separate row for the order (+) and the refund (-)
        # We mark 'Order' lines as completed, unless they are explicitly marked cancelled
        # Simplification: If type implies positive order, it's completed. If type contains cancel/refund, it's cancelled.
        
        df['Type'] = df['Type'].astype(str).fillna('')
        
        # Identify cancellations/refunds
        df['Is_Cancelled'] = df['Type'].str.contains('Cancel|Refund|Adjustment', case=False)
        
        # Identify valid orders (Marketplace orders)
        # We only want to count the positive revenue lines as "Orders" for the count
        df['Is_Completed'] = (df['Type'] == 'Prepaid Order') | (df['Type'] == 'Marketplace')
        
        # Ensure we don't double count cancellations as completions
        df.loc[df['Is_Cancelled'], 'Is_Completed'] = False

        df['Store'] = df['Store_Name'].fillna('Luckin Coffee')
        df['Platform'] = 'Grubhub'
        
        # Remove rows that are just error adjustments or non-orders if revenue is 0
        df = df[df['Revenue'] != 0]
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Grubhub Parse Error: {str(e)}")
        return pd.DataFrame()

# --- HTML Report Generator (Target Logic) ---

def generate_html_report(df):
    # --- 1. CALCULATIONS ---
    
    # Filter for valid date range to match HTML structure (Month View)
    # For this demo, we use the min/max of uploaded data
    if df.empty:
        return "<div>No Data Uploaded</div>"
        
    # Completed orders only for Revenue/GMV stats
    completed_df = df[df['Is_Completed'] == True].copy()
    
    total_orders = len(completed_df)
    total_gmv = completed_df['Revenue'].sum()
    avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
    
    # Find Peak Day
    if not completed_df.empty:
        daily_stats = completed_df.groupby(completed_df['Date'].dt.date).agg({'Revenue': 'sum', 'Platform': 'count'})
        peak_day = daily_stats['Revenue'].idxmax()
        peak_day_str = peak_day.strftime('%m月%d日')
        peak_day_orders = daily_stats.loc[peak_day, 'Platform']
        peak_day_rev = daily_stats.loc[peak_day, 'Revenue']
    else:
        peak_day_str, peak_day_orders, peak_day_rev = "N/A", 0, 0

    # Cancellation Rate
    total_attempts = len(df)
    cancel_count = len(df[df['Is_Cancelled'] == True])
    cancel_rate = (cancel_count / total_attempts * 100) if total_attempts > 0 else 0

    # Data for Charts
    
    # Trend Chart (X-Axis: Dates, Series: Platforms)
    # Create a full date range to ensure lines align
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    all_dates = pd.date_range(min_date, max_date).date
    date_str_list = [d.strftime('%-m/%-d') for d in all_dates] # e.g. 10/1
    
    def get_platform_daily_counts(plat):
        # Count Is_Completed orders per day
        daily = completed_df[completed_df['Platform'] == plat].groupby(completed_df['Date'].dt.date).size()
        return [int(daily.get(d, 0)) for d in all_dates]

    uber_series = get_platform_daily_counts('Uber Eats')
    dd_series = get_platform_daily_counts('DoorDash')
    gh_series = get_platform_daily_counts('Grubhub')

    # Channel Chart (Pie)
    counts = completed_df['Platform'].value_counts()
    c_uber = int(counts.get('Uber Eats', 0))
    c_dd = int(counts.get('DoorDash', 0))
    c_gh = int(counts.get('Grubhub', 0))
    
    # Channel Table Data (Revenue Share)
    revs = completed_df.groupby('Platform')['Revenue'].sum()
    r_uber = revs.get('Uber Eats', 0)
    r_dd = revs.get('DoorDash', 0)
    r_gh = revs.get('Grubhub', 0)
    
    share_uber = (r_uber / total_gmv * 100) if total_gmv else 0
    share_dd = (r_dd / total_gmv * 100) if total_gmv else 0
    share_gh = (r_gh / total_gmv * 100) if total_gmv else 0

    # Store Chart (Bar - Top 5)
    # Clean store names to match report style (remove "Luckin Coffee" prefix if present)
    completed_df['Simple_Store'] = completed_df['Store'].str.replace('Luckin Coffee', '').str.replace('-', '').str.replace('US\d+', '', regex=True).str.strip()
    # Fallback if name becomes empty
    completed_df.loc[completed_df['Simple_Store'] == '', 'Simple_Store'] = completed_df['Store']
    
    store_stats = completed_df.groupby('Simple_Store')['Revenue'].sum().sort_values(ascending=True)
    store_names = store_stats.index.tolist()
    store_values = [round(v, 2) for v in store_stats.values.tolist()]
    
    top_store_name = store_names[-1] if store_names else "N/A"

    # Time Strings
    report_start = min_date.strftime('%Y年%m月%d日')
    report_end = max_date.strftime('%m月%d日')
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # --- 2. HTML TEMPLATE (Exact Copy of ai_studio_code (3).html with injections) ---
    
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Luckin Analytics Report</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        /* --- Luckin Coffee Brand Theme --- */
        :root {{
            --luckin-blue: #232773; /* Signature Dark Blue */
            --luckin-light-blue: #88C1F4; /* App Accent Blue */
            --luckin-white: #FFFFFF;
            --luckin-gray: #F2F3F5;
            --text-main: #333333;
            --text-sub: #666666;
            --risk-red: #D93025;
            --warning-orange: #F9AB00;
            --success-green: #34A853;
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
            background-color: var(--luckin-gray);
            color: var(--text-main);
            line-height: 1.5;
        }}

        /* --- Header Area --- */
        .header {{
            background-color: var(--luckin-blue);
            color: white;
            padding: 15px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .logo-area {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .actual-logo {{
            height: 55px; 
            width: auto; 
            background-color: white; 
            padding: 2px;
            border-radius: 6px; 
            border: 2px solid rgba(255,255,255,0.3);
        }}
        
        .report-title h1 {{ font-size: 24px; font-weight: 600; letter-spacing: 1px; margin: 0; }}
        .report-info {{ text-align: right; font-size: 12px; opacity: 0.9; }}

        /* --- Main Container --- */
        .container {{
            max-width: 1400px;
            margin: 30px auto;
            padding: 0 20px;
        }}

        /* --- Cards (KPIs) --- */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .kpi-card {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            border-left: 5px solid var(--luckin-blue);
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }}
        .kpi-card:hover {{ transform: translateY(-2px); }}
        .kpi-label {{ color: var(--text-sub); font-size: 14px; margin-bottom: 8px; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; color: var(--luckin-blue); }}
        .kpi-sub {{ font-size: 12px; color: var(--text-sub); margin-top: 5px; }}
        .kpi-trend-up {{ color: var(--success-green); }}
        .kpi-trend-down {{ color: var(--risk-red); }}

        /* --- Sections --- */
        .section {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        }}
        .section-header {{
            border-bottom: 1px solid #eee;
            padding-bottom: 15px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: var(--luckin-blue);
        }}
        
        /* --- Charts --- */
        .chart-container {{ width: 100%; height: 400px; min-height: 400px; }}
        
        /* --- Tables --- */
        .styled-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        .styled-table th {{
            background-color: #f8f9fa;
            color: var(--luckin-blue);
            font-weight: 600;
            text-align: left;
            padding: 12px 15px;
            border-bottom: 2px solid var(--luckin-blue);
        }}
        .styled-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }}
        .styled-table tr:hover {{ background-color: #f1f7ff; }}

        /* --- Status Badges --- */
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-success {{ background: #e6f4ea; color: var(--success-green); }}
        .badge-warning {{ background: #fef7e0; color: var(--warning-orange); }}
        .badge-danger {{ background: #fce8e6; color: var(--risk-red); }}

        /* --- Alert Boxes --- */
        .alert {{
            padding: 15px;
            border-radius: 6px;
            margin-top: 15px;
            border: 1px solid transparent;
        }}
        .alert-danger {{
            background-color: #fce8e6;
            border-color: #fad2cf;
            color: #a50e0e;
        }}
        .alert-info {{
            background-color: #e8f0fe;
            border-color: #d2e3fc;
            color: #174ea6;
        }}

        /* --- Footer --- */
        .footer {{
            text-align: center;
            font-size: 12px;
            color: #999;
            margin-top: 40px;
            padding-bottom: 20px;
        }}
    </style>
</head>
<body>

    <!-- Header -->
    <header class="header">
        <div class="logo-area">
            <img src="luckin_logo.png" alt="Luckin Logo" class="actual-logo" onerror="this.style.display='none';">
            <div class="report-title">
                <h1>瑞幸咖啡 (Luckin Coffee)</h1>
                <div style="font-size: 14px; font-weight: normal; opacity: 0.8;">美国市场运营中心 | US Operations</div>
            </div>
        </div>
        <div class="report-info">
            <div>报告周期: {report_start} - {report_end}</div>
            <div>生成时间: {gen_time}</div>
        </div>
    </header>

    <div class="container">
        
        <!-- 1. 数据概览 KPI -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">本月总订单量 (Orders)</div>
                <div class="kpi-value">{total_orders} <span style="font-size:14px; color:#999;">单</span></div>
                <div class="kpi-sub">日均: ~{int(total_orders/len(all_dates))} 单</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">总营收 (GMV)</div>
                <div class="kpi-value">${total_gmv:,.2f}</div>
                <div class="kpi-sub">平均客单价: ${avg_ticket:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">最高单日销量</div>
                <div class="kpi-value">{peak_day_str}</div>
                <div class="kpi-sub">单日: {peak_day_orders} 单 | 营收: ${peak_day_rev:,.0f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: var(--risk-red);">
                <div class="kpi-label">订单异常/取消率</div>
                <div class="kpi-value" style="color: var(--risk-red);">{cancel_rate:.1f}%</div>
                <div class="kpi-sub">⚠️ 需关注退款问题</div>
            </div>
        </div>

        <!-- 2. 趋势分析 Chart -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">【一、全平台日订单趋势分析】</div>
            </div>
            <div class="chart-container" id="trendChart"></div>
        </div>

        <!-- 3. 渠道与门店分析 Split View -->
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <!-- Channel Mix -->
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
                        <tr>
                            <td>Uber Eats</td>
                            <td>{c_uber}</td>
                            <td><span class="badge badge-success">{share_uber:.1f}%</span></td>
                        </tr>
                        <tr>
                            <td>DoorDash</td>
                            <td>{c_dd}</td>
                            <td>{share_dd:.1f}%</td>
                        </tr>
                        <tr>
                            <td>Grubhub</td>
                            <td>{c_gh}</td>
                            <td>{share_gh:.1f}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Store Performance -->
            <div class="section" style="flex: 1; min-width: 400px;">
                <div class="section-header">
                    <div class="section-title">【三、门店表现 (Store Performance)】</div>
                </div>
                <div class="chart-container" id="storeChart" style="height: 300px; min-height: 300px;"></div>
                <div class="alert alert-info" style="font-size: 13px;">
                    <strong>💡 洞察：</strong> {top_store_name} 贡献了最高外卖营收，是目前的核心主力店。
                </div>
            </div>
        </div>

        <!-- 4. 异常检测 & 风险预警 -->
        <div class="section">
            <div class="section-header">
                <div class="section-title" style="color: var(--risk-red);">【四、异常检测与风险预警 (Risk & Anomaly)】</div>
            </div>
            
            <div class="alert alert-danger">
                <h4>⚠️ 1. 退款/取消率分析</h4>
                <ul style="margin-left: 20px; margin-top: 10px; font-size: 14px;">
                    <li><strong>当前取消率：</strong> {cancel_rate:.1f}%</li>
                    <li><strong>涉及订单：</strong> 共 {cancel_count} 笔订单被标记为取消或退款。</li>
                    <li><strong>建议：</strong> 请检查门店库存同步 (Inventory Sync) 及接单设备连接状态。</li>
                </ul>
            </div>

            <div class="alert alert-info" style="margin-top: 15px; border-color: #bee5eb; background-color: #e2e6ea; color: #333;">
                <h4>⚠️ 2. 平台费率波动 (Grubhub)</h4>
                <p style="font-size: 14px; margin-top: 5px;">
                    建议核对 Grubhub 订单的 "Merchant Service Fee" 是否出现较大波动，确保促销活动配置正确。
                </p>
            </div>
        </div>

        <!-- 5. 运营建议 -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">【五、下阶段运营建议 (Recommendations)】</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">1. 运营优化 (Operations)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;">针对 <strong>Uber Eats</strong> (Top Channel) 优化出餐动线，确保骑手取餐等待时间 < 5分钟，提升平台排名权重。</li>
                        <li style="margin-bottom: 8px;">加强核心门店 ({top_store_name}) 周末时段的人员配置，以应对突发的订单高峰。</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">2. 营销策略 (Marketing)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;"><strong>Grubhub 策略：</strong> 该渠道客单价通常较高。建议推出针对办公人群的 "多人咖啡套餐" (Group Bundle)。</li>
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
            
            // Data Injected from Python
            const dates = {json.dumps(date_str_list)};
            const uberData = {json.dumps(uber_series)};
            const ddData = {json.dumps(dd_series)};
            const ghData = {json.dumps(gh_series)};
            const storeNames = {json.dumps(store_names)};
            const storeVals = {json.dumps(store_values)};

            // Check if ECharts is loaded
            if (typeof echarts === 'undefined') {{
                console.error("ECharts library failed to load. Please check internet connection.");
                return;
            }}

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
                        {{ name: 'Grubhub', type: 'line', smooth: true, data: ghData, itemStyle: {{ color: '#F6FA00' }}, lineStyle: {{ width: 3, color: '#FF8000' }} }} 
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
                            itemStyle: {{
                                borderRadius: 10,
                                borderColor: '#fff',
                                borderWidth: 2
                            }},
                            label: {{ show: false, position: 'center' }},
                            emphasis: {{
                                label: {{ show: true, fontSize: 20, fontWeight: 'bold' }}
                            }},
                            data: [
                                {{ value: {c_uber}, name: 'Uber Eats', itemStyle: {{ color: '#06C167' }} }},
                                {{ value: {c_dd}, name: 'DoorDash', itemStyle: {{ color: '#FF3008' }} }},
                                {{ value: {c_gh}, name: 'Grubhub', itemStyle: {{ color: '#FF8000' }} }}
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
        
        st.subheader("📊 Analysis Report")
        # Display HTML with height matching content
        st.components.v1.html(html_report, height=1400, scrolling=True)
        
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
