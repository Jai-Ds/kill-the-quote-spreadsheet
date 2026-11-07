"""Generates the five fabricated vendor replies (real Excel, PDF, Word, photo and email files).

Run once. The app never reads this script: the agents only see the files it writes.
All companies and figures are fictional.
"""
import os
import random
from pathlib import Path

from docx import Document
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1] / "vendor_replies"
SS = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=SS["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("s", parent=SS["BodyText"], fontSize=6.5, leading=8, textColor=colors.HexColor("#555555"))


def vdir(v):
    d = ROOT / v
    d.mkdir(parents=True, exist_ok=True)
    return d


def email(v, sender, date, subject, body):
    text = f"From: {sender}\nTo: procurement@kesavi.example\nDate: {date}\nSubject: {subject}\n\n{body.strip()}\n"
    (vdir(v) / "email.txt").write_text(text, encoding="utf-8")


def coa_pdf(path, company, product, batch, mfg, retest, rows, issued):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm)
    t = Table([["Test", "Specification", "Result"]] + rows, colWidths=[60 * mm, 55 * mm, 45 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    doc.build([
        Paragraph(f"<b>{company}</b>", SS["Title"]),
        Paragraph("CERTIFICATE OF ANALYSIS", SS["Heading2"]),
        Paragraph(f"Product: <b>{product}</b><br/>Batch No: {batch}<br/>Date of manufacture: {mfg}<br/>Retest / expiry date: {retest}<br/>COA issue date: {issued}", BODY),
        Spacer(1, 8), t, Spacer(1, 12),
        Paragraph("Conclusion: batch complies with the above specification.<br/>Authorised by: Quality Assurance", BODY),
    ])


# ---------------------------------------------------------------- V01: Excel that ignores the template
def v01():
    wb = Workbook()
    ws = wb.active
    ws.title = "Offer Nov26"
    ws["A1"] = "KOVAI FINECHEM PVT LTD - PRICE OFFER"
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="0B6E4F")
    ws["A2"] = "Ref: KF/SO/2211   Valid till 31-Dec-2026   All rates ex GST, delivered Hosur"
    head = ["S.No", "Our Product Name", "Pack", "Rate (Rs)", "Per", "MOQ", "Del. days", "Shelf life", "Remarks"]
    for c, h in enumerate(head, 1):
        ws.cell(4, c, h).font = Font(bold=True)
    rows = [
        (1, "1,3-Propanediol Bio 99.7%", "210 L drum", 338, "Litre", "200 kg", 12, "24 M", "Density 1.05 g/ml at 25C"),
        (2, "Refined Glycerine IP 99.7%", "250 L drum", 142, "Litre", "200 kg", 12, "24 M", ""),
        (3, "Nicotinamide PC Grade 99.5%", "25 kg drum", 1220, "Kg", "25 kg", 15, "36 M", ""),
        (4, "D-Panthenol 98", "25 kg carboy", 2050, "Kg", "25 kg", 15, "24 M", "Assay 98% HPLC. Keep below 25C"),
        (5, "PE/EHG 90:10 Preservative", "50 kg carboy", 965, "Kg", "50 kg", 12, "24 M", ""),
        (6, "HEC Viscosity 5000", "25 kg bag", 27000, "Bag", "1 bag", 15, "36 M", "25 kg net per bag"),
    ]
    for r, row in enumerate(rows, 5):
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v)
    for col, w in zip("ABCDEFGHI", [6, 32, 14, 10, 8, 9, 9, 9, 34]):
        ws.column_dimensions[col].width = w
    t = wb.create_sheet("Terms")
    for i, line in enumerate(["Payment: 30 days from invoice", "Freight: included, door delivery Hosur (DAP)",
                              "Remaining shelf life at delivery: minimum 18 months (preservative minimum 15 months)",
                              "Price firm for 6 months from PO date", "Call-off deliveries possible against annual PO"], 1):
        t.cell(i, 1, line)
    t.column_dimensions["A"].width = 80
    q = wb.create_sheet("Your Questions")
    qa = [("Manufacturer or trader?", "Manufacturer for propanediol, glycerine, preservative. Traded: nicotinamide, panthenol, HEC"),
          ("ISO certificates", "ISO 9001:2015 valid to 14-Aug-2027"),
          ("OTIF last 12 months", "95%"),
          ("Rejection rate last 12 months", "0.3%"),
          ("Will you share records?", "Yes, summary report on request"),
          ("SDS", "Available, sent with first dispatch"),
          ("Cosmetics Rules 2020 suitable?", "Yes, all suitable for leave-on use"),
          ("Second site?", "No, single site at Coimbatore. 3 weeks finished stock normally held")]
    for i, (a, b) in enumerate(qa, 1):
        q.cell(i, 1, a)
        q.cell(i, 2, b)
    q.column_dimensions["A"].width = 34
    q.column_dimensions["B"].width = 80
    wb.save(vdir("V01") / "Kovai_Finechem_Offer.xlsx")
    coa_pdf(vdir("V01") / "COA_Kovai_Propanediol.pdf", "Kovai Finechem Pvt Ltd", "1,3-Propanediol Bio", "KF-PD-2609-114",
            "12 Sep 2026", "11 Sep 2028", [["Assay (GC)", ">= 99.5%", "99.7%"], ["Water", "<= 0.1%", "0.04%"], ["Colour APHA", "<= 10", "5"]], "15 Sep 2026")
    email("V01", "Sales Desk <sales@kovaifinechem.example>", "Mon, 9 Nov 2026 11:42", "RE: RFx KPC-2026-014",
          """Dear Sir/Madam,

Please find our offer attached. We use our own format as our ERP generates this, hope that is OK.
Sample COA for propanediol also attached.

Regards
R. Selvam, Sales, Kovai Finechem""")


