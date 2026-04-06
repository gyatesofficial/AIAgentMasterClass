#!/usr/bin/env python3
"""
Build the System & Data Design Masterclass PDF from markdown modules.
Uses markdown → HTML → PDF (via weasyprint) with syntax highlighting.
"""

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from weasyprint import HTML
from pathlib import Path
import re

REWRITE_DIR = Path(__file__).parent
OUTPUT_PDF = REWRITE_DIR.parent / "Data_Engineering_Course.pdf"

# Ordered list of module files
MODULES = [
    "00-introduction.md",
    "01-foundations.md",
    "02-data-modeling.md",
    "03-storage-systems.md",
    "04-batch-processing.md",
    "05-stream-processing.md",
    "06-data-warehouse.md",
    "07-data-lake-lakehouse.md",
    "08-ml-platforms.md",
    "09-event-driven-systems.md",
    "10-observability.md",
    "11-cost-optimization.md",
    "12-case-studies.md",
    "13-interview-prep.md",
]

CSS = """
@page {
    size: A4;
    margin: 2.2cm 2cm 2.5cm 2cm;
    @bottom-center {
        content: "Data Engineering: From Foundations to Production";
        font-size: 8pt;
        color: #888;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
    @bottom-right {
        content: counter(page);
        font-size: 8pt;
        color: #888;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }
}

@page :first {
    margin-top: 0;
    @bottom-center { content: none; }
    @bottom-right { content: none; }
}

/* ---- Cover page ---- */
.cover {
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100vh;
    text-align: center;
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
    color: white;
    margin: -2.2cm -2cm -2.5cm -2cm;
    padding: 3cm 2cm;
}
.cover h1 {
    font-size: 36pt;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin-bottom: 0.3em;
    color: white;
    border: none;
}
.cover .subtitle {
    font-size: 16pt;
    font-weight: 300;
    color: #94a3b8;
    margin-bottom: 2em;
}
.cover .tagline {
    font-size: 11pt;
    color: #64748b;
    max-width: 28em;
    line-height: 1.6;
}

/* ---- TOC page ---- */
.toc-page {
    page-break-after: always;
}
.toc-page h2 {
    font-size: 22pt;
    color: #0f172a;
    border-bottom: 3px solid #3b82f6;
    padding-bottom: 0.3em;
    margin-bottom: 1em;
}
.toc-page ul {
    list-style: none;
    padding: 0;
}
.toc-page li {
    padding: 0.45em 0;
    border-bottom: 1px solid #e2e8f0;
    font-size: 11pt;
    color: #334155;
}
.toc-page li strong {
    color: #0f172a;
}
.toc-page li a {
    color: #334155;
    text-decoration: none;
}
.toc-page li a:hover {
    color: #2563eb;
}

/* ---- Base typography ---- */
body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1e293b;
}

/* ---- Headings ---- */
h1 {
    font-size: 24pt;
    font-weight: 800;
    color: #0f172a;
    margin-top: 0;
    padding-top: 0.5em;
    padding-bottom: 0.3em;
    border-bottom: 3px solid #3b82f6;
    page-break-before: always;
    letter-spacing: -0.3px;
}

/* First h1 in body (after cover+toc) should not break */
.module-content:first-of-type h1:first-child {
    page-break-before: avoid;
}

h2 {
    font-size: 16pt;
    font-weight: 700;
    color: #1e40af;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    padding-bottom: 0.2em;
    border-bottom: 1.5px solid #dbeafe;
}

h3 {
    font-size: 13pt;
    font-weight: 700;
    color: #1e3a5f;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
}

h4 {
    font-size: 11pt;
    font-weight: 700;
    color: #475569;
    margin-top: 1em;
    margin-bottom: 0.3em;
}

/* ---- Paragraphs ---- */
p {
    margin-top: 0.4em;
    margin-bottom: 0.6em;
    text-align: justify;
    hyphens: auto;
}

/* ---- Links ---- */
a {
    color: #2563eb;
    text-decoration: none;
}

/* ---- Lists ---- */
ul, ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
}
li {
    margin-bottom: 0.25em;
}

/* ---- Code: inline ---- */
code {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
    font-size: 9pt;
    background: #f1f5f9;
    color: #be185d;
    padding: 0.1em 0.35em;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}

/* ---- Code: blocks ---- */
pre {
    background: #1e1e2e;
    color: #cdd6f4;
    padding: 1em 1.2em;
    border-radius: 8px;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
    font-size: 8.5pt;
    line-height: 1.5;
    overflow-x: auto;
    margin: 0.8em 0 1em 0;
    page-break-inside: avoid;
    border-left: 4px solid #3b82f6;
    white-space: pre-wrap;
    word-wrap: break-word;
}

pre code {
    background: none;
    color: inherit;
    padding: 0;
    border: none;
    font-size: inherit;
    border-radius: 0;
}

/* ---- Syntax highlighting (Catppuccin Mocha - high contrast on dark bg) ---- */
/* Default text — bright white for maximum readability */
.codehilite { color: #cdd6f4; }
.codehilite .n  { color: #cdd6f4; }  /* names: bright white */
.codehilite .p  { color: #cdd6f4; }  /* punctuation: bright white */

/* Keywords — bold vivid purple */
.codehilite .k,
.codehilite .kn,
.codehilite .kd,
.codehilite .kp,
.codehilite .kr { color: #cba6f7; font-weight: bold; }

/* Strings — bright green */
.codehilite .s,
.codehilite .s1,
.codehilite .s2,
.codehilite .sd,
.codehilite .sb,
.codehilite .sc,
.codehilite .sh,
.codehilite .sx { color: #a6e3a1; }

/* Comments — medium grey italic (still readable) */
.codehilite .c,
.codehilite .c1,
.codehilite .cm,
.codehilite .ch,
.codehilite .cs,
.codehilite .cpf { color: #9399b2; font-style: italic; }

/* Numbers — bright peach/orange */
.codehilite .mi,
.codehilite .mf,
.codehilite .mb,
.codehilite .mh,
.codehilite .mo,
.codehilite .il { color: #fab387; }

/* Builtins — bright blue */
.codehilite .nb { color: #89b4fa; }
.codehilite .bp { color: #89b4fa; }

/* Functions — vivid blue */
.codehilite .nf,
.codehilite .fm { color: #89b4fa; font-weight: bold; }

/* Classes — bright yellow */
.codehilite .nc { color: #f9e2af; font-weight: bold; }

/* Module/namespace names — yellow */
.codehilite .nn { color: #f9e2af; }

/* Operators — bright sky blue */
.codehilite .o  { color: #89dceb; }
.codehilite .ow { color: #cba6f7; font-weight: bold; }

/* Decorators — bright mauve */
.codehilite .nd { color: #f5c2e7; font-weight: bold; }

/* Exceptions — bright red */
.codehilite .ne { color: #f38ba8; font-weight: bold; }

/* String escape/interpolation — bright teal */
.codehilite .se { color: #94e2d5; }
.codehilite .si { color: #94e2d5; }
.codehilite .sa { color: #a6e3a1; }

/* Variables — bright lavender */
.codehilite .nv,
.codehilite .vi,
.codehilite .vm { color: #b4befe; }

/* Constants / attributes */
.codehilite .no { color: #fab387; }
.codehilite .na { color: #89dceb; }
.codehilite .nt { color: #f38ba8; }  /* HTML/XML tags */

/* Preprocessor */
.codehilite .cp { color: #f9e2af; }

/* Generic markers for diffs etc */
.codehilite .gd { color: #f38ba8; }  /* deleted: red */
.codehilite .gi { color: #a6e3a1; }  /* inserted: green */

/* ---- Blockquotes (Key Takeaway boxes) ---- */
blockquote {
    background: #eff6ff;
    border-left: 4px solid #3b82f6;
    margin: 1em 0;
    padding: 0.8em 1.2em;
    border-radius: 0 6px 6px 0;
    page-break-inside: avoid;
}
blockquote p {
    margin: 0.2em 0;
    text-align: left;
    color: #1e3a5f;
    font-size: 10pt;
}
blockquote strong {
    color: #1e40af;
}

/* ---- Tables ---- */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
thead {
    background: #1e3a5f;
    color: white;
}
th {
    padding: 0.5em 0.8em;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
td {
    padding: 0.45em 0.8em;
    border-bottom: 1px solid #e2e8f0;
    vertical-align: top;
}
tr:nth-child(even) {
    background: #f8fafc;
}

/* ---- Horizontal rules (section separators) ---- */
hr {
    border: none;
    border-top: 1.5px solid #cbd5e1;
    margin: 2em 0;
}

/* ---- Strong and emphasis ---- */
strong { color: #0f172a; }
em { color: #475569; }

/* ---- ASCII diagrams (non-highlighted code blocks) ---- */
pre:not(.codehilite) {
    background: #f1f5f9;
    color: #1e293b;
    border-left: 4px solid #64748b;
    font-size: 8.5pt;
    font-weight: 500;
}
"""

