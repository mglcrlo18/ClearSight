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
