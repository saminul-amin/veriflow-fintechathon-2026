"""Render a project markdown document to a print-quality PDF with headless Chrome."""
import re
import subprocess
import sys
from pathlib import Path

import markdown

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font: 10.5pt/1.45 "Segoe UI", Calibri, Arial, sans-serif; color: #18202b; }
h1 { font-size: 21pt; color: #0f2a3d; margin: 0 0 4pt; }
h2 { font-size: 14pt; color: #0f2a3d; border-bottom: 1px solid #d5dee0; padding-bottom: 3pt; margin: 16pt 0 6pt; page-break-after: avoid; }
h3, h4 { color: #1d4e5f; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #eef3f2; padding: 0 3px; border-radius: 3px; }
pre { background: #f5f7f8; border: 1px solid #e3e8ea; border-radius: 6px; padding: 8pt; font-size: 8.2pt; line-height: 1.25; overflow: hidden; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.2pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #1d4e5f; color: #fff; text-align: left; padding: 4pt 6pt; }
td { border-bottom: 1px solid #e3e8ea; padding: 4pt 6pt; vertical-align: top; }
tr:nth-child(even) td { background: #f7f9f9; }
blockquote { border-left: 3px solid #12a37a; margin: 6pt 0; padding: 2pt 10pt; color: #33465a; background: #f2f8f6; }
img { max-width: 100%; max-height: 120mm; display: block; margin: 6pt auto 12pt; border: 1px solid #e3e8ea; border-radius: 6px; page-break-inside: avoid; }
hr { border: 0; border-top: 1px solid #d5dee0; margin: 10pt 0; }
.banner { background: #fff3dc; color: #8a5300; font-weight: 600; font-size: 9pt; padding: 4pt 8pt; border-radius: 4px; margin-bottom: 10pt; }
"""


def prepare(md: str) -> str:
    """Bridge GitHub-flavoured habits that Python-Markdown treats differently."""
    out, in_code = [], False
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("```"):
            in_code = not in_code
        prev = out[-1] if out else ""
        is_item = re.match(r"^\s*(?:[-*]|\d+\.)\s", line)
        prev_item = re.match(r"^\s*(?:[-*]|\d+\.)\s", prev)
        if not in_code and is_item and prev.strip() and not prev_item and not prev.startswith("|"):
            out.append("")
        # consecutive "**Label:** value" lines keep their line breaks
        if not in_code and re.match(r"^\*\*[^*]+:\*\*", line) and i + 1 < len(lines) and re.match(r"^\*\*[^*]+:\*\*", lines[i + 1]):
            line += "  "
        out.append(line)
    return "\n".join(out)


def main(src: str, out: str, tmp_dir: str) -> None:
    src_p = Path(src).resolve()
    body = markdown.markdown(prepare(src_p.read_text(encoding="utf-8")), extensions=["tables", "fenced_code", "sane_lists"])
    html = (f'<!doctype html><html><head><meta charset="utf-8"><base href="{src_p.parent.as_uri()}/">'
            f"<style>{CSS}</style></head><body>"
            '<div class="banner">VeriFlow · Team VeriFlow · FinTechathon 2026 International Track · Topic E · SYNTHETIC sandbox data</div>'
            f"{body}</body></html>")
    tmp = Path(tmp_dir) / (src_p.stem + ".html")
    tmp.write_text(html, encoding="utf-8")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                    f"--print-to-pdf={Path(out).resolve()}", tmp.resolve().as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
