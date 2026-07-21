from __future__ import annotations

import json
import re


def parse_first_json_object(raw: str, *, error_message: str) -> dict:
    """Extract the first valid JSON object from a model response."""
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(text)
    decoder = json.JSONDecoder()

    for candidate in candidates:
        for match in re.finditer(r"\{", candidate):
            try:
                value, _ = decoder.raw_decode(candidate[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value

    raise ValueError(error_message)
