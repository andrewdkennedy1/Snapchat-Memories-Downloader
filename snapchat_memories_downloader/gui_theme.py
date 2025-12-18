from __future__ import annotations

import flet as ft

# Snapchat-ish colors (dark UI)
SC_YELLOW = "#FFFC00"
SC_BLACK = "#000000"
SC_GREY = "#1D1D1D"
SC_WHITE = "#FFFFFF"


def icon(name: str, fallback_name: str = "CIRCLE") -> ft.IconData:
    fallback = getattr(ft.Icons, fallback_name, None)
    return getattr(ft.Icons, name, fallback)

