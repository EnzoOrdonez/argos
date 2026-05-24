"""
Pipeline ARGOS: markdown → HTML interactivo + PDF estilo IDE.

Lee un .md, lo convierte con pandoc, post-procesa los <pre><code> para envolverlos
en .codeblock con barra superior (lang + dots + copy button), y genera:
  - <name>.html   (interactivo, copy buttons funcionales)
  - <name>.pdf    (weasyprint, copy buttons ocultos)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import weasyprint

REPO = Path(__file__).resolve().parents[2].parent   # repo root
BUILD = Path(__file__).resolve().parent              # docs/team/_build
CSS = BUILD / "style.css"

# Mapeo language hint → label en la barra
LANG_LABELS = {
    "bash":       "bash",
    "sh":         "shell",
    "shell":      "shell",
    "powershell": "powershell",
    "ps1":        "powershell",
    "python":     "python",
    "py":         "python",
    "sql":        "sql",
    "yaml":       "yaml",
    "yml":        "yaml",
    "json":       "json",
    "xml":        "xml",
    "ruby":       "ruby",
    "ini":        "ini",
    "ruby":       "ruby",
    "makefile":   "makefile",
    "make":       "makefile",
    "dockerfile": "dockerfile",
    "text":       "salida esperada",
    "output":     "salida esperada",
    "verify":     "verificación",
    "check":      "verificación",
}

# language hints que NO son comandos copiables (outputs, plaintext)
OUTPUT_LANGS = {"text", "output"}
VERIFY_LANGS = {"verify", "check"}


def md_to_html(md_path: Path) -> str:
    out = subprocess.run(
        ["pandoc", "--from=gfm", "--to=html5", "--no-highlight", str(md_path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


# Pandoc 2.9 emits: <pre class="bash"><code>...</code></pre>
# Pandoc with highlight: <pre><code class="language-bash">...</code></pre>
# Support both.
_PRE_CODE_RE = re.compile(
    r'<pre(?:\s+class="([\w-]+)")?>\s*<code(?:\s+class="([\w-]+)")?>(.*?)</code></pre>',
    re.DOTALL,
)


def _wrap_code_block(match: re.Match) -> str:
    pre_cls = match.group(1) or ""
    code_cls = match.group(2) or ""
    body = match.group(3)
    cls = code_cls or pre_cls
    lang = cls.replace("language-", "").lower()
    label = LANG_LABELS.get(lang, lang or "código")
    extra_class = ""
    show_copy = True
    if lang in OUTPUT_LANGS:
        extra_class = " output"
        show_copy = False
    elif lang in VERIFY_LANGS:
        extra_class = " verify"
    btn = (
        '<button class="copy-btn" type="button" onclick="copyCode(this)">Copiar</button>'
        if show_copy else ""
    )
    return (
        f'<div class="codeblock{extra_class}">'
        f'<div class="bar">'
        f'<span><span class="dots"><span></span><span></span><span></span></span>'
        f'<span class="lang">{label}</span></span>'
        f'{btn}'
        f'</div>'
        f'<pre><code class="language-{lang}">{body}</code></pre>'
        f'</div>'
    )


    return html


COPY_JS = """
function copyCode(btn) {
  const block = btn.closest('.codeblock');
  const code = block.querySelector('code');
  const text = code.innerText;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✓ Copiado';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove('copied');
    }, 1400);
  }).catch(err => {
    btn.textContent = 'Error';
    console.error(err);
  });
}
"""


def post_process_html(html: str) -> str:
    """Wrap pandoc <pre>...<code> blocks in styled .codeblock divs."""
    return _PRE_CODE_RE.sub(_wrap_code_block, html)


def build_full_html(
    *,
    title: str,
    cover_subtitle: str,
    role_line: str,
    cover_meta_html: str,
    parts: list[tuple[str, str]],   # [(heading, html_body), ...]
    include_js: bool,
) -> str:
    css = CSS.read_text(encoding="utf-8")
    parts_html = ""
    for i, (heading, body) in enumerate(parts):
        if i > 0:
            parts_html += '<div class="page-break"></div>'
        parts_html += f'<h1>{heading}</h1>\n{body}\n'
    js = f"<script>{COPY_JS}</script>" if include_js else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="cover">
  <div class="brand">ARGOS</div>
  <div class="tag">Adaptive Response Guard with Orchestrated Surveillance</div>
  <h2>Manual del integrante</h2>
  <div class="role">{cover_subtitle}</div>
  <div class="role" style="margin-top:0.4rem;font-size:0.9rem;opacity:0.85">{role_line}</div>
  <div class="deadline">Entrega final: <strong>13 de junio de 2026</strong></div>
  <div class="meta">{cover_meta_html}</div>
</div>
<div class="page-break"></div>
<div class="page-wrap">
{parts_html}
</div>
{js}
</body>
</html>"""


def build_one(
    *,
    short: str,
    full_name: str,
    role_subtitle: str,
    individual_md: Path,
    common_md: Path | None,
    out_dir: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    title = f"ARGOS — Manual {full_name}"
    cover_meta = (
        "Universidad de Lima · Tópicos Avanzados de Ciberseguridad · 2026-1<br/>"
        "Versión 3.0 — manual organizado por orden de implementación"
    )
    role_line = role_subtitle

    parts: list[tuple[str, str]] = []
    if common_md and common_md.exists():
        common_html = post_process_html(md_to_html(common_md))
        parts.append(("Parte I — Introducción común al proyecto", common_html))
    individual_html = post_process_html(md_to_html(individual_md))
    parts.append((f"Parte II — Manual de {full_name}", individual_html))

    # HTML interactivo (con copy buttons)
    html_interactive = build_full_html(
        title=title, cover_subtitle=full_name, role_line=role_line,
        cover_meta_html=cover_meta, parts=parts, include_js=True,
    )
    base_slug = full_name.lower().replace(" ", "-").replace("ñ", "n") \
                          .replace("á","a").replace("é","e").replace("í","i") \
                          .replace("ó","o").replace("ú","u")
    html_path = out_dir / f"argos-manual-{short}-{base_slug}.html"
    html_path.write_text(html_interactive, encoding="utf-8")

    # PDF (sin JS, copy buttons ocultos por CSS print)
    pdf_html = build_full_html(
        title=title, cover_subtitle=full_name, role_line=role_line,
        cover_meta_html=cover_meta, parts=parts, include_js=False,
    )
    pdf_path = out_dir / f"argos-manual-{short}-{base_slug}.pdf"
    weasyprint.HTML(string=pdf_html, base_url=str(REPO)).write_pdf(str(pdf_path))

    return html_path, pdf_path


def main():
    if len(sys.argv) < 5:
        print("usage: build_manual.py <short> <full_name> <role_subtitle> <individual_md> [common_md]")
        sys.exit(2)
    short = sys.argv[1]
    full_name = sys.argv[2]
    role_subtitle = sys.argv[3]
    individual_md = Path(sys.argv[4])
    common_md = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    out_dir = individual_md.parent / "out"
    html, pdf = build_one(
        short=short, full_name=full_name, role_subtitle=role_subtitle,
        individual_md=individual_md, common_md=common_md, out_dir=out_dir,
    )
    try:
        print(f"OK  HTML: {html.relative_to(REPO)}")
    except ValueError:
        print(f"OK  HTML: {html}")
    try:
        print(f"OK  PDF:  {pdf.relative_to(REPO)}  ({pdf.stat().st_size//1024} KB)")
    except ValueError:
        print(f"OK  PDF:  {pdf}  ({pdf.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
