# model.py
import numpy as np
import pandas as pd
 
YEARS = ["Yr 0", "Yr 1", "Yr 2", "Yr 3", "Yr 4", "Yr 5"]
NUM_YEARS = 5
 
 
def _tile(value, n=NUM_YEARS):
    """数値が1つならn年分に広げる。リストならそのまま使う。"""
    if isinstance(value, (list, tuple, np.ndarray)):
        return list(value)
    return [value] * n
 
 
def simulate(p):
    """
    財務モデルの計算本体(DataFrameを使わないので高速)。
    p は辞書。必要なキーは下のとおり。
      rev_growth, cogs_pct, sga_pct : 数値 または 5年分のリスト(年別ドライバ)
      base_cogs_pct, base_sga_pct   : Yr0 の原価率・販管費率
      tax_rate, capex_pct, da_pct, ar_days, inv_days, ap_days
      wacc, perp_growth, interest_rate
      repay_rate  : 年間返済率 (対 初期有利子負債)
      payout      : 配当性向 (対 当期純利益)
      exit_multiple : エグジットEV/EBITDA倍率
      base_rev, base_cash, base_ppe, base_debt, shares_outstanding
    """
    g = _tile(p["rev_growth"])
    c = _tile(p["cogs_pct"])
    s = _tile(p["sga_pct"])
    tax_rate = p["tax_rate"]
    interest_rate = p["interest_rate"]
    wacc = p["wacc"]
    perp = p["perp_growth"]
 
    # ---------------- Yr 0 ----------------
    rev0 = p["base_rev"]
    cogs0 = rev0 * p["base_cogs_pct"]
    sga0 = rev0 * p["base_sga_pct"]
    ebit0 = rev0 - cogs0 - sga0
    interest0 = p["base_debt"] * interest_rate
    ebt0 = ebit0 - interest0
    tax0 = max(0.0, ebt0) * tax_rate
    ni0 = ebt0 - tax0
    nol0 = max(0.0, -ebt0)
 
    ar0 = rev0 * p["ar_days"] / 365
    inv0 = cogs0 * p["inv_days"] / 365
    ap0 = cogs0 * p["ap_days"] / 365
    assets0 = p["base_cash"] + ar0 + inv0 + p["base_ppe"]
    liab0 = ap0 + p["base_debt"]
    # Yr0 は入力値同士が一致する保証がないため、差額を株主資本で調整する
    equity0 = assets0 - liab0
 
    out = {
        "rev": [rev0], "cogs": [cogs0], "gp": [rev0 - cogs0], "sga": [sga0],
        "ebit": [ebit0], "interest": [interest0], "ebt": [ebt0], "tax": [tax0],
        "ni": [ni0], "nol": [nol0],
        "cash": [p["base_cash"]], "ar": [ar0], "inv": [inv0],
        "ppe": [p["base_ppe"]], "assets": [assets0],
        "ap": [ap0], "debt": [p["base_debt"]], "liab": [liab0],
        "equity": [equity0], "liab_eq": [liab0 + equity0], "bs_diff": [0.0],
        "da": [0.0], "capex": [0.0], "div": [0.0], "repay": [0.0],
        "cf_op": [0.0], "cf_inv": [0.0], "cf_fin": [0.0], "fcf": [0.0],
        "net_cash": [0.0], "nopat": [ebit0 - max(0.0, ebit0) * tax_rate],
        "ebitda": [ebit0],
    }
 
    # ---------------- Yr 1 ~ Yr 5 ----------------
    nol_prev = nol0
    for t in range(1, NUM_YEARS + 1):
        rev = out["rev"][t - 1] * (1 + g[t - 1])
        cogs = rev * c[t - 1]
        sga = rev * s[t - 1]
        gp = rev - cogs
        ebit = gp - sga
        interest = out["debt"][t - 1] * interest_rate
        ebt = ebit - interest
 
        # 繰越欠損金: 赤字は繰り越し、黒字の年に課税所得から差し引く
        nol_used = min(nol_prev, max(ebt, 0.0))
        taxable = max(ebt, 0.0) - nol_used
        nol_end = nol_prev - nol_used + max(-ebt, 0.0)
        tax = taxable * tax_rate
        ni = ebt - tax
        nol_prev = nol_end
 
        ar = rev * p["ar_days"] / 365
        inv = cogs * p["inv_days"] / 365
        ap = cogs * p["ap_days"] / 365
        capex = rev * p["capex_pct"]
        da = rev * p["da_pct"]
        ppe = out["ppe"][t - 1] + capex - da
 
        delta_nwc = (
            (ar - out["ar"][t - 1])
            + (inv - out["inv"][t - 1])
            - (ap - out["ap"][t - 1])
        )
 
        # 財務CF: 借入金の返済(初期残高に対する定額)と配当
        repay = min(out["debt"][t - 1], p["base_debt"] * p["repay_rate"])
        div = max(ni, 0.0) * p["payout"]
 
        cf_op = ni + da - delta_nwc
        cf_inv = -capex
        cf_fin = -repay - div
        net_cash = cf_op + cf_inv + cf_fin
 
        cash = out["cash"][t - 1] + net_cash
        debt = out["debt"][t - 1] - repay
        equity = out["equity"][t - 1] + ni - div
 
        assets = cash + ar + inv + ppe
        liab = ap + debt
        liab_eq = liab + equity
 
        # DCF用のFCF(借入や配当の影響を受けない)
        nopat = ebit - max(0.0, ebit) * tax_rate
        fcf = nopat + da - capex - delta_nwc
 
        for key, val in [
            ("rev", rev), ("cogs", cogs), ("gp", gp), ("sga", sga),
            ("ebit", ebit), ("interest", interest), ("ebt", ebt),
            ("tax", tax), ("ni", ni), ("nol", nol_end),
            ("cash", cash), ("ar", ar), ("inv", inv), ("ppe", ppe),
            ("assets", assets), ("ap", ap), ("debt", debt), ("liab", liab),
            ("equity", equity), ("liab_eq", liab_eq),
            ("bs_diff", assets - liab_eq),
            ("da", da), ("capex", capex), ("div", div), ("repay", repay),
            ("cf_op", cf_op), ("cf_inv", cf_inv), ("cf_fin", cf_fin),
            ("fcf", fcf), ("net_cash", net_cash), ("nopat", nopat),
            ("ebitda", ebit + da),
        ]:
            out[key].append(val)
 
    # ---------------- 企業価値 (DCF) ----------------
    fcf_proj = out["fcf"][1:]
    discount_factors = [(1 + wacc) ** i for i in range(1, NUM_YEARS + 1)]
    pv_fcf = [f / d for f, d in zip(fcf_proj, discount_factors)]
    sum_pv_fcf = sum(pv_fcf)
    net_debt = out["debt"][0] - out["cash"][0]
    shares = p["shares_outstanding"]
 
    def to_price(equity_value):
        return equity_value * 100 / shares if shares > 0 else 0.0
 
    # (A) 永続成長法
    if wacc > perp:
        tv_perp = fcf_proj[-1] * (1 + perp) / (wacc - perp)
        pv_tv = tv_perp / (1 + wacc) ** NUM_YEARS
        ev = sum_pv_fcf + pv_tv
        equity_value = ev - net_debt
        price = to_price(equity_value)
    else:
        tv_perp = pv_tv = ev = equity_value = price = float("nan")
 
    # (B) エグジットマルチプル法
    ebitda5 = out["ebitda"][-1]
    tv_mult = ebitda5 * p["exit_multiple"]
    pv_tv_mult = tv_mult / (1 + wacc) ** NUM_YEARS
    ev_mult = sum_pv_fcf + pv_tv_mult
    equity_mult = ev_mult - net_debt
    price_mult = to_price(equity_mult)
 
    # 相互チェック: 一方の前提が、もう一方でいくつに相当するか
    implied_multiple = tv_perp / ebitda5 if ebitda5 > 0 else float("nan")
    denom = tv_mult + fcf_proj[-1]
    implied_growth = (
        (tv_mult * wacc - fcf_proj[-1]) / denom if denom != 0 else float("nan")
    )
 
    out.update({
        "fcf_proj": fcf_proj,
        "discount_factors": discount_factors,
        "pv_fcf": pv_fcf,
        "sum_pv_fcf": sum_pv_fcf,
        "tv_perp": tv_perp,
        "pv_tv": pv_tv,
        "enterprise_value": ev,
        "equity_value": equity_value,
        "implied_share_price": price,
        "net_debt": net_debt,
        "tv_mult": tv_mult,
        "pv_tv_mult": pv_tv_mult,
        "ev_mult": ev_mult,
        "equity_value_mult": equity_mult,
        "price_mult": price_mult,
        "implied_multiple": implied_multiple,
        "implied_growth": implied_growth,
    })
    return out
 
 
