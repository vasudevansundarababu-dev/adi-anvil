"""PDF visuals of already-frozen scores; never a grader or data reader."""

import math
from xml.sax.saxutils import escape


def matched_model_chart(comparisons):
    """Keep each model's matched review sample distinct, including missing scores."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Table, TableStyle

    rows = []
    styles = getSampleStyleSheet()
    colors = [HexColor("#087f82"), HexColor("#7045bd")]
    for comparison in comparisons:
        coverage = comparison.get("coverage") or {}
        title = Paragraph(
            escape(str(comparison["model_key"]))
            + "<br/>"
            + escape(
                f"{coverage.get('comparable', 'Unknown')} comparable / "
                f"{coverage.get('eligible', 'Unknown')} eligible observations"
            ),
            styles["Normal"],
        )
        drawing = Drawing(290, 68)
        for tick in (0, 25, 50, 75, 100):
            x = tick * 2
            drawing.add(Line(x, 15, x, 60, strokeColor=HexColor("#dbe4e9")))
            drawing.add(String(x, 4, str(tick), fontSize=7, textAnchor="middle"))
        for index, key in enumerate(("matched_generated_score", "matched_expert_score")):
            value = comparison.get(key)
            y = 48 - index * 21
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and 0 <= value <= 100
            )
            if valid:
                drawing.add(Rect(0, y, value * 2, 10, fillColor=colors[index], strokeColor=None))
            drawing.add(
                String(
                    208,
                    y + 1,
                    f"{value:.1f} / 100" if valid else "Unscored",
                    fontSize=9,
                )
            )
        rows.append([title, drawing])
    table = Table(rows, colWidths=[150, 290]) if rows else None
    if table:
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
    return table
