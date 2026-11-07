"""Writes the 10-question vendor questionnaire from the original Word file, keeping its intro, lines table and Annexure A."""
import copy
import sys
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto.attributes import QUESTIONS  # noqa: E402

BASE = Path(__file__).resolve().parents[2] / "Base Data"
doc = Document(BASE / "Kesavi_Vendor_Questionnaire.docx")
body = doc.element.body
kids = list(body)
paras = {id(p._p): p for p in doc.paragraphs}


def text(el):
    return paras[id(el)].text if id(el) in paras else ""


start = next(i for i, e in enumerate(kids) if text(e).startswith("A. "))
end = next(i for i, e in enumerate(kids) if text(e) == "Declaration")
style_tbl = next(e for e in kids[start:end] if e.tag.endswith("}tbl"))
sample = next(t for t in doc.tables if t._tbl is style_tbl)
for e in kids[start:end]:
    body.remove(e)

t = doc.add_table(rows=1, cols=3)
t.style = sample.style
for c, h in zip(t.rows[0].cells, ["ID", "Question", "Evidence requested"]):
    c.text = h
    for r in c.paragraphs[0].runs:
        r.bold = True
for qid, _, q, ev, ko, applies in QUESTIONS:
    row = t.add_row().cells
    row[0].text = f"{qid} {'K' if ko else '*'}"
    row[1].text = q + ("" if applies == "All" else f" ({applies})")
    row[2].text = ev
decl = kids[end]
decl.addprevious(copy.deepcopy(t._tbl))
body.remove(t._tbl)
doc.save(BASE / "Kesavi_Vendor_Questionnaire_10Q.docx")
print("saved", len(QUESTIONS), "questions")
