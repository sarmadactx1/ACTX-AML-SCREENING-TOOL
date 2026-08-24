"""Generates the same OpenSanctions-branded, multi-source screening
certificate as the desktop tool, adapted to run server-side and return
bytes instead of writing to a local file path."""

import io
from datetime import datetime
from urllib.parse import quote

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, PageBreak)

from screening import risk_label, uae_classification_en, format_uae_listing_decision

BLUE = "#2563EB"
BLUE_DARKER = "#1E40AF"
BLUE_PALE = "#EFF4FF"
INK = "#0F172A"
MUTED = "#64748B"
PAPER = "#F4F6FA"
LINE = "#E4E8F0"
HIT_TEXT = "#B91C1C"
CLEAR_TEXT = "#15803D"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CertBrand", fontSize=17, leading=20,
                               textColor=colors.HexColor(BLUE), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CertSub", fontSize=9.5, leading=13,
                               textColor=colors.HexColor(MUTED), fontName="Helvetica"))
    styles.add(ParagraphStyle(name="CertTitle", fontSize=13.5, leading=17,
                               textColor=colors.HexColor(INK), fontName="Helvetica-Bold", spaceBefore=4))
    styles.add(ParagraphStyle(name="CertStatusClear", fontSize=13, leading=16,
                               textColor=colors.HexColor(CLEAR_TEXT), fontName="Helvetica-Bold",
                               spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="CertStatusHit", fontSize=13, leading=16,
                               textColor=colors.HexColor(HIT_TEXT), fontName="Helvetica-Bold",
                               spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="CertBody", fontSize=9.5, leading=13.5,
                               textColor=colors.HexColor(INK), fontName="Helvetica"))
    styles.add(ParagraphStyle(name="CertFooter", fontSize=7.5, leading=10.5,
                               textColor=colors.HexColor(MUTED), fontName="Helvetica"))
    styles.add(ParagraphStyle(name="CertLink", fontSize=9.5, leading=13,
                               textColor=colors.HexColor(BLUE), fontName="Helvetica"))
    styles.add(ParagraphStyle(name="CertCodeLabel", fontSize=8, leading=11,
                               textColor=colors.HexColor(INK), fontName="Helvetica-Bold",
                               spaceBefore=10, spaceAfter=3))
    styles.add(ParagraphStyle(name="CertCode", fontSize=8.3, leading=12,
                               textColor=colors.HexColor(BLUE_DARKER), fontName="Courier"))
    styles.add(ParagraphStyle(name="CertSourceTitle", fontSize=11, leading=14,
                               textColor=colors.HexColor(BLUE_DARKER), fontName="Helvetica-Bold",
                               spaceBefore=4, spaceAfter=4))
    styles.add(ParagraphStyle(name="CertAppendixTitle", fontSize=13, leading=16,
                               textColor=colors.HexColor(INK), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CertAppendixSub", fontSize=9, leading=12,
                               textColor=colors.HexColor(MUTED), fontName="Helvetica", spaceAfter=10))
    styles.add(ParagraphStyle(name="CertSignoffTitle", fontSize=10, leading=13,
                               textColor=colors.HexColor(INK), fontName="Helvetica-Bold",
                               spaceBefore=14, spaceAfter=4))
    styles.add(ParagraphStyle(name="CertSignoffLabel", fontSize=8.5, leading=12,
                               textColor=colors.HexColor(MUTED), fontName="Helvetica-Bold"))
    return styles


def _match_table(rows, col_widths):
    mt = Table(rows, colWidths=col_widths, repeatRows=1)
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return mt


