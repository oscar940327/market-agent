import csv
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from data.themes import THEMES


WIKIPEDIA_NASDAQ100_API_URL = (
    "https://en.wikipedia.org/w/api.php?"
    "action=parse&page=Nasdaq-100&prop=text&format=json"
)
NASDAQ100_PROVIDER = "wikipedia_nasdaq100_components"
QQQ100_UNIVERSE = "QQQ100"


@dataclass
class UniverseFetchResult:
    status: str
    provider: str
    records: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    source_url: str = WIKIPEDIA_NASDAQ100_API_URL
    fetched_at: str | None = None


class WikitableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._in_wikitable = False
        self._table_depth = 0
        self._current_table = []
        self._current_row = None
        self._current_cell = None
        self._current_cell_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "table":
            class_names = attrs_dict.get("class", "")
            if not self._in_wikitable and "wikitable" in class_names:
                self._in_wikitable = True
                self._table_depth = 1
                self._current_table = []
                return

            if self._in_wikitable:
                self._table_depth += 1
                return

        if not self._in_wikitable:
            return

        if tag == "tr":
            self._current_row = []
            return

        if tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []
            self._current_cell_tag = tag

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag):
        if not self._in_wikitable:
            return

        if tag in {"th", "td"} and self._current_cell is not None:
            text = clean_cell_text("".join(self._current_cell))
            self._current_row.append({"tag": self._current_cell_tag, "text": text})
            self._current_cell = None
            self._current_cell_tag = None
            return

        if tag == "tr" and self._current_row is not None:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None
            return

        if tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self.tables.append(self._current_table)
                self._current_table = []
                self._in_wikitable = False


