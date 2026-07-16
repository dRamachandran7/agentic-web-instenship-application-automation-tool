"""Compiles LaTeX source to PDF with Tectonic, run as a subprocess so this
service has no external LaTeX-install dependency (Tectonic self-fetches the
packages it needs on first use).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .config import settings

# `\input{glyphtounicode}` + `\pdfgentounicode=1` are pdfTeX-only primitives
# used for PDF text-extraction/ATS glyph mapping. They're extremely common
# boilerplate in resume templates (e.g. Jake's Resume) but undefined under
# Tectonic's XeTeX-based engine, which fails the whole compile. They're safe
# to drop: XeTeX handles Unicode text natively, so the ATS-mapping they exist
# for isn't needed under this engine anyway.
_PDFTEX_ONLY_LINE_RE = re.compile(
    r"^[ \t]*\\(?:input\{glyphtounicode\}|pdfgentounicode=1)[ \t]*$",
    re.MULTILINE,
)


class RenderError(RuntimeError):
    """Raised when Tectonic compilation fails."""


def _strip_pdftex_only_commands(tex_source: str) -> str:
    return _PDFTEX_ONLY_LINE_RE.sub(lambda m: "% " + m.group(0).strip() + "  % stripped: unsupported by Tectonic", tex_source)


def compile_pdf(tex_source: str) -> bytes:
    tex_source = _strip_pdftex_only_commands(tex_source)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tex_file = tmp_path / "resume.tex"
        tex_file.write_text(tex_source, encoding="utf-8")

        try:
            result = subprocess.run(
                [settings.tectonic_bin, str(tex_file), "--outdir", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=settings.compile_timeout_s,
            )
        except FileNotFoundError as exc:
            raise RenderError(
                f"'{settings.tectonic_bin}' not found on PATH. Install Tectonic: "
                "https://tectonic-typesetting.github.io/en-US/install.html"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"Tectonic compilation timed out after {settings.compile_timeout_s}s"
            ) from exc

        if result.returncode != 0:
            raise RenderError(f"Tectonic compilation failed:\n{result.stderr or result.stdout}")

        pdf_file = tmp_path / "resume.pdf"
        if not pdf_file.exists():
            raise RenderError("Tectonic reported success but no PDF was produced")
        return pdf_file.read_bytes()