def generate_certificate_pdf_bytes(record, review=None):
    """record: a ScreeningRecord (or dict with the same shape).
    Returns raw PDF bytes, ready to stream as a download."""
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                             topMargin=16 * mm, bottomMargin=16 * mm)

    subject_name = record.subject_name
    query_row = {"name": subject_name, "schema": record.entity_type,
                 "country": record.country, "birthDate": record.dob}
    threshold = record.threshold
    ref = record.reference_id
    created_at = record.created_at or datetime.utcnow()

    doc.title = f"Screening Certificate - {subject_name} - {ref}"
    doc.author = "ACTX Screening Platform"
    doc.subject = "Multi-Source Sanctions & Terrorism List Screening Certificate"
    doc.creator = "ACTX Screening Platform"

    story = []
    story.append(Paragraph("OpenSanctions", styles["CertBrand"]))
    story.append(Paragraph("Supreme Data on Supreme Leaders \u2014 the open database of sanctions, "
                            "PEPs and watchlists", styles["CertSub"]))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.6, color=colors.HexColor(BLUE)))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Multi-Source Sanctions &amp; Terrorism List Screening Certificate",
                            styles["CertTitle"]))
    story.append(Paragraph("Checked against the OpenSanctions /match API (460+ sanctions, PEP and "
                            "watchlist sources including OFAC, UN, EU and UK HMT), the UAE Local "
                            "Terrorist List, and the UN Consolidated Sanctions List.", styles["CertSub"]))
    story.append(Spacer(1, 12))

    os_sorted = sorted(record.os_matches(), key=lambda m: m.get("score", 0), reverse=True)
    uae_sorted = sorted(record.uae_matches(), key=lambda m: m["score"], reverse=True)
    un_sorted = sorted(record.un_matches(), key=lambda m: m["score"], reverse=True)
    un_checked = getattr(record, "un_checked", False)

    encoded_name = quote(subject_name)
    public_search_url = f"https://www.opensanctions.org/search/?q={encoded_name}"
    api_equivalent_url = f"https://api.opensanctions.org/search/default?q={encoded_name}"

    sources_checked_lines = [
        "\u2022 OpenSanctions API (460+ sources incl. OFAC, UN, EU, UK HMT)",
        "\u2022 UAE Local Terrorist List (Cabinet Resolutions)",
    ]
    if un_checked:
        sources_checked_lines.append("\u2022 UN Consolidated Sanctions List")
    else:
        sources_checked_lines.append("\u2022 UN Consolidated Sanctions List \u2014 NOT CHECKED (not loaded at time of screening)")

    info_rows = [
        ["Reference ID", ref],
        ["Subject screened", subject_name],
        ["Entity type", record.entity_type],
        ["Country / nationality", record.country or "\u2014"],
        ["Date of birth", record.dob or "\u2014"],
        ["Match sensitivity threshold", f"{int(threshold * 100)}%"],
        ["Screening date & time", created_at.strftime("%d %b %Y, %H:%M")],
        ["Screened by", (record.screened_by.username if record.screened_by else "\u2014")],
        ["Sources checked", Paragraph("<br/>".join(sources_checked_lines), styles["CertBody"])],
        ["Verify OpenSanctions online", Paragraph(
            f'<link href="{public_search_url}"><u>{public_search_url}</u></link>', styles["CertLink"])],
    ]
    t = Table(info_rows, colWidths=[55 * mm, 105 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor(INK)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    total_hits = len(os_sorted) + len(uae_sorted) + len(un_sorted)
    if total_hits == 0:
        story.append(Paragraph("OVERALL RESULT: NO MATCHES FOUND", styles["CertStatusClear"]))
        story.append(Paragraph(
            f"No matches were identified against any of the sources checked above, at the "
            f"{int(threshold*100)}% relevance threshold, as of {created_at.strftime('%d %b %Y, %H:%M')}.",
            styles["CertBody"]))
    else:
        flagged = []
        if os_sorted: flagged.append(f"OpenSanctions ({len(os_sorted)})")
        if uae_sorted: flagged.append(f"UAE Local Terrorist List ({len(uae_sorted)})")
        if un_sorted: flagged.append(f"UN Consolidated List ({len(un_sorted)})")
        story.append(Paragraph(f"OVERALL RESULT: {total_hits} POTENTIAL MATCH(ES) IDENTIFIED \u2014 "
                                "REQUIRES MANUAL REVIEW", styles["CertStatusHit"]))
        story.append(Paragraph(f"Flagged by: {', '.join(flagged)}.", styles["CertBody"]))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(LINE)))
    story.append(Spacer(1, 8))

    # Source 1: OpenSanctions
    story.append(Paragraph("1. OpenSanctions API", styles["CertSourceTitle"]))
    story.append(Paragraph("Equivalent request (for independent manual verification)", styles["CertCodeLabel"]))
    code_table = Table([[Paragraph(f"GET {api_equivalent_url}", styles["CertCode"])]], colWidths=[160 * mm])
    code_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BLUE_PALE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(code_table)
    story.append(Spacer(1, 6))
    if not os_sorted:
        story.append(Paragraph("No matches found.", styles["CertBody"]))
    else:
        rows = [["Matched Entity", "Relevance", "Risk Topics", "Source Lists"]]
        for m in os_sorted:
            score = m.get("score", 0)
            topics = ", ".join((m.get("properties") or {}).get("topics", [])) or "\u2014"
            datasets = ", ".join((m.get("datasets") or [])[:3]) or "\u2014"
            entity_url = f"https://www.opensanctions.org/entities/{m.get('id')}/"
            name_link = Paragraph(
                f'<link href="{entity_url}"><u>{m.get("caption", m.get("id", ""))}</u></link>', styles["CertLink"])
            rows.append([name_link, f"{round(score * 100)}% ({risk_label(score)})",
                         Paragraph(topics, styles["CertBody"]), Paragraph(datasets, styles["CertBody"])])
        story.append(_match_table(rows, [42 * mm, 28 * mm, 45 * mm, 45 * mm]))
    story.append(Spacer(1, 12))

    # Source 2: UAE Local Terrorist List
    story.append(Paragraph("2. UAE Local Terrorist List", styles["CertSourceTitle"]))
    story.append(Paragraph("Screened against the UAE Cabinet's locally-designated terrorist "
                            "individuals, organizations and entities list, using fuzzy name matching.",
                            styles["CertSub"]))
    if not uae_sorted:
        story.append(Paragraph("No matches found.", styles["CertBody"]))
    else:
        rows = [["Matched Name", "Relevance", "Classification", "Listing Decision"]]
        for m in uae_sorted:
            rec = m["record"]
            rows.append([
                Paragraph(rec.get("full_name_latin", ""), styles["CertBody"]),
                f"{round(m['score'] * 100)}% ({risk_label(m['score'])})",
                Paragraph(uae_classification_en(rec.get("classification_ar", "")), styles["CertBody"]),
                Paragraph(format_uae_listing_decision(rec.get("listing_decision", "")), styles["CertBody"]),
            ])
        story.append(_match_table(rows, [42 * mm, 28 * mm, 30 * mm, 60 * mm]))

    # Source 3: UN Consolidated Sanctions List
    story.append(Spacer(1, 12))
    story.append(Paragraph("3. UN Consolidated Sanctions List", styles["CertSourceTitle"]))
    if not un_checked:
        story.append(Paragraph("NOT CHECKED \u2014 the UN Consolidated List was not loaded in the "
                                "screening platform at the time of this run. An admin can load it via "
                                "Settings to include this source in future certificates.",
                                styles["CertBody"]))
    else:
        story.append(Paragraph("Screened against the UN Security Council Consolidated Sanctions List "
                                "(individuals and entities), using fuzzy name matching against primary "
                                "names and known aliases.", styles["CertSub"]))
        if not un_sorted:
            story.append(Paragraph("No matches found.", styles["CertBody"]))
        else:
            rows = [["Matched Name", "Relevance", "UN Reference", "Sanctions Regime"]]
            for m in un_sorted:
                rec = m["record"]
                rows.append([
                    Paragraph(rec.get("full_name", ""), styles["CertBody"]),
                    f"{round(m['score'] * 100)}% ({risk_label(m['score'])})",
                    Paragraph(rec.get("reference", "") or "\u2014", styles["CertBody"]),
                    Paragraph(rec.get("un_list_type", "") or "\u2014", styles["CertBody"]),
                ])
            story.append(_match_table(rows, [50 * mm, 28 * mm, 30 * mm, 52 * mm]))

    # Reviewer sign-off (filled in from the platform's review workflow if available)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Reviewer Sign-Off", styles["CertSignoffTitle"]))
    decision_marks = {"Cleared": 0, "Escalated": 1, "Reported": 2}
    idx = decision_marks.get(record.review_status, None)
    boxes = ["[ ] Cleared \u2014 no further action", "[ ] Escalated for further review",
             "[ ] Reported to UAE FIU"]
    if idx is not None:
        boxes[idx] = boxes[idx].replace("[ ]", "[X]")
    signoff_rows = [
        [Paragraph("Reviewed by", styles["CertSignoffLabel"]),
         Paragraph((record.reviewed_by.username if record.reviewed_by else "") or "\u2014", styles["CertBody"])],
        [Paragraph("Date reviewed", styles["CertSignoffLabel"]),
         Paragraph(record.reviewed_at.strftime("%d %b %Y, %H:%M") if record.reviewed_at else "\u2014", styles["CertBody"])],
        [Paragraph("Decision", styles["CertSignoffLabel"]),
         Paragraph(" &nbsp;&nbsp;&nbsp; ".join(boxes), styles["CertBody"])],
        [Paragraph("Notes", styles["CertSignoffLabel"]),
         Paragraph(record.review_notes or "\u2014", styles["CertBody"])],
    ]
    signoff = Table(signoff_rows, colWidths=[32 * mm, 128 * mm])
    signoff.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (1, 0), (1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(PAPER)),
    ]))
    story.append(signoff)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(LINE)))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This certificate reflects a computer-generated comparison against public sanctions, PEP and "
        "watchlist data (and the cached UAE Local Terrorist List) at the time and threshold stated "
        "above. It is not, by itself, a legal or compliance determination \u2014 matches above the "
        "threshold require human review, and a \"no match\" result does not remove the obligation to "
        "apply risk-based due diligence, before any AML/CFT decision is recorded, in accordance with "
        "Federal Decree-Law No. 10/2025 and Cabinet Resolution No. 134/2025.", styles["CertFooter"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"OpenSanctions data: OpenSanctions Datenbanken GmbH \u00b7 opensanctions.org "
                            f"\u00b7 Generated {created_at.strftime('%d %b %Y %H:%M')} \u00b7 Reference {ref}",
                            styles["CertFooter"]))

    # Appendix pages
    for m in os_sorted:
        detail = m.get("_detail") or {}
        entity_url = f"https://www.opensanctions.org/entities/{m.get('id')}/"
        score = m.get("score", 0)
        block = [PageBreak()]
        block.append(Paragraph("OpenSanctions", styles["CertBrand"]))
        block.append(Paragraph("Entity Profile \u2014 appendix to the screening certificate above", styles["CertSub"]))
        block.append(Spacer(1, 8))
        block.append(HRFlowable(width="100%", thickness=1.6, color=colors.HexColor(BLUE)))
        block.append(Spacer(1, 10))
        block.append(Paragraph(m.get("caption", m.get("id", "")), styles["CertAppendixTitle"]))
        block.append(Paragraph(f"{round(score*100)}% match ({risk_label(score)}) against \u201c{subject_name}\u201d "
                                f"\u00b7 Reference {ref} \u00b7 Source: OpenSanctions", styles["CertAppendixSub"]))
        topics = ", ".join((m.get("properties") or {}).get("topics", [])) or "\u2014"
        datasets = ", ".join(m.get("datasets") or []) or "\u2014"
        field_lines = [("Full profile", Paragraph(
            f'<link href="{entity_url}"><u>{entity_url}</u></link>', styles["CertLink"]))]
        if detail.get("also_known_as"):
            field_lines.append(("Also known as", ", ".join(detail["also_known_as"])))
        if detail.get("birth_dates"):
            field_lines.append(("Date of birth", ", ".join(detail["birth_dates"])))
        if detail.get("countries"):
            field_lines.append(("Nationality / country", ", ".join(detail["countries"])))
        if detail.get("positions"):
            field_lines.append(("Position(s)", ", ".join(detail["positions"])))
        field_lines.append(("Risk topics", topics))
        field_lines.append(("Source lists", datasets))
        rows2 = [[k, v if isinstance(v, Paragraph) else Paragraph(str(v), styles["CertBody"])] for k, v in field_lines]
        pt = Table(rows2, colWidths=[38 * mm, 122 * mm])
        pt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ]))
        block.append(pt)
        story.extend(block)

    for m in uae_sorted:
        rec = m["record"]
        block = [PageBreak()]
        block.append(Paragraph("UAE Local Terrorist List", styles["CertBrand"]))
        block.append(Paragraph("Entry Profile \u2014 appendix to the screening certificate above", styles["CertSub"]))
        block.append(Spacer(1, 8))
        block.append(HRFlowable(width="100%", thickness=1.6, color=colors.HexColor(BLUE)))
        block.append(Spacer(1, 10))
        block.append(Paragraph(rec.get("full_name_latin", ""), styles["CertAppendixTitle"]))
        block.append(Paragraph(f"{round(m['score']*100)}% match ({risk_label(m['score'])}) against "
                                f"\u201c{subject_name}\u201d \u00b7 Reference {ref} \u00b7 Source: UAE Local Terrorist List",
                                styles["CertAppendixSub"]))
        field_lines = [
            ("List row #", rec.get("list_row", "")),
            ("Category", uae_classification_en(rec.get("classification_ar", ""))),
            ("Family name (Latin)", rec.get("family_name_latin", "") or "\u2014"),
            ("Document", f"{rec.get('doc_type','')} {rec.get('doc_number','')}".strip() or "\u2014"),
            ("Listing decision", format_uae_listing_decision(rec.get("listing_decision", ""))),
        ]
        rows2 = [[k, Paragraph(str(v), styles["CertBody"])] for k, v in field_lines]
        pt = Table(rows2, colWidths=[42 * mm, 118 * mm])
        pt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ]))
        block.append(pt)
        story.extend(block)

    for m in un_sorted:
        rec = m["record"]
        block = [PageBreak()]
        block.append(Paragraph("UN Consolidated Sanctions List", styles["CertBrand"]))
        block.append(Paragraph("Entry Profile \u2014 appendix to the screening certificate above", styles["CertSub"]))
        block.append(Spacer(1, 8))
        block.append(HRFlowable(width="100%", thickness=1.6, color=colors.HexColor(BLUE)))
        block.append(Spacer(1, 10))
        block.append(Paragraph(rec.get("full_name", ""), styles["CertAppendixTitle"]))
        block.append(Paragraph(f"{round(m['score']*100)}% match ({risk_label(m['score'])}) against "
                                f"\u201c{subject_name}\u201d \u00b7 Reference {ref} \u00b7 Source: UN Consolidated List",
                                styles["CertAppendixSub"]))
        field_lines = [
            ("UN reference", rec.get("reference", "") or "\u2014"),
            ("Category", rec.get("category", "")),
            ("Also known as", ", ".join(rec.get("aliases", [])) or "\u2014"),
            ("Nationality", rec.get("nationality", "") or "\u2014"),
            ("Date of birth", rec.get("dob", "") or "\u2014"),
            ("Sanctions regime", rec.get("un_list_type", "") or "\u2014"),
            ("Listed on", rec.get("listed_on", "") or "\u2014"),
        ]
        rows2 = [[k, Paragraph(str(v), styles["CertBody"])] for k, v in field_lines]
        pt = Table(rows2, colWidths=[38 * mm, 122 * mm])
        pt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(MUTED)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ]))
        block.append(pt)
        story.extend(block)

    doc.build(story)
    return buf.getvalue()
