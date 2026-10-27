# app.py
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
from excel_export import build_excel_bytes
from fetcher import fetch_financial_data, fetch_historical_fmp
from model import NUM_YEARS, YEARS, run_financial_model, simulate
from report_pdf import build_pdf_bytes
 
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
 
# =====================================================================
# 初期値とシナリオ (すべて session_state で管理する)
# =====================================================================
SCENARIOS = {
    "Base (基本)": dict(rev=7.0, cogs=55.0, sga=25.0, capex=4.0, wacc=7.5),
    "Bull (強気)": dict(rev=12.0, cogs=50.0, sga=22.0, capex=6.0, wacc=6.5),
    "Bear (弱気)": dict(rev=3.0, cogs=60.0, sga=28.0, capex=3.0, wacc=8.5),
}
 
COMMON_DEFAULTS = dict(
    tax=30.0, da=3.5, ar=45, inv=30, ap=40, perp=1.0, int=2.0,
    repay=10.0, payout=30.0, exit_mult=10.0,
    base_rev=10000.0, base_cash=2000.0, base_ppe=5000.0,
    base_debt=3000.0, shares_outstanding=1000.0,
    # WACC計算機の入力
    rf=2.0, beta=1.1, erp=5.0, w_debt=25.0,
)
 
INT_KEYS = {"ar", "inv", "ap"}
SAVE_KEYS = [
    "rev", "cogs", "sga", "capex", "wacc", "tax", "da", "ar", "inv", "ap",
    "perp", "int", "repay", "payout", "exit_mult",
    "base_rev", "base_cash", "base_ppe", "base_debt", "shares_outstanding",
]
ADJ_COLS = ["成長率±", "原価率±", "販管費率±"]
 
 
def zero_adj():
    return pd.DataFrame(0.0, index=YEARS[1:], columns=ADJ_COLS)
 
 
if "initialized" not in st.session_state:
    st.session_state.update(COMMON_DEFAULTS)
    st.session_state["scenario"] = "Base (基本)"
    st.session_state.update(SCENARIOS["Base (基本)"])
    st.session_state["adj_df"] = zero_adj()
    st.session_state["adj_ver"] = 0
    st.session_state["initialized"] = True
 
 
# ---- ボタンを押したときの処理 (コールバック) ----
def apply_scenario():
    st.session_state.update(SCENARIOS[st.session_state["scenario"]])
 
 
def load_scenario_cb():
    name = st.session_state.get("load_select")
    if not name or name == "-- 選択してください --":
        return
    params = load_scenario_from_db(name)
    if not params:
        st.toast("シナリオの読み込みに失敗しました。", icon="⚠️")
        return
    for k in SAVE_KEYS:
        if k in params:
            st.session_state[k] = (
                int(params[k]) if k in INT_KEYS else float(params[k])
            )
    if "adj" in params:
        st.session_state["adj_df"] = pd.DataFrame(
            params["adj"], index=YEARS[1:], columns=ADJ_COLS
        )
        st.session_state["adj_ver"] += 1
    st.toast(f"「{name}」を読み込みました！", icon="📂")
 
 
def set_adj(rows):
    st.session_state["adj_df"] = pd.DataFrame(
        rows, index=YEARS[1:], columns=ADJ_COLS
    )
    st.session_state["adj_ver"] += 1
 
 
def reset_adj():
    set_adj(zero_adj().values.tolist())
 
 
def fade_adj():
    set_adj([[0, 0, 0], [-1, 0, 0], [-2, 0, 0], [-3, 0, 0], [-4, 0, 0]])
 
 
def apply_hist(rev_pct, cogs_pct, sga_pct):
    """過去実績の数字をスライダーに反映する(範囲内に丸める)"""
    def fit(x, lo, hi, step):
        return float(min(hi, max(lo, round(x / step) * step)))
 
    st.session_state["rev"] = fit(rev_pct, -5.0, 25.0, 0.5)
    st.session_state["cogs"] = fit(cogs_pct, 30.0, 80.0, 0.5)
    st.session_state["sga"] = fit(sga_pct, 10.0, 40.0, 0.5)
    st.toast("過去実績をスライダーに反映しました。", icon="📈")
 
 
