"""
ClearSight - Local Desktop Backend Server
Zero-cloud execution. Runs on localhost:8540 with zero external data transmission.
"""

import os
import sys
import json
import mimetypes
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Add current directory to path
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURR_DIR)

from engine.ingestion import autodetect_schema, run_hygiene_audit, resolve_google_forms_checkboxes
from engine.stats_engine import (
    calculate_rim_weights, 
    test_pairwise_proportions, 
    test_vs_total_benchmark,
    rao_scott_second_order_mrcv
)
from engine.driver_analysis import compute_johnsons_relative_weights
from engine.taglish_nlp import batch_code_open_ends, scrub_pii
from engine.export_engine import (
    generate_excel_banner_book, 
    generate_customer_voice_snapshot_html,
    generate_thesis_chapter_4_package,
    generate_thesis_excel_tables
)

PORT = 8540

def get_downloads_dir():
    # Explicitly check user's main Downloads directory
    for candidate in ["/Users/macbook/Downloads", str(Path.home() / "Downloads"), str(Path.home())]:
        if os.path.exists(candidate):
            return candidate
    return str(Path.home())

def build_agency_sample_tables():
    """Builds sample tables with Dual Significance rows (Letters + Benchmark)."""
    return [
        {
            "title": "Q1: Brand Preference by Region",
            "banner_cols": ["Total", "NCR", "Balance Luzon", "Visayas", "Mindanao"],
            "col_letters": ["", "A", "B", "C", "D"],
            "unweighted_bases": [412, 120, 150, 72, 70],
            "weighted_bases": [412.0, 57.7, 185.4, 82.4, 86.5],
            "effective_bases": [389.2, 54.1, 178.2, 78.0, 81.3],
            "rows": [
                {
                    "label": "Brand A (Premium Nanotech)",
                    "values": ["42.5%", "55.0%", "38.0%", "36.1%", "40.2%"],
                    "sig_letters": ["-", "B C D", "", "", ""],
                    "sig_benchmarks": ["-", "++", "", "-", ""],
                    "is_net": False
                },
                {
                    "label": "Brand B (Standard Market)",
                    "values": ["31.1%", "28.3%", "33.5%", "30.6%", "32.0%"],
                    "sig_letters": ["-", "", "", "", ""],
                    "sig_benchmarks": ["-", "", "", "", ""],
                    "is_net": False
                },
                {
                    "label": "Brand C (Bio-Oil Formulation)",
                    "values": ["26.4%", "16.7%", "28.5%", "33.3%", "27.8%"],
                    "sig_letters": ["-", "", "A", "A", ""],
                    "sig_benchmarks": ["-", "--", "", "+", ""],
                    "is_net": False
                }
            ]
        },
        {
            "title": "Q2: Overall Customer Satisfaction (CSAT)",
            "banner_cols": ["Total", "NCR", "Balance Luzon", "Visayas", "Mindanao"],
            "col_letters": ["", "A", "B", "C", "D"],
            "unweighted_bases": [412, 120, 150, 72, 70],
            "weighted_bases": [412.0, 57.7, 185.4, 82.4, 86.5],
            "effective_bases": [389.2, 54.1, 178.2, 78.0, 81.3],
            "rows": [
                {
                    "label": "NET: Top-2-Box (Satisfied/Very Satisfied)",
                    "values": ["84.2%", "91.7%", "82.0%", "80.5%", "84.3%"],
                    "sig_letters": ["-", "B C", "", "", ""],
                    "sig_benchmarks": ["-", "++", "", "-", ""],
                    "is_net": True
                },
                {
                    "label": "5 - Very Satisfied",
                    "values": ["48.5%", "60.8%", "46.0%", "43.1%", "47.1%"],
                    "sig_letters": ["-", "B C D", "", "", ""],
                    "sig_benchmarks": ["-", "++", "", "-", ""],
                    "is_net": False
                },
                {
                    "label": "4 - Somewhat Satisfied",
                    "values": ["35.7%", "30.9%", "36.0%", "37.4%", "37.2%"],
                    "sig_letters": ["-", "", "", "", ""],
                    "sig_benchmarks": ["-", "", "", "", ""],
                    "is_net": False
                },
                {
                    "label": "Mean Rating (1-5 Scale)",
                    "values": ["4.12", "4.48", "4.05", "3.98", "4.10"],
                    "sig_letters": ["-", "B C D", "", "", ""],
                    "sig_benchmarks": ["-", "++", "", "-", ""],
                    "is_net": True
                }
            ]
        }
    ]

class SukatRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_file(os.path.join(CURR_DIR, "static", "index.html"), "text/html")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            local_path = os.path.join(CURR_DIR, "static", rel_path)
            mime, _ = mimetypes.guess_type(local_path)
            self.serve_file(local_path, mime or "application/octet-stream")
        elif path == "/preview-snapshot":
            snapshot_path = os.path.join(CURR_DIR, "snapshot_preview.html")
            data = {
                "project_title": "Philippine Consumer Rejuvenation & Retail Study",
                "sample_n": 412,
                "eff_n": 389.2,
                "csat_score": "84.2%",
                "weighting_eff": "94.5%"
            }
            generate_customer_voice_snapshot_html(snapshot_path, data)
            self.serve_file(snapshot_path, "text/html")
        elif path == "/api/export/save-to-downloads":
            # Direct save to user's ~/Downloads directory and reveal in Finder
            downloads_dir = get_downloads_dir()
            target_file = os.path.join(downloads_dir, "ClearSight_Agency_Banner_Book.xlsx")
            sample_tables = build_agency_sample_tables()
            metadata = {
                "date_range": "September - October 2026",
                "unweighted_n": 412,
                "weighted_n": 412.0,
                "effective_n": 389.2,
                "efficiency_pct": 94.5
            }
            generate_excel_banner_book(target_file, "Philippine Consumer Survey", sample_tables, metadata)
            
            # Reveal in macOS Finder
            if sys.platform == "darwin":
                os.system(f'open -R "{target_file}" 2>/dev/null')
            elif sys.platform == "win32":
                os.system(f'explorer /select,"{target_file}" 2>/dev/null')
                
            response = {
                "status": "success",
                "message": "File generated and saved directly to your Downloads folder!",
                "path": target_file,
                "filename": "ClearSight_Agency_Banner_Book.xlsx"
            }
            self.send_json_response(response)
        elif path == "/api/export/excel":
            excel_path = os.path.join(CURR_DIR, "ClearSight_Banner_Book_Export.xlsx")
            sample_tables = build_agency_sample_tables()
            metadata = {
                "date_range": "September - October 2026",
                "unweighted_n": 412,
                "weighted_n": 412.0,
                "effective_n": 389.2,
                "efficiency_pct": 94.5
            }
            generate_excel_banner_book(excel_path, "Philippine Consumer Survey", sample_tables, metadata)
            
            with open(excel_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="ClearSight_Agency_Banner_Book.xlsx"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/export/save-snapshot-to-downloads":
            downloads_dir = get_downloads_dir()
            target_file = os.path.join(downloads_dir, "ClearSight_Customer_Voice_Snapshot_A4.html")
            data = {
                "project_title": "Philippine Consumer Rejuvenation & Retail Study",
                "sample_n": 412,
                "eff_n": 389.2,
                "csat_score": "84.2%",
                "weighting_eff": "94.5%"
            }
            generate_customer_voice_snapshot_html(target_file, data)
            if sys.platform == "darwin":
                os.system(f'open -R "{target_file}" 2>/dev/null')
            elif sys.platform == "win32":
                os.system(f'explorer /select,"{target_file}" 2>/dev/null')
            response = {
                "status": "success",
                "message": "1-Page A4 Snapshot saved directly to your Downloads folder!",
                "path": target_file,
                "filename": "ClearSight_Customer_Voice_Snapshot_A4.html"
            }
            self.send_json_response(response)
        elif path == "/api/export/snapshot-download":
            snapshot_path = os.path.join(CURR_DIR, "snapshot_preview.html")
            data = {
                "project_title": "Philippine Consumer Rejuvenation & Retail Study",
                "sample_n": 412,
                "eff_n": 389.2,
                "csat_score": "84.2%",
                "weighting_eff": "94.5%"
            }
            generate_customer_voice_snapshot_html(snapshot_path, data)
            with open(snapshot_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="ClearSight_Customer_Voice_Snapshot_A4.html"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif path == "/api/export/save-thesis-to-downloads":
            downloads_dir = get_downloads_dir()
            target_html = os.path.join(downloads_dir, "ClearSight_Thesis_Chapter_4_Package.html")
            target_xlsx = os.path.join(downloads_dir, "ClearSight_Thesis_Chapter_4_Tables.xlsx")
            generate_thesis_chapter_4_package(target_html, "Philippine Consumer Survey Analysis", 412, 389.2)
            generate_thesis_excel_tables(target_xlsx, "Philippine Consumer Survey Analysis")
            if sys.platform == "darwin":
                os.system(f'open -R "{target_html}" 2>/dev/null')
            elif sys.platform == "win32":
                os.system(f'explorer /select,"{target_html}" 2>/dev/null')
            response = {
                "status": "success",
                "message": "Thesis Chapter 4 Package saved directly to your Downloads folder!",
                "path": target_html,
                "filename": "ClearSight_Thesis_Chapter_4_Package.html"
            }
            self.send_json_response(response)
        elif path == "/api/export/thesis-download":
            thesis_path = os.path.join(CURR_DIR, "ClearSight_Thesis_Chapter_4_Package.html")
            generate_thesis_chapter_4_package(thesis_path, "Philippine Consumer Survey Analysis", 412, 389.2)
            with open(thesis_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="ClearSight_Thesis_Chapter_4_Package.html"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Endpoint Not Found")

    def send_json_response(self, data: dict):
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_file(self, filepath: str, mime_type: str):
        if not os.path.exists(filepath):
            self.send_error(404, f"File not found: {filepath}")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

def run_server():
    server_address = ('127.0.0.1', PORT)
    httpd = HTTPServer(server_address, SukatRequestHandler)
    print(f"[*] ClearSight Analytical Core Server active on http://127.0.0.1:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server shutdown.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
