# model.py
import numpy as np
import pandas as pd


def run_financial_model(
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
):
  years = ["Yr 0", "Yr 1", "Yr 2", "Yr 3", "Yr 4", "Yr 5"]
  num_years = 5

  is_data = {
      "売上高": [base_rev],
      "売上原価": [base_rev * cogs_pct],
      "売上総利益": [0],
      "販管費": [base_rev * sga_pct],
      "営業利益 (EBIT)": [0],
      "支払利息": [0],
      "税引前利益 (EBT)": [0],
      "法人税等": [0],
      "当期純利益": [0],
  }

  bs_data = {
      "現金預金": [base_cash],
      "売上債権": [(base_rev * ar_days) / 365],
      "棚卸資産": [(base_rev * cogs_pct * inv_days) / 365],
      "有形固定資産 (純額)": [base_ppe],
      "資産合計": [0],
      "買入債務": [(base_rev * cogs_pct * ap_days) / 365],
      "有利子負債": [base_debt],
      "負債合計": [0],
      "株主資本 (利益余剰金含む)": [base_equity],
      "負債・純資産合計": [0],
      "BSバランスチェック (差額)": [0],
  }

  cf_data = {
      "営業CF": [0],
      "投資CF (CapEx)": [0],
      "財務CF": [0],
      "フリーキャッシュフロー (FCF)": [0],
      "期末現金増減": [0],
  }

  is_data["売上総利益"][0] = is_data["売上高"][0] - is_data["売上原価"][0]
  is_data["営業利益 (EBIT)"][0] = (
      is_data["売上総利益"][0] - is_data["販管費"][0]
  )
  is_data["支払利息"][0] = bs_data["有利子負債"][0] * interest_rate
  is_data["税引前利益 (EBT)"][0] = (
      is_data["営業利益 (EBIT)"][0] - is_data["支払利息"][0]
  )
  is_data["法人税等"][0] = max(0, is_data["税引前利益 (EBT)"][0] * tax_rate)
  is_data["当期純利益"][0] = (
      is_data["税引前利益 (EBT)"][0] - is_data["法人税等"][0]
  )

  bs_data["資産合計"][0] = (
      bs_data["現金預金"][0]
      + bs_data["売上債権"][0]
      + bs_data["棚卸資産"][0]
      + bs_data["有形固定資産 (純額)"][0]
  )
  bs_data["負債合計"][0] = bs_data["買入債務"][0] + bs_data["有利子負債"][0]
  bs_data["負債・純資産合計"][0] = (
      bs_data["負債合計"][0] + bs_data["株主資本 (利益余剰金含む)"][0]
  )

  for t in range(1, num_years + 1):
    rev = is_data["売上高"][t - 1] * (1 + rev_growth)
    cogs = rev * cogs_pct
    gp = rev - cogs
    sga = rev * sga_pct
    ebit = gp - sga
    interest = bs_data["有利子負債"][t - 1] * interest_rate
    ebt = ebit - interest
    tax = max(0, ebt * tax_rate)
    net_income = ebt - tax

    is_data["売上高"].append(rev)
    is_data["売上原価"].append(cogs)
    is_data["売上総利益"].append(gp)
    is_data["販管費"].append(sga)
    is_data["営業利益 (EBIT)"].append(ebit)
    is_data["支払利息"].append(interest)
    is_data["税引前利益 (EBT)"].append(ebt)
    is_data["法人税等"].append(tax)
    is_data["当期純利益"].append(net_income)

    ar = (rev * ar_days) / 365
    inv = (cogs * inv_days) / 365
    ap = (cogs * ap_days) / 365

    capex = rev * capex_pct
    da = rev * da_pct
    ppe = bs_data["有形固定資産 (純額)"][t - 1] + capex - da

    nopat = ebit * (1 - tax_rate)
    delta_nwc = (
        (ar - bs_data["売上債権"][t - 1])
        + (inv - bs_data["棚卸資産"][t - 1])
        - (ap - bs_data["買入債務"][t - 1])
    )
    cf_op = net_income + da - delta_nwc
    cf_inv = -capex
    fcf = nopat + da - capex - delta_nwc

    debt = bs_data["有利子負債"][t - 1]
    cf_fin = 0

    net_change_cash = cf_op + cf_inv + cf_fin
    cash = bs_data["現金預金"][t - 1] + net_change_cash
    equity = bs_data["株主資本 (利益余剰金含む)"][t - 1] + net_income

    total_assets = cash + ar + inv + ppe
    total_liab = ap + debt
    total_liab_eq = total_liab + equity
    bs_diff = total_assets - total_liab_eq

    bs_data["現金預金"].append(cash)
    bs_data["売上債権"].append(ar)
    bs_data["棚卸資産"].append(inv)
    bs_data["有形固定資産 (純額)"].append(ppe)
    bs_data["資産合計"].append(total_assets)
    bs_data["買入債務"].append(ap)
    bs_data["有利子負債"].append(debt)
    bs_data["負債合計"].append(total_liab)
    bs_data["株主資本 (利益余剰金含む)"].append(equity)
    bs_data["負債・純資産合計"].append(total_liab_eq)
    bs_data["BSバランスチェック (差額)"].append(bs_diff)

    cf_data["営業CF"].append(cf_op)
    cf_data["投資CF (CapEx)"].append(cf_inv)
    cf_data["財務CF"].append(cf_fin)
    cf_data["フリーキャッシュフロー (FCF)"].append(fcf)
    cf_data["期末現金増減"].append(net_change_cash)

  df_is = pd.DataFrame(is_data, index=years)
  df_bs = pd.DataFrame(bs_data, index=years)
  df_cf = pd.DataFrame(cf_data, index=years)

  ratios = []
  for t in range(len(years)):
    ebit = df_is["営業利益 (EBIT)"].iloc[t]
    nopat = ebit * (1 - tax_rate)
    op_assets = (
        df_bs["売上債権"].iloc[t]
        + df_bs["棚卸資産"].iloc[t]
        + df_bs["有形固定資産 (純額)"].iloc[t]
    )
    op_liab = df_bs["買入債務"].iloc[t]
    invested_capital = op_assets - op_liab

    roic = (nopat / invested_capital * 100) if invested_capital != 0 else 0
    wacc_pct = wacc * 100
    roic_spread = roic - wacc_pct
    roe = (
        (
            df_is["当期純利益"].iloc[t]
            / df_bs["株主資本 (利益余剰金含む)"].iloc[t]
        )
        * 100
        if df_bs["株主資本 (利益余剰金含む)"].iloc[t] != 0
        else 0
    )
    roa = (
        (df_is["当期純利益"].iloc[t] / df_bs["資産合計"].iloc[t]) * 100
        if df_bs["資産合計"].iloc[t] != 0
        else 0
    )
    ebit_margin = (
        (ebit / df_is["売上高"].iloc[t]) * 100
        if df_is["売上高"].iloc[t] != 0
        else 0
    )
    current_ratio = (
        (
            (
                df_bs["現金預金"].iloc[t]
                + df_bs["売上債権"].iloc[t]
                + df_bs["棚卸資産"].iloc[t]
            )
            / df_bs["買入債務"].iloc[t]
        )
        * 100
        if df_bs["買入債務"].iloc[t] != 0
        else 0
    )

    ratios.append({
        "投下資本 (百万円)": invested_capital,
        "NOPAT (百万円)": nopat,
        "ROIC (%)": roic,
        "WACC (%)": wacc_pct,
        "ROICスプレッド (%)": roic_spread,
        "ROE (%)": roe,
        "ROA (%)": roa,
        "営業利益率 (%)": ebit_margin,
        "流動比率 (%)": current_ratio,
    })

  df_ratios = pd.DataFrame(ratios, index=years)

  fcf_proj = df_cf["フリーキャッシュフロー (FCF)"].iloc[1:].tolist()
  discount_factors = [(1 + wacc) ** i for i in range(1, num_years + 1)]
  pv_fcf = [fcf / df for fcf, df in zip(fcf_proj, discount_factors)]
  sum_pv_fcf = sum(pv_fcf)

  terminal_value = (fcf_proj[-1] * (1 + perp_growth)) / (wacc - perp_growth)
  pv_tv = terminal_value / ((1 + wacc) ** num_years)

  enterprise_value = sum_pv_fcf + pv_tv
  net_debt = df_bs["有利子負債"].iloc[0] - df_bs["現金預金"].iloc[0]
  equity_value = enterprise_value - net_debt
  implied_share_price = (
      (equity_value * 100) / shares_outstanding if shares_outstanding > 0 else 0
  )

  return (
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
  )