import io
from datetime import date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import LadderResponse, TransactionRow

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA = "application/pdf"


def ladder_frame(ladder: LadderResponse) -> pd.DataFrame:
    rows = [
        {"Currency": s.currency, "Location": s.location, "Bucket": b.bucket.value, "Assets": b.assets,
         "Liabilities": b.liabilities, "Net gap": b.net_gap, "Asset count": b.asset_count, "Liability count": b.liability_count}
        for s in ladder.series for b in s.buckets
    ]
    return pd.DataFrame(rows)


def recommendations_frame(recs) -> pd.DataFrame:
    return pd.DataFrame([
        {"Severity": r.severity, "Currency": r.currency, "Location": r.location, "Bucket": r.bucket, "Gap type": r.gap_type,
         "Deterministic gap": float(r.deterministic_gap), "AI gap": float(r.ai_gap), "Action": r.action_text, "Rationale": r.rationale}
        for r in recs
    ])


def transactions_frame(rows: list[TransactionRow]) -> pd.DataFrame:
    return pd.DataFrame([r.model_dump(mode="json") for r in rows])


def to_xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            (frame if not frame.empty else pd.DataFrame({"Info": ["No data"]})).to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(len(str(c.value or "")) for c in col) + 2, 60)
    return buffer.getvalue()


def _fmt(v):
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


def to_pdf(title: str, run_date: date, sections: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7, leading=9)
    story = [Paragraph(title, styles["Title"]), Paragraph(f"Run date: {run_date.isoformat()}", styles["Normal"]), Spacer(1, 12)]
    for heading, frame in sections.items():
        story.append(Paragraph(heading, styles["Heading2"]))
        if frame.empty:
            story += [Paragraph("No data", styles["Normal"]), Spacer(1, 10)]
            continue
        data = [list(frame.columns)] + [[Paragraph(_fmt(v), cell) for v in row] for row in frame.itertuples(index=False)]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2B45")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D2E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story += [table, Spacer(1, 14)]
    doc.build(story)
    return buffer.getvalue()
