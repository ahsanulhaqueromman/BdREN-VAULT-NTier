"""Summary report: what changed, what failed, and who logged in over the last 7 or 30 days - built as a
PDF on request (Change Reports > "Weekly summary" / "Monthly summary"). Nothing is scheduled or emailed;
it is generated fresh each time someone downloads it."""
import io

from django.utils import timezone

PERIODS = {"weekly": 7, "monthly": 30}   # label -> days back from now


def build_summary(period):
    """Everything the report shows, gathered fresh for the chosen period ("weekly" = last 7 days,
    "monthly" = last 30 days, both ending now)."""
    from apps.backups import selectors as backups
    from apps.backups import reports
    from apps.devices import selectors as devices
    from apps.radius.selectors import login_summary, recent_logins

    days = PERIODS.get(period, 7)
    end = timezone.localtime()
    start = end - timezone.timedelta(days=days)
    changes = reports.change_report(start=start, end=end)
    backup_counts = backups.backup_counts_between(start, end)
    logins = login_summary(since=start, until=end)
    login_rows, _ = recent_logins(since=start, until=end, limit=2000)
    accepted_users = sorted({r["username"] for r in login_rows if r["reply"] == "Access-Accept" and r["username"]})
    top_changed = sorted((r for r in changes["devices"] if r["changes"]), key=lambda r: -r["changes"])[:10]
    return {
        "period": period, "days": days, "start": start, "end": end,
        "devices_total": devices.device_count(),
        "devices_changed": changes["summary"]["changed"],
        "devices_unchanged": changes["summary"]["unchanged"],
        "config_changes": changes["summary"]["changes"],
        "lines_added": changes["summary"]["added"],
        "lines_removed": changes["summary"]["removed"],
        "top_changed": top_changed,
        "backups_saved": backup_counts.get("SUCCESS", 0),
        "backups_unchanged": backup_counts.get("UNCHANGED", 0),
        "backups_failed": backup_counts.get("FAILED", 0),
        "logins_total": logins["total"], "logins_accepted": logins["accepted"],
        "logins_rejected": logins["rejected"], "login_users": accepted_users,
    }


# The app's own palette (static/css/app.css :root), so the PDF matches the product instead of looking bolted on.
_INK, _MUTE, _LINE = "#0f1b2d", "#5b6b82", "#e2e8f1"
_BLUE, _BLUE_D = "#2f5bea", "#2449c7"
_OK, _OK_BG = "#0a7a54", "#e2f6ee"
_BAD, _BAD_BG = "#d63447", "#fdecee"
_NEUTRAL_BG = "#eef2fb"


def _logo_path():
    from pathlib import Path

    from django.conf import settings
    p = Path(settings.BASE_DIR) / "static" / "img" / "bdren-logo.png"
    return str(p) if p.exists() else None