def fetch_nasdaq100_components(open_url=urlopen) -> UniverseFetchResult:
    fetched_at = utc_now_iso()
    request = Request(
        WIKIPEDIA_NASDAQ100_API_URL,
        headers={
            "User-Agent": "market-agent/0.1 universe-provider",
            "Accept": "application/json",
        },
    )

    try:
        with open_url(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return UniverseFetchResult(
            status="provider_error",
            provider=NASDAQ100_PROVIDER,
            errors=[{"message": str(exc)}],
            fetched_at=fetched_at,
        )

    html = payload.get("parse", {}).get("text", {}).get("*", "")
    components = parse_nasdaq100_components_html(html)

    if not components:
        return UniverseFetchResult(
            status="no_components",
            provider=NASDAQ100_PROVIDER,
            errors=[{"message": "Could not find Nasdaq-100 components table."}],
            fetched_at=fetched_at,
        )

    records = [
        normalize_universe_record(component=component, fetched_at=fetched_at)
        for component in components
    ]

    return UniverseFetchResult(
        status="success",
        provider=NASDAQ100_PROVIDER,
        records=records,
        fetched_at=fetched_at,
    )


def parse_nasdaq100_components_html(html: str) -> list[dict]:
    parser = WikitableParser()
    parser.feed(html)

    for table in parser.tables:
        parsed = parse_component_table(table)
        if parsed:
            return parsed

    return []


def parse_component_table(table: list[list[dict]]) -> list[dict]:
    if not table:
        return []

    header_index = None
    headers = []

    for index, row in enumerate(table):
        candidate_headers = [cell["text"] for cell in row]
        normalized_headers = [normalize_header(header) for header in candidate_headers]

        if has_header(normalized_headers, "ticker", "symbol") and has_header(
            normalized_headers,
            "company",
            "security",
            "name",
        ):
            header_index = index
            headers = normalized_headers
            break

    if header_index is None:
        return []

    ticker_index = find_header_index(headers, "ticker", "symbol")
    name_index = find_header_index(headers, "company", "security", "name")
    industry_index = find_header_index(headers, "industry", "sector")

    if ticker_index is None or name_index is None:
        return []

    components = []

    for row in table[header_index + 1 :]:
        values = [cell["text"] for cell in row]
        if len(values) <= max(ticker_index, name_index):
            continue

        ticker = clean_ticker(values[ticker_index])
        name = values[name_index].strip()
        industry = (
            values[industry_index].strip()
            if industry_index is not None and len(values) > industry_index
            else None
        )

        if ticker:
            components.append(
                {
                    "ticker": ticker,
                    "name": name or None,
                    "industry": industry or None,
                }
            )

    return components


def normalize_universe_record(*, component: dict, fetched_at: str) -> dict:
    ticker = clean_ticker(component.get("ticker", ""))

    return {
        "ticker": ticker,
        "name": clean_optional_text(component.get("name")),
        "industry": clean_optional_text(component.get("industry")),
        "themes": get_ticker_theme_keys(ticker),
        "market_cap_bucket": None,
        "volatility_bucket": None,
        "universe": QQQ100_UNIVERSE,
        "universe_provider": NASDAQ100_PROVIDER,
        "is_active": True,
        "first_seen_at": fetched_at,
        "last_seen_at": fetched_at,
        "updated_at": fetched_at,
    }


def write_universe_snapshot(
    *,
    records: list[dict],
    output_dir: str | Path = "data/market/universe",
    snapshot_date: str | None = None,
) -> Path:
    date_label = snapshot_date or datetime.now().astimezone().date().isoformat()
    output_path = Path(output_dir) / f"qqq100_universe_{date_label}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "ticker",
        "name",
        "industry",
        "themes",
        "universe",
        "universe_provider",
        "is_active",
        "first_seen_at",
        "last_seen_at",
        "updated_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field) for field in fieldnames}
            row["themes"] = ";".join(record.get("themes") or [])
            writer.writerow(row)

    return output_path


def write_missing_metadata_report(
    *,
    records: list[dict],
    output_dir: str | Path = "data/market/universe",
    snapshot_date: str | None = None,
) -> tuple[Path, list[dict]]:
    date_label = snapshot_date or datetime.now().astimezone().date().isoformat()
    output_path = Path(output_dir) / f"qqq100_missing_metadata_{date_label}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    missing_rows = build_missing_metadata_rows(records)
    fieldnames = [
        "ticker",
        "missing_fields",
        "name",
        "industry",
        "themes",
        "universe_provider",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(missing_rows)

    return output_path, missing_rows


def build_missing_metadata_rows(records: list[dict]) -> list[dict]:
    missing_rows = []

    for record in records:
        missing_fields = []

        if not record.get("name"):
            missing_fields.append("name")
        if not record.get("industry"):
            missing_fields.append("industry")
        if not record.get("themes"):
            missing_fields.append("themes")

        if missing_fields:
            missing_rows.append(
                {
                    "ticker": record["ticker"],
                    "missing_fields": ";".join(missing_fields),
                    "name": record.get("name") or "",
                    "industry": record.get("industry") or "",
                    "themes": ";".join(record.get("themes") or []),
                    "universe_provider": record.get("universe_provider") or "",
                }
            )

    return missing_rows


def get_ticker_theme_keys(ticker: str) -> list[str]:
    normalized_ticker = ticker.upper()
    theme_keys = []

    for theme_key, theme in THEMES.items():
        if normalized_ticker in theme["tickers"]:
            theme_keys.append(theme_key)

    return theme_keys


def clean_cell_text(value: str) -> str:
    value = re.sub(r"\[[^\]]+\]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = clean_cell_text(str(value))
    return cleaned or None


def clean_ticker(value: str) -> str:
    value = clean_cell_text(value)
    value = value.split()[0] if value else ""
    value = re.sub(r"[^A-Za-z0-9.\-]", "", value)
    return value.upper()


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def has_header(headers: list[str], *needles: str) -> bool:
    return find_header_index(headers, *needles) is not None


def find_header_index(headers: list[str], *needles: str) -> int | None:
    for index, header in enumerate(headers):
        if any(needle in header for needle in needles):
            return index

    return None


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
