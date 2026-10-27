# fetcher.py
import numpy as np
import pandas as pd
import requests
import yfinance as yf


def fetch_financial_data(ticker_symbol):
  """従来通りyfinanceを使って直近のYr0初期値を取得（互換性維持）"""
  try:
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info

    financials = ticker.financials
    if not financials.empty and "Total Revenue" in financials.index:
      base_rev = float(financials.loc["Total Revenue"].iloc[0]) / 1e6
    else:
      base_rev = float(info.get("totalRevenue", 10000000000)) / 1e6

    bs = ticker.balance_sheet
    if not bs.empty:
      base_cash = (
          float(
              bs.loc["Cash And Cash Equivalents"].iloc[0]
              if "Cash And Cash Equivalents" in bs.index
              else 2000000000
          )
          / 1e6
      )
      base_ppe = (
          float(
              bs.loc["Net PPE"].iloc[0]
              if "Net PPE" in bs.index
              else 5000000000
          )
          / 1e6
      )
      base_debt = (
          float(
              bs.loc["Total Debt"].iloc[0]
              if "Total Debt" in bs.index
              else 3000000000
          )
          / 1e6
      )
      base_equity = (
          float(
              bs.loc["Stockholders Equity"].iloc[0]
              if "Stockholders Equity" in bs.index
              else 5000000000
          )
          / 1e6
      )
    else:
      base_cash = 2000.0
      base_ppe = 5000.0
      base_debt = 3000.0
      base_equity = 5000.0

    shares_outstanding = (
        float(info.get("sharesOutstanding", 1000000000)) / 1e4
    )

    return {
        "base_rev": round(base_rev, 1),
        "base_cash": round(base_cash, 1),
        "base_ppe": round(base_ppe, 1),
        "base_debt": round(base_debt, 1),
        "base_equity": round(base_equity, 1),
        "shares_outstanding": round(shares_outstanding, 1),
        "company_name": info.get("shortName", ticker_symbol),
    }
  except Exception as e:
    return None


def fetch_historical_fmp(ticker_symbol, api_key):
  """Financial Modeling Prep (FMP) APIを使って過去10年分の財務データを取得"""
  if not api_key:
    return None, {"error": "APIキーが入力されていません"}

  try:
    # FMP stable インカムステートメント API
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol={ticker_symbol}&apikey={api_key}"
    response = requests.get(url)

    if response.status_code != 200:
      return None, {
          "error": f"API接続エラー (ステータスコード: {response.status_code})"
      }

    try:
      data = response.json()
    except Exception:
      return None, {
          "error": (
              "APIからの応答をJSONとして読み込めませんでした。APIキーやURLを確認してください。"
          )
      }

    if not data or (isinstance(data, dict) and "Error Message" in data):
      err_msg = (
          data.get("Error Message", "データが見つかりませんでした。")
          if isinstance(data, dict)
          else "データが見つかりませんでした。"
      )
      return None, {"error": err_msg}

    if not isinstance(data, list):
      return None, {
          "error": (
              "予期せぬデータ形式です。ティッカーコード（例: AAPL）を確認してください。"
          )
      }

    # データを古い順（時系列順）に並べ替え
    data_sorted = sorted(
        data, key=lambda x: x.get("calendarYear", x.get("date", ""))
    )

    years = []
    revenues = []
    cogs = []
    gross_profits = []
    ebit = []
    net_income = []

    for item in data_sorted:
      years.append(str(item.get("calendarYear", item.get("date")[:4])))
      revenues.append(item.get("revenue", 0) / 1e6)
      cogs.append(item.get("costOfRevenue", 0) / 1e6)
      gross_profits.append(item.get("grossProfit", 0) / 1e6)
      ebit.append(item.get("operatingIncome", 0) / 1e6)
      net_income.append(item.get("netIncome", 0) / 1e6)

    df_hist = pd.DataFrame(
        {
            "売上高": revenues,
            "売上原価": cogs,
            "売上総利益": gross_profits,
            "営業利益 (EBIT)": ebit,
            "当期純利益": net_income,
        },
        index=years,
    ).T

    metrics = {}
    if len(revenues) >= 2 and revenues[0] > 0:
      start_val = revenues[0]
      end_val = revenues[-1]
      n = len(revenues) - 1
      cagr = ((end_val / start_val) ** (1 / n) - 1) * 100
      metrics["売上高 CAGR (%)"] = round(cagr, 2)
    else:
      metrics["売上高 CAGR (%)"] = 0.0

    rev_arr = np.array(revenues)
    cogs_arr = np.array(cogs)
    ebit_arr = np.array(ebit)

    valid_mask = rev_arr > 0
    if np.any(valid_mask):
      metrics["平均売上原価率 (%)"] = round(
          np.mean((cogs_arr[valid_mask] / rev_arr[valid_mask]) * 100), 2
      )
      metrics["平均営業利益率 (%)"] = round(
          np.mean((ebit_arr[valid_mask] / rev_arr[valid_mask]) * 100), 2
      )
    else:
      metrics["平均売上原価率 (%)"] = 55.0
      metrics["平均営業利益率 (%)"] = 15.0

    return df_hist, metrics

  except Exception as e:
    return None, {"error": str(e)}