def build_pdf(period):
    """(bytes, filename): a branded PDF (reportlab, no system package needed) with the summary,
    styled after the app's own palette: a blue header band, coloured stat cards and a striped table."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def c(hex_):
        return colors.HexColor(hex_)

    s = build_summary(period)
    title = "Weekly" if s["period"] == "weekly" else "Monthly"
    base = getSampleStyleSheet()
    h2 = ParagraphStyle("h2", parent=base["Heading2"], textColor=c(_INK), spaceBefore=0, spaceAfter=6,
                        fontSize=13, leading=16)
    big = ParagraphStyle("big", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=20, leading=23)
    small = ParagraphStyle("small", parent=base["Normal"], textColor=c(_MUTE), fontSize=8.5, leading=11)
    normal = ParagraphStyle("normal", parent=base["Normal"], textColor=c(_INK), fontSize=10, leading=14)
    bannerTitle = ParagraphStyle("bannerTitle", parent=base["Normal"], textColor=colors.white,
                                 fontName="Helvetica-Bold", fontSize=20, leading=23)
    bannerSub = ParagraphStyle("bannerSub", parent=base["Normal"], textColor=colors.HexColor("#dbe4ff"), fontSize=10.5)

    PAGE_W = A4[0] - 36 * mm

    def card(label, value, color):
        """One stat tile: a big coloured number over a muted label, sized to fill its panel cell."""
        cell = Table([[Paragraph(str(value), ParagraphStyle("v", parent=big, textColor=c(color)))],
                      [Paragraph(label, small)]], rowHeights=[22, 13])
        cell.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        return cell

    def card_row(cards):
        """Up to 3 stat tiles per row, each in its own tinted panel, with a thin gap between panels."""
        rows, i = [], 0
        while i < len(cards):
            chunk = cards[i:i + 3]
            cells = [card(label, value, color) for label, value, color, bg in chunk]
            gap = 3 * mm
            widths = []
            for j in range(len(chunk)):
                widths += [PAGE_W / len(chunk) - gap] + ([gap] if j < len(chunk) - 1 else [])
            padded = []
            for j, cell in enumerate(cells):
                padded.append(cell)
                if j < len(cells) - 1:
                    padded.append("")
            row = Table([padded], colWidths=widths)
            style = [("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                     ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                     ("VALIGN", (0, 0), (-1, -1), "TOP")]
            for j, (_, _, _, bg) in enumerate(chunk):
                col = j * 2
                style.append(("BACKGROUND", (col, 0), (col, 0), c(bg)))
            row.setStyle(TableStyle(style))
            rows.append(row)
            i += 3
        return rows

    def section(title_, tiles):
        return [Spacer(1, 7 * mm), Paragraph(title_, h2)] + card_row(tiles)

    def striped_table(header, rows, widths):
        data = [header] + rows
        t = Table(data, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), c(_BLUE)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 1), (-1, -1), c(_INK)),
                 ("ALIGN", (-1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, c(_LINE))]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), c("#f7f9fd")))
        t.setStyle(TableStyle(style))
        return t

    # ---- header banner: logo on white, title + period on blue ----
    logo = _logo_path()
    logo_cell = Image(logo, width=16 * mm, height=10.3 * mm) if logo else Paragraph("VAULT", bannerTitle)
    banner = Table([[logo_cell, [Paragraph(f"{title} Summary", bannerTitle),
                                 Paragraph(f"{s['start'].strftime('%d %b %Y')} &ndash; {s['end'].strftime('%d %b %Y')}"
                                           f"  ({s['days']} days)  &middot;  BdREN VAULT", bannerSub)]]],
                   colWidths=[26 * mm, PAGE_W - 26 * mm], rowHeights=[20 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.white),
                                ("BACKGROUND", (1, 0), (1, 0), c(_BLUE)),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
                                ("LEFTPADDING", (1, 0), (1, 0), 10), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

    story = [banner,
             *section("Devices", [
                 ("Devices with a backup", f"{s['devices_total']:,}", _BLUE_D, _NEUTRAL_BG),
                 ("Changed in this period", f"{s['devices_changed']:,}", _OK, _OK_BG),
                 ("Unchanged", f"{s['devices_unchanged']:,}", _MUTE, _NEUTRAL_BG)]),
             *section("Configuration changes", [
                 ("Changes saved", f"{s['config_changes']:,}", _BLUE_D, _NEUTRAL_BG),
                 ("Lines added", f"+{s['lines_added']:,}", _OK, _OK_BG),
                 ("Lines removed", f"-{s['lines_removed']:,}", _BAD, _BAD_BG)]),
             *section("Backup jobs", [
                 ("Saved (changed)", f"{s['backups_saved']:,}", _OK, _OK_BG),
                 ("Unchanged", f"{s['backups_unchanged']:,}", _MUTE, _NEUTRAL_BG),
                 ("Failed", f"{s['backups_failed']:,}", _BAD, _BAD_BG if s["backups_failed"] else _NEUTRAL_BG)]),
             *section("RADIUS logins", [
                 ("Accepted", f"{s['logins_accepted']:,}", _OK, _OK_BG),
                 ("Rejected (last 24 h)", f"{s['logins_rejected']:,}", _BAD, _BAD_BG if s["logins_rejected"] else _NEUTRAL_BG),
                 ("Different users", f"{len(s['login_users']):,}", _BLUE_D, _NEUTRAL_BG)])]

    if s["top_changed"]:
        story += [Spacer(1, 7 * mm), Paragraph("Most-changed devices", h2),
                  striped_table(["Device", "Changes"],
                                [[r["device"], str(r["changes"])] for r in s["top_changed"]],
                                [PAGE_W - 30 * mm, 30 * mm])]
    if s["login_users"]:
        names = ", ".join(s["login_users"][:100]) + (" ..." if len(s["login_users"]) > 100 else "")
        box = Table([[Paragraph(names, normal)]], colWidths=[PAGE_W])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), c(_NEUTRAL_BG)),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                 ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story += [Spacer(1, 7 * mm), Paragraph("Users who logged in", h2), box]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(c(_MUTE))
        canvas.drawString(18 * mm, 10 * mm, f"Generated by BdREN VAULT on {timezone.localtime():%d %b %Y, %H:%M}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.setStrokeColor(c(_LINE))
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"VAULT {title.lower()} summary",
                            topMargin=18 * mm, bottomMargin=20 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    filename = f"vault-{s['period']}-summary-{s['end'].strftime('%Y%m%d')}.pdf"
    return buf.getvalue(), filename
