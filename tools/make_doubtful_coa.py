"""Writes a deliberately cooked-up COA, used to test whether the Evidence Verifier catches a fake."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

out = Path(__file__).resolve().parents[1] / "vendor_replies" / "followups" / "COA_Nilagiri_Rosemary.pdf"
ss = getSampleStyleSheet()
t = Table([["Test", "Limit", "Result"], ["Rosmarinic acid", "20.00%", "20.00%"], ["Moisture", "5.00%", "5.00%"], ["Heavy metals", "Pass", "Pass"], ["Microbial", "Pass", "Pass"]], colWidths=[60 * mm, 45 * mm, 45 * mm])
SimpleDocTemplate(str(out), pagesize=A4).build([
    Paragraph("Certificate of Analysis", ss["Title"]),
    Paragraph("Product: Rosemary leaf extract<br/>Batch No: 001<br/>Date of manufacture: 15 Jan 2027<br/>Retest date: 15 Jan 2031<br/>COA issue date: 02 Nov 2026", ss["BodyText"]),
    Spacer(1, 10), t, Spacer(1, 12), Paragraph("Certified 100% pure and best quality.", ss["BodyText"]),
])
print(out)
