from __future__ import annotations

"""Ice/cyber glass theme for Argus NiceGUI pages."""

from nicegui import ui

_THEME_APPLIED = False

ICE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
  :root {
    --ice-bg: #060a14;
    --ice-panel: rgba(15, 25, 45, 0.65);
    --ice-border: rgba(77, 208, 225, 0.28);
    --ice-cyan: #4dd0e1;
    --ice-glow: rgba(77, 208, 225, 0.35);
    --ice-muted: #8ba3b8;
    --ice-text: #e8f4ff;
  }
  body, .nicegui-content {
    background-color: var(--ice-bg) !important;
    background-image:
      radial-gradient(circle at 20% 20%, rgba(77, 208, 225, 0.08), transparent 35%),
      radial-gradient(circle at 80% 0%, rgba(77, 208, 225, 0.06), transparent 30%),
      linear-gradient(rgba(77, 208, 225, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(77, 208, 225, 0.03) 1px, transparent 1px);
    background-size: auto, auto, 48px 48px, 48px 48px;
    color: var(--ice-text);
    font-family: 'Inter', sans-serif;
  }
  .ice-heading { font-size: 2rem; font-weight: 700; letter-spacing: 0.08em; color: var(--ice-text); text-shadow: 0 0 18px var(--ice-glow); }
  .ice-subheading { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--ice-muted); letter-spacing: 0.12em; text-transform: uppercase; }
  .ice-muted { color: var(--ice-muted) !important; }
  .ice-card {
    background: var(--ice-panel) !important;
    backdrop-filter: blur(12px);
    border: 1px solid var(--ice-border) !important;
    border-radius: 16px !important;
    box-shadow: 0 0 24px rgba(77, 208, 225, 0.08);
  }
  .ice-row {
    background: rgba(10, 18, 32, 0.55) !important;
    border: 1px solid rgba(77, 208, 225, 0.15) !important;
    border-radius: 12px !important;
  }
  .ice-thread {
    background: rgba(8, 14, 26, 0.75) !important;
    border: 1px solid var(--ice-border) !important;
    border-radius: 12px !important;
  }
  .ice-nav-link { color: var(--ice-muted); font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; cursor: pointer; }
  .ice-nav-link:hover { color: var(--ice-cyan); }
  .ice-logo { font-size: 1.1rem; font-weight: 700; letter-spacing: 0.2em; color: var(--ice-text); text-shadow: 0 0 16px var(--ice-glow); cursor: pointer; }
  .ice-footer { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: var(--ice-muted); letter-spacing: 0.1em; text-transform: uppercase; }
  .ice-login-card { min-height: 420px; }
  .ice-login-icon {
    width: 56px; height: 56px; border-radius: 14px;
    border: 1px solid var(--ice-border);
    display: flex; align-items: center; justify-content: center;
    margin: 0 auto; color: var(--ice-cyan);
    box-shadow: 0 0 20px rgba(77, 208, 225, 0.15);
  }
  .ice-google-btn {
    background: #fff !important; color: #1f1f1f !important;
    font-family: 'JetBrains Mono', monospace !important;
    letter-spacing: 0.06em; text-transform: uppercase;
    border-radius: 10px !important;
  }
  .ice-citation { color: var(--ice-cyan) !important; }
  .q-field__label, .q-field__native, .q-item__label { color: var(--ice-text) !important; }
  .q-field--outlined .q-field__control { border-color: var(--ice-border) !important; background: rgba(8, 14, 26, 0.6) !important; }
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
    with ui.row().classes('w-full max-w-6xl items-center justify-between mb-6 px-2'):
        ui.label('ARGUS').classes('ice-logo').on('click', lambda: ui.navigate.to('/'))
        with ui.row().classes('gap-6 items-center'):
            for label, path in [('Library', '/'), ('Study', '/chat')]:
                classes = 'ice-nav-link'
                if active == path:
                    classes += ' text-[#4dd0e1]'
                ui.label(label).classes(classes).on('click', lambda p=path: ui.navigate.to(p))
            ui.label('Logout').classes('ice-nav-link').on('click', lambda: ui.navigate.to('/logout'))
    ui.label('CRYSTAL_CORE v2.0').classes('ice-footer mb-4')


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