def run_financial_model(p):
    """simulate() の結果を、画面表示用のDataFrameにまとめて返す。"""
    o = simulate(p)
    wacc = p["wacc"]
 
    df_is = pd.DataFrame(
        {
            "売上高": o["rev"],
            "売上原価": o["cogs"],
            "売上総利益": o["gp"],
            "販管費": o["sga"],
            "営業利益 (EBIT)": o["ebit"],
            "支払利息": o["interest"],
            "税引前利益 (EBT)": o["ebt"],
            "法人税等": o["tax"],
            "当期純利益": o["ni"],
            "(参考) 期末繰越欠損金": o["nol"],
        },
        index=YEARS,
    )
    df_bs = pd.DataFrame(
        {
            "現金預金": o["cash"],
            "売上債権": o["ar"],
            "棚卸資産": o["inv"],
            "有形固定資産 (純額)": o["ppe"],
            "資産合計": o["assets"],
            "買入債務": o["ap"],
            "有利子負債": o["debt"],
            "負債合計": o["liab"],
            "株主資本 (利益余剰金含む)": o["equity"],
            "負債・純資産合計": o["liab_eq"],
            "BSバランスチェック (差額)": o["bs_diff"],
        },
        index=YEARS,
    )
    df_cf = pd.DataFrame(
        {
            "営業CF": o["cf_op"],
            "投資CF (CapEx)": o["cf_inv"],
            "財務CF": o["cf_fin"],
            "　うち借入金返済": [-x for x in o["repay"]],
            "　うち配当支払": [-x for x in o["div"]],
            "フリーキャッシュフロー (FCF)": o["fcf"],
            "期末現金増減": o["net_cash"],
        },
        index=YEARS,
    )
 
    ratios = []
    for t in range(len(YEARS)):
        invested_capital = o["ar"][t] + o["inv"][t] + o["ppe"][t] - o["ap"][t]
        nopat = o["nopat"][t]
        roic = nopat / invested_capital * 100 if invested_capital != 0 else 0
        roe = o["ni"][t] / o["equity"][t] * 100 if o["equity"][t] != 0 else 0
        roa = o["ni"][t] / o["assets"][t] * 100 if o["assets"][t] != 0 else 0
        margin = o["ebit"][t] / o["rev"][t] * 100 if o["rev"][t] != 0 else 0
        current = (
            (o["cash"][t] + o["ar"][t] + o["inv"][t]) / o["ap"][t] * 100
            if o["ap"][t] != 0
            else 0
        )
        ratios.append({
            "投下資本 (百万円)": invested_capital,
            "NOPAT (百万円)": nopat,
            "ROIC (%)": roic,
            "WACC (%)": wacc * 100,
            "ROICスプレッド (%)": roic - wacc * 100,
            "ROE (%)": roe,
            "ROA (%)": roa,
            "営業利益率 (%)": margin,
            "流動比率 (%)": current,
        })
    df_ratios = pd.DataFrame(ratios, index=YEARS)
 
    result = dict(o)
    result.update(
        df_is=df_is, df_bs=df_bs, df_cf=df_cf, df_ratios=df_ratios
    )
    return result
 