from __future__ import annotations

from pathlib import Path


def pick_html_file(title: str = "Select memories_history.html") -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    try:
        root.wm_attributes("-topmost", 1)
    except Exception:
        pass

    try:
        selected = filedialog.askopenfilename(
            title=title,
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    if not selected:
        return None
    return Path(selected)


def show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return

    root = tk.Tk()
    root.withdraw()
    try:
        root.wm_attributes("-topmost", 1)
    except Exception:
        pass

    try:
        messagebox.showerror(title, message)
    finally:
        try:
            root.destroy()
        except Exception:
            pass

