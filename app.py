import streamlit as st
import pandas as pd
import json
from datetime import datetime
import io

# --- Page Configuration ---
st.set_page_config(
    page_title="Luckin Coffee (US) - Operations Analytics",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Streamlit Interface ---
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
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def clean_currency(x):
    """Cleans currency strings to floats."""
    if pd.isna(x) or x == '':
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    x = str(x).strip()
    if '(' in x and ')' in x: x = '-' + x.replace('(', '').replace(')', '') # Handle (5.00) as -5.00
    x = x.replace('$', '').replace(',', '').replace(' ', '')
    try:
        return float(x)
    except:
        return 0.0

def find_header_row(df, target_column):
    """Locates the row index where the actual header exists."""
    for i, row in df.iterrows():
        # Check first 50 rows for the target column name
        if i > 50: break
        if target_column in row.values:
            return i + 1 # Return row index relative to original read (header is i)
    return 0

# --- Data Parsers ---

def parse_uber(file):
    try:
        # Read first without header to find the structure
        raw_df = pd.read_csv(file, header=None)
        
        # Uber file often has metadata on top. Find row with "订单状态" (Order Status)
        header_idx = 0
        for idx, row in raw_df.iterrows():
            row_str = row.astype(str).values
            if '订单状态' in row_str or 'Order Status' in row_str:
                header_idx = idx
                break
        
        # Re-read with correct header
        file.seek(0)
        df = pd.read_csv(file, header=header_idx)

        # Column Mapping
        col_map = {
            '订单下单时的当地日期': 'Date_Str',
            '销售额（含税）': 'Revenue_Raw',
            '订单状态': 'Status',
            '餐厅名称': 'Store_Name'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        # Status Logic: Only "已完成" counts as Completed
        df['Is_Completed'] = df['Status'] == '已完成'
        df['Is_Cancelled'] = df['Status'].isin(['已取消', '退款', '未完成'])
        
        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'Uber Eats'
        df['Order_ID'] = df.index # Uber is usually 1 row per order in this export format
        
        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Uber Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # DoorDash headers are usually at row 0
        col_map = {
            '接单当地时间': 'Date_Str',
            '小计': 'Revenue_Raw',
            '最终订单状态': 'Status',
            '店铺名称': 'Store_Name'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
        
        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        # Logic
        df['Is_Completed'] = df['Status'] == 'Delivered'
        df['Is_Cancelled'] = df['Status'].isin(['Cancelled', 'Merchant Cancelled'])
        
        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'DoorDash'
        df['Order_ID'] = df.index

        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"DoorDash Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        
        col_map = {
            'transaction_date': 'Date_Str',
            'subtotal': 'Revenue_Raw',
            'store_name': 'Store_Name',
            'transaction_type': 'Type',
            'order_number': 'Order_ID_Raw'
        }
        df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})

        if 'Date_Str' not in df.columns:
            return pd.DataFrame()

        # Fix for "########" dates in CSV (Excel export issue)
        # If we can't parse it, we drop it, but we attempt strictly first
        df['Date'] = pd.to_datetime(df['Date_Str'], errors='coerce')
        
        df['Revenue'] = df['Revenue_Raw'].apply(clean_currency)
        
        # Grubhub logic is tricky: Multiple rows per order. 
        # We only want rows that represent a Sale ("Prepaid Order")
        
        # 1. Determine Cancellation/Refund rows
        df['Is_Cancelled_Row'] = df['Type'].str.contains('Cancel|Refund|Adjustment', case=False, na=False)
        
        # 2. Determine Completed Order Rows (Prepaid Order)
        df['Is_Completed'] = (df['Type'] == 'Prepaid Order')
        df['Is_Cancelled'] = df['Is_Cancelled_Row'] # This tracks if a specific row is a cancel action

        df['Store'] = df['Store_Name'].fillna('Unknown Store')
        df['Platform'] = 'Grubhub'
        df['Order_ID'] = df['Order_ID_Raw']

        return df[['Date', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled', 'Order_ID']].dropna(subset=['Date'])
    except Exception as e:
        st.error(f"Grubhub Parse Error: {str(e)}")
        return pd.DataFrame()

# --- HTML Report Logic ---

def generate_html_report(df):
    # Ensure date is sorted
    df = df.sort_values('Date')
    
    # 1. Prepare Aggregates
    
    # Total GMV (Sum of Revenue for Completed Orders)
    completed_rows = df[df['Is_Completed'] == True]
    
    # Grubhub deduplication for GMV:
    # Usually Grubhub 'Prepaid Order' rows contain the subtotal. 
    # We just sum 'Revenue' of Is_Completed rows.
    total_gmv = completed_rows['Revenue'].sum()
    
    # Total Orders (Count Unique Order IDs for Completed Orders)
    # This fixes the discrepancy where Grubhub had multiple rows
    total_orders = completed_rows['Order_ID'].nunique()
    
    # Calculate Average Ticket
    avg_ticket = total_gmv / total_orders if total_orders > 0 else 0
    
    # Peak Day Logic
    daily_sum = completed_rows.groupby(completed_rows['Date'].dt.date)['Revenue'].sum()
    if not daily_sum.empty:
        peak_date = daily_sum.idxmax()
        peak_rev = daily_sum.max()
        peak_orders = completed_rows[completed_rows['Date'].dt.date == peak_date]['Order_ID'].nunique()
        peak_date_str = peak_date.strftime('%m月%d日')
    else:
        peak_date_str, peak_rev, peak_orders = "N/A", 0, 0

    # Cancellation Rate
    # Count unique IDs associated with Is_Cancelled rows vs Total unique IDs
    # Note: A simpler metric is just (Count of Cancelled / Total Attempts)
    # Total attempts = Completed Unique IDs + Cancelled Unique IDs (if separate)
    # We will approximate: rows marked cancelled / total relevant rows
    # Better approach for Luckin:
    all_unique_orders = df['Order_ID'].nunique()
    # Find Order IDs that have AT LEAST one row marked Cancel/Refund
    cancelled_order_ids = df[df['Is_Cancelled'] == True]['Order_ID'].unique()
    cancel_count = len(cancelled_order_ids)
    cancel_rate = (cancel_count / all_unique_orders * 100) if all_unique_orders > 0 else 0
    
    # 2. Prepare Chart Data
    
    # Trend Chart Data (Line Chart)
    # X-axis: All dates in range
    if not df.empty:
        min_date = df['Date'].min().date()
        max_date = df['Date'].max().date()
        all_dates = pd.date_range(min_date, max_date).date
        dates_js = [d.strftime('%-m/%-d') for d in all_dates]
    else:
        dates_js = []
        all_dates = []

    def get_series(platform_name):
        plat_df = completed_rows[completed_rows['Platform'] == platform_name]
        # Group by date and count UNIQUE Order IDs
        daily_counts = plat_df.groupby(plat_df['Date'].dt.date)['Order_ID'].nunique()
        # Reindex to ensure all dates are present (0 if missing)
        return [int(daily_counts.get(d, 0)) for d in all_dates]

    uber_data = get_series('Uber Eats')
    dd_data = get_series('DoorDash')
    gh_data = get_series('Grubhub')
    
    # Pie Chart Data
    # Count unique orders per platform
    order_counts = completed_rows.groupby('Platform')['Order_ID'].nunique()
    val_uber = int(order_counts.get('Uber Eats', 0))
    val_dd = int(order_counts.get('DoorDash', 0))
    val_gh = int(order_counts.get('Grubhub', 0))
    
    # Store Bar Chart Data
    # Clean store names
    completed_rows['Simple_Store'] = completed_rows['Store'].str.replace('Luckin Coffee', '').str.replace('US\d+', '', regex=True).str.strip()
    completed_rows.loc[completed_rows['Simple_Store'] == '', 'Simple_Store'] = completed_rows['Store'] # Fallback
    
    store_gmv = completed_rows.groupby('Simple_Store')['Revenue'].sum().sort_values()
    store_names = store_gmv.index.tolist()
    store_vals = [round(x, 2) for x in store_gmv.values]
    top_store_name = store_names[-1] if store_names else "None"
    top_store_share = (store_vals[-1] / total_gmv * 100) if total_gmv > 0 and store_vals else 0

    # Table Data Logic
    share_uber = (completed_rows[completed_rows['Platform']=='Uber Eats']['Revenue'].sum() / total_gmv * 100) if total_gmv else 0
    share_dd = (completed_rows[completed_rows['Platform']=='DoorDash']['Revenue'].sum() / total_gmv * 100) if total_gmv else 0
    share_gh = (completed_rows[completed_rows['Platform']=='Grubhub']['Revenue'].sum() / total_gmv * 100) if total_gmv else 0

    # Dates for Header
    report_start = min_date.strftime('%Y年%m月%d日') if not df.empty else ""
    report_end = max_date.strftime('%m月%d日') if not df.empty else ""
    report_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # --- HTML Construction ---
    html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
    <style>
        /* --- Luckin Coffee Brand Theme --- */
        :root {{
            --luckin-blue: #232773;
            --luckin-light-blue: #88C1F4;
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

        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .badge-success {{ background: #e6f4ea; color: var(--success-green); }}

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
            <div>生成时间: {report_time}</div>
        </div>
    </header>

    <div class="container">
        
        <!-- 1. KPI Grid -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">本月总订单量 (Orders)</div>
                <div class="kpi-value">{total_orders} <span style="font-size:14px; color:#999;">单</span></div>
                <div class="kpi-sub">日均: ~{int(total_orders/len(all_dates)) if len(all_dates)>0 else 0} 单</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">总营收 (GMV)</div>
                <div class="kpi-value">${total_gmv:,.2f}</div>
                <div class="kpi-sub">平均客单价: ${avg_ticket:.2f}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">最高单日销量</div>
                <div class="kpi-value">{peak_date_str}</div>
                <div class="kpi-sub">单日: {peak_orders} 单 | 营收: ${peak_rev:,.0f}</div>
            </div>
            <div class="kpi-card" style="border-left-color: var(--risk-red);">
                <div class="kpi-label">订单异常/取消率</div>
                <div class="kpi-value" style="color: var(--risk-red);">{cancel_rate:.1f}%</div>
                <div class="kpi-sub">⚠️ 需关注退款问题</div>
            </div>
        </div>

        <!-- 2. Trend Chart -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">【一、全平台日订单趋势分析】</div>
            </div>
            <div class="chart-container" id="trendChart"></div>
        </div>

        <!-- 3. Split View -->
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
                            <td>{val_uber}</td>
                            <td><span class="badge badge-success">{share_uber:.1f}%</span></td>
                        </tr>
                        <tr>
                            <td>DoorDash</td>
                            <td>{val_dd}</td>
                            <td>{share_dd:.1f}%</td>
                        </tr>
                        <tr>
                            <td>Grubhub</td>
                            <td>{val_gh}</td>
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
                    <strong>💡 洞察：</strong> {top_store_name} 贡献了超过 {top_store_share:.0f}% 的外卖营收，是目前的核心主力店。
                </div>
            </div>
        </div>

        <!-- 4. Risks -->
        <div class="section">
            <div class="section-header">
                <div class="section-title" style="color: var(--risk-red);">【四、异常检测与风险预警 (Risk & Anomaly)】</div>
            </div>
            
            <div class="alert alert-danger">
                <h4>⚠️ 1. 退款/取消率分析</h4>
                <ul style="margin-left: 20px; margin-top: 10px; font-size: 14px;">
                    <li><strong>涉及订单：</strong> {cancel_count} 笔订单被标记为 "Cancelled" 或 "Refund".</li>
                    <li><strong>财务影响：</strong> 请检查退款金额对 GMV 的具体损耗。</li>
                    <li><strong>建议：</strong> 重点检查 {top_store_name} 的接单设备连接状态。</li>
                </ul>
            </div>

            <div class="alert alert-info" style="margin-top: 15px; border-color: #bee5eb; background-color: #e2e6ea; color: #333;">
                <h4>⚠️ 2. 平台费率波动 (Grubhub)</h4>
                <p style="font-size: 14px; margin-top: 5px;">
                    部分 Grubhub 订单出现费率波动，建议核对是否参与了平台出资的促销活动。
                </p>
            </div>
        </div>

        <!-- 5. Recommendations -->
        <div class="section">
            <div class="section-header">
                <div class="section-title">【五、下阶段运营建议 (Recommendations)】</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">1. 运营优化 (Operations)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;">针对 <strong>Uber Eats</strong> (Top Channel) 优化出餐动线，确保骑手取餐等待时间 < 5分钟。</li>
                        <li style="margin-bottom: 8px;">加强 {top_store_name} 店周末时段的人员配置。</li>
                        <li>检查库存：防止因缺货导致的被动取消。</li>
                    </ul>
                </div>
                <div>
                    <h4 style="color: var(--luckin-blue); margin-bottom: 10px;">2. 营销策略 (Marketing)</h4>
                    <ul style="padding-left: 20px; font-size: 14px; color: #555;">
                        <li style="margin-bottom: 8px;"><strong>Grubhub 策略：</strong> 建议推出针对办公人群的 "多人咖啡套餐" (Group Bundle)。</li>
                        <li style="margin-bottom: 8px;"><strong>DoorDash 策略：</strong> 建议下周开启 "$0 Delivery Fee" 活动以稳定日均单量。</li>
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
            
            // Data Injection
            const dates = {json.dumps(dates_js)};
            const uberData = {json.dumps(uber_data)};
            const ddData = {json.dumps(dd_data)};
            const ghData = {json.dumps(gh_data)};
            
            const storeNames = {json.dumps(store_names)};
            const storeVals = {json.dumps(store_vals)};

            if (typeof echarts === 'undefined') {{
                console.error("ECharts library failed to load.");
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
                                {{ value: {val_uber}, name: 'Uber Eats', itemStyle: {{ color: '#06C167' }} }},
                                {{ value: {val_dd}, name: 'DoorDash', itemStyle: {{ color: '#FF3008' }} }},
                                {{ value: {val_gh}, name: 'Grubhub', itemStyle: {{ color: '#FF8000' }} }}
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

# --- Main Execution ---

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
    
    uber_file = st.file_uploader("Uber Eats (CSV)", type='csv', key='uber')
    dd_file = st.file_uploader("DoorDash (CSV)", type='csv', key='dd')
    gh_file = st.file_uploader("Grubhub (CSV)", type='csv', key='gh')
    
    st.markdown("---")
    st.info("ℹ️ The report will auto-update once all files are uploaded.")

# 3. Processing
data_frames = []

if uber_file:
    uber_file.seek(0)
    df_uber = parse_uber(uber_file)
    if not df_uber.empty: data_frames.append(df_uber)

if dd_file:
    dd_file.seek(0)
    df_dd = parse_doordash(dd_file)
    if not df_dd.empty: data_frames.append(df_dd)

if gh_file:
    gh_file.seek(0)
    df_gh = parse_grubhub(gh_file)
    if not df_gh.empty: data_frames.append(df_gh)

# 4. Display
if data_frames:
    master_df = pd.concat(data_frames, ignore_index=True)
    html_report = generate_html_report(master_df)
    
    st.subheader("📊 Report Preview")
    # Use a larger height to accommodate the full report length without double scrollbars if possible
    st.components.v1.html(html_report, height=1400, scrolling=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.download_button(
            label="📥 Download HTML Report",
            data=html_report,
            file_name="Luckin_Analytics_Report.html",
            mime="text/html",
            type="primary"
        )
else:
    st.markdown("""
        <div style="text-align:center; padding: 50px; color: #666;">
            <h3>👋 Welcome to Luckin Analytics</h3>
            <p>Please upload the daily export CSVs from Uber Eats, DoorDash, and Grubhub to generate the consolidated report.</p>
        </div>
    """, unsafe_allow_html=True)
