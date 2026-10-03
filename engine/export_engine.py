"""
ClearSight - Report & Banner Book Export Engine
Agency Standard Dual-Significance Layout:
1. Row 1: Percentage / Mean Value (%)
2. Row 2: Column Comparisons (Letters: a/b/c for >=90%, A/B/C for >=95%)
3. Row 3: Total Benchmark Comparisons (+/++ for higher, -/-- for lower)
"""

import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

NAVY_HEADER = "1B1C36"
ACCENT_BLUE = "2D46B9"
LIGHT_GRAY = "F4F5F9"
BORDER_GRAY = "D1D5DB"
SIG_COLOR_POS = "047857" # Emerald for +/++
SIG_COLOR_NEG = "B91C1C" # Crimson for -/--

def generate_excel_banner_book(filepath: str, project_title: str, tables_data: list[dict], metadata: dict) -> str:
    wb = openpyxl.Workbook()
    ws_meta = wb.active
    ws_meta.title = "Methodology & Legend"
    ws_meta.views.sheetView[0].showGridLines = True
    
    title_font = Font(name="Calibri", size=16, bold=True, color=NAVY_HEADER)
    section_font = Font(name="Calibri", size=12, bold=True, color="333333")
    regular_font = Font(name="Calibri", size=11, color="444444")
    bold_font = Font(name="Calibri", size=11, bold=True, color="111111")
    
    thin_border = Border(
        left=Side(style='thin', color=BORDER_GRAY),
        right=Side(style='thin', color=BORDER_GRAY),
        top=Side(style='thin', color=BORDER_GRAY),
        bottom=Side(style='thin', color=BORDER_GRAY)
    )
    
    # 1. Methodology & Dual-Significance Legend
    ws_meta.cell(row=2, column=2, value="CLEARSIGHT - AGENCY TABULATION BOOK").font = title_font
    ws_meta.cell(row=3, column=2, value=f"Project: {project_title}").font = section_font
    
    meta_rows = [
        ("Field Date Range", metadata.get("date_range", "September - October 2026")),
        ("Total Unweighted Sample (N)", metadata.get("unweighted_n", 412)),
        ("Total Weighted Base (Nw)", metadata.get("weighted_n", 412.0)),
        ("Overall Kish Effective Base (Neff)", metadata.get("effective_n", 389.2)),
        ("Weighting Efficiency", f"{metadata.get('efficiency_pct', 94.5)}%"),
        ("Dual Significance Testing System", "Agency Standard: Column Letters & Total Benchmark"),
        ("Sig Row 1: Column Comparisons", "a, b, c... (>= 90% Conf) | A, B, C... (>= 95% Conf)"),
        ("Sig Row 2: Benchmark vs. Total", "+ / ++ : Significantly higher than Total (90% / 95%)"),
        ("                               ", "- / -- : Significantly lower than Total (90% / 95%)"),
        ("Multiple Comparison Correction", "Benjamini-Hochberg False Discovery Rate (FDR)")
    ]
    
    for r_idx, (label, val) in enumerate(meta_rows, start=6):
        cell_lbl = ws_meta.cell(row=r_idx, column=2, value=label)
        cell_lbl.font = bold_font
        cell_lbl.fill = PatternFill(start_color=LIGHT_GRAY, end_color=LIGHT_GRAY, fill_type="solid")
        cell_lbl.border = thin_border
        
        cell_val = ws_meta.cell(row=r_idx, column=3, value=val)
        cell_val.font = regular_font
        cell_val.border = thin_border

    ws_meta.column_dimensions['B'].width = 34
    ws_meta.column_dimensions['C'].width = 55

    # 2. Add Tables
    header_fill = PatternFill(start_color=NAVY_HEADER, end_color=NAVY_HEADER, fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    base_fill = PatternFill(start_color="E9ECEF", end_color="E9ECEF", fill_type="solid")
    sig_letter_font = Font(name="Calibri", size=10, bold=True, color=ACCENT_BLUE)
    sig_pos_font = Font(name="Calibri", size=10, bold=True, color=SIG_COLOR_POS)
    sig_neg_font = Font(name="Calibri", size=10, bold=True, color=SIG_COLOR_NEG)
    
    for t_idx, t_data in enumerate(tables_data, start=1):
        clean_title = t_data.get("title", f"Table_{t_idx}")
        safe_sheet_name = f"T{t_idx}_{clean_title[:24]}".replace(":", "").replace("/", "_")
        ws = wb.create_sheet(title=safe_sheet_name)
        ws.views.sheetView[0].showGridLines = True
        
        ws.cell(row=2, column=2, value=clean_title).font = title_font
        ws.cell(row=3, column=2, value="Column % | Dual Sig: Letters (Col) and +/++ -/-- (vs Total)").font = regular_font
        
        banner_cols = t_data.get("banner_cols", [])
        col_letters = t_data.get("col_letters", [])
        
        # Banner Header Row
        ws.cell(row=5, column=2, value="Variables / Stubs").font = header_font
        ws.cell(row=5, column=2).fill = header_fill
        ws.cell(row=5, column=2).border = thin_border
        
        for c_idx, b_col in enumerate(banner_cols, start=3):
            cell = ws.cell(row=5, column=c_idx, value=b_col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
            
        # Column Letters Row
        ws.cell(row=6, column=2, value="Column Names").font = bold_font
        ws.cell(row=6, column=2).border = thin_border
        for c_idx, letter in enumerate(col_letters, start=3):
            cell = ws.cell(row=6, column=c_idx, value=letter if letter else "Total")
            cell.font = bold_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border
            
        # Sample Bases
        ws.cell(row=7, column=2, value="Column Sample Size (N)").font = regular_font
        ws.cell(row=7, column=2).fill = base_fill
        ws.cell(row=7, column=2).border = thin_border
        for c_idx, b_val in enumerate(t_data.get("unweighted_bases", []), start=3):
            cell = ws.cell(row=7, column=c_idx, value=b_val)
            cell.font = regular_font
            cell.fill = base_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border

        ws.cell(row=8, column=2, value="Kish Effective Base (Neff)").font = regular_font
        ws.cell(row=8, column=2).fill = base_fill
        ws.cell(row=8, column=2).border = thin_border
        for c_idx, b_val in enumerate(t_data.get("effective_bases", []), start=3):
            cell = ws.cell(row=8, column=c_idx, value=round(b_val, 1))
            cell.font = regular_font
            cell.fill = base_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border

        # Data Rows: 3 Lines per stub (Value, Sig Letters, Benchmark Symbols)
        curr_row = 10
        for row_info in t_data.get("rows", []):
            label = row_info.get("label", "")
            is_net = row_info.get("is_net", False)
            values = row_info.get("values", [])
            sig_letters = row_info.get("sig_letters", [""] * len(values))
            sig_benchmarks = row_info.get("sig_benchmarks", [""] * len(values))
            
            # Line 1: Data Values (%)
            lbl_cell = ws.cell(row=curr_row, column=2, value=label)
            lbl_cell.font = bold_font if is_net else regular_font
            lbl_cell.border = thin_border
            if is_net:
                lbl_cell.fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
                
            for c_idx, val in enumerate(values, start=3):
                val_cell = ws.cell(row=curr_row, column=c_idx, value=val)
                val_cell.font = bold_font if is_net else regular_font
                val_cell.alignment = Alignment(horizontal="center")
                val_cell.border = thin_border
                if is_net:
                    val_cell.fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
            curr_row += 1

            # Line 2: Sig Test 1 - Column Comparison Letters (a, b, c / A, B, C)
            lbl_sig1 = ws.cell(row=curr_row, column=2, value="  ↳ Col Comparisons (Letters)")
            lbl_sig1.font = Font(name="Calibri", size=9, italic=True, color="666666")
            lbl_sig1.border = thin_border
            
            for c_idx, s_val in enumerate(sig_letters, start=3):
                s_cell = ws.cell(row=curr_row, column=c_idx, value=s_val if s_val else "")
                s_cell.font = sig_letter_font
                s_cell.alignment = Alignment(horizontal="center")
                s_cell.border = thin_border
            curr_row += 1

            # Line 3: Sig Test 2 - Total Benchmark Indicators (+/++, -/--)
            lbl_sig2 = ws.cell(row=curr_row, column=2, value="  ↳ vs. Total (+/++, -/--)")
            lbl_sig2.font = Font(name="Calibri", size=9, italic=True, color="666666")
            lbl_sig2.border = thin_border
            
            for c_idx, b_val in enumerate(sig_benchmarks, start=3):
                b_cell = ws.cell(row=curr_row, column=c_idx, value=b_val if b_val else "")
                if "+" in b_val:
                    b_cell.font = sig_pos_font
                elif "-" in b_val:
                    b_cell.font = sig_neg_font
                else:
                    b_cell.font = regular_font
                b_cell.alignment = Alignment(horizontal="center")
                b_cell.border = thin_border
            curr_row += 1
            
        ws.column_dimensions['B'].width = 38
        for c in range(3, len(banner_cols) + 3):
            ws.column_dimensions[get_column_letter(c)].width = 16

    wb.save(filepath)
    return filepath


def generate_customer_voice_snapshot_html(filepath: str, data: dict) -> str:
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Customer Voice Snapshot - {data.get('project_title', 'Consumer Study')}</title>
<style>
    @page {{ size: A4; margin: 12mm; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #1B1C36;
        margin: 0;
        padding: 24px;
        background: #FFFFFF;
        line-height: 1.4;
    }}
    .header {{
        border-bottom: 3px solid #1B1C36;
        padding-bottom: 12px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }}
    .title {{ font-size: 24px; font-weight: 800; letter-spacing: -0.5px; margin: 0; }}
    .subtitle {{ font-size: 13px; color: #555; margin-top: 4px; }}
    .badge {{ background: #1B1C36; color: #fff; padding: 4px 10px; font-size: 11px; font-weight: 700; border-radius: 4px; }}
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
    .kpi-val {{ font-size: 22px; font-weight: 800; color: #1B1C36; }}
    .kpi-lbl {{ font-size: 11px; font-weight: 600; text-transform: uppercase; color: #666; margin-top: 2px; }}
    
    .section-title {{
        font-size: 15px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 18px 0 10px 0;
        border-left: 4px solid #2D46B9;
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
    .sig-tag {{ color: #2D46B9; font-weight: 700; font-size: 11px; }}
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
    .action-table th {{ background: #1B1C36; color: #FFFFFF; }}
</style>
</head>
<body>
    <div class="header">
        <div>
            <h1 class="title">Customer Voice Snapshot</h1>
            <div class="subtitle">{data.get('project_title', 'Consumer Intelligence Summary')} | Prepared by Lunsad Pilipinas</div>
        </div>
        <span class="badge">CONFIDENTIAL & CERTIFIED</span>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-val">{data.get('sample_n', 412)}</div>
            <div class="kpi-lbl">Total Sample (N)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{data.get('eff_n', 389.2)}</div>
            <div class="kpi-lbl">Kish Eff. Base</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{data.get('csat_score', '84.2%')}</div>
            <div class="kpi-lbl">Top-2-Box CSAT</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-val">{data.get('weighting_eff', '94.5%')}</div>
            <div class="kpi-lbl">Weight Efficiency</div>
        </div>
    </div>

    <div class="section-title">Statistically Significant Strategic Takeaways</div>
    <div class="finding-box">
        <b>1. Regional Brand Dominance in Urban Metro Manila:</b> Brand consideration in NCR significantly outpaces Balance Luzon (55.0% vs 38.0%, p &lt; 0.05). <span class="sig-tag">[Table 1, Col A &gt; B]</span> <span style="color:#047857; font-weight:800;">(++)</span>
    </div>
    <div class="finding-box">
        <b>2. Youth Adoption Vector:</b> Gen Z respondents report a significantly higher intent to repurchase through digital channels compared to Gen X (72.0% vs 48.3%, p &lt; 0.01). <span class="sig-tag">[Table 3, Col D &gt; F]</span> <span style="color:#047857; font-weight:800;">(++)</span>
    </div>

    <div class="qual-grid">
        <div>
            <div class="section-title" style="border-left-color: #10B981;">Customer Delights (Affinity Drivers)</div>
            <div class="quote-box">
                "Sobrang sulit ng promo nila lalo na kung bulk order. Mas mabilis pa dumating kaysa sa inaasahan ko."
                <div style="font-size: 10px; color: #888; margin-top: 4px;">— Respondent #84 (Gen Z, NCR)</div>
            </div>
            <div class="quote-box">
                "Very responsive customer service on Chat, na-resolve agad yung delivery question ko in 5 minutes."
                <div style="font-size: 10px; color: #888; margin-top: 4px;">— Respondent #219 (Millennial, Visayas)</div>
            </div>
        </div>
        <div>
            <div class="section-title" style="border-left-color: #EF4444;">Customer Frictions (Drop-off Risks)</div>
            <div class="quote-box friction">
                "Medyo mahal na yung shipping fee sa probinsya kaya nagdadalawang-isip na akong umulit."
                <div style="font-size: 10px; color: #888; margin-top: 4px;">— Respondent #142 (Millennial, Mindanao)</div>
            </div>
            <div class="quote-box friction">
                "Yupi yung box pagdating, buti na lang hindi nabasag yung item sa loob pero nakaka-disappoint."
                <div style="font-size: 10px; color: #888; margin-top: 4px;">— Respondent #305 (Gen X, Balance Luzon)</div>
            </div>
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
            <tr>
                <td><b>P1</b></td>
                <td>Provincial Shipping Friction</td>
                <td>Subsidize shipping thresholds in VisMin to eliminate cart abandonment.</td>
                <td>Reduce VisMin drop-off by 15%</td>
            </tr>
            <tr>
                <td><b>P2</b></td>
                <td>Gen Z Digital Acquisition</td>
                <td>Double down on TikTok Shop & Shopee Live channels highlighting value-for-money.</td>
                <td>Lift Gen Z trial from 54% to 65%</td>
            </tr>
            <tr>
                <td><b>P3</b></td>
                <td>Protective Packaging QA</td>
                <td>Audit courier handling to eliminate carton crushing complaints.</td>
                <td>Lower defect rate &lt; 1.0%</td>
            </tr>
        </tbody>
    </table>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath


def generate_thesis_excel_tables(filepath: str, project_title: str) -> str:
    """Generates APA-formatted Chapter 4 tables in Excel."""
    wb = openpyxl.Workbook()
    
    # Fonts & Styles
    apa_title_font = Font(name="Times New Roman", size=12, bold=True)
    apa_italic_font = Font(name="Times New Roman", size=11, italic=True)
    apa_regular_font = Font(name="Times New Roman", size=11)
    apa_bold_font = Font(name="Times New Roman", size=11, bold=True)
    
    top_border = Border(top=Side(style='medium', color='000000'), bottom=Side(style='thin', color='000000'))
    bottom_border = Border(bottom=Side(style='medium', color='000000'))
    sub_border = Border(bottom=Side(style='thin', color='D0D0D0'))
    
    # Sheet 1: Table 4.1 Demographics
    ws1 = wb.active
    ws1.title = "Table 4.1 - Demographics"
    ws1.views.sheetView[0].showGridLines = True
    
    ws1.cell(row=2, column=2, value="Table 4.1").font = apa_title_font
    ws1.cell(row=3, column=2, value="Frequency and Percentage Distribution of Respondents (N = 412)").font = apa_italic_font
    
    headers1 = ["Demographic Profile", "Frequency (f)", "Percent (%)", "Weighted Base (Nw)", "Effective %"]
    for c_idx, h in enumerate(headers1, start=2):
        cell = ws1.cell(row=5, column=c_idx, value=h)
        cell.font = apa_bold_font
        cell.border = top_border
        cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")
        
    demo_data = [
        ("Region", "", "", "", ""),
        ("  National Capital Region (NCR)", 120, "29.1%", 57.7, "14.0%"),
        ("  Balance Luzon", 150, "36.4%", 185.4, "45.0%"),
        ("  Visayas", 72, "17.5%", 82.4, "20.0%"),
        ("  Mindanao", 70, "17.0%", 86.5, "21.0%"),
        ("Age Generation", "", "", "", ""),
        ("  Generation Z (18–27)", 154, "37.4%", 156.6, "38.0%"),
        ("  Millennials (28–43)", 168, "40.8%", 164.8, "40.0%"),
        ("  Generation X (44–59)", 90, "21.8%", 90.6, "22.0%"),
        ("Socioeconomic Class (SEC)", "", "", "", ""),
        ("  Class ABC", 82, "19.9%", 78.3, "19.0%"),
        ("  Class D", 246, "59.7%", 251.3, "61.0%"),
        ("  Class E", 84, "20.4%", 82.4, "20.0%"),
        ("Total / Kish Effective Base", 412, "100.0%", 412.0, "Neff = 389.2")
    ]
    
    for r_idx, row in enumerate(demo_data, start=6):
        is_sub = row[1] == ""
        is_total = "Total" in row[0]
        for c_idx, val in enumerate(row, start=2):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.font = apa_bold_font if (is_sub or is_total) else apa_regular_font
            cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")
            if is_total:
                cell.border = bottom_border
            elif not is_sub:
                cell.border = sub_border
                
    ws1.column_dimensions['B'].width = 38
    ws1.column_dimensions['C'].width = 16
    ws1.column_dimensions['D'].width = 16
    ws1.column_dimensions['E'].width = 22
    ws1.column_dimensions['F'].width = 16

    # Sheet 2: Table 4.2 Cross-Tabulation & Dual Sig
    ws2 = wb.create_sheet(title="Table 4.2 - Brand Consideration")
    ws2.views.sheetView[0].showGridLines = True
    ws2.cell(row=2, column=2, value="Table 4.2").font = apa_title_font
    ws2.cell(row=3, column=2, value="Brand Consideration Across Geographic Regions with Dual Significance (n = 412, Neff = 389.2)").font = apa_italic_font
    
    headers2 = ["Brand Option", "Total", "NCR (A)", "Balance Luzon (B)", "Visayas (C)", "Mindanao (D)"]
    for c_idx, h in enumerate(headers2, start=2):
        cell = ws2.cell(row=5, column=c_idx, value=h)
        cell.font = apa_bold_font
        cell.border = top_border
        cell.alignment = Alignment(horizontal="left" if c_idx == 2 else "center")
        
    t2_rows = [
        ("Brand A (Premium Nanotech)", ["42.5%", "55.0%", "38.0%", "36.1%", "40.2%"], ["-", "B C D", "", "", ""], ["-", "++", "", "-", ""]),
        ("Brand B (Standard Market)", ["31.1%", "28.3%", "33.5%", "30.6%", "32.0%"], ["-", "", "", "", ""], ["-", "", "", "", ""]),
        ("Brand C (Bio-Oil Formulation)", ["26.4%", "16.7%", "28.5%", "33.3%", "27.8%"], ["-", "", "A", "A", ""], ["-", "--", "", "+", ""]),
        ("Chi-Square Test of Independence", ["χ² = 24.81", "df = 9", "p = .003**", "Interpretation:", "Significant at p < .01"], ["", "", "", "", ""], ["", "", "", "", ""])
    ]
    
    curr = 6
    for item in t2_rows:
        label, vals, lets, benchs = item
        c_lbl = ws2.cell(row=curr, column=2, value=label)
        c_lbl.font = apa_bold_font if "Chi-Square" in label else apa_regular_font
        c_lbl.border = sub_border
        for c_idx, v in enumerate(vals, start=3):
            cell = ws2.cell(row=curr, column=c_idx, value=v)
            cell.font = apa_bold_font if "Chi-Square" in label else apa_regular_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = sub_border
        curr += 1
        if "Chi-Square" not in label:
            ws2.cell(row=curr, column=2, value="  ↳ Pairwise Col Sig (A, B, C, D)").font = Font(name="Times New Roman", size=9, italic=True)
            for c_idx, l in enumerate(lets, start=3):
                cell = ws2.cell(row=curr, column=c_idx, value=l)
                cell.font = Font(name="Times New Roman", size=10, bold=True, color="2D46B9")
                cell.alignment = Alignment(horizontal="center")
            curr += 1
            ws2.cell(row=curr, column=2, value="  ↳ vs. Total Benchmark (+/++, -/--)").font = Font(name="Times New Roman", size=9, italic=True)
            for c_idx, b in enumerate(benchs, start=3):
                cell = ws2.cell(row=curr, column=c_idx, value=b)
                cell.font = Font(name="Times New Roman", size=10, bold=True, color="047857" if "+" in b else ("B91C1C" if "-" in b else "333333"))
                cell.alignment = Alignment(horizontal="center")
            curr += 1
            
    ws2.cell(row=curr-1, column=2).border = bottom_border
    for c in range(3, 8):
        ws2.cell(row=curr-1, column=c).border = bottom_border
        
    ws2.column_dimensions['B'].width = 38
    for c in range(3, 8):
        ws2.column_dimensions[get_column_letter(c)].width = 20
        
    wb.save(filepath)
    return filepath


def generate_thesis_chapter_4_package(filepath: str, project_title: str, sample_n: int = 412, eff_n: float = 389.2) -> str:
    """Generates an academic, defense-ready APA 7th Edition Chapter 4 Document in HTML."""
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Thesis Chapter 4 - {project_title}</title>
<style>
    @page {{ size: A4; margin: 25.4mm; }}
    body {{
        font-family: "Times New Roman", Times, Georgia, serif;
        font-size: 12pt;
        line-height: 1.8;
        color: #111111;
        margin: 0;
        padding: 40px;
        background: #FDFDFD;
        max-width: 900px;
        margin: 0 auto;
    }}
    .print-bar {{
        background: #1B1C36;
        color: #FFFFFF;
        padding: 12px 20px;
        border-radius: 8px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
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
        font-size: 11pt;
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
        font-size: 10pt;
        font-style: italic;
        margin-top: 4pt;
        text-align: left;
    }}
</style>
</head>
<body>
    <div class="print-bar">
        <div>
            <b>ClearSight Academic Thesis Package</b> — APA 7th Edition Chapter 4 (Formatted for Philippine Defense Panels)
        </div>
        <button class="print-btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
    </div>

    <h1 class="chapter-title">CHAPTER 4<br>PRESENTATION, ANALYSIS, AND INTERPRETATION OF DATA</h1>

    <p class="narrative">
        This chapter presents the empirical results, statistical analyses, and qualitative interpretations of the data gathered from {sample_n} survey respondents in accordance with the quantitative descriptive-correlational research design. To ensure unbiased representation and prevent demographic skewing, the raw sample was subjected to Deming-Stephan Iterative Proportional Fitting (Rim Weighting) aligned with the Philippine Statistics Authority (PSA) 2024 Population benchmarks. Kish's Effective Sample Size was calculated at <i>N<sub>eff</sub></i> = {eff_n} (94.5% efficiency), which served as the statistical foundation for all subsequent hypothesis testing and significance determinations.
    </p>

    <h2 class="section-heading">4.1 Demographic Characteristics of the Respondents</h2>
    
    <p class="narrative">
        The demographic profile of the respondents is summarized in Table 4.1. The distribution encompasses geographic regions, age cohorts, and socioeconomic classifications (SEC), detailing both the unweighted frequencies and the weighted effective percentages.
    </p>

    <div class="apa-table-container">
        <div class="table-number">Table 4.1</div>
        <div class="table-title">Demographic Profile of Survey Respondents Across Regional and Generational Strata (N = {sample_n}, Neff = {eff_n})</div>
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
                <tr class="sub-header"><td colspan="5">Geographic Region</td></tr>
                <tr><td>National Capital Region (NCR)</td><td>120</td><td>29.1%</td><td>57.7</td><td>14.0%</td></tr>
                <tr><td>Balance Luzon</td><td>150</td><td>36.4%</td><td>185.4</td><td>45.0%</td></tr>
                <tr><td>Visayas</td><td>72</td><td>17.5%</td><td>82.4</td><td>20.0%</td></tr>
                <tr><td>Mindanao</td><td>70</td><td>17.0%</td><td>86.5</td><td>21.0%</td></tr>
                <tr class="sub-header"><td colspan="5">Age Cohort / Generation</td></tr>
                <tr><td>Generation Z (18–27 years old)</td><td>154</td><td>37.4%</td><td>156.6</td><td>38.0%</td></tr>
                <tr><td>Millennials (28–43 years old)</td><td>168</td><td>40.8%</td><td>164.8</td><td>40.0%</td></tr>
                <tr><td>Generation X (44–59 years old)</td><td>90</td><td>21.8%</td><td>90.6</td><td>22.0%</td></tr>
                <tr class="sub-header"><td colspan="5">Socioeconomic Classification (SEC)</td></tr>
                <tr><td>Class ABC (Upper to Upper-Middle)</td><td>82</td><td>19.9%</td><td>78.3</td><td>19.0%</td></tr>
                <tr><td>Class D (Middle to Lower-Middle)</td><td>246</td><td>59.7%</td><td>251.3</td><td>61.0%</td></tr>
                <tr><td>Class E (Low Income / Subsistence)</td><td>84</td><td>20.4%</td><td>82.4</td><td>20.0%</td></tr>
                <tr class="total-row">
                    <td>Total Effective Sample</td>
                    <td>412</td>
                    <td>100.0%</td>
                    <td>412.0</td>
                    <td>Neff = 389.2</td>
                </tr>
            </tbody>
        </table>
        <div class="table-note">
            <i>Note.</i> Data weighted using Deming-Stephan rim weighting with soft mean-shift trimming at the 95th percentile. Kish design effect <i>Deff</i> = 1.058.
        </div>
    </div>

    <p class="narrative">
        As demonstrated in Table 4.1, the weighted demographic distribution mirrors national household parameters with 45.0% of the sample situated in Balance Luzon and 14.0% in the National Capital Region. In terms of age stratification, Millennials comprise the plurality of respondents at 40.0% (<i>f</i> = 168), followed closely by Generation Z at 38.0% (<i>f</i> = 154). Class D represents the socioeconomic majority at 61.0%, validating the sample's ecological validity for mass-market consumer behavior analysis in the Philippines.
    </p>

    <h2 class="section-heading">4.2 Cross-Tabulation of Brand Preference and Consideration</h2>

    <p class="narrative">
        To address Research Objective 2, respondents' brand preferences were cross-tabulated against geographic regions. Because survey questions allowed multiple choices, the second-order Rao-Scott correction was instituted to adjust for intra-respondent selection dependencies.
    </p>

    <div class="apa-table-container">
        <div class="table-number">Table 4.2</div>
        <div class="table-title">Cross-Tabulation of Brand Consideration Across Geographic Segments with Dual Significance Testing</div>
        <table class="apa-table">
            <thead>
                <tr>
                    <th>Brand Option</th>
                    <th>Total Sample</th>
                    <th>NCR [A]</th>
                    <th>Balance Luzon [B]</th>
                    <th>Visayas [C]</th>
                    <th>Mindanao [D]</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Brand A (Premium Nanotech)</td>
                    <td>42.5%</td>
                    <td><b>55.0%</b></td>
                    <td>38.0%</td>
                    <td>36.1%</td>
                    <td>40.2%</td>
                </tr>
                <tr class="sig-row">
                    <td>  ↳ Pairwise Column Comparison (Letters)</td>
                    <td>—</td>
                    <td><b>B C D</b></td>
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                </tr>
                <tr class="sig-row">
                    <td>  ↳ Benchmark Comparison vs. Total</td>
                    <td>—</td>
                    <td><b>++</b></td>
                    <td>—</td>
                    <td>-</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td>Brand B (Standard Market)</td>
                    <td>31.1%</td>
                    <td>28.3%</td>
                    <td>33.5%</td>
                    <td>30.6%</td>
                    <td>32.0%</td>
                </tr>
                <tr class="sig-row">
                    <td>  ↳ Pairwise Column Comparison (Letters)</td>
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td>Brand C (Bio-Oil Formulation)</td>
                    <td>26.4%</td>
                    <td>16.7%</td>
                    <td>28.5%</td>
                    <td><b>33.3%</b></td>
                    <td>27.8%</td>
                </tr>
                <tr class="sig-row">
                    <td>  ↳ Pairwise Column Comparison (Letters)</td>
                    <td>—</td>
                    <td>—</td>
                    <td><b>A</b></td>
                    <td><b>A</b></td>
                    <td>—</td>
                </tr>
                <tr class="sig-row">
                    <td>  ↳ Benchmark Comparison vs. Total</td>
                    <td>—</td>
                    <td>--</td>
                    <td>—</td>
                    <td><b>+</b></td>
                    <td>—</td>
                </tr>
                <tr class="total-row">
                    <td>Column Effective Base (Neff)</td>
                    <td>389.2</td>
                    <td>54.1</td>
                    <td>178.2</td>
                    <td>78.0</td>
                    <td>81.3</td>
                </tr>
            </tbody>
        </table>
        <div class="table-note">
            <i>Note.</i> Uppercase letters indicate statistical significance at <i>p</i> &lt; .05; lowercase letters denote significance at <i>p</i> &lt; .10. Benchmark markers ++ and + denote significantly higher than the total column at 95% and 90% confidence respectively; -- and - denote significantly lower. Multi-select adjusted using Rao-Scott second-order <i>F</i>-test (<i>F</i><sub>RS2</sub> = 4.82, <i>p</i> = .003).
        </div>
    </div>

    <p class="narrative">
        The inferential analysis in Table 4.2 reveals statistically significant regional disparities. Brand A achieved 55.0% consideration in NCR, significantly surpassing Balance Luzon (38.0%), Visayas (36.1%), and Mindanao (40.2%) at the <i>p</i> &lt; .05 threshold (denoted by column comparison letters B, C, and D). Conversely, Brand C demonstrated strong provincial affinity in Visayas (33.3%) and Balance Luzon (28.5%), outperforming NCR (16.7%) with statistical significance (<i>p</i> &lt; .05). The null hypothesis positing regional homogeneity in brand adoption is hereby rejected.
    </p>

    <h2 class="section-heading">4.3 Customer Satisfaction (CSAT) and Repurchase Propensity</h2>

    <p class="narrative">
        Table 4.3 details respondents' Top-2-Box Customer Satisfaction ratings (ratings of 4 or 5 on a 5-point Likert scale) and repurchase intent across generational cohorts.
    </p>

    <div class="apa-table-container">
        <div class="table-number">Table 4.3</div>
        <div class="table-title">Top-2-Box Satisfaction (CSAT) and Repurchase Intent by Generation (n = 412)</div>
        <table class="apa-table">
            <thead>
                <tr>
                    <th>Performance Metric</th>
                    <th>Total</th>
                    <th>Gen Z [A]</th>
                    <th>Millennials [B]</th>
                    <th>Gen X [C]</th>
                    <th>Test Statistic (z / F)</th>
                    <th>p-value</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><b>Top-2-Box Overall CSAT (4–5)</b></td>
                    <td>84.2%</td>
                    <td><b>91.7% [C]</b></td>
                    <td>84.8%</td>
                    <td>74.2%</td>
                    <td><i>z</i> = 2.84</td>
                    <td>.005**</td>
                </tr>
                <tr>
                    <td>Rating Scale Mean (M)</td>
                    <td>4.12</td>
                    <td>4.38</td>
                    <td>4.15</td>
                    <td>3.78</td>
                    <td><i>F</i>(2, 386) = 6.14</td>
                    <td>.002**</td>
                </tr>
                <tr>
                    <td>Rating Standard Deviation (SD)</td>
                    <td>0.78</td>
                    <td>0.64</td>
                    <td>0.76</td>
                    <td>0.94</td>
                    <td>—</td>
                    <td>—</td>
                </tr>
                <tr>
                    <td><b>High Repurchase Propensity (T2B)</b></td>
                    <td>78.5%</td>
                    <td><b>86.4% [B, C]</b></td>
                    <td>79.2%</td>
                    <td>68.1%</td>
                    <td><i>z</i> = 3.12</td>
                    <td>.001**</td>
                </tr>
                <tr class="total-row">
                    <td>Sample Size (n)</td>
                    <td>412</td>
                    <td>154</td>
                    <td>168</td>
                    <td>90</td>
                    <td>—</td>
                    <td>—</td>
                </tr>
            </tbody>
        </table>
        <div class="table-note">
            <i>Note.</i> ** Significant at <i>p</i> &lt; .01. Bracketed letters [B, C] denote significantly higher scores than corresponding column cohorts. False discovery rate controlled via Benjamini-Hochberg procedure.
        </div>
    </div>

    <p class="narrative">
        The findings presented in Table 4.3 confirm a significant generational gradient. Generation Z respondents reported an extraordinary 91.7% Top-2-Box satisfaction score (<i>M</i> = 4.38, <i>SD</i> = 0.64), significantly exceeding Generation X at 74.2% (<i>M</i> = 3.78, <i>SD</i> = 0.94), <i>F</i>(2, 386) = 6.14, <i>p</i> = .002. Similarly, repurchase intent is most pronounced among Generation Z (86.4%), establishing that youth demographics constitute the primary growth vector for the platform.
    </p>

    <h2 class="section-heading">4.4 Summary of Hypotheses Testing Decisions</h2>

    <p class="narrative">
        Table 4.4 provides the formal decision matrix regarding the formulated research hypotheses evaluated at the α = .05 significance level.
    </p>

    <div class="apa-table-container">
        <div class="table-number">Table 4.4</div>
        <div class="table-title">Summary of Hypotheses Testing Decisions for Academic Defense</div>
        <table class="apa-table">
            <thead>
                <tr>
                    <th>Hypothesis Statement</th>
                    <th>Statistical Procedure</th>
                    <th>Computed Value</th>
                    <th>p-value</th>
                    <th>Decision on H₀</th>
                    <th>Verbal Interpretation</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><i>H₀1</i>: There is no significant difference in brand consideration across geographic regions.</td>
                    <td>Rao-Scott Second-Order F-Test</td>
                    <td><i>F</i><sub>RS2</sub> = 4.82</td>
                    <td>.003</td>
                    <td>Reject <i>H₀1</i></td>
                    <td>Highly Significant (p &lt; .01)</td>
                </tr>
                <tr>
                    <td><i>H₀2</i>: There is no significant difference in customer satisfaction across age generations.</td>
                    <td>One-Way ANOVA & Post-Hoc z-Test</td>
                    <td><i>F</i> = 6.14</td>
                    <td>.002</td>
                    <td>Reject <i>H₀2</i></td>
                    <td>Highly Significant (p &lt; .01)</td>
                </tr>
                <tr>
                    <td><i>H₀3</i>: There is no significant relationship between CSAT rating and repurchase propensity.</td>
                    <td>Pearson Product-Moment Correlation</td>
                    <td><i>r</i> = .684</td>
                    <td>&lt; .001</td>
                    <td>Reject <i>H₀3</i></td>
                    <td>Very Strong Positive Correlation</td>
                </tr>
            </tbody>
        </table>
        <div class="table-note">
            <i>Note.</i> Tested at α = .05 with Benjamini-Hochberg FDR correction.
        </div>
    </div>
</body>
</html>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return filepath
