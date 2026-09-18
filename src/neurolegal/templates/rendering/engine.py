"""docxtpl over python-docx: placeholder scan + deterministic render.

The render is a pure function of (template bytes, values): no LLM anywhere
near it, values are inserted as data (autoescape), Jinja syntax inside a
user value is not executed. Formatting of the .docx is preserved by docxtpl.
"""

from collections.abc import Mapping
from io import BytesIO

from docxtpl import DocxTemplate

from neurolegal.contracts import TemplateField


def scan_placeholders(data: bytes) -> list[str]:
    """All ``{{ … }}`` names of a template .docx, sorted for stable output."""
    tpl = DocxTemplate(BytesIO(data))
    return sorted(tpl.get_undeclared_template_variables())


def default_fields(names: list[str]) -> list[TemplateField]:
    """Fresh-scan defaults: the operator refines label/hint/kind by hand."""
    return [TemplateField(name=name, label=name) for name in names]


def render_docx(data: bytes, values: Mapping[str, str]) -> bytes:
    """Deterministic substitution of `values` into the template bytes.

    autoescape: user values are data — `<`, `&`, `{{ … }}` land in the
    document literally instead of breaking the XML or being executed.
    Placeholders absent from `values` (optional fields) render as empty.
    """
    tpl = DocxTemplate(BytesIO(data))
    tpl.render(dict(values), autoescape=True)
    out = BytesIO()
    tpl.save(out)
    return out.getvalue()
