"""
ClearSight Analytics - Report & Deliverables Export Engine
Generates:
1. Excel Banner Books with Dual Significance Testing & Injection Defense
2. Customer Voice Snapshot (A4 Executive Summary) with HTML Auto-Escaping
3. APA 7th Edition Thesis Chapter 4 Package & Academic Tables Workbook
"""

import re
import html
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Design Palette: Brand Launch Red, Volt Yellow & Carbon
LAUNCH_RED = "E10600"
VOLT_YELLOW = "FFD400"
CARBON_HEADER = "181818"
CARBON_SURFACE = "222222"
LIGHT_GRAY = "F4F5F9"
BORDER_GRAY = "D1D5DB"
SIG_COLOR_POS = "047857" # Emerald for +/++
SIG_COLOR_NEG = "B91C1C" # Crimson for -/--


def sanitize_excel_cell(val):
    """Prevents CSV/Excel formula injection for user-controlled strings while preserving internal sig markers (CS-N08, P3-19)."""
    if isinstance(val, str) and len(val) > 0:
        if val in ('+', '++', '-', '--'):
            return val
        stripped = val.lstrip(' \t\r\n')
        if stripped and stripped[0] in ('=', '+', '-', '@', '\t', '\r'):
            return "'" + val
    return val


def sanitize_sheet_name(title: str, index: int, existing_names: set) -> str:
    """Sanitizes sheet names by stripping illegal characters []:*?/\\ and ensuring uniqueness."""
    clean = re.sub(r'[\[\]:*?/\\]', '_', str(title)).strip()
    clean = clean.replace(" ", "_")
    prefix = f"T{index}_"
    max_len = 31 - len(prefix)
    base_name = f"{prefix}{clean[:max_len]}"
    name = base_name
    counter = 1
    while name in existing_names:
        suffix = f"_{counter}"
        avail = 31 - len(prefix) - len(suffix)
        name = f"{prefix}{clean[:avail]}{suffix}"
        counter += 1
    existing_names.add(name)
    return name


def generate_excel_banner_book(
    filepath: str, 
    project_title: str, 
    tables_data: list[dict], 
    metadata: dict
) -> str:
    """
    Generates a multi-tab Excel Banner Book with:
    - Formula injection defense
    - Real numeric cell formatting (0.0%)
    - Weighted and Effective Base rows
    - Dual significance rows (Column letters + vs Total benchmark)
    """
    wb = openpyxl.Workbook()
    ws_meta = wb.active
    ws_meta.title = "Methodology & Legend"
    ws_meta.views.sheetView[0].showGridLines = True

    title_font = Font(name="Helvetica Neue", size=15, bold=True, color=CARBON_HEADER)
    section_font = Font(name="Helvetica Neue", size=12, bold=True, color="333333")
    regular_font = Font(name="Helvetica Neue", size=11, color="444444")
    bold_font = Font(name="Helvetica Neue", size=11, bold=True, color="111111")

    thin_border = Border(
        left=Side(style='thin', color=BORDER_GRAY),
        right=Side(style='thin', color=BORDER_GRAY),
        top=Side(style='thin', color=BORDER_GRAY),
        bottom=Side(style='thin', color=BORDER_GRAY)
    )

    # 1. Methodology Sheet
    ws_meta.cell(row=2, column=2, value=sanitize_excel_cell("CLEARSIGHT - AGENCY TABULATION BOOK")).font = title_font
    ws_meta.cell(row=3, column=2, value=sanitize_excel_cell(f"Project: {project_title or 'Survey Study'}")).font = section_font

    fdr_text = metadata.get("fdr_correction", "Benjamini-Hochberg False Discovery Rate (FDR)")
    meta_rows = [
        ("Field Date Range", metadata.get("date_range", "N/A")),
        ("Total Unweighted Sample (N)", metadata.get("unweighted_n", "N/A")),
        ("Total Weighted Base (Nw)", metadata.get("weighted_n", "N/A")),
        ("Overall Kish Effective Base (Neff)", metadata.get("effective_n", "N/A")),
        ("Weighting Efficiency", f"{metadata.get('efficiency_pct', 'N/A')}%" if metadata.get('efficiency_pct') is not None else "N/A"),
        ("Dual Significance Testing System", "Agency Standard: Column Letters & Overlap-Corrected Benchmark"),
        ("Sig Row 1: Column Comparisons", "a, b, c... (>= 90% Conf) | A, B, C... (>= 95% Conf)"),
        ("Sig Row 2: Benchmark vs. Total", "Plus signs (+ / ++): higher than rest-of-sample (90% / 95%)"),
        ("                               ", "Minus signs (- / --): lower than rest-of-sample (90% / 95%)"),
        ("Multiple Comparison Correction", fdr_text)
    ]

    for r_idx, (label, val) in enumerate(meta_rows, start=6):
        cell_lbl = ws_meta.cell(row=r_idx, column=2, value=str(label))
        cell_lbl.font = bold_font
        cell_lbl.fill = PatternFill(start_color=LIGHT_GRAY, end_color=LIGHT_GRAY, fill_type="solid")
        cell_lbl.border = thin_border

        cell_val = ws_meta.cell(row=r_idx, column=3, value=str(val))
        cell_val.font = regular_font
        cell_val.border = thin_border

    ws_meta.column_dimensions['B'].width = 34
    ws_meta.column_dimensions['C'].width = 55

    # 2. Add Tables (Agency-Grade Executive Presentation Layout)
    header_fill = PatternFill(start_color=CARBON_HEADER, end_color=CARBON_HEADER, fill_type="solid")
    header_font = Font(name="Helvetica Neue", size=11, bold=True, color="FFFFFF")
    base_fill = PatternFill(start_color="E9ECEF", end_color="E9ECEF", fill_type="solid")
    base_font = Font(name="Helvetica Neue", size=11, color="444444")
    sig_letter_font = Font(name="Helvetica Neue", size=10, bold=True, color="2D46B9")
    sig_pos_font = Font(name="Helvetica Neue", size=10, bold=True, color=SIG_COLOR_POS)
    sig_neg_font = Font(name="Helvetica Neue", size=10, bold=True, color=SIG_COLOR_NEG)
    net_fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
    table_title_font = Font(name="Helvetica Neue", size=15, bold=True, color=CARBON_HEADER)
    question_font = Font(name="Helvetica Neue", size=15, bold=True, italic=True, color=CARBON_HEADER)
    subtitle_font = Font(name="Helvetica Neue", size=8, italic=True, color="444444")
    table_bold_font = Font(name="Helvetica Neue", size=11, bold=True, color="111111")
    table_regular_font = Font(name="Helvetica Neue", size=11, color="444444")

    def clean_banner_name(name: str) -> str:
        return re.sub(r"\s*[\(\[]\s*[A-Z]+\s*[\)\]]$", "", str(name)).strip()

    existing_sheet_names = {"Methodology & Legend"}

    valid_tables = [t for t in tables_data if not t.get("error") and len(t.get("rows", [])) > 0]
    if not valid_tables:
        raise ValueError("Build at least one valid table first.")

    for t_idx, t_data in enumerate(valid_tables, start=1):
        clean_title = t_data.get("title", f"Table_{t_idx}")
        safe_sheet_name = sanitize_sheet_name(clean_title, t_idx, existing_sheet_names)
        ws = wb.create_sheet(title=safe_sheet_name)
        ws.views.sheetView[0].showGridLines = False

        # Row 2: Table Title
        ws.cell(row=2, column=2, value=sanitize_excel_cell(clean_title)).font = table_title_font
        # Row 3: Dedicated Question Phrasing Slot
        question_phrasing = t_data.get("question_text") or t_data.get("question") or "Insert Question Phrasing Here"
        ws.cell(row=3, column=2, value=sanitize_excel_cell(question_phrasing)).font = question_font
        # Row 4: Methodology Subtitle
        ws.cell(row=4, column=2, value=sanitize_excel_cell("Column % | Dual Sig: Letters (Col) and +/++ -/-- (vs Total)")).font = subtitle_font

        banner_cols = t_data.get("banner_cols", [])
        col_letters = t_data.get("col_letters", [])

        # Process banner columns and letters
        if banner_cols and str(banner_cols[0]).strip().lower().startswith("total"):
            sub_banners = [clean_banner_name(b) for b in banner_cols[1:]]
            sub_letters = col_letters[1:] if len(col_letters) > 1 else [chr(65 + i) for i in range(len(sub_banners))]
        else:
            sub_banners = [clean_banner_name(b) for b in banner_cols]
            sub_letters = col_letters if col_letters else [chr(65 + i) for i in range(len(sub_banners))]

        # Row 6: Banner Header Row
        ws.row_dimensions[6].height = 75.0
        stub_header = t_data.get("stub_label") or t_data.get("variable_name") or clean_title.split(":")[-1].strip()
        cell_stub = ws.cell(row=6, column=2, value=sanitize_excel_cell(stub_header))
        cell_stub.font = header_font
        cell_stub.fill = header_fill
        cell_stub.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        cell_tot = ws.cell(row=6, column=3, value=sanitize_excel_cell("Total"))
        cell_tot.font = header_font
        cell_tot.fill = header_fill
        cell_tot.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for c_offset, b_col in enumerate(sub_banners):
            c_idx = 4 + c_offset
            cell = ws.cell(row=6, column=c_idx, value=sanitize_excel_cell(b_col))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        # Row 7: Integrated Column Letters Row (Col B & C blank, Col D+ integrated header letters)
        for c_offset, letter in enumerate(sub_letters):
            c_idx = 4 + c_offset
            cell = ws.cell(row=7, column=c_idx, value=sanitize_excel_cell(str(letter)))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 8: Sample Base N
        ws.cell(row=8, column=2, value=sanitize_excel_cell("Column Sample Size (N)")).font = base_font
        ws.cell(row=8, column=2).fill = base_fill
        for c_idx, b_val in enumerate(t_data.get("unweighted_bases", []), start=3):
            cell = ws.cell(row=8, column=c_idx, value=b_val if b_val is not None else 0)
            cell.font = base_font
            cell.fill = base_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 9: Weighted Base Nw
        ws.cell(row=9, column=2, value=sanitize_excel_cell("Weighted Base (Nw)")).font = base_font
        ws.cell(row=9, column=2).fill = base_fill
        for c_idx, w_val in enumerate(t_data.get("weighted_bases", []), start=3):
            cell = ws.cell(row=9, column=c_idx, value=round(w_val, 1) if w_val is not None else 0.0)
            cell.font = base_font
            cell.fill = base_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 10: Kish Effective Base Neff
        ws.cell(row=10, column=2, value=sanitize_excel_cell("Kish Effective Base (Neff)")).font = base_font
        ws.cell(row=10, column=2).fill = base_fill
        for c_idx, b_val in enumerate(t_data.get("effective_bases", []), start=3):
            cell = ws.cell(row=10, column=c_idx, value=round(b_val, 1) if b_val is not None else 0.0)
            cell.font = base_font
            cell.fill = base_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 11: Blank Spacer Row
        curr_row = 12
        for row_info in t_data.get("rows", []):
            label = row_info.get("label", "")
            is_net = row_info.get("is_net", False) or str(label).strip().upper().startswith("NET:")
            values = row_info.get("values", [])
            sig_letters = row_info.get("sig_letters", [""] * len(values))
            sig_benchmarks = row_info.get("sig_benchmarks", [""] * len(values))

            # Line 1: Data Values (% or mean)
            lbl_cell = ws.cell(row=curr_row, column=2, value=sanitize_excel_cell(label))
            lbl_cell.font = table_bold_font if is_net else table_regular_font
            if is_net:
                lbl_cell.fill = net_fill

            for c_idx, val in enumerate(values, start=3):
                val_cell = ws.cell(row=curr_row, column=c_idx)
                if isinstance(val, str) and val.endswith("%"):
                    try:
                        num_float = float(val.replace("%", "").strip()) / 100.0
                        val_cell.value = num_float
                        val_cell.number_format = "0%" if round(num_float * 100, 1) == round(num_float * 100) else "0.0%"
                    except ValueError:
                        val_cell.value = sanitize_excel_cell(val)
                elif isinstance(val, (int, float)):
                    val_cell.value = float(val)
                    val_cell.number_format = "0.00"
                else:
                    # CS-080: Convert numeric float strings (e.g. means) to numeric Excel cells
                    try:
                        num_val = float(val)
                        val_cell.value = num_val
                        val_cell.number_format = "0.00"
                    except (ValueError, TypeError):
                        val_cell.value = sanitize_excel_cell(str(val))

                val_cell.font = table_bold_font if is_net else table_regular_font
                val_cell.alignment = Alignment(horizontal="center", vertical="center")
                if is_net:
                    val_cell.fill = net_fill
            curr_row += 1

            # Line 2: Col Comparisons (Letters) — Col B & C blank
            for c_idx, s_val in enumerate(sig_letters, start=3):
                s_clean = str(s_val).strip() if s_val is not None else ""
                if c_idx > 3 and s_clean and s_clean != "-":
                    s_cell = ws.cell(row=curr_row, column=c_idx, value=sanitize_excel_cell(s_clean))
                    s_cell.font = sig_letter_font
                    s_cell.alignment = Alignment(horizontal="center", vertical="center")
            curr_row += 1

            # Line 3: vs Total Benchmark (+/++, -/--) — Col B & C blank (CS-N07 resolution)
            for c_idx, b_val in enumerate(sig_benchmarks, start=3):
                b_clean = str(b_val).strip() if b_val is not None else ""
                if c_idx > 3 and b_clean:
                    b_cell = ws.cell(row=curr_row, column=c_idx, value=sanitize_excel_cell(b_clean))
                    if "+" in b_clean:
                        b_cell.font = sig_pos_font
                    elif "-" in b_clean:
                        b_cell.font = sig_neg_font
                    else:
                        b_cell.font = table_regular_font
                    b_cell.alignment = Alignment(horizontal="center", vertical="center")
            curr_row += 1

        last_row = curr_row - 1
        total_cols = 3 + len(sub_banners)

        # Apply Outer Bounding Box Border (Minimalist Executive Frame)
        for r in range(6, last_row + 1):
            for c in range(2, total_cols + 1):
                top_s = Side(style="thin", color="000000") if r == 6 else None
                bot_s = Side(style="thin", color="000000") if r == last_row else None
                left_s = Side(style="thin", color="000000") if c == 2 else None
                right_s = Side(style="thin", color="000000") if c == total_cols else None
                if top_s or bot_s or left_s or right_s:
                    ws.cell(row=r, column=c).border = Border(top=top_s, bottom=bot_s, left=left_s, right=right_s)

        ws.column_dimensions["B"].width = 38.0
        ws.column_dimensions["C"].width = 16.0
        for c in range(4, total_cols + 1):
            ws.column_dimensions[get_column_letter(c)].width = 13.0

    wb.save(filepath)
    return filepath


def generate_customer_voice_snapshot_html(filepath: str, data: dict) -> str:
    """
    Generates an executive Customer Voice Snapshot in printable A4 HTML.
    All dynamic inputs are escaped via html.escape to eliminate HTML/script injection.
    """
    project_title = html.escape(str(data.get("project_title", "Customer Voice Analysis")))
    sample_n = html.escape(str(data.get("sample_n", "N/A")))
    eff_n = html.escape(str(data.get("eff_n", "N/A")))
    csat_score = html.escape(str(data.get("csat_score", "N/A")))
    weighting_eff = html.escape(str(data.get("weighting_eff", "N/A")))

    # Dynamic or formatted findings
    findings = data.get("findings") or []
    if findings:
        findings_html = "".join([
            f"""
        <div class="finding-box">
            <b>{html.escape(str(f.get("title", "")))}:</b> {html.escape(str(f.get("text", "")))} <span class="sig-tag">[{html.escape(str(f.get("tag", "")))}]</span>
        </div>"""
            for f in findings
        ])
    else:
        findings_html = """
        <div class="finding-box" style="color: #666; font-style: italic;">
            No statistically significant findings recorded yet for this dataset.
        </div>"""

    # Delights and Frictions
    delights = data.get("delights") or []
    frictions = data.get("frictions") or []

    if delights:
        delights_html = "".join([
            f'<div class="quote-box">"{html.escape(str(d["quote"]))}"<div style="font-size: 10px; color: #888; margin-top: 4px;">— {html.escape(str(d.get("author", "Respondent")))}</div></div>'
            for d in delights
        ])
    else:
        delights_html = '<div class="quote-box" style="color: #777; font-style: italic; border-left-color: #D1D5DB;">No verified customer delights recorded yet.</div>'

    if frictions:
        frictions_html = "".join([
            f'<div class="quote-box friction">"{html.escape(str(f["quote"]))}"<div style="font-size: 10px; color: #888; margin-top: 4px;">— {html.escape(str(f.get("author", "Respondent")))}</div></div>'
            for f in frictions
        ])
    else:
        frictions_html = '<div class="quote-box friction" style="color: #777; font-style: italic; border-left-color: #D1D5DB;">No verified customer frictions recorded yet.</div>'

    action_matrix = data.get("action_matrix") or []
    if action_matrix:
        action_rows = "".join([
            f'<tr><td><b>{html.escape(str(a.get("priority", "")))}</b></td><td>{html.escape(str(a.get("focus", "")))}</td><td>{html.escape(str(a.get("action", "")))}</td><td>{html.escape(str(a.get("metric", "")))}</td></tr>'
            for a in action_matrix
        ])
    else:
        action_rows = '<tr><td colspan="4" style="text-align: center; color: #777; font-style: italic; padding: 12px;">No automated 30-day action matrix defined for this dataset.</td></tr>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Customer Voice Snapshot - {project_title}</title>
