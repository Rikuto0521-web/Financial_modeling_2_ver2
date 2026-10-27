# app.py
import io
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from database import (
    get_all_scenario_names,
    init_db,
    load_scenario_from_db,
    save_scenario_to_db,
)
from fetcher import fetch_financial_data, fetch_historical_fmp
from model import run_financial_model

init_db()

st.set_page_config(
    page_title="Advanced Financial Modeling & Valuation Suite",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main { background-color: #f4f6f9; }
    div.stMetric {
        background-color: #ffffff;
        padding: 16px;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        border: 1px solid #e1e8ed;
    }
    h1, h2, h3 { color: #1e293b; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border-radius: 6px 6px 0px 0px;
        padding: 10px 20px;
        font-weight: 600;
        border: 1px solid #e1e8ed;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2b5c8f !important;
        color: white !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("📊 財務3表連動モデル & 過去10年ヒストリカル分析")
st.caption("プロフェッショナル仕様の財務モデリング・企業価値分析システム")

st.sidebar.header("⚙️ モデリング パラメータ")

# --- 🔍 APIによる財務データ自動取得 (yfinance & FMP) ---
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 企業データ自動取得 (API)")
ticker_input = st.sidebar.text_input(
    "ティッカー / 銘柄コード",
    value="AAPL",
    help="米国株例: AAPL, MSFT / 日本株例: 7203.T",
)
fmp_api_key = st.sidebar.text_input(
    "FMP APIキー (10年分析用)",
    value="",
    type="password",
    help="Financial Modeling PrepのAPIキーを入力すると過去10年分析が有効になります",
)

if st.sidebar.button("⚡ 予測用モデルデータを取得 (yfinance)"):
  with st.spinner(f"「{ticker_input}」のデータを取得中..."):
    fetched_data = fetch_financial_data(ticker_symbol=ticker_input)
    if fetched_data:
      st.session_state["base_rev"] = fetched_data["base_rev"]
      st.session_state["base_cash"] = fetched_data["base_cash"]
      st.session_state["base_ppe"] = fetched_data["base_ppe"]
      st.session_state["base_debt"] = fetched_data["base_debt"]
      st.session_state["base_equity"] = fetched_data["base_equity"]
      st.session_state["shares_outstanding"] = fetched_data[
          "shares_outstanding"
      ]
      st.sidebar.success(f"「{fetched_data['company_name']}」を取得完了！")
      st.rerun()
    else:
      st.sidebar.error("データ取得に失敗しました。")

# --- 💾 DBシナリオ保存・読込 ---
st.sidebar.markdown("---")
st.sidebar.subheader("💾 シナリオの保存・読込")

saved_list = get_all_scenario_names()
selected_load_name = st.sidebar.selectbox(
    "保存済みシナリオから読込", ["-- 選択してください --"] + saved_list
)

if st.sidebar.button("📂 シナリオを読み込む"):
  if selected_load_name != "-- 選択してください --":
    loaded_params = load_scenario_from_db(selected_load_name)
    if loaded_params:
      st.session_state["rev"] = float(loaded_params[0] * 100)
      st.session_state["cogs"] = float(loaded_params[1] * 100)
      st.session_state["sga"] = float(loaded_params[2] * 100)
      st.session_state["tax"] = float(loaded_params[3] * 100)
      st.session_state["capex"] = float(loaded_params[4] * 100)
      st.session_state["da"] = float(loaded_params[5] * 100)
      st.session_state["ar"] = int(loaded_params[6])
      st.session_state["inv"] = int(loaded_params[7])
      st.session_state["ap"] = int(loaded_params[8])
      st.session_state["wacc"] = float(loaded_params[9] * 100)
      st.session_state["perp"] = float(loaded_params[10] * 100)
      st.session_state["int"] = float(loaded_params[11] * 100)
      st.session_state["base_rev"] = float(loaded_params[12])
      st.session_state["base_cash"] = float(loaded_params[13])
      st.session_state["base_ppe"] = float(loaded_params[14])
      st.session_state["base_debt"] = float(loaded_params[15])
      st.session_state["base_equity"] = float(loaded_params[16])
      st.session_state["shares_outstanding"] = float(loaded_params[17])

      st.sidebar.success(f"「{selected_load_name}」を読み込みました！")
      st.rerun()

scenario = st.sidebar.radio(
    "📌 デフォルトシナリオ選択",
    ["Base (基本)", "Bull (強気)", "Bear (弱気)"],
    index=0,
)

if scenario == "Bull (強気)":
  def_rev, def_cogs, def_sga, def_capex, def_wacc = 12.0, 50.0, 22.0, 6.0, 6.5
elif scenario == "Bear (弱気)":
  def_rev, def_cogs, def_sga, def_capex, def_wacc = 3.0, 60.0, 28.0, 3.0, 8.5
else:
  def_rev, def_cogs, def_sga, def_capex, def_wacc = 7.0, 55.0, 25.0, 4.0, 7.5

st.sidebar.markdown("---")

with st.sidebar.expander("📈 1. 損益・成長ドライバ", expanded=True):
  rev_growth = (
      st.slider(
          "売上高成長率 (%)",
          -5.0,
          25.0,
          value=def_rev,
          step=0.5,
          key="rev",
      )
      / 100.0
  )
  cogs_pct = (
      st.slider(
          "売上原価率 (%)",
          30.0,
          80.0,
          value=def_cogs,
          step=0.5,
          key="cogs",
      )
      / 100.0
  )
  sga_pct = (
      st.slider(
          "販管費率 (%)", 10.0, 40.0, value=def_sga, step=0.5, key="sga"
      )
      / 100.0
  )
  tax_rate = (
      st.slider("実効税率 (%)", 20.0, 40.0, value=30.0, step=0.5, key="tax")
      / 100.0
  )

with st.sidebar.expander("🔄 2. 運転資本・設備投資ドライバ", expanded=False):
  capex_pct = (
      st.slider(
          "設備投資率 (対売上 %)",
          1.0,
          15.0,
          value=def_capex,
          step=0.5,
          key="capex",
      )
      / 100.0
  )
  da_pct = (
      st.slider(
          "減価償却費率 (対売上 %)",
          1.0,
          10.0,
          value=3.5,
          step=0.5,
          key="da",
      )
      / 100.0
  )
  ar_days = st.slider("売上債権回転日数 (日)", 10, 90, value=45, step=1, key="ar")
  inv_days = st.slider(
      "棚卸資産回転日数 (日)", 10, 120, value=30, step=1, key="inv"
  )
  ap_days = st.slider(
      "買入債務回転日数 (日)", 10, 90, value=40, step=1, key="ap"
  )

with st.sidebar.expander("💰 3. 資本構成・DCF設定", expanded=False):
  wacc = (
      st.slider(
          "WACC (資本コスト) (%)",
          4.0,
          12.0,
          value=def_wacc,
          step=0.25,
          key="wacc",
      )
      / 100.0
  )
  perp_growth = (
      st.slider(
          "永続成長率 (%)", 0.0, 3.0, value=1.0, step=0.25, key="perp"
      )
      / 100.0
  )
  interest_rate = (
      st.slider(
          "借入金利息率 (%)", 0.5, 5.0, value=2.0, step=0.1, key="int"
      )
      / 100.0
  )

with st.sidebar.expander("🏢 4. 基準年度 初期値 (Yr 0)", expanded=True):
  base_rev = st.number_input(
      "基準売上高 (単位数値)", value=10000.0, step=500.0, key="base_rev"
  )
  base_cash = st.number_input(
      "初期現金預金 (単位数値)", value=2000.0, step=100.0, key="base_cash"
  )
  base_ppe = st.number_input(
      "初期有形固定資産 (単位数値)",
      value=5000.0,
      step=500.0,
      key="base_ppe",
  )
  base_debt = st.number_input(
      "初期有利子負債 (単位数値)",
      value=3000.0,
      step=500.0,
      key="base_debt",
  )
  base_equity = st.number_input(
      "初期株主資本 (単位数値)",
      value=5000.0,
      step=500.0,
      key="base_equity",
  )
  shares_outstanding = st.number_input(
      "発行済株式数 (万株/万株相当)",
      value=1000.0,
      step=100.0,
      key="shares_outstanding",
  )

st.sidebar.markdown("---")
new_scenario_name = st.sidebar.text_input("保存するシナリオ名", value="MyScenario_1")
if st.sidebar.button("💾 現在の設定を保存する"):
  if new_scenario_name:
    params_to_save = (
        rev_growth,
        cogs_pct,
        sga_pct,
        tax_rate,
        capex_pct,
        da_pct,
        ar_days,
        inv_days,
        ap_days,
        wacc,
        perp_growth,
        interest_rate,
        base_rev,
        base_cash,
        base_ppe,
        base_debt,
        base_equity,
        shares_outstanding,
    )
    save_scenario_to_db(new_scenario_name, params_to_save)
    st.sidebar.success(f"シナリオ「{new_scenario_name}」を保存しました！")
    st.rerun()
  else:
    st.sidebar.error("シナリオ名を入力してください。")

(
    df_is,
    df_bs,
    df_cf,
    df_ratios,
    fcf_proj,
    discount_factors,
    pv_fcf,
    sum_pv_fcf,
    pv_tv,
    enterprise_value,
    equity_value,
    implied_share_price,
    net_debt,
) = run_financial_model(
    rev_growth,
    cogs_pct,
    sga_pct,
    tax_rate,
    capex_pct,
    da_pct,
    ar_days,
    inv_days,
    ap_days,
    wacc,
    perp_growth,
    interest_rate,
    base_rev,
    base_cash,
    base_ppe,
    base_debt,
    base_equity,
    shares_outstanding,
)

years = ["Yr 0", "Yr 1", "Yr 2", "Yr 3", "Yr 4", "Yr 5"]
num_years = 5

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 過去10年ヒストリカル分析",
    "📑 財務3表モデル",
    "🎯 ROIC & レーシオ分析",
    "💰 DCFバリュエーション",
    "🎛️ シナリオ・感度分析",
    "📥 Excel/CSV 出力",
])

with tab0:
  st.subheader(f"📈 過去10年ヒストリカル実績分析 ({ticker_input})")
  st.markdown(
      "FMP APIを用いて、過去最大10年分の決算実績と長期CAGR・平均マージンを検証します。"
  )

  if not fmp_api_key:
    st.info(
        "💡 過去10年分のデータを取得するには、サイドバーに **FMP APIキー**"
        " を入力してください。（無料のアカウント登録で取得可能です）"
    )
  else:
    with st.spinner("FMPから過去10年分の財務データを取得中..."):
      df_hist, hist_metrics = fetch_historical_fmp(ticker_input, fmp_api_key)

    if df_hist is not None and not df_hist.empty:
      col_m1, col_m2, col_m3 = st.columns(3)
      col_m1.metric(
          "売上高 CAGR (長期年平均成長率)",
          f"{hist_metrics.get('売上高 CAGR (%)', 0):.2f}%",
      )
      col_m2.metric(
          "過去平均 売上原価率",
          f"{hist_metrics.get('平均売上原価率 (%)', 0):.2f}%",
      )
      col_m3.metric(
          "過去平均 営業利益率",
          f"{hist_metrics.get('平均営業利益率 (%)', 0):.2f}%",
      )

      st.markdown("---")
      st.markdown("#### 過去10年 損益主要項目の推移")
      st.dataframe(df_hist.style.format("{:,.1f}"), use_container_width=True)

      fig_hist = px.bar(
          df_hist.T,
          barmode="group",
          title="過去10年間の業績推移トレンド",
          labels={"value": "金額", "variable": "勘定科目"},
      )
      st.plotly_chart(fig_hist, use_container_width=True)
    else:
      err_msg = (
          hist_metrics.get("error", "不明なエラー")
          if isinstance(hist_metrics, dict)
          else "取得失敗"
      )
      st.error(f"データの取得に失敗しました: {err_msg}")

with tab1:
  st.subheader(f"📊 財務3表連動モデル (シナリオ: {scenario})")
  st.markdown("#### 損益計算書 (P&L)")
  st.dataframe(df_is.T.style.format("{:,.1f}"), use_container_width=True)

  st.markdown("#### 貸借対照表 (B/S)")
  st.dataframe(
      df_bs.T.style.format("{:,.1f}").highlight_between(
          left=-0.01, right=0.01, props="background-color: #e6ffe6;"
      ),
      use_container_width=True,
  )

  st.markdown("#### キャッシュフロー計算書 (C/F)")
  st.dataframe(df_cf.T.style.format("{:,.1f}"), use_container_width=True)

with tab2:
  st.subheader("🎯 ROICスプレッド & 財務比率 (レーシオ) 分析")

  c1, c2, c3, c4 = st.columns(4)
  c1.metric("Yr 5 予想 ROIC", f"{df_ratios['ROIC (%)'].iloc[-1]:.2f}%")
  c2.metric("WACC (資本コスト)", f"{wacc*100:.2f}%")
  c3.metric(
      "ROICスプレッド", f"{df_ratios['ROICスプレッド (%)'].iloc[-1]:.2f}%"
  )
  c4.metric("Yr 5 予想 ROE", f"{df_ratios['ROE (%)'].iloc[-1]:.2f}%")

  st.markdown("---")
  fig_roic = go.Figure()
  fig_roic.add_trace(
      go.Bar(
          x=years,
          y=df_ratios["ROIC (%)"],
          name="ROIC (%)",
          marker_color="#2b5c8f",
      )
  )
  fig_roic.add_trace(
      go.Scatter(
          x=years,
          y=df_ratios["WACC (%)"],
          name="WACC (%)",
          line=dict(color="#d9534f", width=3, dash="dash"),
      )
  )
  fig_roic.update_layout(
      title="ROICとWACCの比較推移", yaxis_title="%", height=400
  )
  st.plotly_chart(fig_roic, use_container_width=True)

  st.markdown("#### 財務比率一覧表")
  st.dataframe(df_ratios.T.style.format("{:,.2f}"), use_container_width=True)

with tab3:
  st.subheader("💰 DCF企業価値評価 サマリー")

  m1, m2, m3, m4 = st.columns(4)
  m1.metric("事業価値 (PV of FCF)", f"{sum_pv_fcf:,.0f}")
  m2.metric("ターミナルバリュー", f"{pv_tv:,.0f}")
  m3.metric("企業価値 (EV)", f"{enterprise_value:,.0f}")
  m4.metric(
      "理論株価",
      f"{implied_share_price:,.0f}",
      delta=f"株主資本: {equity_value:,.0f}",
  )

  st.markdown("---")
  st.markdown("#### DCF 割引計算詳細")
  df_dcf = pd.DataFrame(
      {
          "FCF": fcf_proj,
          "割引係数": [1 / df for df in discount_factors],
          "割引現在価値 PV": pv_fcf,
      },
      index=years[1:],
  )
  st.dataframe(df_dcf.style.format("{:,.2f}"), use_container_width=True)

with tab4:
  st.subheader("🎛️ 感度分析 (WACC × 永続成長率)")

  wacc_list = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
  perp_list = [
      perp_growth - 0.005,
      perp_growth,
      perp_growth + 0.005,
      perp_growth + 0.01,
  ]

  sens_matrix = []
  for p_val in perp_list:
    row = []
    for w in wacc_list:
      if w <= p_val:
        row.append(np.nan)
        continue
      pv_f = sum([f / ((1 + w) ** (i + 1)) for i, f in enumerate(fcf_proj)])
      tv = (fcf_proj[-1] * (1 + p_val)) / (w - p_val)
      pv_t = tv / ((1 + w) ** num_years)
      ev = pv_f + pv_t
      eq = ev - net_debt
      price = (eq * 100) / shares_outstanding if shares_outstanding > 0 else 0
      row.append(round(price, 0))
    sens_matrix.append(row)

  df_sens = pd.DataFrame(
      sens_matrix,
      index=[f"永続成長率 {p_val*100:.1f}%" for p_val in perp_list],
      columns=[f"WACC {w*100:.2f}%" for w in wacc_list],
  )

  fig_sens = px.imshow(
      df_sens,
      text_auto=True,
      color_continuous_scale="Blues",
      title="理論株価の感度分析マトリクス",
  )
  st.plotly_chart(fig_sens, use_container_width=True)

with tab5:
  st.subheader("📥 モデルデータ・レポートのエクスポート")
  st.markdown("計算結果をCSVまたは統合Excel形式でダウンロードできます。")

  col_exp1, col_exp2 = st.columns(2)
  with col_exp1:
    st.markdown("#### 📄 CSVダウンロード")
    csv_is = df_is.to_csv(index=True).encode("utf-8-sig")
    st.download_button(
        "損益計算書 (CSV)",
        csv_is,
        file_name=f"IS_{scenario}.csv",
        mime="text/csv",
    )
    csv_ratios = df_ratios.to_csv(index=True).encode("utf-8-sig")
    st.download_button(
        "ROIC・財務比率 (CSV)",
        csv_ratios,
        file_name=f"ratios_{scenario}.csv",
        mime="text/csv",
    )

  with col_exp2:
    st.markdown("#### 📘 統合Excelファイル")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
      df_is.to_excel(writer, sheet_name="損益計算書(IS)")
      df_bs.to_excel(writer, sheet_name="貸借対照表(BS)")
      df_cf.to_excel(writer, sheet_name="キャッシュフロー(CF)")
      df_ratios.to_excel(writer, sheet_name="ROIC・財務比率")
      df_sens.to_excel(writer, sheet_name="DCF感度分析")

    st.download_button(
        "📊 完全版モデル (Excel) をダウンロード",
        data=buffer.getvalue(),
        file_name=f"Full_Financial_Model_{scenario}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )