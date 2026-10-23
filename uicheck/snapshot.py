"""Data model shared by the browser scanner and the offline auditor."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field


@dataclass
class ViewportResult:
    """What one viewport size observed on one route."""

    width: int
    height: int
    label: str = ""
    # None means "not measured" (offline mode); True/False come from the browser.
    horizontal_overflow: bool | None = None
    scroll_width: int | None = None
    client_width: int | None = None
    screenshot_png: bytes | None = None

    def screenshot_data_uri(self) -> str | None:
        if self.screenshot_png is None:
            return None
        return "data:image/png;base64," + base64.b64encode(self.screenshot_png).decode("ascii")


@dataclass
class PageSnapshot:
    """Everything a check needs to know about one visited route."""

    route: str
    url: str
    html: str = ""
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    # internal href -> HTTP status, or None if the request never completed.
    link_statuses: dict[str, int | None] = field(default_factory=dict)
    viewports: list[ViewportResult] = field(default_factory=list)

    def to_json(self) -> str:
        def encode(vp: ViewportResult) -> dict:
            d = {k: v for k, v in vp.__dict__.items() if k != "screenshot_png"}
            if vp.screenshot_png is not None:
                d["screenshot_b64"] = base64.b64encode(vp.screenshot_png).decode("ascii")
            return d

        return json.dumps(
            {
                "route": self.route,
                "url": self.url,
                "html": self.html,
                "console_errors": self.console_errors,
                "page_errors": self.page_errors,
                "failed_requests": self.failed_requests,
                "link_statuses": self.link_statuses,
                "viewports": [encode(vp) for vp in self.viewports],
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "PageSnapshot":
        data = json.loads(text)
        viewports = []
        for d in data.get("viewports", []):
            b64 = d.pop("screenshot_b64", None)
            vp = ViewportResult(**d)
            if b64:
                vp.screenshot_png = base64.b64decode(b64)
            viewports.append(vp)
        return cls(
            route=data["route"],
            url=data["url"],
            html=data.get("html", ""),
            console_errors=data.get("console_errors", []),
            page_errors=data.get("page_errors", []),
            failed_requests=data.get("failed_requests", []),
            link_statuses=data.get("link_statuses", {}),
            viewports=viewports,
        )