def build_toc():
    """Generate a table of contents from module file names."""
    entries = [
        ("Module 0: Welcome & Setup", "00"),
        ("Module 1: Data Modeling Foundations", "01"),
        ("Module 2: SQL for Data Engineers", "02"),
        ("Module 3: Python for Data Engineers", "03"),
        ("Module 4: Apache Airflow — Orchestration", "04"),
        ("Module 5: Apache Spark & Big Data Processing", "05"),
        ("Module 6: Apache Kafka & Streaming", "06"),
        ("Module 7: Data Quality & Testing", "07"),
        ("Module 8: Cloud Infrastructure for Data Engineers", "08"),
        ("Module 9: Data Engineering for AI", "09"),
        ("Module 10: Capstone Project — Real-Time E-Commerce Analytics", "10"),
        ("Appendix A: Career Resources & Cost Optimization", "11"),
        ("Appendix B: Real-World Case Studies", "12"),
        ("Appendix C: Interview Preparation", "13"),
    ]
    items = "\n".join(f'  <li><a href="#module-{num}"><strong>{num}</strong> &mdash; {title}</a></li>'
                       for title, num in entries)
    return f"""
<div class="toc-page">
  <h2>Table of Contents</h2>
  <ul>
{items}
  </ul>
</div>
"""


