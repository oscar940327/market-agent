from skills.stock_price_skill import get_recent_price_data

def main():
    print("Market Agent")
    print("Project skeleton is ready.")
    print()

    ticker = input("請輸入股票代號（例如：MU）：")

    price_data = get_recent_price_data(ticker)

    print()
    print(f"{ticker} 近期股價：")
    print(price_data.tail()) # 印出最後 5 筆

if __name__ == "__main__":
    main()