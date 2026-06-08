from skills.stock_price_skill import get_recent_price_data
from skills.technical_analysis_skill import analyze_moving_averages
from strategies.breakout_strategy import check_breakout
from strategies.volume_surge_strategy import check_volume_surge


def main():
    print("Market Agent")
    print("Project skeleton is ready.")
    print()

    ticker = input("請輸入股票代號（例如：MU）：")

    price_data = get_recent_price_data(ticker)
    analysis_result = analyze_moving_averages(price_data)
    breakout_result = check_breakout(price_data)
    volume_surge_result = check_volume_surge(price_data)

    print()
    print(f"{ticker} 技術分析結果：")
    print(analysis_result) 

    print()
    print(f"{ticker} 突破策略結果：")
    print(breakout_result)

    print()
    print(f"{ticker} 成交量放大策略結果：")
    print(volume_surge_result)

if __name__ == "__main__":
    main()