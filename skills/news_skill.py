# 根據股票代號或關鍵字，抓取近期新聞資料，並整理成乾淨的 list[dict]

from urllib.parse import quote_plus
from urllib.request import urlopen
import xml.etree.ElementTree as ET

def get_stock_news(query: str, max_items: int = 5) -> list[dict]:
    encoded_query = quote_plus(query)

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    )

    with urlopen(rss_url) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    news_items = []

    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        published = item.findtext("pubDate", default="")

        news_items.append(
            {
                "title": title,
                "link": link,
                "published": published,
            }
        )

    return news_items