import pandas as pd
import streamlit as st
import plotly.express as px
import random
import requests
import re
from datetime import datetime

# --- Function 1: Load Historical Baseline ---
@st.cache_data
def load_historical_data():
    try:
        demand_df = pd.read_csv("data/demand_2023.csv", skiprows=3)
        price_df = pd.read_csv("data/price_2023.csv", skiprows=3)

        demand_df.columns = demand_df.columns.str.strip()
        price_df.columns = price_df.columns.str.strip()
        hoep_col = [col for col in price_df.columns if 'HOEP' in col][0]

        demand_cols = ['Date', 'Hour', 'Ontario Demand']
        price_cols = ['Date', 'Hour', hoep_col]
        
        demand_df = demand_df[demand_cols]
        price_df = price_df[price_cols]

        price_df.rename(columns={hoep_col: 'HOEP'}, inplace=True)
        df = pd.merge(demand_df, price_df, on=['Date', 'Hour'])

        df['Hour_Zero_Indexed'] = df['Hour'] - 1
        df['Datetime'] = pd.to_datetime(df['Date']) + pd.to_timedelta(df['Hour_Zero_Indexed'], unit='h')
        
        df.drop(columns=['Hour_Zero_Indexed'], inplace=True)
        df.dropna(inplace=True)

        return df

    except Exception as e:
        return None

# --- Function 2: The Modern XML Live Engine ---
def get_current_grid_status(historical_df):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        # 1. FETCH LIVE DEMAND (Secure XML)
        demand_url = 'https://reports-public.ieso.ca/public/RealtimeTotals/PUB_RealtimeTotals.xml'
        demand_res = requests.get(demand_url, headers=headers, timeout=5)
        
        if demand_res.status_code == 200:
            # Laser-targeted Regex based on exact IESO XML structure
            demand_matches = re.findall(r'<MarketQuantity>ONTARIO DEMAND</MarketQuantity>\s*<EnergyMW>([0-9\.]+)</EnergyMW>', demand_res.text, re.IGNORECASE)
            
            if demand_matches:
                # Grab the last match in the file (the most recent 5-minute interval)
                current_demand = float(demand_matches[-1])
                current_hour = datetime.now().hour + 1
                
                # 2. FETCH LIVE PRICE (Secure XML)
                price_url = 'https://reports-public.ieso.ca/public/DispUnconsHOEP/PUB_DispUnconsHOEP.xml'
                price_res = requests.get(price_url, headers=headers, timeout=5)
                
                if price_res.status_code == 200:
                    price_matches = re.findall(r'<.*?HOEP>([0-9\.\-]+)</.*?HOEP>', price_res.text, re.IGNORECASE)
                    if price_matches:
                        current_price = float(price_matches[-1])
                    else:
                        current_price = historical_df[historical_df['Hour'] == current_hour].sample(1).iloc[0]['HOEP'] * random.uniform(0.95, 1.10)
                else:
                    current_price = historical_df[historical_df['Hour'] == current_hour].sample(1).iloc[0]['HOEP'] * random.uniform(0.95, 1.10)

                return current_demand, current_price, current_hour, "🟢 LIVE IESO API (Secure XML)"
                
    except Exception as e:
        pass # Move to fallback

    # 3. FALLBACK: SIMULATE DATA (If API is offline)
    try:
        current_hour_zero_index = datetime.now().hour
        current_hour_ieso = current_hour_zero_index + 1

        hour_data = historical_df[historical_df['Hour'] == current_hour_ieso]
        scenario = hour_data.sample(1).iloc[0]
        
        sim_demand = scenario['Ontario Demand'] * random.uniform(0.98, 1.02)
        sim_price = scenario['HOEP'] * random.uniform(0.95, 1.10)

        return sim_demand, sim_price, current_hour_ieso, "🟠 SIMULATED FALLBACK (API OFFLINE)"
        
    except Exception as e:
        return None, None, None, "🔴 ERROR"

# --- DASHBOARD UI ---
st.set_page_config(page_title="Grid Dashboard", layout="wide")
st.title("⚡ Ontario Grid Stress & Market Pricing Dashboard")

historical_data = load_historical_data()

# --- 🔴 LIVE OPERATIONS SECTION ---
st.header("🔴 Live Grid Operations")

if historical_data is not None:
    current_demand, current_price, current_hour, data_source_flag = get_current_grid_status(historical_data)

    if current_demand is not None:
        st.caption(f"**Data Source Status:** {data_source_flag}")

        if current_demand > 22000:
            risk_level = "HIGH RISK (Outage Warning)"
            st.error(f"⚠️ **{risk_level}**: Grid is severely constrained. Demand Response deployment recommended.")
        elif current_demand > 18000:
            risk_level = "ELEVATED (Grid Stress)"
            st.warning(f"⚡ **{risk_level}**: Approaching peak capacity. High market prices expected.")
        else:
            risk_level = "NORMAL (Low Risk)"
            st.success(f"✅ **{risk_level}**: Sufficient generation capacity available.")

        live_col1, live_col2, live_col3 = st.columns(3)
        live_col1.metric("Current Demand", f"{current_demand:,.0f} MW", f"Hour {current_hour}")
        live_col2.metric("Current Price", f"${current_price:,.2f}/MWh")
        live_col3.metric("System Outage Risk Score", risk_level)

st.divider()

# --- 📊 HISTORICAL BASELINE SECTION ---
st.header("📊 System Pattern Analysis (Historical Baseline)")

if historical_data is not None:
    col1, col2, col3 = st.columns(3)
    
    max_demand = historical_data['Ontario Demand'].max()
    max_price = historical_data['HOEP'].max()
    avg_price = historical_data['HOEP'].mean()
    
    col1.metric("2023 Peak Demand (MW)", f"{max_demand:,.0f}")
    col2.metric("2023 Max Hourly Price", f"${max_price:,.2f}/MWh")
    col3.metric("2023 Average Price", f"${avg_price:,.2f}/MWh")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("1. Average Daily Load Profile")
        avg_hourly_load = historical_data.groupby('Hour')['Ontario Demand'].mean().reset_index()
        fig_load = px.line(avg_hourly_load, x='Hour', y='Ontario Demand', markers=True)
        st.plotly_chart(fig_load, use_container_width=True)

    with chart_col2:
        st.subheader("2. Market Price Volatility")
        fig_price = px.scatter(historical_data, x='Ontario Demand', y='HOEP', 
                               opacity=0.3, color='HOEP', color_continuous_scale="Reds")
        st.plotly_chart(fig_price, use_container_width=True)