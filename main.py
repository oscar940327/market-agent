from skills.stock_price_skill import get_recent_price_data
from skills.technical_analysis_skill import analyze_moving_averages

def main():
    print("Market Agent")
    print("Project skeleton is ready.")
    print()

    ticker = input("請輸入股票代號（例如：MU）：")

    price_data = get_recent_price_data(ticker)
    analysis_result = analyze_moving_averages(price_data)

    print()
    print(f"{ticker} 技術分析結果：")
    print(analysis_result) 

if __name__ == "__main__":
    main()