# ---------------------------------------------------------------- V02: PDF on letterhead, discount in a footnote
def v02():
    d = vdir("V02")
    path = d / "Tungabhadra_Quotation.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=12 * mm)
    data = [["Item", "Description", "Spec", "Packing", "Basic rate", "MOQ", "Lead time"],
            ["1", "Propanediol USP", "99.5% min", "Drum", "Rs 62,000 / drum", "2 drums", "18 days"],
            ["2", "Niacinamide", "99% min", "25 kg", "Rs 1,180 / kg", "25 kg", "18 days"],
            ["3", "Panthenol solution", "75% in water", "25 kg", "Rs 1,520 / kg", "25 kg", "18 days"],
            ["4", "Caffeine anhyd.", "98.5% min", "25 kg", "Rs 1,760 / kg", "25 kg", "18 days"],
            ["5", "Phenoxyethanol EHG blend", "90:10", "50 kg", "Rs 990 / kg", "50 kg", "18 days"],
            ["6", "Copper Tripeptide-1 soln", "1000 ppm", "5 kg", "Rs 24,500 / kg", "20 kg", "30 days"],
            ["7", "Acetyl Tetrapeptide-3 soln", "500 ppm", "5 kg", "Rs 14,800 / kg", "20 kg", "30 days"]]
    t = Table(data, colWidths=[10 * mm, 48 * mm, 24 * mm, 15 * mm, 34 * mm, 16 * mm, 19 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7A1F1F")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
    doc.build([
        Paragraph("<font color='#7A1F1F' size='17'><b>TUNGABHADRA ACTIVES LLP</b></font>", SS["Normal"]), Spacer(1, 7),
        Paragraph("Authorised distributor of speciality ingredients | Plot 22, Gokul Road, Hubballi 580030 | GSTIN 29XXXXX0000X1Z5", SMALL),
        Spacer(1, 10), Paragraph("Quotation No TA/Q/1187 &nbsp;&nbsp; Date: 12 November 2026 &nbsp;&nbsp; Validity: 30 days", BODY), Spacer(1, 6),
        Paragraph("Kind attn: Category Manager, Kesavi Personal Care. We are pleased to quote as below.<super>*</super>", BODY), Spacer(1, 6), t, Spacer(1, 8),
        Paragraph("<b>Terms.</b> Freight extra at actuals, approx Rs 6 per kg to Hosur. Payment 45 days. Taxes extra. "
                  "Hydroxyethylcellulose: we regret, not available at present.", BODY), Spacer(1, 4),
        Paragraph("<b>Shelf life.</b> 24 months for items 1 to 5, with at least 18 months at delivery. Peptides items 6 and 7: 12 months from manufacture, "
                  "8 months remaining at delivery, store 2-8 C. Peptides are despatched in insulated boxes with gel packs; no temperature logger is included.", BODY), Spacer(1, 4),
        Paragraph("<b>Performance.</b> Our OTIF is 96% and customer rejection is below 1%. Certification: ISO 9001:2015 (valid to 30 Mar 2027). "
                  "We are a distributor; items 6 and 7 are sourced from an overseas manufacturer whose name is confidential. "
                  "As a matter of company policy we do not share internal rejection or delivery records with customers.", BODY), Spacer(1, 4),
        Paragraph("SDS provided on order. All materials suitable for cosmetic use. COA for niacinamide attached.", BODY), Spacer(1, 40),
        Paragraph("* Trade discount of 4% on basic rate applies to items 1 to 5 where the order value for the line exceeds Rs 2,00,000. Not applicable to peptides. E&amp;OE.", SMALL),
    ])
    coa_pdf(d / "COA_Tungabhadra_Niacinamide.pdf", "Tungabhadra Actives LLP (on behalf of manufacturer)", "Niacinamide", "NIA-2603-07", "04 Mar 2026", "03 Mar 2029",
            [["Assay (HPLC)", "99.0-101.0%", "99.4%"], ["Loss on drying", "<= 0.5%", "0.2%"], ["Heavy metals", "<= 10 ppm", "< 5 ppm"]], "10 Mar 2026")
    email("V02", "Anand K <anand@tungabhadra-actives.example>", "Thu, 12 Nov 2026 18:05", "Quotation for your RFx",
          "Dear Madam,\n\nQuotation and COA attached. Kindly note our footnote. Waiting for your valued order.\n\nThanks\nAnand")


# ---------------------------------------------------------------- V03: Word doc, commercials in a paragraph
def v03():
    d = vdir("V03")
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Georgia"
    st.font.size = Pt(11)
    doc.add_heading("Vembanad Botanicals Pvt. Ltd.", 1)
    doc.add_paragraph("Commercial proposal for Kesavi Personal Care: RFx KPC-2026-014. 10 November 2026.")
    doc.add_paragraph("Thank you for inviting us. Vembanad has supplied Kesavi with vegetable glycerin for several years, and we are delighted to extend the relationship to botanicals. "
                      "Our family-run plant near Kochi is certified to ISO 9001 (valid to 20 June 2028) and ISO 22716 GMP (valid to 20 June 2028).")
    doc.add_paragraph("On vegetable glycerin, we would continue at one hundred and twelve rupees per kilogram delivered to Hosur, in 250 kg net drums, with a minimum order of 500 kg and our usual ten-day lead time. "
                      "Shelf life is twenty-four months and you will receive at least twenty months at delivery.")
    doc.add_paragraph("For the rosemary leaf extract, we offer our standardised powder at 10% rosmarinic acid by HPLC, in 5 kg foil packs, at Rs 4,000 per kg, delivered, with a minimum order of 25 kg. "
                      "Lead time is twenty-one days. Shelf life is twenty-four months, and we would guarantee eighteen months at delivery. Please store in a cool place away from light.")
    doc.add_paragraph("Payment terms remain 30 days. We have been on time and in full on 98% of deliveries in the last year, with a rejection rate of 0.2%, and we are happy to share the summary records. "
                      "Our extract COA is enclosed. SDS will follow with the sample, and both materials are suitable for leave-on cosmetic use under the Cosmetics Rules, 2020.")
    doc.add_paragraph("Warm regards,\nMeera Thomas, Director")
    doc.save(d / "Vembanad_Commercial_Proposal.docx")
    coa_pdf(d / "COA_Vembanad_Rosemary.pdf", "Vembanad Botanicals Pvt. Ltd.", "Rosemary Leaf Extract Powder", "VB-RM-2411-03", "28 Nov 2024", "30 Nov 2026",
            [["Rosmarinic acid (HPLC)", ">= 10.0%", "10.3%"], ["Moisture", "<= 5%", "3.1%"], ["Total plate count", "<= 1000 cfu/g", "< 100 cfu/g"]], "02 Dec 2024")
    email("V03", "Meera Thomas <meera@vembanadbotanicals.example>", "Tue, 10 Nov 2026 09:15", "Kesavi RFx: our proposal",
          "Dear Team,\n\nOur proposal and the rosemary COA are attached.\n\nWarm regards\nMeera")


# ---------------------------------------------------------------- V04: angled phone photo of a printed rate card + USD
def font(size, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", size)


def perspective_coeffs(dst, src):
    import numpy as np
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(m, float), np.array(src, float).reshape(8))


def v04():
    d = vdir("V04")
    random.seed(7)
    W, H = 1500, 1120
    card = Image.new("RGB", (W, H), (247, 244, 236))
    dr = ImageDraw.Draw(card)
    dr.text((60, 40), "LUMEN PEPTIDE TRADING PTE. LTD.", font=font(46, True), fill=(20, 40, 90))
    dr.text((60, 102), "Singapore | Cosmetic actives | Rate card Q4 2026 | Prices in US$", font=font(28), fill=(70, 70, 70))
    dr.line((60, 150, W - 60, 150), fill=(20, 40, 90), width=4)
    cols = [60, 560, 790, 980, 1160, 1320]
    for x, h in zip(cols, ["Product", "Grade", "US$/kg", "MOQ", "Lead", "Shelf"]):
        dr.text((x, 175), h, font=font(30, True), fill=(0, 0, 0))
    rows = [("Copper Tripeptide-1 solution", "1000 ppm", "240", "100 kg", "10 wks", "12 mth"),
            ("Acetyl Tetrapeptide-3 solution", "500 ppm", "148", "200 kg", "10 wks", "12 mth"),
            ("Rosemary leaf extract", "20% carnosic", "78", "10 kg", "8 wks", "24 mth")]
    y = 235
    for r in rows:
        for x, v in zip(cols, r):
            dr.text((x, y), v, font=font(30), fill=(25, 25, 25))
        y += 72
    dr.line((60, y + 4, W - 60, y + 4), fill=(120, 120, 120), width=2)
    notes = ["CIF Chennai. Import duty, clearance and inland freight to buyer's account.",
             "Peptides shipped 2-8 C, validated cold pack with data logger in each box.",
             "Remaining shelf life at delivery: peptides 10 months, botanicals 20 months.",
             "Payment: 100% TT before shipment. Prices valid to 31 Jan 2027."]
    y += 30
    for n in notes:
        dr.text((60, y), n, font=font(28), fill=(50, 50, 50))
        y += 46
    # phone photo: warp onto a table, add shadow, blur and noise
    bg = Image.new("RGB", (1700, 1300), (92, 66, 44))
    px = bg.load()
    for yy in range(1300):
        for xx in range(0, 1700, 3):
            n = random.randint(-9, 9) + int(8 * ((yy // 37) % 2))
            c = (92 + n, 66 + n, 44 + n)
            px[xx, yy] = c
            if xx + 1 < 1700:
                px[xx + 1, yy] = c
            if xx + 2 < 1700:
                px[xx + 2, yy] = c
    dst = [(175, 120), (1530, 215), (1420, 1205), (70, 1050)]
    coeffs = perspective_coeffs(dst, [(0, 0), (W, 0), (W, H), (0, H)])
    warped = card.transform(bg.size, Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    mask = Image.new("L", (W, H), 255).transform(bg.size, Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    shadow = Image.new("RGB", bg.size, (30, 22, 15))
    bg.paste(shadow, (22, 26), mask.filter(ImageFilter.GaussianBlur(18)))
    bg.paste(warped, (0, 0), mask)
    glare = Image.new("L", bg.size, 0)
    ImageDraw.Draw(glare).ellipse((900, 300, 1500, 800), fill=48)
    bg.paste(Image.new("RGB", bg.size, (255, 255, 250)), (0, 0), glare.filter(ImageFilter.GaussianBlur(90)))
    bg = bg.filter(ImageFilter.GaussianBlur(0.8)).rotate(-1.5, resample=Image.BICUBIC, fillcolor=(60, 44, 30))
    bg.save(d / "IMG_20261113_rate_card.jpg", quality=80)
    coa_pdf(d / "COA_Lumen_CopperTripeptide.pdf", "Lumen Peptide Trading Pte. Ltd.", "Copper Tripeptide-1 solution", "LP-CT1-2608-22", "18 Aug 2026", "17 Aug 2027",
            [["Peptide content (HPLC)", ">= 800 ppm", "812 ppm"], ["pH", "5.5-7.0", "6.2"], ["Appearance", "Blue liquid", "Complies"]], "22 Aug 2026")
    email("V04", "Jasper Lim <jasper@lumenpeptide.example>", "Fri, 13 Nov 2026 22:31", "rate card",
          """Hi, travelling so sending photo of our printed rate card, pls see attached along with COA for copper peptide.

We are a trading company, material made by partner plants in China and Korea. Density of both solutions about 1.03.
OTIF 97%, rejection 0.5%. Sorry no records to share at the moment as we are new in India, can give 2 references in Singapore.
Suitable for cosmetics, ISO 9001 at manufacturer level. SDS later.

Jasper
Sent from my phone""")


# ---------------------------------------------------------------- V05: one short email
def v05():
    email("V05", "Prakash <prakash.nilagiri@mail.example>", "Sat, 14 Nov 2026 08:03", "Re: RFx",
          """Sir

glycerine 118/kg, rosemary 20% rosmarinic 7000/kg MOQ 100 kg shelf life 12 months, caffeine 1650/kg if you lift one full lot.
freight extra around Rs 9 per kg. 50% advance rest on delivery. delivery 3 weeks.

we are very reliable, 99% on time always and zero rejection. new to your company but serving many big brands.
certificates under renewal will send later. COA after order only.

Prakash
Nilagiri Phytolabs, Ooty""")


# ---------------------------------------------------------------- follow-up replies used by the clarification loop
def followups():
    d = ROOT / "followups"
    d.mkdir(exist_ok=True)
    (d / "V01.txt").write_text("Dear Team, density of our refined glycerine is 1.26 g/ml at 25C. Regards, R. Selvam\n", encoding="utf-8")
    (d / "V02.txt").write_text("Dear Madam, our propanediol drum is 215 kg net. Thanks, Anand\n", encoding="utf-8")
    (d / "V03.txt").write_text("Dear Team, apologies, the COA we sent was an old batch. Our current rosemary batch VB-RM-2609-11 was made on 14 Sep 2026, COA issued 18 Sep 2026, retest date 13 Sep 2028, rosmarinic acid 10.4% by HPLC. Regards, Meera", encoding="utf-8")
    (d / "V04.txt").write_text("Hi, checked with plant. The rosemary grade is 20% carnosic acid and also about 8% rosmarinic acid by HPLC. Jasper\n", encoding="utf-8")


if __name__ == "__main__":
    for f in (v01, v02, v03, v04, v05, followups):
        f()
    print("done", sum(1 for p in ROOT.rglob("*") if p.is_file()), "files")