def apply_capm_wacc(value_pct):
    st.session_state["wacc"] = float(min(12.0, max(4.0, round(value_pct / 0.25) * 0.25)))
    st.toast("WACCをスライダーに反映しました。", icon="🧮")
 
 
st.title("📊 財務3表連動モデル & 過去10年ヒストリカル分析")
st.caption("プロフェッショナル仕様の財務モデリング・企業価値分析システム")
 
# =====================================================================
# サイドバー
# =====================================================================
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
    "FMP APIキー (過去実績分析用)",
    value="",
    type="password",
    help="Financial Modeling PrepのAPIキーを入力すると過去実績分析が有効になります",
)
 
if st.sidebar.button("⚡ 予測用モデルデータを取得 (yfinance)"):
    with st.spinner(f"「{ticker_input}」のデータを取得中..."):
        fetched_data = fetch_financial_data(ticker_symbol=ticker_input)
    if fetched_data:
        st.session_state["base_rev"] = fetched_data["base_rev"]
        st.session_state["base_cash"] = fetched_data["base_cash"]
        st.session_state["base_ppe"] = fetched_data["base_ppe"]
        st.session_state["base_debt"] = fetched_data["base_debt"]
        st.session_state["shares_outstanding"] = fetched_data["shares_outstanding"]
        st.toast(f"「{fetched_data['company_name']}」を取得完了！", icon="✅")
        st.rerun()
    else:
        st.sidebar.error("データ取得に失敗しました。")
 
# --- 💾 DBシナリオ読込 ---
st.sidebar.markdown("---")
st.sidebar.subheader("💾 シナリオの保存・読込")
saved_list = get_all_scenario_names()
st.sidebar.selectbox(
    "保存済みシナリオから読込",
    ["-- 選択してください --"] + saved_list,
    key="load_select",
)
st.sidebar.button("📂 シナリオを読み込む", on_click=load_scenario_cb)
 
st.sidebar.radio(
    "📌 デフォルトシナリオ選択",
    list(SCENARIOS.keys()),
    key="scenario",
    on_change=apply_scenario,
)
scenario = st.session_state["scenario"]
 
st.sidebar.markdown("---")
 
with st.sidebar.expander("📈 1. 損益・成長ドライバ (基準値)", expanded=True):
    rev_growth = st.slider("売上高成長率 (%)", -5.0, 25.0, step=0.5, key="rev") / 100.0
    cogs_pct = st.slider("売上原価率 (%)", 30.0, 80.0, step=0.5, key="cogs") / 100.0
    sga_pct = st.slider("販管費率 (%)", 10.0, 40.0, step=0.5, key="sga") / 100.0
    tax_rate = st.slider("実効税率 (%)", 20.0, 40.0, step=0.5, key="tax") / 100.0
 
with st.sidebar.expander("📅 年別ドライバ (基準値からの上乗せ)", expanded=False):
    st.caption(
        "Yr1〜Yr5 の各年について、上の基準値に何ポイント足すかを入力します。"
        "例: 成長率±に -2 と入れると、その年の成長率が基準より2ポイント低くなります。"
    )
    c_a, c_b = st.columns(2)
    c_a.button("すべて0に戻す", on_click=reset_adj, use_container_width=True)
    c_b.button("成長率を徐々に鈍化", on_click=fade_adj, use_container_width=True)
    adj_df = st.data_editor(
        st.session_state["adj_df"],
        key=f"adj_editor_{st.session_state['adj_ver']}",
        use_container_width=True,
        column_config={
            col: st.column_config.NumberColumn(col, step=0.5, format="%.1f")
            for col in ADJ_COLS
        },
    )
 
with st.sidebar.expander("🔄 2. 運転資本・設備投資ドライバ", expanded=False):
    capex_pct = st.slider("設備投資率 (対売上 %)", 1.0, 15.0, step=0.5, key="capex") / 100.0
    da_pct = st.slider("減価償却費率 (対売上 %)", 1.0, 10.0, step=0.5, key="da") / 100.0
    ar_days = st.slider("売上債権回転日数 (日)", 10, 90, step=1, key="ar")
    inv_days = st.slider("棚卸資産回転日数 (日)", 10, 120, step=1, key="inv")
    ap_days = st.slider("買入債務回転日数 (日)", 10, 90, step=1, key="ap")
 
