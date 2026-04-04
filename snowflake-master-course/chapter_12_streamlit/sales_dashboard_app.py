"""
Chapter 12: Streamlit in Snowflake – Sales Dashboard
======================================================
Snowflake Master Course
A production-quality Streamlit in Snowflake (SiS) application.

To deploy:
  1. Open Snowsight → Streamlit → + Streamlit App
  2. Paste this file or upload it.
  3. Ensure the active warehouse and database have access to the tables below.

Tables required (adjust database/schema to match your environment):
  ANALYTICS.MARTS.FCT_ORDERS
  ANALYTICS.MARTS.DIM_CUSTOMERS
  ANALYTICS.MARTS.DIM_PRODUCTS
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.functions import col
import pandas as pd
import altair as alt

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Sales Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Get active Snowpark session (provided automatically by Streamlit in Snowflake)
# ---------------------------------------------------------------------------
session = get_active_session()


# ---------------------------------------------------------------------------
# Utility: run a parameterized SQL query safely and return a Pandas DataFrame
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Querying Snowflake...")
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Execute parameterized SQL and return a Pandas DataFrame."""
    try:
        return session.sql(sql, params).to_pandas()
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

# Date range
min_date = pd.to_datetime("2024-01-01").date()
max_date = pd.to_datetime("2024-12-31").date()

