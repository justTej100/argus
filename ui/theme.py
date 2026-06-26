from __future__ import annotations

"""Ice/cyber glass theme for Argus NiceGUI pages."""

from contextlib import contextmanager
from typing import Iterator

from nicegui import ui

_THEME_APPLIED = False

ICE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
  :root {
    --ice-bg: #040810;
    --ice-panel: rgba(10, 22, 38, 0.72);
    --ice-border: rgba(77, 208, 225, 0.32);
    --ice-cyan: #4dd0e1;
    --ice-cyan-dim: rgba(77, 208, 225, 0.55);
    --ice-glow: rgba(77, 208, 225, 0.45);
    --ice-muted: #8ba3b8;
    --ice-text: #e8f4ff;
  }
  @keyframes icePulse {
    0%, 100% { opacity: 0.85; text-shadow: 0 0 12px var(--ice-glow); }
    50% { opacity: 1; text-shadow: 0 0 22px var(--ice-glow), 0 0 40px rgba(77, 208, 225, 0.15); }
  }
  @keyframes gridDrift {
    0% { background-position: 0 0, 0 0, 0 0, 0 0; }
    100% { background-position: 0 0, 0 0, 48px 48px, 48px 48px; }
  }
  body, .nicegui-content {
    background-color: var(--ice-bg) !important;
    background-image:
      radial-gradient(ellipse 80% 50% at 20% -10%, rgba(77, 208, 225, 0.12), transparent 55%),
      radial-gradient(ellipse 60% 40% at 90% 10%, rgba(100, 180, 255, 0.06), transparent 50%),
      linear-gradient(rgba(77, 208, 225, 0.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(77, 208, 225, 0.04) 1px, transparent 1px);
    background-size: auto, auto, 48px 48px, 48px 48px;
    animation: gridDrift 120s linear infinite;
    color: var(--ice-text);
    font-family: 'Inter', sans-serif;
    font-size: 15px;
    line-height: 1.55;
  }
  .ice-logo {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: 0.22em;
    color: var(--ice-text);
    text-shadow: 0 0 16px var(--ice-glow);
    animation: icePulse 4s ease-in-out infinite;
    cursor: pointer;
  }
  .ice-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ice-cyan-dim);
  }
  .ice-page-title {
    font-size: 1.65rem;
    font-weight: 700;
    color: var(--ice-text);
    text-shadow: 0 0 20px rgba(77, 208, 225, 0.2);
  }
  .ice-page-subtitle {
    font-size: 0.95rem;
    color: var(--ice-muted);
    margin-bottom: 1.25rem;
    line-height: 1.5;
  }
  .ice-section-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ice-cyan);
  }
  .ice-muted { color: var(--ice-muted) !important; }
  .ice-card, .ice-panel {
    background: var(--ice-panel) !important;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--ice-border) !important;
    border-radius: 14px !important;
    box-shadow: 0 0 28px rgba(77, 208, 225, 0.08), inset 0 1px 0 rgba(255,255,255,0.04);
  }
  .ice-monolith {
    border-color: rgba(77, 208, 225, 0.45) !important;
    box-shadow: 0 0 40px rgba(77, 208, 225, 0.12), inset 0 0 60px rgba(77, 208, 225, 0.03);
  }
  .ice-row {
    background: rgba(6, 14, 26, 0.65) !important;
    border: 1px solid rgba(77, 208, 225, 0.18) !important;
    border-radius: 10px !important;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .ice-row:hover {
    border-color: rgba(77, 208, 225, 0.35) !important;
    box-shadow: 0 0 16px rgba(77, 208, 225, 0.06);
  }
  .ice-thread {
    background: rgba(4, 10, 20, 0.8) !important;
    border: 1px solid var(--ice-border) !important;
    border-radius: 12px !important;
    box-shadow: inset 0 0 40px rgba(77, 208, 225, 0.03);
  }
  .ice-bubble-user {
    background: rgba(20, 40, 60, 0.7) !important;
    border: 1px solid rgba(77, 208, 225, 0.25) !important;
    border-radius: 10px !important;
  }
  .ice-bubble-assistant {
    background: rgba(8, 24, 40, 0.85) !important;
    border: 1px solid rgba(77, 208, 225, 0.4) !important;
    border-radius: 10px !important;
    box-shadow: 0 0 24px rgba(77, 208, 225, 0.1);
  }
  .ice-toolbar {
    background: rgba(8, 18, 32, 0.75) !important;
    border: 1px solid var(--ice-border) !important;
    border-radius: 12px !important;
    padding: 12px 16px;
  }
  .ice-nav-link {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ice-muted);
    cursor: pointer;
    padding: 0.4rem 0.65rem;
    border-radius: 6px;
    border-bottom: 2px solid transparent;
  }
  .ice-nav-link:hover { color: var(--ice-text); background: rgba(77, 208, 225, 0.06); }
  .ice-nav-active {
    color: var(--ice-cyan) !important;
    border-bottom-color: var(--ice-cyan) !important;
    text-shadow: 0 0 10px var(--ice-glow);
  }
  .ice-shell-bar {
    border-bottom: 1px solid rgba(77, 208, 225, 0.2) !important;
    margin-bottom: 1.5rem;
    padding-bottom: 0.75rem;
  }
  .ice-login-card { min-height: 400px; }
  .ice-login-icon {
    width: 58px; height: 58px; border-radius: 14px;
    border: 1px solid var(--ice-border);
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto; color: var(--ice-cyan);
    box-shadow: 0 0 24px rgba(77, 208, 225, 0.2);
  }
  .ice-google-btn {
    background: #fff !important; color: #1a1a1a !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
  }
  .ice-citation {
    font-family: 'JetBrains Mono', monospace;
    color: var(--ice-cyan) !important;
    font-size: 0.8rem;
    font-weight: 500;
  }
  .ice-status-ready { color: #86efac; background: rgba(34, 197, 94, 0.12); padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.05em; text-transform: uppercase; }
  .ice-status-processing { color: #fcd34d; background: rgba(245, 158, 11, 0.12); padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.05em; text-transform: uppercase; }
  .ice-status-error { color: #fca5a5; background: rgba(239, 68, 68, 0.12); padding: 2px 8px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.05em; text-transform: uppercase; }
  .ice-upload-status {
    background: rgba(4, 12, 24, 0.85);
    border: 1px solid var(--ice-border);
    border-radius: 10px;
    padding: 12px 14px;
  }
  .ice-upload-status-done { border-color: rgba(34, 197, 94, 0.45); box-shadow: 0 0 16px rgba(34, 197, 94, 0.08); }
  .ice-upload-status-error { border-color: rgba(239, 68, 68, 0.45); }
  .ice-hud-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ice-cyan-dim);
  }
  .q-field__label { color: var(--ice-muted) !important; font-size: 0.85rem !important; }
  .q-field__native, .q-item__label { color: var(--ice-text) !important; font-size: 0.95rem !important; }
  .q-field--outlined .q-field__control {
    border-color: var(--ice-border) !important;
    background: rgba(4, 10, 20, 0.75) !important;
    border-radius: 8px !important;
  }
  .q-field--outlined.q-field--focused .q-field__control {
    box-shadow: 0 0 0 1px rgba(77, 208, 225, 0.35) !important;
  }
  .q-btn { font-weight: 600 !important; }
  .q-linear-progress { color: var(--ice-cyan) !important; }
  .prose, .prose p, .prose li, .prose h1, .prose h2, .prose h3 { color: var(--ice-text) !important; }
</style>
"""


def apply_ice_theme() -> None:
    """Inject global ice theme assets once."""
    global _THEME_APPLIED
    if _THEME_APPLIED:
        return
    ui.add_head_html(ICE_CSS)
    _THEME_APPLIED = True


def ice_shell(active: str = '') -> None:
    """Render shared top navigation for authenticated pages."""
    with ui.row().classes('w-full max-w-6xl items-center justify-between ice-shell-bar px-2'):
        ui.label('ARGUS').classes('ice-logo').on('click', lambda: ui.navigate.to('/'))
        with ui.row().classes('gap-1 items-center'):
            for label, path in [('Library', '/'), ('Study', '/chat')]:
                classes = 'ice-nav-link ice-nav-active' if active == path else 'ice-nav-link'
                ui.label(label).classes(classes).on('click', lambda p=path: ui.navigate.to(p))
            ui.label('Log out').classes('ice-nav-link').on('click', lambda: ui.navigate.to('/logout'))
    ui.label('CRYSTAL_CORE v2.0').classes('ice-tag mb-4')


def ice_page_header(title: str, subtitle: str) -> None:
    """Consistent page hero block."""
    ui.label(title).classes('ice-page-title mb-1')
    ui.label(subtitle).classes('ice-page-subtitle')


@contextmanager
def ice_panel(*, monolith: bool = False, extra_classes: str = '') -> Iterator[None]:
    """Glass panel wrapper for page sections."""
    classes = 'w-full ice-panel p-6 gap-4'
    if monolith:
        classes += ' ice-monolith'
    if extra_classes:
        classes += f' {extra_classes}'
    with ui.card().classes(classes):
        yield


def status_chip(status: str) -> None:
    """Render a colored status label for document rows."""
    css = {
        'ready': 'ice-status-ready',
        'processing': 'ice-status-processing',
        'error': 'ice-status-error',
    }.get(status, 'ice-muted')
    ui.label(status.replace('_', ' ')).classes(css)


def render_ice_markdown(content: str) -> None:
    """Render markdown and typeset LaTeX with KaTeX."""
    element = ui.markdown(content).classes('prose max-w-none ice-markdown')
    element.id = f'ice-md-{element.id}'

    async def typeset() -> None:
        await ui.run_javascript(
            f"""
            (() => {{
              const el = document.getElementById('{element.id}');
              if (!el || !window.renderMathInElement) return;
              renderMathInElement(el, {{
                delimiters: [
                  {{left: '$$', right: '$$', display: true}},
                  {{left: '$', right: '$', display: false}}
                ],
                throwOnError: false
              }});
            }})();
            """
        )

    ui.timer(0.05, typeset, once=True)
