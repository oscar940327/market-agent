from dataclasses import dataclass, field

import pandas as pd

from data_providers import stooq_provider, yfinance_provider


@dataclass
class PriceFetchResult:
    data: pd.DataFrame
    provider: str | None
    attempted_providers: list[str]
    errors: list[dict] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.provider is not None and self.data is not None and not self.data.empty


def fetch_recent_price_data(
    ticker: str,
    period: str = "6mo",
    providers: tuple[str, ...] = ("yfinance", "stooq"),
) -> PriceFetchResult:
    attempted_providers = []
    errors = []

    for provider in providers:
        attempted_providers.append(provider)

        try:
            data = fetch_from_provider(provider, ticker=ticker, period=period)
        except Exception as error:
            errors.append(
                {
                    "provider": provider,
                    "message": str(error),
                }
            )
            continue

        if data is not None and not data.empty:
            return PriceFetchResult(
                data=data,
                provider=provider,
                attempted_providers=attempted_providers,
                errors=errors,
            )

        errors.append(
            {
                "provider": provider,
                "message": "provider returned no price data",
            }
        )

    return PriceFetchResult(
        data=pd.DataFrame(),
        provider=None,
        attempted_providers=attempted_providers,
        errors=errors,
    )


def fetch_from_provider(provider: str, ticker: str, period: str) -> pd.DataFrame:
    if provider == "yfinance":
        return yfinance_provider.fetch_price_data(ticker=ticker, period=period)

    if provider == "stooq":
        return stooq_provider.fetch_price_data(ticker=ticker, period=period)

    raise ValueError(f"Unsupported price provider: {provider}")