date_range = st.sidebar.date_input(
    "Order Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

# Region filter
region_options_df = run_query(
    "SELECT DISTINCT REGION FROM ANALYTICS.MARTS.FCT_ORDERS ORDER BY 1"
)
region_options = ["All"] + region_options_df["REGION"].tolist() if not region_options_df.empty else ["All"]
selected_regions = st.sidebar.multiselect(
    "Region",
    options=region_options[1:],  # exclude "All" from multiselect
    default=[],
    placeholder="All regions",
)

# Product category filter
cat_options_df = run_query(
    "SELECT DISTINCT CATEGORY FROM ANALYTICS.MARTS.DIM_PRODUCTS ORDER BY 1"
)
cat_options = cat_options_df["CATEGORY"].tolist() if not cat_options_df.empty else []
selected_categories = st.sidebar.multiselect(
    "Product Category",
    options=cat_options,
    default=[],
    placeholder="All categories",
)

# Customer segment filter
segment_options = ["Bronze", "Silver", "Gold", "Platinum"]
selected_segments = st.sidebar.multiselect(
    "Customer Segment",
    options=segment_options,
    default=[],
    placeholder="All segments",
)

# Status filter
status_options = ["COMPLETED", "PENDING", "CANCELLED", "REFUNDED"]
selected_statuses = st.sidebar.multiselect(
    "Order Status",
    options=status_options,
    default=["COMPLETED"],
    placeholder="All statuses",
)

# ---------------------------------------------------------------------------
# Build dynamic WHERE clause fragments (safe parameterization)
# ---------------------------------------------------------------------------
where_clauses = [
    f"o.ORDER_DATE BETWEEN '{start_date}' AND '{end_date}'"
]
if selected_regions:
    regions_in = ", ".join(f"'{r}'" for r in selected_regions)
    where_clauses.append(f"o.REGION IN ({regions_in})")
if selected_statuses:
    statuses_in = ", ".join(f"'{s}'" for s in selected_statuses)
    where_clauses.append(f"o.STATUS IN ({statuses_in})")
if selected_segments:
    segs_in = ", ".join(f"'{s}'" for s in selected_segments)
    where_clauses.append(f"c.SEGMENT IN ({segs_in})")
if selected_categories:
    cats_in = ", ".join(f"'{c}'" for c in selected_categories)
    where_clauses.append(f"p.CATEGORY IN ({cats_in})")

where_sql = " AND ".join(where_clauses)

BASE_JOIN = """
    FROM ANALYTICS.MARTS.FCT_ORDERS      o
    JOIN ANALYTICS.MARTS.DIM_CUSTOMERS   c ON o.CUSTOMER_ID = c.CUSTOMER_ID
    JOIN ANALYTICS.MARTS.DIM_PRODUCTS    p ON o.PRODUCT_ID  = p.PRODUCT_ID
"""

# ---------------------------------------------------------------------------
# KPI queries
# ---------------------------------------------------------------------------
kpi_sql = f"""
SELECT
    COALESCE(SUM(o.AMOUNT), 0)                             AS total_revenue,
    COUNT(o.ORDER_ID)                                      AS total_orders,
    COUNT(DISTINCT o.CUSTOMER_ID)                          AS unique_customers,
    COALESCE(AVG(o.AMOUNT), 0)                             AS avg_order_value
{BASE_JOIN}
WHERE {where_sql}
"""

kpi_df = run_query(kpi_sql)

# ---------------------------------------------------------------------------
# Dashboard title
# ---------------------------------------------------------------------------
st.title("Sales Performance Dashboard")
st.markdown(
    f"Showing data from **{start_date}** to **{end_date}**  "
    + (f"| Regions: **{', '.join(selected_regions)}**" if selected_regions else "")
)
st.divider()

# ---------------------------------------------------------------------------
# KPI metric cards
# ---------------------------------------------------------------------------
if not kpi_df.empty:
    rev   = kpi_df["TOTAL_REVENUE"].iloc[0]
    ords  = int(kpi_df["TOTAL_ORDERS"].iloc[0])
    custs = int(kpi_df["UNIQUE_CUSTOMERS"].iloc[0])
    aov   = kpi_df["AVG_ORDER_VALUE"].iloc[0]
else:
    rev = ords = custs = aov = 0

kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
kpi_col1.metric("Total Revenue",       f"${rev:,.2f}")
kpi_col2.metric("Total Orders",        f"{ords:,}")
kpi_col3.metric("Unique Customers",    f"{custs:,}")
kpi_col4.metric("Avg Order Value",     f"${aov:,.2f}")

st.divider()

# ---------------------------------------------------------------------------
# Row 2: Revenue trend (area chart) + Top 10 products (bar chart)
# ---------------------------------------------------------------------------
chart_col1, chart_col2 = st.columns([3, 2])

# Revenue trend over time
with chart_col1:
    st.subheader("Revenue Trend")
    trend_sql = f"""
    SELECT
        DATE_TRUNC('week', o.ORDER_DATE)::DATE AS week_start,
        SUM(o.AMOUNT)                          AS weekly_revenue
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1
    ORDER BY 1
    """
    trend_df = run_query(trend_sql)
    if not trend_df.empty:
        trend_df.columns = trend_df.columns.str.lower()
        area_chart = (
            alt.Chart(trend_df)
            .mark_area(
                line={"color": "#1f77b4"},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color="#1f77b4", offset=1),
                        alt.GradientStop(color="white",   offset=0),
                    ],
                    x1=1, x2=1, y1=1, y2=0,
                ),
            )
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("weekly_revenue:Q", title="Revenue ($)"),
                tooltip=["week_start:T", "weekly_revenue:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(area_chart, use_container_width=True)
    else:
        st.info("No trend data for the selected filters.")

# Top 10 products by revenue
with chart_col2:
    st.subheader("Top 10 Products by Revenue")
    top_products_sql = f"""
    SELECT
        p.PRODUCT_NAME,
        SUM(o.AMOUNT) AS product_revenue
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 10
    """
    prod_df = run_query(top_products_sql)
    if not prod_df.empty:
        prod_df.columns = prod_df.columns.str.lower()
        bar_chart = (
            alt.Chart(prod_df)
            .mark_bar(color="#2ca02c")
            .encode(
                x=alt.X("product_revenue:Q", title="Revenue ($)"),
                y=alt.Y("product_name:N", sort="-x", title="Product"),
                tooltip=["product_name:N", "product_revenue:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(bar_chart, use_container_width=True)
    else:
        st.info("No product data for the selected filters.")

st.divider()

# ---------------------------------------------------------------------------
# Row 3: Revenue by region (donut) + Top customers table
# ---------------------------------------------------------------------------
donut_col, table_col = st.columns([2, 3])

# Revenue by region – donut chart
with donut_col:
    st.subheader("Revenue by Region")
    region_sql = f"""
    SELECT
        o.REGION,
        SUM(o.AMOUNT) AS region_revenue
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1
    ORDER BY 2 DESC
    """
    region_df = run_query(region_sql)
    if not region_df.empty:
        region_df.columns = region_df.columns.str.lower()
        donut = (
            alt.Chart(region_df)
            .mark_arc(innerRadius=60)
            .encode(
                theta=alt.Theta("region_revenue:Q"),
                color=alt.Color(
                    "region:N",
                    scale=alt.Scale(scheme="tableau10"),
                    legend=alt.Legend(title="Region"),
                ),
                tooltip=["region:N", "region_revenue:Q"],
            )
            .properties(height=300)
        )
        st.altair_chart(donut, use_container_width=True)
    else:
        st.info("No region data for the selected filters.")

# Top customers table
with table_col:
    st.subheader("Top 15 Customers by Revenue")
    top_cust_sql = f"""
    SELECT
        c.CUSTOMER_ID,
        c.FULL_NAME,
        c.SEGMENT,
        c.COUNTRY_CODE,
        COUNT(o.ORDER_ID)  AS order_count,
        SUM(o.AMOUNT)      AS total_spent,
        MAX(o.ORDER_DATE)  AS last_order_date
    {BASE_JOIN}
    WHERE {where_sql}
    GROUP BY 1, 2, 3, 4
    ORDER BY total_spent DESC
    LIMIT 15
    """
    cust_df = run_query(top_cust_sql)
    if not cust_df.empty:
        cust_df.columns = cust_df.columns.str.lower()
        cust_df["total_spent"] = cust_df["total_spent"].map("${:,.2f}".format)
        st.dataframe(
            cust_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "customer_id":     st.column_config.TextColumn("Customer ID"),
                "full_name":       st.column_config.TextColumn("Name"),
                "segment":         st.column_config.TextColumn("Segment"),
                "country_code":    st.column_config.TextColumn("Country"),
                "order_count":     st.column_config.NumberColumn("Orders"),
                "total_spent":     st.column_config.TextColumn("Total Spent"),
                "last_order_date": st.column_config.DateColumn("Last Order"),
            },
        )
    else:
        st.info("No customer data for the selected filters.")

st.divider()

# ---------------------------------------------------------------------------
# Expandable raw data viewer with CSV download
# ---------------------------------------------------------------------------
with st.expander("Raw Order Data", expanded=False):
    raw_sql = f"""
    SELECT
        o.ORDER_ID,
        o.ORDER_DATE,
        c.FULL_NAME    AS customer_name,
        c.SEGMENT,
        p.PRODUCT_NAME,
        p.CATEGORY,
        o.AMOUNT,
        o.STATUS,
        o.REGION
    {BASE_JOIN}
    WHERE {where_sql}
    ORDER BY o.ORDER_DATE DESC
    LIMIT 1000
    """
    raw_df = run_query(raw_sql)
    if not raw_df.empty:
        raw_df.columns = raw_df.columns.str.lower()

        # Row count indicator
        st.caption(f"Showing up to 1,000 rows. Total matching: {len(raw_df):,}")

        # Search box for client-side filter
        search_term = st.text_input("Search by customer name or product", "")
        if search_term:
            mask = (
                raw_df["customer_name"].str.contains(search_term, case=False, na=False)
                | raw_df["product_name"].str.contains(search_term, case=False, na=False)
            )
            raw_df = raw_df[mask]

        st.dataframe(raw_df, use_container_width=True, hide_index=True)

        # CSV download button
        csv_bytes = raw_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download as CSV",
            data=csv_bytes,
            file_name="orders_export.csv",
            mime="text/csv",
        )
    else:
        st.info("No raw data for the selected filters.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.caption("Snowflake Master Course – Chapter 12: Streamlit in Snowflake")