def convert_md_to_html(md_text: str) -> str:
    """Convert markdown to HTML with syntax highlighting."""
    extensions = [
        FencedCodeExtension(),
        CodeHiliteExtension(
            linenums=False,
            css_class='codehilite',
            guess_lang=True,
            use_pygments=True,
        ),
        TableExtension(),
        TocExtension(),
        'smarty',
    ]
    return markdown.markdown(md_text, extensions=extensions)


def main():
    print("Building Data Engineering: From Foundations to Production PDF...")

    # Read all modules
    all_html_parts = []
    for filename in MODULES:
        filepath = REWRITE_DIR / filename
        if not filepath.exists():
            print(f"  WARNING: {filename} not found, skipping")
            continue
        md_text = filepath.read_text(encoding="utf-8")
        html = convert_md_to_html(md_text)
        # Extract module number from filename (e.g. "04-batch-processing.md" → "04")
        module_id = filename.split("-")[0]
        all_html_parts.append(f'<div class="module-content" id="module-{module_id}">{html}</div>')
        print(f"  ✓ {filename}")

    # Build cover page
    cover = """
<div class="cover">
  <h1>Data Engineering</h1>
  <div class="subtitle">From Foundations to Production</div>
  <div class="tagline">
    Modules 0–10 &middot; Hands-on Practitioner's Guide<br>
    2026 Edition
  </div>
</div>
"""

    # Assemble full document
    toc = build_toc()
    body = "\n".join(all_html_parts)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Data Engineering: From Foundations to Production</title>
  <style>{CSS}</style>
</head>
<body>
{cover}
{toc}
{body}
</body>
</html>"""

    # Also save the HTML for reference
    html_path = REWRITE_DIR / "combined.html"
    html_path.write_text(full_html, encoding="utf-8")
    print(f"  ✓ Combined HTML saved to {html_path}")

    # Generate PDF
    print("  Generating PDF (this may take a minute)...")
    HTML(string=full_html).write_pdf(str(OUTPUT_PDF))

    # Report file size
    size_mb = OUTPUT_PDF.stat().st_size / (1024 * 1024)
    print(f"\n✅ PDF generated: {OUTPUT_PDF}")
    print(f"   Size: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
