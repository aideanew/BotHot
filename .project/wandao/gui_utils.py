#!/usr/bin/env python3
# Author: tllovesxs
"""Small Tkinter helpers shared by Wandao GUI tools."""

from __future__ import annotations

import tkinter as tk


def create_scrollable_body(root: tk.Tk | tk.Toplevel) -> tk.Frame:
    """Return a full-window frame whose content can scroll vertically."""
    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    body = tk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=body, anchor="nw")

    def update_scroll_region(_event: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def fit_body_width(event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    def on_mousewheel(event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-delta / 120), "units")

    def on_linux_scroll_up(_event: tk.Event) -> None:
        canvas.yview_scroll(-3, "units")

    def on_linux_scroll_down(_event: tk.Event) -> None:
        canvas.yview_scroll(3, "units")

    def bind_wheel(_event: tk.Event) -> None:
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_linux_scroll_up)
        canvas.bind_all("<Button-5>", on_linux_scroll_down)

    def unbind_wheel(_event: tk.Event) -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    body.bind("<Configure>", update_scroll_region)
    canvas.bind("<Configure>", fit_body_width)
    canvas.bind("<Enter>", bind_wheel)
    canvas.bind("<Leave>", unbind_wheel)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return body


def create_collapsible_section(
    parent: tk.Misc,
    title: str,
    *,
    open_by_default: bool = False,
) -> tuple[tk.Frame, tk.Button]:
    """Create a simple collapsible section and return its content frame."""
    wrapper = tk.Frame(parent)
    wrapper.pack(fill="x", padx=14, pady=(4, 0))

    header = tk.Frame(wrapper)
    header.pack(fill="x")
    content = tk.Frame(wrapper)
    expanded = tk.BooleanVar(value=open_by_default)

    def refresh() -> None:
        if expanded.get():
            toggle.configure(text=f"▼ {title}")
            content.pack(fill="x", pady=(6, 0))
        else:
            toggle.configure(text=f"▶ {title}")
            content.pack_forget()

    def toggle_section() -> None:
        expanded.set(not expanded.get())
        refresh()

    toggle = tk.Button(header, text="", command=toggle_section, anchor="w", relief="flat")
    toggle.pack(fill="x")
    refresh()
    return content, toggle