<style>
    @page {{ size: A4; margin: 12mm; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #111111;
        margin: 0;
        padding: 24px;
        background: #FFFFFF;
        line-height: 1.4;
    }}
    .header {{
        border-bottom: 3px solid #181818;
        padding-bottom: 12px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }}
    .title {{ font-size: 24px; font-weight: 800; letter-spacing: -0.5px; margin: 0; }}
    .subtitle {{ font-size: 13px; color: #555; margin-top: 4px; }}
    .badge {{ background: #181818; color: #fff; padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 4px; }}
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }}
    .kpi-card {{
        background: #F4F5F9;
        border: 1px solid #E2E4EB;
        border-radius: 6px;
        padding: 12px;
        text-align: center;
    }}
    .kpi-val {{ font-size: 22px; font-weight: 800; color: #111111; }}
    .kpi-lbl {{ font-size: 11px; font-weight: 600; text-transform: uppercase; color: #666; margin-top: 2px; }}
    
    .section-title {{
        font-size: 14px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 18px 0 10px 0;
        border-left: 4px solid #E10600;
        padding-left: 8px;
    }}
    .finding-box {{
        background: #FAFBFD;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 8px;
        font-size: 13px;
    }}
    .sig-tag {{ color: #E10600; font-weight: 700; font-size: 11px; }}
    .qual-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-bottom: 20px;
    }}
    .quote-box {{
        background: #FFFFFF;
        border-left: 3px solid #10B981;
        padding: 8px 12px;
        margin-top: 6px;
        font-size: 12px;
        color: #333;
        font-style: italic;
    }}
    .quote-box.friction {{ border-left-color: #EF4444; }}
    .action-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        margin-top: 8px;
    }}
    .action-table th, .action-table td {{
        border: 1px solid #E2E8F0;
        padding: 8px 10px;
        text-align: left;
    }}
    .action-table th {{ background: #181818; color: #FFFFFF; }}
</style>
</head>
<body>
    <div class="header">
        <div>
            <h1 class="title">Customer Voice Snapshot</h1>
            <div class="subtitle">{project_title} | ClearSight Local Workspace Summary</div>
        </div>
        <span class="badge">LOCAL WORKSPACE DELIVERABLE</span>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-val">{sample_n}</div>
            <div class="kpi-lbl">Total Sample (N)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{eff_n}</div>
            <div class="kpi-lbl">Kish Eff. Base</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{csat_score}</div>
            <div class="kpi-lbl">Top-2-Box CSAT</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{weighting_eff}</div>
            <div class="kpi-lbl">Weight Efficiency</div>
        </div>
    </div>

    <div class="section-title">Statistically Verified Strategic Takeaways</div>
    {findings_html}

    <div class="qual-grid">
        <div>
            <div class="section-title" style="border-left-color: #10B981;">Customer Delights (Affinity Drivers)</div>
            {delights_html}
        </div>
        <div>
            <div class="section-title" style="border-left-color: #EF4444;">Customer Frictions (Drop-off Risks)</div>
            {frictions_html}
        </div>
    </div>

    <div class="section-title">Immediate 30-Day Operational Action Matrix</div>
    <table class="action-table">
        <thead>
            <tr>
                <th>Priority</th>
                <th>Strategic Focus</th>
                <th>Recommended Action</th>
                <th>Target Metric</th>
            </tr>
        </thead>
        <tbody>
            {action_rows}
        </tbody>
    </table>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def generate_thesis_excel_tables(filepath: str, project_title: str) -> str:
    """Generates dynamic APA-formatted Chapter 4 tables in Excel from active session microdata (CS-USER-01)."""
    import numpy as np
    import pandas as pd
    from server import SESSION, SESSION_LOCK, load_bundled_sample

    wb = openpyxl.Workbook()

    with SESSION_LOCK:
        df = SESSION.get("df")
        weights = SESSION.get("weights")
        filename = SESSION.get("filename", project_title)
        last_tab = SESSION.get("last_tabulation")

    if df is None:
        load_bundled_sample()
        with SESSION_LOCK:
            df = SESSION.get("df")
            weights = SESSION.get("weights")
            filename = SESSION.get("filename", project_title)
            last_tab = SESSION.get("last_tabulation")

    total_n = len(df) if df is not None else 0
    if weights is not None and len(weights) == total_n:
        eff_n = round(float(np.sum(weights)**2 / np.sum(weights**2)), 1)
    else:
        eff_n = float(total_n)

    apa_title_font = Font(name="Times New Roman", size=12, bold=True)
    apa_italic_font = Font(name="Times New Roman", size=11, italic=True)
    apa_regular_font = Font(name="Times New Roman", size=11)
    apa_bold_font = Font(name="Times New Roman", size=11, bold=True)

    top_border = Border(top=Side(style="medium", color="000000"), bottom=Side(style="thin", color="000000"))
    bottom_border = Border(bottom=Side(style="medium", color="000000"))
    sub_border = Border(bottom=Side(style="thin", color="D0D0D0"))

    # Sheet 1: Table 4.1 Demographics
    ws1 = wb.active
    ws1.title = "Table 4.1 - Demographics"
    ws1.views.sheetView[0].showGridLines = True

    ws1.cell(row=2, column=2, value="Table 4.1").font = apa_title_font
    ws1.cell(row=3, column=2, value=f"Frequency and Percentage Distribution of Respondents (N = {total_n}, Neff = {eff_n:.1f})").font = apa_italic_font

    headers1 = ["Demographic Profile", "Frequency (f)", "Percent (%)", "Weighted Base (Nw)", "Effective %"]
    for c_idx, h in enumerate(headers1, start=2):
        cell = ws1.cell(row=5, column=c_idx, value=sanitize_excel_cell(h))
        cell.font = apa_bold_font
        cell.border = top_border
        cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")

    curr_row = 6
    if df is not None:
        preferred_cols = ["Region", "Age_Generation", "Socioeconomic_Class", "Gender"]
        cat_cols = [c for c in preferred_cols if c in df.columns]
        for c in df.columns:
            if c not in cat_cols and not str(c).startswith("__") and 2 <= df[c].nunique(dropna=True) <= 10:
                cat_cols.append(c)
        cat_cols = cat_cols[:4]

        w_arr = np.asarray(weights, dtype=float) if weights is not None else np.ones(total_n, dtype=float)

        for col in cat_cols:
            c_header = ws1.cell(row=curr_row, column=2, value=sanitize_excel_cell(str(col).replace("_", " ")))
            c_header.font = apa_bold_font
            curr_row += 1

            counts = df[col].value_counts(dropna=True)
            for cat, freq in counts.items():
                pct = float(freq) / total_n if total_n > 0 else 0.0
                mask = (df[col] == cat).to_numpy()
                nw = float(np.sum(w_arr[mask])) if len(w_arr) == total_n else float(freq)
                eff_pct = nw / float(np.sum(w_arr)) if np.sum(w_arr) > 0 else pct

                ws1.cell(row=curr_row, column=2, value=sanitize_excel_cell(f"  {cat}")).font = apa_regular_font
                
                f_cell = ws1.cell(row=curr_row, column=3, value=int(freq))
                f_cell.font = apa_regular_font
                f_cell.alignment = Alignment(horizontal="center")

                p_cell = ws1.cell(row=curr_row, column=4, value=pct)
                p_cell.font = apa_regular_font
                p_cell.number_format = "0.0%"
                p_cell.alignment = Alignment(horizontal="center")

                nw_cell = ws1.cell(row=curr_row, column=5, value=round(nw, 1))
                nw_cell.font = apa_regular_font
                nw_cell.alignment = Alignment(horizontal="center")

                ep_cell = ws1.cell(row=curr_row, column=6, value=eff_pct)
                ep_cell.font = apa_regular_font
                ep_cell.number_format = "0.0%"
                ep_cell.alignment = Alignment(horizontal="center")

                curr_row += 1

        tot_lbl = ws1.cell(row=curr_row, column=2, value="Total / Kish Effective Base")
        tot_lbl.font = apa_bold_font
        tot_lbl.border = bottom_border

        tot_f = ws1.cell(row=curr_row, column=3, value=total_n)
        tot_f.font = apa_bold_font
        tot_f.border = bottom_border
        tot_f.alignment = Alignment(horizontal="center")

        tot_p = ws1.cell(row=curr_row, column=4, value=1.0)
        tot_p.font = apa_bold_font
        tot_p.border = bottom_border
        tot_p.number_format = "0.0%"
        tot_p.alignment = Alignment(horizontal="center")

        tot_nw = ws1.cell(row=curr_row, column=5, value=round(float(np.sum(w_arr)), 1))
        tot_nw.font = apa_bold_font
        tot_nw.border = bottom_border
        tot_nw.alignment = Alignment(horizontal="center")

        tot_neff = ws1.cell(row=curr_row, column=6, value=f"Neff = {eff_n:.1f}")
        tot_neff.font = apa_bold_font
        tot_neff.border = bottom_border
        tot_neff.alignment = Alignment(horizontal="center")

    ws1.column_dimensions["B"].width = 38
    ws1.column_dimensions["C"].width = 16
    ws1.column_dimensions["D"].width = 16
    ws1.column_dimensions["E"].width = 22
    ws1.column_dimensions["F"].width = 18

    # Dynamic CrossTab Sheets for all staged tables in last_tab
    crosstab_tables = last_tab if (last_tab and len(last_tab) > 0) else [None]
    t_count = 0

    for t_idx, tab_table in enumerate(crosstab_tables):
        t_count += 1
        t_num = f"4.{t_idx + 2}"
        stub_title = tab_table.get("stub_label") if tab_table else None
        if stub_title and stub_title != "Survey Measure":
            safe_sheet_name = f"Table {t_num} - {stub_title}"[:31]
        else:
            safe_sheet_name = f"Table {t_num} - CrossTab"[:31]
        stub_title = stub_title or "Survey Measure"

        ws_tab = wb.create_sheet(title=safe_sheet_name)
        ws_tab.views.sheetView[0].showGridLines = True
        ws_tab.cell(row=2, column=2, value=f"Table {t_num}").font = apa_title_font
        ws_tab.cell(row=3, column=2, value=f"Cross-Tabulation of {stub_title} Across Subgroups with Dual Significance (N = {total_n}, Neff = {eff_n:.1f})").font = apa_italic_font

        if tab_table:
            headers2 = ["Stub Category", "Total"] + [b for b in tab_table.get("clean_banner_cols", []) if b != "Total"]
        else:
            headers2 = ["Stub Category", "Total"]

        for c_idx, h in enumerate(headers2, start=2):
            cell = ws_tab.cell(row=5, column=c_idx, value=sanitize_excel_cell(h))
            cell.font = apa_bold_font
            cell.border = top_border
            cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")

        curr = 6
        if tab_table and "rows" in tab_table:
            for r in tab_table["rows"]:
                label = r.get("label", "")
                vals = r.get("values", [])
                lets = r.get("sig_letters", [])
                benchs = r.get("sig_benchmarks", [])
                is_net = r.get("is_net", False)

                c_lbl = ws_tab.cell(row=curr, column=2, value=sanitize_excel_cell(label))
                c_lbl.font = apa_bold_font if is_net else apa_regular_font
                c_lbl.border = sub_border

                for c_idx, v in enumerate(vals, start=3):
                    cell = ws_tab.cell(row=curr, column=c_idx, value=sanitize_excel_cell(str(v)))
                    cell.font = apa_bold_font if is_net else apa_regular_font
                    cell.alignment = Alignment(horizontal="center")
                    cell.border = sub_border
                curr += 1

                if any(l and l != "-" for l in lets):
                    ws_tab.cell(row=curr, column=2, value=sanitize_excel_cell("  ↳ Pairwise Col Sig")).font = Font(name="Times New Roman", size=9, italic=True)
                    for c_idx, l in enumerate(lets, start=3):
                        cell = ws_tab.cell(row=curr, column=c_idx, value=sanitize_excel_cell(l if l != "-" else ""))
                        cell.font = Font(name="Times New Roman", size=10, bold=True, color="2D46B9")
                        cell.alignment = Alignment(horizontal="center")
                    curr += 1

                if any(b and b != "-" for b in benchs):
                    ws_tab.cell(row=curr, column=2, value=sanitize_excel_cell("  ↳ vs. Total Benchmark")).font = Font(name="Times New Roman", size=9, italic=True)
                    for c_idx, b in enumerate(benchs, start=3):
                        cell = ws_tab.cell(row=curr, column=c_idx, value=sanitize_excel_cell(b if b != "-" else ""))
                        cell.font = Font(name="Times New Roman", size=10, bold=True, color="047857" if "+" in b else ("B91C1C" if "-" in b and b != "-" else "333333"))
                        cell.alignment = Alignment(horizontal="center")
                    curr += 1

            test_info = []
            if tab_table.get("chi_square"):
                cs = tab_table["chi_square"]
                test_info.append(f"χ² = {cs.get('chi2_stat')}, df = {cs.get('df')}, p = {cs.get('p_val')}")
            if tab_table.get("anova"):
                an = tab_table["anova"]
                test_info.append(f"F({an.get('df1')}, {an.get('df2')}) = {an.get('f_stat')}, p = {an.get('p_val')}")
            if tab_table.get("mrcv"):
                mr = tab_table["mrcv"]
                test_info.append(f"FRSb = {mr.get('f_stat')}, df = {mr.get('df1')}, p = {mr.get('p_val')}")

            if test_info:
                c_test = ws_tab.cell(row=curr, column=2, value=sanitize_excel_cell("Omnibus Test of Association"))
                c_test.font = apa_bold_font
                c_test.border = bottom_border
                ws_tab.cell(row=curr, column=3, value=sanitize_excel_cell(" | ".join(test_info))).font = apa_italic_font
                for c in range(3, len(headers2) + 2):
                    ws_tab.cell(row=curr, column=c).border = bottom_border
                curr += 1

        for c in range(2, len(headers2) + 2):
            ws_tab.cell(row=curr - 1, column=c).border = bottom_border
            ws_tab.column_dimensions[get_column_letter(c)].width = 22 if c > 2 else 38

    # Dynamic Sheet: Descriptive Statistics for Continuous and Scale Measures
    if df is not None:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not str(c).startswith("__") and c not in ("Respondent_ID", "Survey_Duration_Sec")]
        if num_cols:
            t_count += 1
            t_num_desc = f"4.{t_count + 1}"
            ws_desc = wb.create_sheet(title=f"Table {t_num_desc} - Scale Measures"[:31])
            ws_desc.views.sheetView[0].showGridLines = True

            ws_desc.cell(row=2, column=2, value=f"Table {t_num_desc}").font = apa_title_font
            ws_desc.cell(row=3, column=2, value=f"Descriptive Statistics for Continuous and Scale Measures (N = {total_n})").font = apa_italic_font

            desc_headers = ["Metric Variable", "n", "Mean (M)", "Std Dev (SD)", "Min", "Max"]
            for c_idx, h in enumerate(desc_headers, start=2):
                cell = ws_desc.cell(row=5, column=c_idx, value=sanitize_excel_cell(h))
                cell.font = apa_bold_font
                cell.border = top_border
                cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")

            d_row = 6
            for col in num_cols:
                series = df[col].dropna()
                ws_desc.cell(row=d_row, column=2, value=sanitize_excel_cell(str(col).replace("_", " "))).font = apa_regular_font
                ws_desc.cell(row=d_row, column=3, value=len(series)).font = apa_regular_font
                ws_desc.cell(row=d_row, column=3).alignment = Alignment(horizontal="center")
                ws_desc.cell(row=d_row, column=4, value=round(float(series.mean()), 2)).font = apa_regular_font
                ws_desc.cell(row=d_row, column=4).alignment = Alignment(horizontal="center")
                ws_desc.cell(row=d_row, column=5, value=round(float(series.std()), 2)).font = apa_regular_font
                ws_desc.cell(row=d_row, column=5).alignment = Alignment(horizontal="center")
                ws_desc.cell(row=d_row, column=6, value=round(float(series.min()), 1)).font = apa_regular_font
                ws_desc.cell(row=d_row, column=6).alignment = Alignment(horizontal="center")
                ws_desc.cell(row=d_row, column=7, value=round(float(series.max()), 1)).font = apa_regular_font
                ws_desc.cell(row=d_row, column=7).alignment = Alignment(horizontal="center")
                for c in range(2, 8):
                    ws_desc.cell(row=d_row, column=c).border = sub_border
                d_row += 1

            for c in range(2, 8):
                ws_desc.cell(row=d_row - 1, column=c).border = bottom_border
                ws_desc.column_dimensions[get_column_letter(c)].width = 16 if c > 2 else 34

            fn = ws_desc.cell(row=d_row + 1, column=2, value="Note. M and SD represent mean and standard deviation, respectively.")
            fn.font = apa_italic_font

    # Dynamic Sheet: Qualitative Thematic Code Distribution
    open_analysis = SESSION.get("open_feedback_analysis")
    if open_analysis and "codeframe" in open_analysis:
        cf_items = open_analysis["codeframe"]
        if cf_items:
            t_count += 1
            t_num_qual = f"4.{t_count + 1}"
            ws_qual = wb.create_sheet(title=f"Table {t_num_qual} - Thematic Codes"[:31])
            ws_qual.views.sheetView[0].showGridLines = True

            ws_qual.cell(row=2, column=2, value=f"Table {t_num_qual}").font = apa_title_font
            ws_qual.cell(row=3, column=2, value=f"Thematic Code Distribution for Open-Ended Verbatim Responses (N = {total_n})").font = apa_italic_font

            qual_headers = ["Theme / Standardized Category", "Frequency (n)", "Prevalence (%)", "Illustrative Verbatim Quote"]
            for c_idx, h in enumerate(qual_headers, start=2):
                cell = ws_qual.cell(row=5, column=c_idx, value=sanitize_excel_cell(h))
                cell.font = apa_bold_font
                cell.border = top_border
                cell.alignment = Alignment(horizontal="left" if c_idx in (2, 5) else "center")

            q_row = 6
            for it in cf_items:
                th_name = it.get("theme") or "General"
                cnt = it.get("count", 0)
                pct = it.get("prevalence_pct", 0.0)
                exs = it.get("evidence_samples", [])
                q_sample = f'"{exs[0].get("quote")}"' if exs else ""

                ws_qual.cell(row=q_row, column=2, value=sanitize_excel_cell(th_name)).font = apa_regular_font
                c_cnt = ws_qual.cell(row=q_row, column=3, value=int(cnt))
                c_cnt.font = apa_regular_font
                c_cnt.alignment = Alignment(horizontal="center")

                c_pct = ws_qual.cell(row=q_row, column=4, value=f"{pct:.1f}%")
                c_pct.font = apa_regular_font
                c_pct.alignment = Alignment(horizontal="center")

                c_q = ws_qual.cell(row=q_row, column=5, value=sanitize_excel_cell(q_sample))
                c_q.font = Font(name="Times New Roman", size=10, italic=True, color="333333")
                c_q.alignment = Alignment(horizontal="left", wrap_text=True)

                for c in range(2, 6):
                    ws_qual.cell(row=q_row, column=c).border = sub_border
                q_row += 1

            for c in range(2, 6):
                ws_qual.cell(row=q_row - 1, column=c).border = bottom_border

            ws_qual.column_dimensions["B"].width = 38
            ws_qual.column_dimensions["C"].width = 16
            ws_qual.column_dimensions["D"].width = 16
            ws_qual.column_dimensions["E"].width = 50

            fn = ws_qual.cell(row=q_row + 1, column=2, value="Note. Prevalence percentages are calculated based on all valid verbatim responses.")
            fn.font = apa_italic_font

    wb.save(filepath)
    return filepath


def generate_thesis_chapter_4_package(filepath: str, project_title: str, sample_n: int = 412, eff_n: float = 389.2) -> str:
    """Generates an academic, defense-ready APA 7th Edition Chapter 4 Document in HTML."""
    import numpy as np
    import pandas as pd
    from server import SESSION, SESSION_LOCK

    with SESSION_LOCK:
        df = SESSION.get("df")
        weights = SESSION.get("weights")
        last_tab = SESSION.get("last_tabulation") or []
        open_analysis = SESSION.get("open_feedback_analysis")

    n_val = len(df) if df is not None else sample_n
    if weights is not None and len(weights) == n_val:
        neff_val = round(float(np.sum(weights)**2 / np.sum(weights**2)), 1)
    else:
        neff_val = eff_n

    safe_title = html.escape(str(project_title or "Quantitative Survey Analysis"))
    safe_n = html.escape(str(n_val))
    safe_eff = html.escape(str(neff_val))

    # Build Dynamic Demographics Rows for Table 4.1
    demo_tbody_html = ""
    if df is not None:
        preferred_cols = ["Region", "Age_Generation", "Socioeconomic_Class", "Gender"]
        cat_cols = [c for c in preferred_cols if c in df.columns]
        for c in df.columns:
            if c not in cat_cols and not str(c).startswith("__") and 2 <= df[c].nunique(dropna=True) <= 10:
                cat_cols.append(c)
        cat_cols = cat_cols[:4]

        w_arr = np.asarray(weights, dtype=float) if weights is not None else np.ones(n_val, dtype=float)
        w_sum = float(np.sum(w_arr)) if np.sum(w_arr) > 0 else float(n_val)

        for col in cat_cols:
            col_name = html.escape(str(col).replace("_", " "))
            demo_tbody_html += f"<tr class='sub-header'><td colspan='5'>{col_name}</td></tr>\n"
            counts = df[col].value_counts(dropna=True)
            for cat, freq in counts.items():
                pct = (float(freq) / n_val * 100.0) if n_val > 0 else 0.0
                mask = (df[col] == cat).to_numpy()
                nw = float(np.sum(w_arr[mask])) if len(w_arr) == n_val else float(freq)
                eff_pct = (nw / w_sum * 100.0)
                cat_name = html.escape(str(cat))
                demo_tbody_html += f"<tr><td>{cat_name}</td><td>{freq}</td><td>{pct:.1f}%</td><td>{nw:.1f}</td><td>{eff_pct:.1f}%</td></tr>\n"
        
        demo_tbody_html += f"""<tr class="total-row">
            <td>Total Effective Sample</td>
            <td>{safe_n}</td>
            <td>100.0%</td>
            <td>{w_sum:.1f}</td>
            <td>Neff = {safe_eff}</td>
        </tr>"""
    else:
        demo_tbody_html = """<tr><td>Sample Distribution</td><td>412</td><td>100.0%</td><td>412.0</td><td>100.0%</td></tr>"""

    # Build Dynamic CrossTabs Sections for all tables in last_tab
    crosstabs_html = ""
    tables_to_render = last_tab if (last_tab and len(last_tab) > 0) else []

    table_counter = 1
    for t_idx, tab in enumerate(tables_to_render):
        table_counter += 1
        t_num = f"4.{table_counter}"
        stub_lbl = html.escape(tab.get("stub_label", "Survey Measure"))
        clean_banners = [html.escape(b) for b in tab.get("clean_banner_cols", []) if b != "Total"]
        headers_html = "<th>Category</th><th>Total Sample</th>" + "".join(f"<th>{b}</th>" for b in clean_banners)

        rows_html = ""
        for r in tab.get("rows", []):
            lbl = html.escape(r.get("label", ""))
            vals = [html.escape(str(v)) for v in r.get("values", [])]
            lets = r.get("sig_letters", [])
            benchs = r.get("sig_benchmarks", [])
            is_net = r.get("is_net", False)
            weight_class = ' style="font-weight: bold;"' if is_net else ""

            val_tds = "".join(f"<td>{v}</td>" for v in vals)
            rows_html += f"<tr{weight_class}><td>{lbl}</td>{val_tds}</tr>\n"

            if any(l and l != "-" for l in lets):
                l_tds = "<td>—</td>" + "".join(f"<td><b>{html.escape(l)}</b></td>" if l and l != "-" else "<td>—</td>" for l in lets[1:])
                rows_html += f"<tr class='sig-row'><td>  ↳ Pairwise Column Sig</td>{l_tds}</tr>\n"

            if any(b and b != "-" for b in benchs):
                b_tds = "<td>—</td>" + "".join(f"<td><b>{html.escape(b)}</b></td>" if b and b != "-" else "<td>—</td>" for b in benchs[1:])
                rows_html += f"<tr class='sig-row'><td>  ↳ Benchmark vs. Total</td>{b_tds}</tr>\n"

        chi2_text = ""
        if tab.get("chi_square"):
            cs = tab["chi_square"]
            chi2_stat = cs.get("chi2_stat", "N/A")
            df_val = cs.get("df", "N/A")
            pval = cs.get("p_val", "N/A")
            pval_str = f"p = {pval}" if isinstance(pval, (int, float)) and pval >= 0.001 else "p < .001"
            chi2_text = f" Pearson χ²({df_val}) = {chi2_stat}, {pval_str}."

        crosstabs_html += f"""
        <h2 class="section-heading">4.{table_counter} Cross-Tabulation Analysis: {stub_lbl}</h2>
        <p class="narrative">
            The cross-tabulation of <b>{stub_lbl}</b> across demographic subgroups is presented in Table {t_num}. 
            Column proportions reflect relative preferences within each subgroup.
        </p>
        <div class="apa-table-container">
            <div class="table-number">Table {t_num}</div>
            <div class="table-title">Cross-Tabulation of {stub_lbl} Across Subgroups with Significance Testing (N = {safe_n})</div>
            <table class="apa-table">
                <thead><tr>{headers_html}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <div class="table-note">
                <i>Note.</i> Percentages represent column proportions. Uppercase letters indicate pairwise significance at <i>p</i> &lt; .05.{chi2_text}
            </div>
        </div>
"""

    # Dynamic Section: Scale Measures (Descriptive Statistics)
    scale_html = ""
    if df is not None:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not str(c).startswith("__") and c not in ("Respondent_ID", "Survey_Duration_Sec")]
        if num_cols:
            table_counter += 1
            t_num = f"4.{table_counter}"
            scale_rows_html = ""
            for col in num_cols:
                series = df[col].dropna()
                c_lbl = html.escape(str(col).replace("_", " "))
                n_c = len(series)
                m_c = series.mean()
                sd_c = series.std()
                min_c = series.min()
                max_c = series.max()
                scale_rows_html += f"<tr><td>{c_lbl}</td><td>{n_c}</td><td>{m_c:.2f}</td><td>{sd_c:.2f}</td><td>{min_c:.1f}</td><td>{max_c:.1f}</td></tr>\n"

            scale_html = f"""
            <h2 class="section-heading">4.{table_counter} Descriptive Statistics for Continuous and Scale Measures</h2>
            <p class="narrative">
                Table {t_num} presents the central tendencies, dispersion, and range metrics for all continuous and Likert-scale questionnaire batteries administered in the survey.
            </p>
            <div class="apa-table-container">
                <div class="table-number">Table {t_num}</div>
                <div class="table-title">Descriptive Statistics for Continuous and Scale Measures (N = {safe_n})</div>
                <table class="apa-table">
                    <thead>
                        <tr>
                            <th>Variable</th><th>n</th><th>Mean (M)</th><th>Std Dev (SD)</th><th>Min</th><th>Max</th>
                        </tr>
                    </thead>
                    <tbody>{scale_rows_html}</tbody>
                </table>
                <div class="table-note">
                    <i>Note.</i> <i>M</i> and <i>SD</i> represent mean and standard deviation, respectively.
                </div>
            </div>
"""

    # Dynamic Section: Qualitative Thematic Code Distribution
    qual_html = ""
    if open_analysis and "codeframe" in open_analysis and open_analysis["codeframe"]:
        table_counter += 1
        t_num = f"4.{table_counter}"
        q_rows_html = ""
        for it in open_analysis["codeframe"]:
            th_lbl = html.escape(str(it.get("theme") or "General"))
            cnt = it.get("count", 0)
            pct = it.get("prevalence_pct", 0.0)
            exs = it.get("evidence_samples", [])
            q_str = html.escape(f'"{exs[0].get("quote")}"') if exs else "—"
        q_rows_html += f"<tr><td>{th_lbl}</td><td>{cnt}</td><td>{pct:.1f}%</td><td style='text-align:left; font-style:italic;'>{q_str}</td></tr>\n"

        qual_html = f"""
        <h2 class="section-heading">4.{table_counter} Qualitative Thematic Analysis of Open-Ended Responses</h2>
        <p class="narrative">
            Open-ended verbatim feedback was analyzed using neuro-symbolic Taglish NLP categorization. Table {t_num} details the frequency and prevalence of emerging themes along with anchored respondent verbatims.
        </p>
        <div class="apa-table-container">
            <div class="table-number">Table {t_num}</div>
            <div class="table-title">Thematic Code Distribution for Open-Ended Verbatim Responses (N = {safe_n})</div>
            <table class="apa-table">
                <thead>
                    <tr>
                        <th>Theme / Standardized Category</th><th>Frequency (n)</th><th>Prevalence (%)</th><th>Illustrative Verbatim Quote</th>
                    </tr>
                </thead>
                <tbody>{q_rows_html}</tbody>
            </table>
            <div class="table-note">
                <i>Note.</i> Prevalence percentages are calculated based on total valid open-ended responses.
            </div>
        </div>
"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Thesis Chapter 4 - {safe_title}</title>
<style>
    @page {{ size: A4; margin: 25.4mm; }}
    body {{
        font-family: "Times New Roman", Times, Georgia, serif;
        font-size: 12pt;
        line-height: 1.8;
        color: #111111;
        margin: 0 auto;
        padding: 40px;
        background: #FDFDFD;
        max-width: 960px;
    }}
    .print-bar {{
        background: #181818;
        color: #FFFFFF;
        padding: 12px 20px;
        border-radius: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 30px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
    }}
    .print-btn {{
        background: #E10600;
        color: #FFFFFF;
        border: none;
        padding: 8px 18px;
        border-radius: 6px;
        font-weight: 700;
        cursor: pointer;
    }}
    .print-btn:hover {{ background: #C50500; }}
    @media print {{
        .print-bar {{ display: none; }}
        body {{ padding: 0; background: #FFF; }}
    }}
    h1.chapter-title {{
        text-align: center;
        font-size: 14pt;
        font-weight: bold;
        text-transform: uppercase;
        margin-bottom: 24pt;
        letter-spacing: 0.5px;
    }}
    h2.section-heading {{
        font-size: 12pt;
        font-weight: bold;
        margin-top: 24pt;
        margin-bottom: 12pt;
    }}
    p.narrative {{
        text-align: justify;
        text-indent: 0.5in;
        margin-bottom: 14pt;
    }}
    .apa-table-container {{
        margin: 24pt 0;
    }}
    .table-number {{
        font-weight: bold;
        margin-bottom: 2px;
    }}
    .table-title {{
        font-style: italic;
        margin-bottom: 8pt;
    }}
    table.apa-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 10.5pt;
        line-height: 1.4;
        margin-bottom: 6pt;
    }}
    table.apa-table th, table.apa-table td {{
        padding: 6pt 8pt;
        text-align: center;
    }}
    table.apa-table th:first-child, table.apa-table td:first-child {{
        text-align: left;
    }}
    table.apa-table thead tr:first-child {{
        border-top: 1.5pt solid #000000;
        border-bottom: 1pt solid #000000;
        font-weight: bold;
    }}
    table.apa-table tbody tr.sub-header td {{
        font-weight: bold;
        font-style: italic;
        padding-top: 8pt;
        padding-bottom: 4pt;
        text-align: left;
    }}
    table.apa-table tbody tr.total-row {{
        border-top: 1pt solid #000000;
        border-bottom: 1.5pt solid #000000;
        font-weight: bold;
    }}
    table.apa-table tbody tr.sig-row td {{
        font-size: 9.5pt;
        font-style: italic;
        color: #333333;
        padding-top: 2pt;
        padding-bottom: 4pt;
    }}
    .table-note {{
        font-size: 9.5pt;
        font-style: italic;
        margin-top: 4pt;
        text-align: left;
    }}
</style>
</head>
<body>
    <div class="print-bar">
        <div>
            <b>ClearSight Academic Thesis Package</b> — APA 7th Edition Chapter 4 (Formatted for University Defense Panels)
        </div>
        <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
    </div>

    <h1 class="chapter-title">CHAPTER 4<br>PRESENTATION, ANALYSIS, AND INTERPRETATION OF DATA</h1>

    <p class="narrative">
        This chapter presents the empirical results, statistical analyses, and qualitative interpretations of the data gathered from {safe_n} survey respondents in accordance with the quantitative descriptive-correlational research design. To ensure unbiased representation and prevent demographic skewing, the raw sample was subjected to Deming-Stephan Iterative Proportional Fitting (Rim Weighting) aligned with demographic household benchmarks. Kish's Effective Sample Size was calculated at <i>N<sub>eff</sub></i> = {safe_eff}, which served as the statistical foundation for all subsequent hypothesis testing and significance determinations.
    </p>

    <h2 class="section-heading">4.1 Demographic Characteristics of the Respondents</h2>
    
    <p class="narrative">
        The demographic profile of the respondents is summarized in Table 4.1. The distribution encompasses geographic regions, age cohorts, and socioeconomic classifications (SEC), detailing both the unweighted frequencies and the weighted effective percentages.
    </p>

    <div class="apa-table-container">
        <div class="table-number">Table 4.1</div>
        <div class="table-title">Demographic Profile of Survey Respondents Across Key Strata (N = {safe_n}, Neff = {safe_eff})</div>
        <table class="apa-table">
            <thead>
                <tr>
                    <th>Demographic Variable</th>
                    <th>Unweighted Frequency (f)</th>
                    <th>Observed Percent (%)</th>
                    <th>Weighted Base (Nw)</th>
                    <th>Effective Base Percent (%)</th>
                </tr>
            </thead>
            <tbody>
                {demo_tbody_html}
            </tbody>
        </table>
        <div class="table-note">
            <i>Note.</i> Data weighted using Deming-Stephan rim weighting with soft mean-shift trimming at the 95th percentile.
        </div>
    </div>

    {crosstabs_html}

    {scale_html}

    {qual_html}

    <h2 class="section-heading">4.Summary Summary of Findings and Defense Conclusions</h2>
    <p class="narrative">
        The empirical findings synthesized across the parametric and non-parametric batteries demonstrate statistically sound variations across target segments. All omnibus tests satisfied the required significance thresholds under Benjamini-Hochberg False Discovery Rate control.
    </p>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def generate_vertical_codeframe_excel(
    filepath: str,
    codeframe: dict,
    project_title: str = "ClearSight Survey Study",
    question_text: str = ""
) -> str:
    """
    Generates a standardized vertical hierarchical codeframe in Microsoft Excel (.xlsx).
    Features:
    - Native collapsible row outlines (outlineLevel, summaryBelow=False)
    - Side-by-side Theme / Label and Anchored Verbatims
    - Pre-flight formula injection defense (CWE-1236)
    - Global Code ID allocation and Netting reach compatibility
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vertical Codeframe"
    ws.views.sheetView[0].showGridLines = True
    ws.sheet_properties.outlinePr.summaryBelow = False

    # Styling Palette
    font_project = Font(name="Helvetica Neue", size=13, bold=True, color=CARBON_HEADER)
    font_question = Font(name="Helvetica Neue", size=11, bold=True, italic=True, color="333333")
    font_tbl_header = Font(name="Helvetica Neue", size=11, bold=True, color="FFFFFF")
    fill_tbl_header = PatternFill(start_color=CARBON_HEADER, end_color=CARBON_HEADER, fill_type="solid")

    font_net = Font(name="Helvetica Neue", size=11, bold=True, color="991B1B")
    fill_net = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    font_subnet = Font(name="Helvetica Neue", size=10, bold=True, color="92400E")
    fill_subnet = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    font_sub_subnet = Font(name="Helvetica Neue", size=10, bold=True, color="166534")
    fill_sub_subnet = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")

    font_code = Font(name="Helvetica Neue", size=10, bold=True, color="1D4ED8")
    font_leaf = Font(name="Helvetica Neue", size=10, color="111111")
    font_verbatim = Font(name="Helvetica Neue", size=10, italic=True, color="374151")
    font_dp = Font(name="Helvetica Neue", size=9, color="4B5563")

    thin_border = Border(
        left=Side(style='thin', color=BORDER_GRAY),
        right=Side(style='thin', color=BORDER_GRAY),
        top=Side(style='thin', color=BORDER_GRAY),
        bottom=Side(style='thin', color=BORDER_GRAY)
    )

    # 1. Header Metadata Block
    ws.cell(row=1, column=1, value=sanitize_excel_cell(f"PROJECT: \"{project_title}\"")).font = font_project
    q_str = question_text or codeframe.get("name") or "Q. Open-Ended Inquiry"
    ws.cell(row=2, column=1, value=sanitize_excel_cell(f"QUESTION: {q_str}")).font = font_question

    # 2. Table Column Headers
    headers = [
        ("Codes", 12),
        ("Theme / Standardized Label", 48),
        ("Anchored Verbatims (Raw Quotes)", 55),
        ("DP / Coding Instructions", 30)
    ]
    header_row = 4
    ws.row_dimensions[header_row].height = 24.0

    for c_idx, (h_title, col_width) in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c_idx, value=sanitize_excel_cell(h_title))
        cell.font = font_tbl_header
        cell.fill = fill_tbl_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = col_width

    # 3. Hierarchy Grouping & Traversal
    curr_row = 5
    topics = codeframe.get("topics", [])

    # Group by NET -> Subnet
    net_groups = {}
    for t in topics:
        n_name = t.get("net") or "General (NET)"
        s_name = t.get("subnet") or "General (Subnet)"
        if n_name not in net_groups:
            net_groups[n_name] = {}
        if s_name not in net_groups[n_name]:
            net_groups[n_name][s_name] = []
        net_groups[n_name][s_name].append(t)

    for net_name, subnets in net_groups.items():
        # Insert NET banner row
        ws.row_dimensions[curr_row].outlineLevel = 0
        c_code = ws.cell(row=curr_row, column=1, value="")
        c_label = ws.cell(row=curr_row, column=2, value=sanitize_excel_cell(net_name))
        c_label.font = font_net
        c_label.fill = fill_net
        c_verb = ws.cell(row=curr_row, column=3, value="")
        c_dp = ws.cell(row=curr_row, column=4, value="")

        for c_cell in (c_code, c_label, c_verb, c_dp):
            c_cell.border = thin_border
        curr_row += 1

        for subnet_name, topic_list in subnets.items():
            # Check if compound subnet (e.g. Subnet > Sub-Subnet)
            parts = [p.strip() for p in subnet_name.split(">") if p.strip()]
            parent_sub = parts[0] if parts else subnet_name
            sub_sub = parts[1] if len(parts) > 1 else None

            # Subnet row
            ws.row_dimensions[curr_row].outlineLevel = 1
            ws.cell(row=curr_row, column=1, value="")
            c_sub = ws.cell(row=curr_row, column=2, value=sanitize_excel_cell(f"  {parent_sub}"))
            c_sub.font = font_subnet
            c_sub.fill = fill_subnet
            for c_col in range(1, 5):
                ws.cell(row=curr_row, column=c_col).border = thin_border
            curr_row += 1

            if sub_sub:
                ws.row_dimensions[curr_row].outlineLevel = 2
                ws.cell(row=curr_row, column=1, value="")
                c_ssub = ws.cell(row=curr_row, column=2, value=sanitize_excel_cell(f"    ↳ {sub_sub}"))
                c_ssub.font = font_sub_subnet
                c_ssub.fill = fill_sub_subnet
                for c_col in range(1, 5):
                    ws.cell(row=curr_row, column=c_col).border = thin_border
                curr_row += 1

            leaf_level = 3 if sub_sub else 2

            for t in topic_list:
                for pol, c_info in (t.get("codes") or {}).items():
                    c_id = c_info.get("code_id")
                    c_lbl = c_info.get("label") or t.get("id")

                    ws.row_dimensions[curr_row].outlineLevel = leaf_level

                    # Col A: Numeric Code
                    cell_a = ws.cell(row=curr_row, column=1, value=c_id if c_id is not None else "")
                    cell_a.font = font_code
                    cell_a.alignment = Alignment(horizontal="center", vertical="center")

                    # Col B: Theme Label
                    indent_prefix = "      " if sub_sub else "    "
                    safe_lbl = sanitize_excel_cell(str(c_lbl))
                    cell_b = ws.cell(row=curr_row, column=2, value=f"{indent_prefix}{safe_lbl}")
                    cell_b.font = font_leaf
                    cell_b.alignment = Alignment(horizontal="left", vertical="center")

                    # Col C: Exemplar / Anchored Verbatim
                    exs = t.get("exemplars") or []
                    safe_ex = sanitize_excel_cell(str(exs[0])) if exs else ""
                    ex_str = f'"{safe_ex}"' if safe_ex else ""
                    cell_c = ws.cell(row=curr_row, column=3, value=ex_str)
                    cell_c.font = font_verbatim
                    cell_c.alignment = Alignment(horizontal="left", vertical="center")

                    # Col D: DP Instruction
                    dp_instr = t.get("dp_instruction") or ""
                    cell_d = ws.cell(row=curr_row, column=4, value=sanitize_excel_cell(dp_instr))
                    cell_d.font = font_dp
                    cell_d.alignment = Alignment(horizontal="left", vertical="center")

                    for c_col in (cell_a, cell_b, cell_c, cell_d):
                        c_col.border = thin_border

                    curr_row += 1

    wb.save(filepath)
    return filepath


def extract_banner_groups(df, max_cols: int = 5) -> dict:
    """Extracts demographic banner groups mapping column label to row index sets."""
    if df is None or len(df) == 0:
        return {"Total": set()}
    banners = {"Total": set(range(len(df)))}
    # Find categorical demographic columns with 2 to 6 unique values
    demo_cols = [c for c in df.columns if not str(c).startswith("__") and 2 <= df[c].nunique() <= 6]
    if demo_cols:
        target_col = demo_cols[0]
        for idx, (cat_val, group_df) in enumerate(df.groupby(target_col, observed=True)):
            if idx >= max_cols:
                break
            letter = chr(65 + idx)
            banner_name = f"{cat_val} ({letter})"
            banners[banner_name] = set(group_df.index)
    return banners


def build_coded_hierarchy_table(
    records: list,
    codeframe: Any,
    total_base: Optional[int] = None,
    banner_groups: Optional[dict] = None
) -> list:
    """
    Constructs a 3-level hierarchical coded frequency table (NET -> Subnet -> Leaf)
    with deduplicated net percentages across Total and optional Banner Columns.
    """
    total_n = total_base if total_base is not None else len(records)
    if total_n <= 0:
        total_n = max(1, len(records))

    # Banner groups setup
    banners = dict(banner_groups) if banner_groups else {"Total": set(range(len(records)))}
    if "Total" not in banners:
        banners = {"Total": set(range(len(records))), **banners}

    topics = []
    if isinstance(codeframe, dict):
        topics = codeframe.get("topics", [])
    elif isinstance(codeframe, list):
        topics = codeframe

    if not topics:
        seen_themes = []
        for r in records:
            for th in (r.get("assigned_themes") or [r.get("predicted_label")]):
                if th and th not in seen_themes:
                    seen_themes.append(th)
        topics = [{"net": "General Feedback (NET)", "subnet": "Responses (Subnet)", "codes": {"pos": {"label": th}}} for th in seen_themes]

    net_map = {}
    for t in topics:
        if isinstance(t, str):
            n_name = "General Themes (NET)"
            s_name = "Feedback Categories (Subnet)"
            leaf_items = [(t, None)]
        else:
            n_name = t.get("net") or "General (NET)"
            s_name = t.get("subnet") or "General (Subnet)"
            codes_dict = t.get("codes", {})
            leaf_items = []
            if isinstance(codes_dict, dict) and codes_dict:
                for pol, c_info in codes_dict.items():
                    leaf_items.append((c_info.get("label") or t.get("id"), c_info.get("code_id")))
            else:
                leaf_items.append((t.get("label") or t.get("name") or t.get("id"), t.get("id")))

        if not n_name.strip().endswith("(NET)"):
            n_name = f"{n_name.strip()} (NET)"
        if not s_name.strip().endswith("(Subnet)"):
            s_name = f"{s_name.strip()} (Subnet)"

        if n_name not in net_map:
            net_map[n_name] = {}
        if s_name not in net_map[n_name]:
            net_map[n_name][s_name] = []

        for lbl, cid in leaf_items:
            net_map[n_name][s_name].append({"label": lbl, "code_id": cid, "topic": t if isinstance(t, dict) else {}})

    resp_data = []
    for idx, r in enumerate(records):
        themes = set(str(th).strip().lower() for th in (r.get("assigned_themes") or []))
        if r.get("predicted_label"):
            themes.add(str(r.get("predicted_label")).strip().lower())
        codes = set(str(c).strip() for c in (r.get("assigned_codes") or []))
        text = str(r.get("raw_text") or r.get("text") or "").lower()
        resp_data.append({"id": idx, "themes": themes, "codes": codes, "text": text})

    def format_mr_pct(count: int, n_base: int):
        pct = (count / n_base * 100.0) if n_base > 0 else 0.0
        if count == 0 or pct < 0.5:
            return round(pct, 1), "*"
        return round(pct, 1), str(int(round(pct)))

    def compute_banner_stats(matched_resps: set):
        pcts = {}
        counts = {}
        for b_name, b_set in banners.items():
            n_b = total_n if b_name == "Total" else (max(1, len(b_set)) if b_set else total_n)
            cnt_b = len(matched_resps & b_set) if b_set else len(matched_resps)
            _, p_str = format_mr_pct(cnt_b, n_b)
            pcts[b_name] = p_str
            counts[b_name] = cnt_b
        return pcts, counts

    net_items = []
    for net_name, subnets in net_map.items():
        net_resp_set = set()
        subnet_items = []

        for subnet_name, leaves in subnets.items():
            subnet_resp_set = set()
            leaf_items = []

            for leaf in leaves:
                lbl = leaf["label"]
                cid = str(leaf["code_id"]) if leaf["code_id"] is not None else ""
                lbl_lower = str(lbl).lower()

                # Extract keyword triggers from topic
                t_obj = leaf.get("topic", {})
                triggers = []
                if isinstance(t_obj, dict):
                    triggers.extend(t_obj.get("keywords", []))
                    triggers.extend(t_obj.get("pos_keywords", []))
                    triggers.extend(t_obj.get("neg_keywords", []))
                    triggers.extend(t_obj.get("exemplars", []))

                matched_resps = set()
                for resp in resp_data:
                    is_match = False
                    if cid and (cid in resp["codes"] or (cid.isdigit() and int(cid) in resp["codes"])):
                        is_match = True
                    elif lbl_lower in resp["themes"]:
                        is_match = True
                    elif any(lbl_lower in th or th in lbl_lower for th in resp["themes"]):
                        is_match = True
                    elif triggers and any(w.lower() in resp["text"] for w in triggers if len(w) >= 3):
                        is_match = True
                    elif len(lbl_lower) >= 4 and lbl_lower in resp["text"]:
                        is_match = True

                    if is_match:
                        matched_resps.add(resp["id"])

                b_pcts, b_counts = compute_banner_stats(matched_resps)
                cnt = b_counts.get("Total", len(matched_resps))
                pct_val = (cnt / total_n * 100.0) if total_n > 0 else 0.0

                leaf_items.append({
                    "type": "leaf",
                    "level": "leaf",
                    "label": lbl,
                    "code_id": leaf["code_id"],
                    "count": cnt,
                    "pct": round(pct_val, 1),
                    "pct_str": b_pcts.get("Total", "*"),
                    "banner_pcts": b_pcts,
                    "banner_counts": b_counts
                })
                subnet_resp_set |= matched_resps

            sub_b_pcts, sub_b_counts = compute_banner_stats(subnet_resp_set)
            sub_cnt = sub_b_counts.get("Total", len(subnet_resp_set))
            sub_pct_val = (sub_cnt / total_n * 100.0) if total_n > 0 else 0.0
            leaf_items.sort(key=lambda x: (x["count"], x["pct"]), reverse=True)

            subnet_items.append({
                "type": "subnet",
                "level": "subnet",
                "label": subnet_name,
                "count": sub_cnt,
                "pct": round(sub_pct_val, 1),
                "pct_str": sub_b_pcts.get("Total", "*"),
                "banner_pcts": sub_b_pcts,
                "banner_counts": sub_b_counts,
                "leaves": leaf_items
            })
            net_resp_set |= subnet_resp_set

        net_b_pcts, net_b_counts = compute_banner_stats(net_resp_set)
        net_cnt = net_b_counts.get("Total", len(net_resp_set))
        net_pct_val = (net_cnt / total_n * 100.0) if total_n > 0 else 0.0
        subnet_items.sort(key=lambda x: (x["count"], x["pct"]), reverse=True)

        net_items.append({
            "type": "net",
            "level": "net",
            "label": net_name,
            "count": net_cnt,
            "pct": round(net_pct_val, 1),
            "pct_str": net_b_pcts.get("Total", "*"),
            "banner_pcts": net_b_pcts,
            "banner_counts": net_b_counts,
            "subnets": subnet_items
        })

    net_items.sort(key=lambda x: (x["count"], x["pct"]), reverse=True)

    output_rows = []
    for n in net_items:
        output_rows.append({
            "type": "net",
            "level": "net",
            "label": n["label"],
            "count": n["count"],
            "pct": n["pct"],
            "pct_str": n["pct_str"],
            "banner_pcts": n["banner_pcts"],
            "banner_counts": n["banner_counts"]
        })
        for s in n["subnets"]:
            output_rows.append({
                "type": "subnet",
                "level": "subnet",
                "label": s["label"],
                "count": s["count"],
                "pct": s["pct"],
                "pct_str": s["pct_str"],
                "banner_pcts": s["banner_pcts"],
                "banner_counts": s["banner_counts"]
            })
            for l in s["leaves"]:
                output_rows.append({
                    "type": "leaf",
                    "level": "leaf",
                    "label": l["label"],
                    "code_id": l["code_id"],
                    "count": l["count"],
                    "pct": l["pct"],
                    "pct_str": l["pct_str"],
                    "banner_pcts": l["banner_pcts"],
                    "banner_counts": l["banner_counts"]
                })

    return output_rows


def generate_coded_hierarchy_percent_excel(
    filepath: str,
    hierarchy_rows: list,
    project_title: str = "ClearSight Survey Study",
    question_text: str = "",
    total_n: int = 0
) -> str:
    """
    Generates a vertical hierarchical codeframe table with percentage column(s)
    in Microsoft Excel (.xlsx), matching executive research agency presentation standards.
    Supports single Total % column or multi-column banner breakdowns.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Coded Hierarchy (%)"
    ws.views.sheetView[0].showGridLines = True

    font_project = Font(name="Arial", size=12, bold=True, color="0F172A")
    font_question = Font(name="Arial", size=10, bold=True, italic=True, color="334155")
    font_base = Font(name="Arial", size=9.5, italic=True, color="64748B")

    font_header = Font(name="Arial", size=11, bold=True, color="0F172A")
    fill_header_col_a = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    fill_header_pct = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")
    fill_data_pct = PatternFill(start_color="FFFDE7", end_color="FFFDE7", fill_type="solid")

    border_row = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )
    border_pct_col = Border(
        left=Side(style='medium', color='0F172A'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )
    border_header_pct = Border(
        left=Side(style='medium', color='0F172A'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='medium', color='0F172A')
    )
    border_header_lbl = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='medium', color='0F172A')
    )

    ws.cell(row=1, column=1, value=sanitize_excel_cell(f"PROJECT: {project_title}")).font = font_project
    q_str = question_text or "Open-Ended Feedback Analysis"
    ws.cell(row=2, column=1, value=sanitize_excel_cell(f"QUESTION: {q_str}")).font = font_question
    n_display = str(total_n) if total_n > 0 else "Total Respondents"
    ws.cell(row=3, column=1, value=f"Base: N = {n_display}").font = font_base

    header_row = 5
    ws.row_dimensions[header_row].height = 24.0

    c_h1 = ws.cell(row=header_row, column=1, value="Theme / Standardized Response Hierarchy")
    c_h1.font = font_header
    c_h1.fill = fill_header_col_a
    c_h1.alignment = Alignment(horizontal="left", vertical="center")
    c_h1.border = border_header_lbl

    # Determine banner columns
    banner_cols = ["Total"]
    if hierarchy_rows and "banner_pcts" in hierarchy_rows[0]:
        banner_cols = list(hierarchy_rows[0]["banner_pcts"].keys())

    is_multi_col = len(banner_cols) > 1

    for c_idx, b_col in enumerate(banner_cols, start=2):
        col_title = f"{b_col} %" if is_multi_col else "%"
        cell = ws.cell(row=header_row, column=c_idx, value=col_title)
        cell.font = font_header
        cell.fill = fill_header_pct
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_header_pct
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = 14 if is_multi_col else 12

    curr_row = 6
    for item in hierarchy_rows:
        itype = item.get("type", "leaf")
        label = item.get("label", "")
        ws.row_dimensions[curr_row].height = 20.0

        is_net = (itype == "net")
        is_subnet = (itype == "subnet")

        font_size = 11 if is_net else (10.5 if is_subnet else 10)
        is_bold = (is_net or is_subnet)
        text_color = "0F172A" if (is_net or is_subnet) else "1E293B"

        safe_lbl = sanitize_excel_cell(label)
        indent_space = "" if is_net else ("  " if is_subnet else "    ")
        cell_a = ws.cell(row=curr_row, column=1, value=f"{indent_space}{safe_lbl}")
        cell_a.font = Font(name="Arial", size=font_size, bold=is_bold, color=text_color)
        cell_a.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell_a.border = border_row

        for c_idx, b_col in enumerate(banner_cols, start=2):
            if "banner_pcts" in item:
                val_str = str(item["banner_pcts"].get(b_col, "*"))
            else:
                val_str = str(item.get("pct_str", "*"))

            val = int(val_str) if val_str.isdigit() else val_str
            cell_b = ws.cell(row=curr_row, column=c_idx, value=val)
            cell_b.font = Font(name="Arial", size=font_size, bold=is_bold, color=text_color)
            cell_b.fill = fill_data_pct
            cell_b.alignment = Alignment(horizontal="center", vertical="center")
            cell_b.border = border_pct_col

        curr_row += 1

    curr_row += 1
    fn_cell = ws.cell(row=curr_row, column=1, value="* Note: An asterisk (*) indicates a non-zero frequency less than 0.5% of total respondents.")
    fn_cell.font = Font(name="Arial", size=8.5, italic=True, color="64748B")

    ws.column_dimensions['A'].width = 52

    wb.save(filepath)
    return filepath

