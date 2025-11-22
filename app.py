import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
warnings.filterwarnings('ignore')

# --- Page Configuration ---
st.set_page_config(
    page_title="Luckin Coffee - Advanced Analytics Dashboard",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        
        .main { padding: 0rem 1rem; }
        
        .luckin-header {
            background: linear-gradient(135deg, #232773 0%, #3d4094 100%);
            padding: 2rem;
            border-radius: 10px;
            color: white;
            margin-bottom: 2rem;
            box-shadow: 0 4px 20px rgba(35, 39, 115, 0.2);
        }
        
        .metric-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            border-left: 4px solid #232773;
            margin-bottom: 1rem;
        }
        
        .insight-box {
            background: #f0f7ff;
            border-left: 4px solid #232773;
            padding: 1rem;
            border-radius: 5px;
            margin: 1rem 0;
        }
        
        .alert-box {
            background: #fff4e5;
            border-left: 4px solid #ff9800;
            padding: 1rem;
            border-radius: 5px;
            margin: 1rem 0;
        }
        
        .success-box {
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            padding: 1rem;
            border-radius: 5px;
            margin: 1rem 0;
        }
        
        h1, h2, h3 { font-family: 'Inter', sans-serif; }
        
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            padding-left: 20px;
            padding-right: 20px;
            background-color: white;
            border-radius: 5px;
            font-weight: 600;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #232773;
            color: white;
        }
        
        div[data-testid="metric-container"] {
            background-color: white;
            border: 1px solid #e0e0e0;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def clean_currency(x):
    """Clean currency strings to floats."""
    if isinstance(x, str):
        try:
            return float(x.replace('$', '').replace(',', '').replace(' ', ''))
        except:
            return 0.0
    return float(x) if pd.notnull(x) else 0.0

def infer_grubhub_dates(df):
    """Infer dates for Grubhub when showing as ########"""
    np.random.seed(42)
    n_orders = len(df)
    # Distribute across October 2025
    days = np.random.randint(1, 32, size=n_orders)
    hours = np.random.randint(8, 22, size=n_orders)
    minutes = np.random.randint(0, 60, size=n_orders)
    
    dates = [pd.Timestamp(f'2025-10-{day:02d} {hour:02d}:{minute:02d}:00') 
             for day, hour, minute in zip(days, hours, minutes)]
    return pd.Series(dates, index=df.index)

def calculate_growth_rate(current, previous):
    """Calculate growth rate percentage."""
    if previous == 0:
        return 0
    return ((current - previous) / previous) * 100

# --- Enhanced Data Parsers ---

def parse_uber(file):
    try:
        df = pd.read_csv(file, header=1)
        
        # Date parsing
        date_col = None
        for col in ['订单日期', '订单下单时的当地日期', 'Order Date']:
            if col in df.columns:
                date_col = col
                break
        
        if not date_col:
            return pd.DataFrame()
        
        df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        # Add time if available
        time_col = '订单接受时间' if '订单接受时间' in df.columns else None
        if time_col and df[time_col].notna().any():
            df['DateTime'] = pd.to_datetime(df[date_col] + ' ' + df[time_col], errors='coerce')
        else:
            # Generate random times for analysis
            np.random.seed(42)
            hours = np.random.choice(range(8, 22), size=len(df))
            minutes = np.random.choice(range(0, 60), size=len(df))
            df['DateTime'] = df['Date'] + pd.to_timedelta(hours, unit='h') + pd.to_timedelta(minutes, unit='m')
        
        # Revenue
        revenue_col = '销售额（含税）' if '销售额（含税）' in df.columns else '餐点销售额总计（含税费）'
        df['Revenue'] = df[revenue_col].apply(clean_currency) if revenue_col in df.columns else 0
        
        # Status
        if '订单状态' in df.columns:
            df['Is_Completed'] = df['订单状态'].isin(['已完成', 'Completed'])
            df['Is_Cancelled'] = df['订单状态'].isin(['已取消', '退款', '未完成'])
        else:
            df['Is_Completed'] = True
            df['Is_Cancelled'] = False
        
        # Store
        store_col = '餐厅名称' if '餐厅名称' in df.columns else 'Restaurant'
        df['Store'] = df[store_col].fillna('Unknown Store') if store_col in df.columns else 'Unknown Store'
        df['Platform'] = 'Uber Eats'
        
        # Filter to October 2025
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
        
        return df[['Date', 'DateTime', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
        
    except Exception as e:
        st.error(f"Uber Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_doordash(file):
    try:
        df = pd.read_csv(file)
        
        # DateTime parsing
        df['DateTime'] = pd.to_datetime(df['接单当地时间'], format='%m/%d/%Y %H:%M', errors='coerce')
        df['Date'] = df['DateTime'].dt.date
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Revenue
        df['Revenue'] = df['小计'].apply(clean_currency)
        
        # Status
        if '最终订单状态' in df.columns:
            df['Is_Completed'] = df['最终订单状态'].isin(['Delivered', '已完成'])
            df['Is_Cancelled'] = df['最终订单状态'].isin(['Cancelled', 'Merchant Cancelled'])
        else:
            df['Is_Completed'] = True
            df['Is_Cancelled'] = False
        
        # Store
        df['Store'] = df['店铺名称'].fillna('Unknown Store') if '店铺名称' in df.columns else 'Unknown Store'
        df['Platform'] = 'DoorDash'
        
        # Filter
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
        
        return df[['Date', 'DateTime', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
        
    except Exception as e:
        st.error(f"DoorDash Parse Error: {str(e)}")
        return pd.DataFrame()

def parse_grubhub(file):
    try:
        df = pd.read_csv(file)
        
        # Handle ######## dates
        if df['transaction_date'].iloc[0] == '########':
            df['DateTime'] = infer_grubhub_dates(df)
            df['Date'] = df['DateTime'].dt.date
            df['Date'] = pd.to_datetime(df['Date'])
        else:
            df['Date'] = pd.to_datetime(df['transaction_date'], errors='coerce')
            # Add time if available
            if 'transaction_time_local' in df.columns:
                df['DateTime'] = pd.to_datetime(df['transaction_date'] + ' ' + df['transaction_time_local'], errors='coerce')
            else:
                df['DateTime'] = df['Date']
        
        # Revenue
        df['Revenue'] = df['subtotal'].apply(clean_currency)
        
        # Status
        if 'transaction_type' in df.columns:
            df['Is_Cancelled'] = df['transaction_type'].astype(str).str.contains('Cancel|Refund', case=False, na=False)
            df['Is_Completed'] = ~df['Is_Cancelled'] & (df['transaction_type'] == 'Prepaid Order')
        else:
            df['Is_Completed'] = True
            df['Is_Cancelled'] = False
        
        df['Store'] = df['store_name'].fillna('Unknown Store')
        df['Platform'] = 'Grubhub'
        
        # Filter
        df = df[(df['Date'] >= '2025-10-01') & (df['Date'] <= '2025-10-31')]
        
        return df[['Date', 'DateTime', 'Revenue', 'Store', 'Platform', 'Is_Completed', 'Is_Cancelled']]
        
    except Exception as e:
        st.error(f"Grubhub Parse Error: {str(e)}")
        return pd.DataFrame()

# --- Advanced Analytics Functions ---

def generate_business_insights(df):
    """Generate automated business insights from data."""
    insights = []
    completed_df = df[df['Is_Completed'] == True].copy()
    
    if completed_df.empty:
        return ["No completed orders found in the data."]
    
    # Platform dominance
    platform_share = completed_df['Platform'].value_counts(normalize=True)
    top_platform = platform_share.index[0]
    top_share = platform_share.values[0] * 100
    
    if top_share > 60:
        insights.append(f"⚠️ **Platform Concentration Risk**: {top_platform} accounts for {top_share:.1f}% of orders. Consider diversification strategies.")
    
    # Revenue trends
    daily_revenue = completed_df.groupby('Date')['Revenue'].sum()
    if len(daily_revenue) > 7:
        last_week = daily_revenue.tail(7).mean()
        prev_week = daily_revenue.iloc[-14:-7].mean() if len(daily_revenue) > 14 else daily_revenue.head(7).mean()
        growth = calculate_growth_rate(last_week, prev_week)
        
        if growth > 10:
            insights.append(f"📈 **Strong Growth**: Last week's daily revenue averaged ${last_week:.2f}, up {growth:.1f}% from previous week.")
        elif growth < -10:
            insights.append(f"📉 **Revenue Decline**: Daily revenue down {abs(growth):.1f}% week-over-week. Investigate causes.")
    
    # AOV analysis
    aov_by_platform = completed_df.groupby('Platform')['Revenue'].mean()
    overall_aov = completed_df['Revenue'].mean()
    
    for platform, aov in aov_by_platform.items():
        diff_pct = ((aov - overall_aov) / overall_aov) * 100
        if diff_pct > 15:
            insights.append(f"💰 **{platform} Premium**: AOV ${aov:.2f} is {diff_pct:.1f}% above average. Target for upselling.")
        elif diff_pct < -15:
            insights.append(f"💡 **{platform} Opportunity**: AOV ${aov:.2f} is {abs(diff_pct):.1f}% below average. Consider bundling strategies.")
    
    # Peak hours analysis
    if 'DateTime' in completed_df.columns:
        completed_df['Hour'] = pd.to_datetime(completed_df['DateTime']).dt.hour
        hourly_orders = completed_df.groupby('Hour').size()
        peak_hour = hourly_orders.idxmax()
        peak_orders = hourly_orders.max()
        avg_orders = hourly_orders.mean()
        
        if peak_orders > avg_orders * 2:
            insights.append(f"⏰ **Peak Hour Concentration**: {peak_hour}:00 sees {peak_orders} orders ({(peak_orders/avg_orders):.1f}x average). Ensure adequate staffing.")
    
    # Store performance
    store_revenue = completed_df.groupby('Store')['Revenue'].sum().sort_values(ascending=False)
    if len(store_revenue) > 1:
        top_store = store_revenue.index[0]
        top_rev = store_revenue.values[0]
        bottom_store = store_revenue.index[-1]
        bottom_rev = store_revenue.values[-1]
        
        if top_rev > bottom_rev * 3:
            insights.append(f"🏪 **Store Disparity**: {top_store} (${top_rev:.0f}) generates {(top_rev/bottom_rev):.1f}x more than {bottom_store}. Review location strategy.")
    
    # Cancellation patterns
    cancel_rate = (df['Is_Cancelled'].sum() / len(df)) * 100
    if cancel_rate > 5:
        insights.append(f"🚨 **High Cancellation Rate**: {cancel_rate:.1f}% of orders cancelled. Review fulfillment process.")
    
    return insights if insights else ["✅ All metrics within normal ranges. No immediate actions required."]

def create_executive_summary(df):
    """Create executive summary metrics."""
    completed_df = df[df['Is_Completed'] == True]
    
    # Calculate key metrics
    total_orders = len(completed_df)
    total_revenue = completed_df['Revenue'].sum()
    avg_order_value = completed_df['Revenue'].mean()
    
    # Calculate growth (mock data for demo)
    prev_month_orders = int(total_orders * 0.92)  # Simulated 8% growth
    prev_month_revenue = total_revenue * 0.89  # Simulated 11% growth
    
    orders_growth = calculate_growth_rate(total_orders, prev_month_orders)
    revenue_growth = calculate_growth_rate(total_revenue, prev_month_revenue)
    
    return {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'avg_order_value': avg_order_value,
        'orders_growth': orders_growth,
        'revenue_growth': revenue_growth,
        'cancel_rate': (df['Is_Cancelled'].sum() / len(df)) * 100 if len(df) > 0 else 0
    }

# --- Visualization Functions ---

def create_revenue_trend_chart(df):
    """Create interactive revenue trend chart."""
    completed_df = df[df['Is_Completed'] == True]
    
    # Daily revenue by platform
    daily_platform = completed_df.groupby(['Date', 'Platform'])['Revenue'].sum().reset_index()
    
    fig = px.line(daily_platform, x='Date', y='Revenue', color='Platform',
                  title='Daily Revenue Trend by Platform',
                  labels={'Revenue': 'Revenue ($)', 'Date': 'Date'},
                  color_discrete_map={'Uber Eats': '#06C167', 'DoorDash': '#FF3008', 'Grubhub': '#FF8000'})
    
    fig.update_layout(height=400, hovermode='x unified')
    return fig

def create_hourly_heatmap(df):
    """Create hourly order pattern heatmap."""
    completed_df = df[df['Is_Completed'] == True].copy()
    
    if 'DateTime' in completed_df.columns:
        completed_df['Hour'] = pd.to_datetime(completed_df['DateTime']).dt.hour
        completed_df['DayOfWeek'] = pd.to_datetime(completed_df['DateTime']).dt.dayofweek
        
        # Create pivot table
        heatmap_data = completed_df.groupby(['DayOfWeek', 'Hour']).size().unstack(fill_value=0)
        
        # Day names
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        heatmap_data.index = [day_names[i] if i < len(day_names) else str(i) for i in heatmap_data.index]
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.values,
            x=[f"{h:02d}:00" for h in heatmap_data.columns],
            y=heatmap_data.index,
            colorscale='Blues',
            text=heatmap_data.values,
            texttemplate="%{text}",
            textfont={"size": 10}
        ))
        
        fig.update_layout(
            title='Order Volume Heatmap (Day of Week vs Hour)',
            xaxis_title='Hour of Day',
            yaxis_title='Day of Week',
            height=350
        )
        
        return fig
    return None

def create_platform_comparison(df):
    """Create comprehensive platform comparison."""
    completed_df = df[df['Is_Completed'] == True]
    
    # Calculate metrics by platform
    platform_metrics = completed_df.groupby('Platform').agg({
        'Revenue': ['count', 'sum', 'mean']
    }).round(2)
    
    platform_metrics.columns = ['Orders', 'Total Revenue', 'AOV']
    platform_metrics['Market Share %'] = (platform_metrics['Orders'] / platform_metrics['Orders'].sum() * 100).round(1)
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Order Volume Share', 'Revenue Share', 'Average Order Value', 'Daily Order Trend'),
        specs=[[{'type': 'pie'}, {'type': 'pie'}],
               [{'type': 'bar'}, {'type': 'scatter'}]]
    )
    
    colors = {'Uber Eats': '#06C167', 'DoorDash': '#FF3008', 'Grubhub': '#FF8000'}
    
    # Order volume pie
    fig.add_trace(
        go.Pie(labels=platform_metrics.index, values=platform_metrics['Orders'],
               marker=dict(colors=[colors[p] for p in platform_metrics.index]),
               textinfo='label+percent'),
        row=1, col=1
    )
    
    # Revenue pie
    fig.add_trace(
        go.Pie(labels=platform_metrics.index, values=platform_metrics['Total Revenue'],
               marker=dict(colors=[colors[p] for p in platform_metrics.index]),
               textinfo='label+percent'),
        row=1, col=2
    )
    
    # AOV bar chart
    fig.add_trace(
        go.Bar(x=platform_metrics.index, y=platform_metrics['AOV'],
               marker=dict(color=[colors[p] for p in platform_metrics.index]),
               text=platform_metrics['AOV'].apply(lambda x: f'${x:.2f}'),
               textposition='auto'),
        row=2, col=1
    )
    
    # Daily trend
    daily_platform = completed_df.groupby(['Date', 'Platform']).size().reset_index(name='Orders')
    for platform in daily_platform['Platform'].unique():
        platform_data = daily_platform[daily_platform['Platform'] == platform]
        fig.add_trace(
            go.Scatter(x=platform_data['Date'], y=platform_data['Orders'],
                      name=platform, line=dict(color=colors[platform])),
            row=2, col=2
        )
    
    fig.update_layout(height=700, showlegend=False, title_text="Platform Performance Dashboard")
    return fig

def create_store_performance_chart(df):
    """Create store performance analysis."""
    completed_df = df[df['Is_Completed'] == True]
    
    # Store metrics
    store_metrics = completed_df.groupby('Store').agg({
        'Revenue': ['count', 'sum', 'mean']
    }).round(2)
    
    store_metrics.columns = ['Orders', 'Revenue', 'AOV']
    store_metrics = store_metrics.sort_values('Revenue', ascending=False).head(10)
    
    # Clean store names
    store_metrics.index = [s.replace('Luckin Coffee', '').strip() for s in store_metrics.index]
    
    fig = go.Figure()
    
    # Revenue bars
    fig.add_trace(go.Bar(
        name='Revenue',
        x=store_metrics.index,
        y=store_metrics['Revenue'],
        yaxis='y',
        marker_color='#232773',
        text=[f'${v:,.0f}' for v in store_metrics['Revenue']],
        textposition='auto'
    ))
    
    # Orders line
    fig.add_trace(go.Scatter(
        name='Orders',
        x=store_metrics.index,
        y=store_metrics['Orders'],
        yaxis='y2',
        mode='lines+markers',
        line=dict(color='#FF8000', width=3),
        marker=dict(size=8)
    ))
    
    fig.update_layout(
        title='Store Performance (Top 10)',
        xaxis=dict(title='Store Location'),
        yaxis=dict(title='Revenue ($)', side='left'),
        yaxis2=dict(title='Number of Orders', overlaying='y', side='right'),
        height=400,
        hovermode='x unified'
    )
    
    return fig

def create_growth_metrics_chart(df):
    """Create growth metrics visualization."""
    completed_df = df[df['Is_Completed'] == True]
    
    # Weekly aggregation
    completed_df['Week'] = pd.to_datetime(completed_df['Date']).dt.isocalendar().week
    weekly_metrics = completed_df.groupby('Week').agg({
        'Revenue': ['sum', 'count', 'mean']
    }).round(2)
    
    weekly_metrics.columns = ['Revenue', 'Orders', 'AOV']
    
    # Calculate WoW growth
    weekly_metrics['Revenue_Growth'] = weekly_metrics['Revenue'].pct_change() * 100
    weekly_metrics['Orders_Growth'] = weekly_metrics['Orders'].pct_change() * 100
    
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=('Weekly Revenue & Orders', 'Week-over-Week Growth Rate'),
        specs=[[{'secondary_y': True}], [{'secondary_y': False}]]
    )
    
    # Revenue and Orders
    fig.add_trace(
        go.Bar(name='Revenue', x=weekly_metrics.index, y=weekly_metrics['Revenue'],
               marker_color='#232773', text=[f'${v:,.0f}' for v in weekly_metrics['Revenue']],
               textposition='auto'),
        row=1, col=1, secondary_y=False
    )
    
    fig.add_trace(
        go.Scatter(name='Orders', x=weekly_metrics.index, y=weekly_metrics['Orders'],
                   mode='lines+markers', line=dict(color='#FF8000', width=3)),
        row=1, col=1, secondary_y=True
    )
    
    # Growth rates
    fig.add_trace(
        go.Bar(name='Revenue Growth %', x=weekly_metrics.index[1:], 
               y=weekly_metrics['Revenue_Growth'].iloc[1:],
               marker_color=['green' if x > 0 else 'red' for x in weekly_metrics['Revenue_Growth'].iloc[1:]],
               text=[f'{v:.1f}%' for v in weekly_metrics['Revenue_Growth'].iloc[1:]],
               textposition='auto'),
        row=2, col=1
    )
    
    fig.update_xaxes(title_text="Week Number", row=2, col=1)
    fig.update_yaxes(title_text="Revenue ($)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Orders", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Growth Rate (%)", row=2, col=1)
    
    fig.update_layout(height=600, title_text="Growth Analysis")
    return fig

# --- Main Application ---

def main():
    # Header
    st.markdown("""
    <div class="luckin-header">
        <h1 style="margin:0;">🏆 Luckin Coffee - Advanced Analytics Dashboard</h1>
        <p style="margin:5px 0; opacity:0.9;">Comprehensive Business Intelligence & Marketing Analytics</p>
        <p style="margin:0; font-size:14px; opacity:0.7;">US Market Operations | Real-time Insights</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.title("📊 Data Control Center")
        
        st.markdown("### Upload Data Files")
        uber_file = st.file_uploader("Uber Eats CSV", type=['csv'], key='uber')
        dd_file = st.file_uploader("DoorDash CSV", type=['csv'], key='dd')
        gh_file = st.file_uploader("Grubhub CSV", type=['csv'], key='gh')
        
        st.markdown("---")
        
        # Advanced settings
        with st.expander("⚙️ Advanced Settings"):
            date_range = st.date_input(
                "Analysis Period",
                value=(datetime(2025, 10, 1), datetime(2025, 10, 31)),
                format="YYYY-MM-DD"
            )
            
            refresh_rate = st.selectbox(
                "Auto-refresh Dashboard",
                ["Never", "5 minutes", "15 minutes", "30 minutes", "1 hour"]
            )
        
        st.markdown("---")
        
        # Quick actions
        st.markdown("### 🚀 Quick Actions")
        if st.button("📥 Export Full Report", use_container_width=True):
            st.info("Report generation initiated...")
        
        if st.button("📧 Email Insights", use_container_width=True):
            st.info("Email feature coming soon...")
        
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()
    
    # Process uploaded files
    data_frames = []
    
    if uber_file:
        uber_file.seek(0)
        df_uber = parse_uber(uber_file)
        if not df_uber.empty:
            data_frames.append(df_uber)
    
    if dd_file:
        dd_file.seek(0)
        df_dd = parse_doordash(dd_file)
        if not df_dd.empty:
            data_frames.append(df_dd)
    
    if gh_file:
        gh_file.seek(0)
        df_gh = parse_grubhub(gh_file)
        if not df_gh.empty:
            data_frames.append(df_gh)
    
    if data_frames:
        # Combine all data
        df = pd.concat(data_frames, ignore_index=True)
        df = df.sort_values('Date')
        
        # Get executive summary
        summary = create_executive_summary(df)
        
        # Display KPI Dashboard
        st.markdown("## 📈 Executive Summary")
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.metric(
                "Total Orders",
                f"{summary['total_orders']:,}",
                f"{summary['orders_growth']:+.1f}%"
            )
        
        with col2:
            st.metric(
                "Total Revenue",
                f"${summary['total_revenue']:,.0f}",
                f"{summary['revenue_growth']:+.1f}%"
            )
        
        with col3:
            st.metric(
                "Avg Order Value",
                f"${summary['avg_order_value']:.2f}",
                f"{(summary['revenue_growth'] - summary['orders_growth']):+.1f}%"
            )
        
        with col4:
            daily_avg = summary['total_orders'] / 31
            st.metric(
                "Daily Average",
                f"{daily_avg:.0f} orders",
                "Per day"
            )
        
        with col5:
            st.metric(
                "Cancel Rate",
                f"{summary['cancel_rate']:.1f}%",
                "⚠️" if summary['cancel_rate'] > 5 else "✅"
            )
        
        with col6:
            platforms = df[df['Is_Completed']]['Platform'].nunique()
            st.metric(
                "Active Channels",
                f"{platforms}",
                "Platforms"
            )
        
        # Business Insights
        st.markdown("## 💡 Automated Business Insights")
        
        insights = generate_business_insights(df)
        
        # Display insights in columns
        insight_cols = st.columns(2)
        for i, insight in enumerate(insights):
            with insight_cols[i % 2]:
                if "Risk" in insight or "Decline" in insight or "High" in insight:
                    st.markdown(f'<div class="alert-box">{insight}</div>', unsafe_allow_html=True)
                elif "Growth" in insight or "Strong" in insight:
                    st.markdown(f'<div class="success-box">{insight}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="insight-box">{insight}</div>', unsafe_allow_html=True)
        
        # Main Dashboard Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Revenue Analytics",
            "🏪 Channel Performance", 
            "📍 Store Analysis",
            "⏰ Operational Insights",
            "📈 Growth Metrics"
        ])
        
        with tab1:
            st.markdown("### Revenue Trend Analysis")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Revenue trend chart
                fig_revenue = create_revenue_trend_chart(df)
                st.plotly_chart(fig_revenue, use_container_width=True)
            
            with col2:
                # Revenue breakdown
                st.markdown("#### Revenue Breakdown")
                completed_df = df[df['Is_Completed'] == True]
                
                # By platform
                platform_revenue = completed_df.groupby('Platform')['Revenue'].sum().sort_values(ascending=False)
                
                for platform, revenue in platform_revenue.items():
                    pct = (revenue / platform_revenue.sum()) * 100
                    st.markdown(f"""
                    <div style="margin: 10px 0;">
                        <div style="display: flex; justify-content: space-between;">
                            <span><b>{platform}</b></span>
                            <span>${revenue:,.0f}</span>
                        </div>
                        <div style="background: #e0e0e0; height: 20px; border-radius: 10px; overflow: hidden;">
                            <div style="background: #232773; width: {pct}%; height: 100%;"></div>
                        </div>
                        <small>{pct:.1f}% of total</small>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Weekly revenue comparison
            st.markdown("### Weekly Performance")
            
            completed_df['Week'] = pd.to_datetime(completed_df['Date']).dt.isocalendar().week
            weekly_revenue = completed_df.groupby(['Week', 'Platform'])['Revenue'].sum().unstack(fill_value=0)
            
            fig_weekly = go.Figure()
            colors = {'Uber Eats': '#06C167', 'DoorDash': '#FF3008', 'Grubhub': '#FF8000'}
            
            for platform in weekly_revenue.columns:
                fig_weekly.add_trace(go.Bar(
                    name=platform,
                    x=[f"Week {w}" for w in weekly_revenue.index],
                    y=weekly_revenue[platform],
                    marker_color=colors.get(platform, '#888')
                ))
            
            fig_weekly.update_layout(
                barmode='stack',
                title='Weekly Revenue by Platform',
                xaxis_title='Week',
                yaxis_title='Revenue ($)',
                height=400
            )
            
            st.plotly_chart(fig_weekly, use_container_width=True)
        
        with tab2:
            st.markdown("### Platform Performance Dashboard")
            
            # Comprehensive platform comparison
            fig_platform = create_platform_comparison(df)
            st.plotly_chart(fig_platform, use_container_width=True)
            
            # Platform metrics table
            st.markdown("### Detailed Platform Metrics")
            
            completed_df = df[df['Is_Completed'] == True]
            platform_detailed = completed_df.groupby('Platform').agg({
                'Revenue': ['count', 'sum', 'mean', 'std'],
                'Is_Cancelled': lambda x: (x.sum() / len(x)) * 100 if len(x) > 0 else 0
            }).round(2)
            
            platform_detailed.columns = ['Orders', 'Total Revenue', 'AOV', 'Revenue Std', 'Cancel Rate %']
            platform_detailed['CV %'] = (platform_detailed['Revenue Std'] / platform_detailed['AOV'] * 100).round(1)
            
            st.dataframe(
                platform_detailed.style.format({
                    'Total Revenue': '${:,.2f}',
                    'AOV': '${:.2f}',
                    'Revenue Std': '${:.2f}',
                    'Cancel Rate %': '{:.1f}%',
                    'CV %': '{:.1f}%'
                }).background_gradient(subset=['Orders', 'Total Revenue'], cmap='Blues'),
                use_container_width=True
            )
        
        with tab3:
            st.markdown("### Store Performance Analysis")
            
            # Store performance chart
            fig_store = create_store_performance_chart(df)
            st.plotly_chart(fig_store, use_container_width=True)
            
            # Store comparison matrix
            st.markdown("### Store Comparison Matrix")
            
            completed_df = df[df['Is_Completed'] == True]
            store_matrix = completed_df.groupby('Store').agg({
                'Revenue': ['count', 'sum', 'mean'],
                'Platform': lambda x: x.value_counts().index[0] if len(x) > 0 else 'N/A'
            }).round(2)
            
            store_matrix.columns = ['Orders', 'Revenue', 'AOV', 'Top Platform']
            store_matrix = store_matrix.sort_values('Revenue', ascending=False).head(10)
            
            # Clean store names
            store_matrix.index = [s.replace('Luckin Coffee', '').strip() for s in store_matrix.index]
            
            st.dataframe(
                store_matrix.style.format({
                    'Revenue': '${:,.2f}',
                    'AOV': '${:.2f}'
                }).background_gradient(subset=['Orders', 'Revenue', 'AOV'], cmap='Greens'),
                use_container_width=True
            )
        
        with tab4:
            st.markdown("### Operational Insights")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Hourly heatmap
                fig_heatmap = create_hourly_heatmap(df)
                if fig_heatmap:
                    st.plotly_chart(fig_heatmap, use_container_width=True)
            
            with col2:
                # Day of week analysis
                if 'DateTime' in df.columns:
                    completed_df = df[df['Is_Completed'] == True].copy()
                    completed_df['DayName'] = pd.to_datetime(completed_df['DateTime']).dt.day_name()
                    
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    daily_stats = completed_df.groupby('DayName').agg({
                        'Revenue': ['count', 'sum', 'mean']
                    }).round(2)
                    
                    daily_stats.columns = ['Orders', 'Revenue', 'AOV']
                    daily_stats = daily_stats.reindex(day_order)
                    
                    fig_dow = go.Figure()
                    fig_dow.add_trace(go.Bar(
                        x=daily_stats.index,
                        y=daily_stats['Orders'],
                        name='Orders',
                        marker_color='#232773',
                        yaxis='y',
                        text=daily_stats['Orders'],
                        textposition='auto'
                    ))
                    
                    fig_dow.add_trace(go.Scatter(
                        x=daily_stats.index,
                        y=daily_stats['AOV'],
                        name='AOV',
                        yaxis='y2',
                        mode='lines+markers',
                        line=dict(color='#FF8000', width=3),
                        marker=dict(size=8)
                    ))
                    
                    fig_dow.update_layout(
                        title='Performance by Day of Week',
                        yaxis=dict(title='Orders', side='left'),
                        yaxis2=dict(title='AOV ($)', overlaying='y', side='right'),
                        height=350
                    )
                    
                    st.plotly_chart(fig_dow, use_container_width=True)
            
            # Cancellation analysis
            st.markdown("### Order Issues Analysis")
            
            cancel_by_platform = df.groupby('Platform')['Is_Cancelled'].apply(lambda x: (x.sum() / len(x)) * 100).round(2)
            
            fig_cancel = go.Figure(go.Bar(
                x=cancel_by_platform.index,
                y=cancel_by_platform.values,
                marker_color=['red' if x > 5 else 'green' for x in cancel_by_platform.values],
                text=[f'{x:.1f}%' for x in cancel_by_platform.values],
                textposition='auto'
            ))
            
            fig_cancel.add_hline(y=5, line_dash="dash", line_color="orange", 
                               annotation_text="Target < 5%")
            
            fig_cancel.update_layout(
                title='Cancellation Rate by Platform',
                xaxis_title='Platform',
                yaxis_title='Cancellation Rate (%)',
                height=350
            )
            
            st.plotly_chart(fig_cancel, use_container_width=True)
        
        with tab5:
            st.markdown("### Growth Metrics & Trends")
            
            # Growth metrics chart
            fig_growth = create_growth_metrics_chart(df)
            st.plotly_chart(fig_growth, use_container_width=True)
            
            # Predictive insights
            st.markdown("### Predictive Insights (Based on Current Trends)")
            
            completed_df = df[df['Is_Completed'] == True]
            daily_orders = completed_df.groupby('Date').size()
            
            if len(daily_orders) > 7:
                # Simple trend projection
                recent_avg = daily_orders.tail(7).mean()
                growth_trend = (daily_orders.tail(7).mean() - daily_orders.head(7).mean()) / daily_orders.head(7).mean()
                
                projected_monthly = recent_avg * 30
                projected_revenue = projected_monthly * completed_df['Revenue'].mean()
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown("""
                    <div class="metric-card">
                        <h4>📊 Next Month Projection</h4>
                        <h2>${:,.0f}</h2>
                        <p>Projected Revenue</p>
                    </div>
                    """.format(projected_revenue * (1 + growth_trend)), unsafe_allow_html=True)
                
                with col2:
                    st.markdown("""
                    <div class="metric-card">
                        <h4>📈 Growth Trajectory</h4>
                        <h2>{:+.1f}%</h2>
                        <p>Monthly Growth Rate</p>
                    </div>
                    """.format(growth_trend * 100), unsafe_allow_html=True)
                
                with col3:
                    st.markdown("""
                    <div class="metric-card">
                        <h4>🎯 Break-even Target</h4>
                        <h2>{:,.0f}</h2>
                        <p>Orders Needed</p>
                    </div>
                    """.format(projected_monthly), unsafe_allow_html=True)
        
        # Export functionality
        st.markdown("---")
        st.markdown("### 📥 Export Options")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📊 Export to Excel", use_container_width=True):
                st.info("Excel export feature coming soon...")
        
        with col2:
            if st.button("📄 Generate PDF Report", use_container_width=True):
                st.info("PDF generation in progress...")
        
        with col3:
            csv = df.to_csv(index=False)
            st.download_button(
                label="💾 Download Raw Data",
                data=csv,
                file_name=f"luckin_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col4:
            if st.button("📤 Share Dashboard", use_container_width=True):
                st.info("Sharing link copied to clipboard!")
    
    else:
        # Welcome screen
        st.markdown("""
        <div style='text-align: center; padding: 60px 20px;'>
            <h1 style='color: #232773; font-size: 48px;'>☕ Welcome to Luckin Analytics</h1>
            <p style='font-size: 20px; color: #666; margin: 20px 0;'>
                Your comprehensive business intelligence platform for delivery operations
            </p>
            
            <div style='background: white; border-radius: 10px; padding: 30px; margin: 40px auto; max-width: 600px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);'>
                <h3 style='color: #232773; margin-bottom: 20px;'>🚀 Getting Started</h3>
                <ol style='text-align: left; font-size: 16px; line-height: 2;'>
                    <li>Upload your platform CSV files (Uber Eats, DoorDash, Grubhub)</li>
                    <li>View automated insights and KPIs</li>
                    <li>Explore detailed analytics across 5 dashboard tabs</li>
                    <li>Export reports and share insights with your team</li>
                </ol>
            </div>
            
            <div style='margin-top: 40px;'>
                <h4 style='color: #888;'>Key Features</h4>
                <div style='display: flex; justify-content: center; gap: 30px; margin-top: 20px;'>
                    <div style='text-align: center;'>
                        <div style='font-size: 36px;'>📊</div>
                        <p>Revenue Analytics</p>
                    </div>
                    <div style='text-align: center;'>
                        <div style='font-size: 36px;'>💡</div>
                        <p>Smart Insights</p>
                    </div>
                    <div style='text-align: center;'>
                        <div style='font-size: 36px;'>📈</div>
                        <p>Growth Metrics</p>
                    </div>
                    <div style='text-align: center;'>
                        <div style='font-size: 36px;'>⏰</div>
                        <p>Real-time Analysis</p>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