with st.sidebar.expander("🏦 3. 財務(借入返済・配当)", expanded=False):
    interest_rate = st.slider("借入金利息率 (%)", 0.5, 5.0, step=0.1, key="int") / 100.0
    repay_rate = st.slider(
        "年間返済率 (初期有利子負債に対する %)", 0.0, 50.0, step=1.0, key="repay"
    ) / 100.0
    payout = st.slider("配当性向 (対当期純利益 %)", 0.0, 100.0, step=5.0, key="payout") / 100.0
 
with st.sidebar.expander("💰 4. 企業価値評価(DCF)設定", expanded=False):
    wacc = st.slider("WACC (資本コスト) (%)", 4.0, 12.0, step=0.25, key="wacc") / 100.0
    perp_growth = st.slider("永続成長率 (%)", 0.0, 3.0, step=0.25, key="perp") / 100.0
    exit_multiple = st.slider("エグジットEV/EBITDA倍率 (倍)", 3.0, 30.0, step=0.5, key="exit_mult")
 
with st.sidebar.expander("🏢 5. 基準年度 初期値 (Yr 0)", expanded=True):
    base_rev = st.number_input("基準売上高 (百万円)", step=500.0, key="base_rev")
    base_cash = st.number_input("初期現金預金 (百万円)", step=100.0, key="base_cash")
    base_ppe = st.number_input("初期有形固定資産 (百万円)", step=500.0, key="base_ppe")
    base_debt = st.number_input("初期有利子負債 (百万円)", step=500.0, key="base_debt")
    shares_outstanding = st.number_input("発行済株式数 (万株)", step=100.0, key="shares_outstanding")
    st.caption("※ Yr0の株主資本は、貸借が一致するよう「資産 − 負債」で自動計算します。")
 
st.sidebar.markdown("---")
new_scenario_name = st.sidebar.text_input("保存するシナリオ名", value="MyScenario_1")
if st.sidebar.button("💾 現在の設定を保存する"):
    if new_scenario_name:
        params_to_save = {k: st.session_state[k] for k in SAVE_KEYS}
        params_to_save["adj"] = adj_df.to_numpy(dtype=float).tolist()
        save_scenario_to_db(new_scenario_name, params_to_save)
        st.toast(f"シナリオ「{new_scenario_name}」を保存しました！", icon="💾")
        st.rerun()
    else:
        st.sidebar.error("シナリオ名を入力してください。")
 
# =====================================================================
# モデル計算
# =====================================================================
adj = adj_df.fillna(0.0).to_numpy(dtype=float) / 100.0
p = dict(
    rev_growth=[rev_growth + adj[i, 0] for i in range(NUM_YEARS)],
    cogs_pct=[cogs_pct + adj[i, 1] for i in range(NUM_YEARS)],
    sga_pct=[sga_pct + adj[i, 2] for i in range(NUM_YEARS)],
    base_cogs_pct=cogs_pct,
    base_sga_pct=sga_pct,
    tax_rate=tax_rate,
    capex_pct=capex_pct,
    da_pct=da_pct,
    ar_days=ar_days,
    inv_days=inv_days,
    ap_days=ap_days,
    wacc=wacc,
    perp_growth=perp_growth,
    interest_rate=interest_rate,
    repay_rate=repay_rate,
    payout=payout,
    exit_multiple=exit_multiple,
    base_rev=base_rev,
    base_cash=base_cash,
    base_ppe=base_ppe,
    base_debt=base_debt,
    shares_outstanding=shares_outstanding,
)
res = run_financial_model(p)
df_is, df_bs, df_cf, df_ratios = res["df_is"], res["df_bs"], res["df_cf"], res["df_ratios"]
net_debt = res["net_debt"]
 
if wacc <= perp_growth:
    st.error("WACCが永続成長率以下のため、永続成長法の企業価値は計算できません。")
