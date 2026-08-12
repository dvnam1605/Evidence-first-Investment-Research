"""Reproduce HOSE public endpoint behavior for DATA-10 blocker evidence."""

from __future__ import annotations

import httpx

URL = "https://www.hsx.vn/Modules/Listed/Web/DisclosureList"
PARAMS = {
    "pageFieldName1": "Code",
    "pageFieldValue1": "FPT",
    "pageFieldOperator1": "eq",
    "pageCriteriaLength": "1",
    "_search": "false",
    "rows": 3,
    "page": 1,
    "sidx": "PublicDate",
    "sord": "desc",
}


def main() -> None:
    response = httpx.get(
        URL,
        params=PARAMS,
        headers={
            "User-Agent": "InvestmentResearchBot/0.1",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    print("status:", response.status_code)
    print("content-type:", response.headers.get("content-type"))
    print("body-prefix:", response.text[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