if min(res["cash"]) < 0:
    st.warning(
        "予測期間中に現金預金がマイナスになる年があります。"
        "返済率・配当性向・設備投資などを見直してください。"
    )
 
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 過去実績分析",
    "📑 財務3表モデル",
    "🎯 ROIC & レーシオ分析",
    "💰 DCFバリュエーション",
    "🎛️ 感度分析・シミュレーション",
    "📥 Excel/PDF/CSV 出力",
])
 
# =====================================================================
# タブ0: 過去実績
# =====================================================================
with tab0:
    st.subheader(f"📈 過去実績分析 ({ticker_input})")
    st.markdown("FMP APIを用いて、取得できる範囲の決算実績と長期CAGR・平均マージンを検証します。")
 
    if not fmp_api_key:
        st.info(
            "💡 過去実績を取得するには、サイドバーに **FMP APIキー**"
            " を入力してください。（無料のアカウント登録で取得可能です）"
        )
    else:
        with st.spinner("FMPから過去の財務データを取得中..."):
            df_hist, hist_metrics = fetch_historical_fmp(ticker_input, fmp_api_key)
 
        if df_hist is not None and not df_hist.empty:
            hist_rev = df_hist.loc["売上高"]
            valid = hist_rev > 0
            hist_sga_avg = float(
                (
                    (df_hist.loc["売上総利益"][valid] - df_hist.loc["営業利益 (EBIT)"][valid])
                    / hist_rev[valid]
                ).mean()
                * 100
            ) if valid.any() else 25.0
 
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("売上高 CAGR", f"{hist_metrics.get('売上高 CAGR (%)', 0):.2f}%")
            col_m2.metric("過去平均 売上原価率", f"{hist_metrics.get('平均売上原価率 (%)', 0):.2f}%")
            col_m3.metric("過去平均 販管費率", f"{hist_sga_avg:.2f}%")
            col_m4.metric("過去平均 営業利益率", f"{hist_metrics.get('平均営業利益率 (%)', 0):.2f}%")
 
            st.button(
                "⬅️ この実績を成長率・原価率・販管費率に反映する",
                on_click=apply_hist,
                args=(
                    hist_metrics.get("売上高 CAGR (%)", 7.0),
                    hist_metrics.get("平均売上原価率 (%)", 55.0),
                    hist_sga_avg,
                ),
                help="サイドバーの基準値スライダーが、過去実績の数字に置き換わります。",
            )
 
            st.markdown("---")
            st.markdown("#### 過去 損益主要項目の推移")
            st.dataframe(df_hist.style.format("{:,.1f}"), use_container_width=True)
 
            fig_hist = px.bar(
                df_hist.T,
                barmode="group",
                title="過去の業績推移トレンド",
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
 
# =====================================================================
# タブ1: 3表
# =====================================================================
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
    st.caption(
        f"Yr0の株主資本は「資産 − 負債」で自動計算しています ({df_bs['株主資本 (利益余剰金含む)'].iloc[0]:,.1f})。"
        " 緑のセルは差額が0であることを示します。"
    )
 
    st.markdown("#### キャッシュフロー計算書 (C/F)")
    st.dataframe(df_cf.T.style.format("{:,.1f}"), use_container_width=True)
 
# =====================================================================
# タブ2: ROIC
# =====================================================================
with tab2:
    st.subheader("🎯 ROICスプレッド & 財務比率 (レーシオ) 分析")
 
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Yr 5 予想 ROIC", f"{df_ratios['ROIC (%)'].iloc[-1]:.2f}%")
    c2.metric("WACC (資本コスト)", f"{wacc * 100:.2f}%")
    c3.metric("ROICスプレッド", f"{df_ratios['ROICスプレッド (%)'].iloc[-1]:.2f}%")
    c4.metric("Yr 5 予想 ROE", f"{df_ratios['ROE (%)'].iloc[-1]:.2f}%")
 
    st.markdown("---")
    fig_roic = go.Figure()
    fig_roic.add_trace(
        go.Bar(x=YEARS, y=df_ratios["ROIC (%)"], name="ROIC (%)", marker_color="#2b5c8f")
    )
    fig_roic.add_trace(
        go.Scatter(
            x=YEARS, y=df_ratios["WACC (%)"], name="WACC (%)",
            line=dict(color="#d9534f", width=3, dash="dash"),
        )
    )
    fig_roic.update_layout(title="ROICとWACCの比較推移", yaxis_title="%", height=400)
    st.plotly_chart(fig_roic, use_container_width=True)
 
    st.markdown("#### 財務比率一覧表")
    st.dataframe(df_ratios.T.style.format("{:,.2f}"), use_container_width=True)
 
# =====================================================================
# タブ3: DCF
# =====================================================================
with tab3:
    st.subheader("💰 DCF企業価値評価 サマリー")
 
    with st.expander("🧮 WACCをCAPMで計算する", expanded=False):
        st.caption("株主資本コスト = 無リスク金利 + ベータ × 株式リスクプレミアム。負債コストは、サイドバーの借入金利息率と実効税率を使います。")
        w1, w2, w3, w4 = st.columns(4)
        rf = w1.number_input("無リスク金利 (%)", step=0.1, key="rf")
        beta = w2.number_input("ベータ", step=0.05, key="beta")
        erp = w3.number_input("株式リスクプレミアム (%)", step=0.5, key="erp")
        w_debt = w4.number_input("目標負債比率 D/(D+E) (%)", step=5.0, key="w_debt")
        ke = rf + beta * erp
        kd_after = interest_rate * 100 * (1 - tax_rate)
        wacc_calc = ke * (1 - w_debt / 100) + kd_after * (w_debt / 100)
        st.markdown(
            f"株主資本コスト **{ke:.2f}%**　／　税引後負債コスト **{kd_after:.2f}%**　"
            f"→　WACC **{wacc_calc:.2f}%**"
        )
        st.button("⬅️ このWACCをスライダーに反映する", on_click=apply_capm_wacc, args=(wacc_calc,))
 
    st.markdown("##### 永続成長法")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("FCFの現在価値合計", f"{res['sum_pv_fcf']:,.0f}")
    m2.metric("ターミナルバリュー(現在価値)", f"{res['pv_tv']:,.0f}")
    m3.metric("企業価値 (EV)", f"{res['enterprise_value']:,.0f}")
    m4.metric(
        "理論株価",
        f"{res['implied_share_price']:,.0f}",
        delta=f"株主価値: {res['equity_value']:,.0f}",
        delta_color="off",
    )
 
    st.markdown("##### エグジットマルチプル法")
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("FCFの現在価値合計", f"{res['sum_pv_fcf']:,.0f}")
    n2.metric("ターミナルバリュー(現在価値)", f"{res['pv_tv_mult']:,.0f}")
    n3.metric("企業価値 (EV)", f"{res['ev_mult']:,.0f}")
    n4.metric(
        "理論株価",
        f"{res['price_mult']:,.0f}",
        delta=f"株主価値: {res['equity_value_mult']:,.0f}",
        delta_color="off",
    )
 
    imp_mult = res["implied_multiple"]
    imp_g = res["implied_growth"]
    st.info(
        "🔎 **相互チェック**: 永続成長法のターミナルバリューは、Yr5 EBITDAの "
        f"**{imp_mult:.1f}倍** に相当します(設定した倍率は {exit_multiple:.1f}倍)。"
        f"逆に、設定した倍率は永続成長率 **{imp_g * 100:.2f}%** に相当します"
        f"(設定した永続成長率は {perp_growth * 100:.2f}%)。"
        " 2つが大きくかけ離れているときは、どちらかの前提を見直すサインです。"
    )
 
    st.markdown("---")
    st.markdown("#### DCF 割引計算詳細")
    df_dcf = pd.DataFrame(
        {
            "FCF": res["fcf_proj"],
            "割引係数": [1 / d for d in res["discount_factors"]],
            "割引現在価値 PV": res["pv_fcf"],
        },
        index=YEARS[1:],
    )
    st.dataframe(df_dcf.style.format("{:,.2f}"), use_container_width=True)
 
# =====================================================================
# タブ4: 感度分析・シミュレーション
# =====================================================================
with tab4:
    st.subheader("🎛️ 感度分析")
 
    def price_with(key="implied_share_price", **override):
        return simulate(dict(p, **override))[key]
 
    def heatmap(matrix, rows, cols, title):
        df = pd.DataFrame(matrix, index=rows, columns=cols).round(0)
        fig = px.imshow(df, text_auto=",.0f", color_continuous_scale="Blues", title=title)
        st.plotly_chart(fig, use_container_width=True)
        return df
 
    # (1) WACC × 永続成長率
    wacc_list = [wacc - 0.01, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.01]
    perp_list = [perp_growth - 0.005, perp_growth, perp_growth + 0.005, perp_growth + 0.01]
    m = [[price_with(wacc=w, perp_growth=g) for w in wacc_list] for g in perp_list]
    df_sens = heatmap(
        m,
        [f"永続成長率 {g * 100:.2f}%" for g in perp_list],
        [f"WACC {w * 100:.2f}%" for w in wacc_list],
        "理論株価: WACC × 永続成長率 (永続成長法)",
    )
 
    # (2) WACC × エグジット倍率
    mult_list = [max(1.0, exit_multiple + d) for d in (-4, -2, 0, 2, 4)]
    m = [[price_with("price_mult", wacc=w, exit_multiple=x) for w in wacc_list] for x in mult_list]
    df_sens_mult = heatmap(
        m,
        [f"倍率 {x:.1f}x" for x in mult_list],
        [f"WACC {w * 100:.2f}%" for w in wacc_list],
        "理論株価: WACC × エグジット倍率 (マルチプル法)",
    )
 
    # (3) 売上成長率 × 売上原価率 (全年を一律にずらす)
    d_list = [-0.02, -0.01, 0.0, 0.01, 0.02]
 
    def shifted(arr, d):
        return [x + d for x in arr]
 
    m = [
        [
            price_with(
                rev_growth=shifted(p["rev_growth"], dg),
                cogs_pct=shifted(p["cogs_pct"], dc),
            )
            for dg in d_list
        ]
        for dc in d_list
    ]
    df_sens_ops = heatmap(
        m,
        [f"原価率 {d * 100:+.0f}pt" for d in d_list],
        [f"成長率 {d * 100:+.0f}pt" for d in d_list],
        "理論株価: 売上成長率 × 売上原価率 (永続成長法、全年を一律にずらす)",
    )
 
    st.markdown("---")
    st.subheader("🎲 モンテカルロ・シミュレーション")
    st.markdown(
        "前提を確率的にゆらして何度も計算し、理論株価がどれくらいばらつくかを見ます(永続成長法)。"
        " 各前提は、現在の設定値を中心とした正規分布から選びます。"
    )
    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    n_trials = mc1.select_slider("試行回数", [500, 1000, 2000, 5000], value=2000)
    sd_g = mc2.number_input("成長率のばらつき (pt)", 0.0, 10.0, 2.0, 0.5)
    sd_c = mc3.number_input("原価率のばらつき (pt)", 0.0, 10.0, 2.0, 0.5)
    sd_w = mc4.number_input("WACCのばらつき (pt)", 0.0, 3.0, 0.5, 0.25)
    sd_p = mc5.number_input("永続成長率のばらつき (pt)", 0.0, 2.0, 0.25, 0.25)
 
    if st.button("▶️ シミュレーションを実行"):
        rng = np.random.default_rng(42)
        prices = []
        for _ in range(int(n_trials)):
            dg = rng.normal(0, sd_g / 100)
            dc = rng.normal(0, sd_c / 100)
            g_p = max(0.0, rng.normal(perp_growth, sd_p / 100))
            w = max(rng.normal(wacc, sd_w / 100), g_p + 0.01)
            out = simulate(
                dict(
                    p,
                    rev_growth=shifted(p["rev_growth"], dg),
                    cogs_pct=[min(1.2, max(0.1, x + dc)) for x in p["cogs_pct"]],
                    wacc=w,
                    perp_growth=g_p,
                )
            )
            prices.append(out["implied_share_price"])
        st.session_state["mc"] = dict(
            prices=prices, base=res["implied_share_price"]
        )
 
    mc = st.session_state.get("mc")
    if mc:
        arr = np.array(mc["prices"])
        arr = arr[np.isfinite(arr)]
        pct = np.percentile(arr, [5, 25, 50, 75, 95])
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("中央値", f"{pct[2]:,.0f}")
        s2.metric("平均", f"{arr.mean():,.0f}")
        s3.metric("5%点 (弱気側)", f"{pct[0]:,.0f}")
        s4.metric("95%点 (強気側)", f"{pct[4]:,.0f}")
        fig_mc = go.Figure(go.Histogram(x=arr, nbinsx=50, marker_color="#2b5c8f"))
        fig_mc.add_vline(
            x=mc["base"], line_dash="dash", line_color="#d9534f",
            annotation_text="現在の設定", annotation_position="top",
        )
        fig_mc.update_layout(
            title="理論株価の分布", xaxis_title="理論株価 (円)",
            yaxis_title="試行回数", height=380,
        )
        st.plotly_chart(fig_mc, use_container_width=True)
        st.caption(
            "※ 設定を変えたあとは、もう一度「シミュレーションを実行」を押してください。"
            f" 25%〜75%の範囲: {pct[1]:,.0f} 〜 {pct[3]:,.0f}"
        )
 
# =====================================================================
# タブ5: 出力
# =====================================================================
with tab5:
    st.subheader("📥 モデルデータ・レポートのエクスポート")
    st.markdown("計算結果をCSV・数式入りExcel・PDFレポートでダウンロードできます。")
 
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    with col_exp1:
        st.markdown("#### 📄 CSVダウンロード")
        st.download_button(
            "損益計算書 (CSV)",
            df_is.to_csv(index=True).encode("utf-8-sig"),
            file_name=f"IS_{scenario}.csv",
            mime="text/csv",
        )
        st.download_button(
            "ROIC・財務比率 (CSV)",
            df_ratios.to_csv(index=True).encode("utf-8-sig"),
            file_name=f"ratios_{scenario}.csv",
            mime="text/csv",
        )
 
    with col_exp2:
        st.markdown("#### 📘 数式入りExcel")
        st.caption("「前提」シートの数字を変えると、3表とDCFが自動で再計算されます。")
        excel_bytes = build_excel_bytes(
            p,
            extra_sheets={
                "ROIC・財務比率": df_ratios,
                "感度_WACC×永続成長率": df_sens,
                "感度_WACC×倍率": df_sens_mult,
                "感度_成長率×原価率": df_sens_ops,
            },
        )
        st.download_button(
            "📊 完全版モデル (Excel) をダウンロード",
            data=excel_bytes,
            file_name=f"Full_Financial_Model_{scenario}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
 
    with col_exp3:
        st.markdown("#### 📕 PDFレポート (1枚)")
        st.caption("前提・業績予測・2つの評価方法をA4・1枚にまとめます。")
        assumptions = [
            ("売上高成長率 (Yr1→Yr5)", f"{p['rev_growth'][0] * 100:.1f}% → {p['rev_growth'][-1] * 100:.1f}%"),
            ("売上原価率 (Yr1→Yr5)", f"{p['cogs_pct'][0] * 100:.1f}% → {p['cogs_pct'][-1] * 100:.1f}%"),
            ("販管費率 (Yr1→Yr5)", f"{p['sga_pct'][0] * 100:.1f}% → {p['sga_pct'][-1] * 100:.1f}%"),
            ("実効税率", f"{tax_rate * 100:.1f}%"),
            ("設備投資率 / 減価償却費率", f"{capex_pct * 100:.1f}% / {da_pct * 100:.1f}%"),
            ("年間返済率 / 配当性向", f"{repay_rate * 100:.0f}% / {payout * 100:.0f}%"),
            ("WACC", f"{wacc * 100:.2f}%"),
            ("永続成長率", f"{perp_growth * 100:.2f}%"),
            ("エグジット倍率", f"{exit_multiple:.1f}x"),
            ("基準売上高 (Yr0)", f"{base_rev:,.0f}"),
        ]
        pdf_bytes = build_pdf_bytes(
            res,
            title="財務モデル & 企業価値評価レポート",
            scenario_label=scenario,
            assumptions=assumptions,
            ticker=ticker_input,
        )
        st.download_button(
            "📄 PDFレポートをダウンロード",
            data=pdf_bytes,
            file_name=f"Valuation_Report_{scenario}.pdf",
            mime="application/pdf",
        )