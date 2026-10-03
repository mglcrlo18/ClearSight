# ClearSight

> **Zero-Cloud Survey Tabulation, Advanced Statistical Cross-Tabs & Taglish Consumer Insights Platform**  
> *Native Desktop Application for macOS & Windows*

---

## 🎯 Overview

**ClearSight** is an agency-grade, zero-cloud desktop analytics platform engineered to resolve the severe polarization in market research tooling. It bridges the divide between overpriced Western enterprise software ($3,000–$5,000+ per user/year) and simplistic spreadsheet tools that lack valid survey statistical architecture.

Built as a lightweight native desktop application, ClearSight executes all mathematical calculations, demographic raking, significance testing, and qualitative processing locally on the user's machine. By eliminating cloud server compute overhead, ClearSight democratizes agency-grade research analytics for Philippine research agencies (MORES members), brand marketing teams, MSMEs, and academic researchers while ensuring absolute data sovereignty under the **Philippine Data Privacy Act of 2012 (RA 10173)**.

---

## 🚀 Key Architectural & Statistical Features

### 1. Robust Survey Data Ingestion
* **Google Forms Delimiter Collision Resolver:** Uses string-backtracking to prevent splitting on commas contained inside multi-select option labels (e.g. *"National Capital Region (NCR), Metro Manila"*).
* **Metadata Extraction:** Extracts variable labels, categorical value mapping dictionaries, and user-defined missing codes from SPSS (`.sav`), Excel (`.xlsx`), and CSV files.
* **Automated Data Hygiene Checklist:** Flags speeders ($< \frac{1}{3}$ median completion time), straight-liners (zero variance on Likert scales), and demographic duplicates to an immutable local `cleaning_audit_trail.log`.

### 2. Applied Survey Mathematics & Weighting
* **Deming-Stephan Iterative Proportional Fitting (Rim Weighting):** Balances sample marginal distributions to target population benchmarks (Region, Sex, Age, SEC) without collapsing cells.
* **Soft Mean-Shift Weight Trimming:** Smoothly compresses extreme outlier weights at the 95th percentile and redistributes residual mass proportionally so $\sum w_i = N$.
* **Kish Effective Sample Size ($n_{\text{eff}}$):** Dynamically computes:
  $$n_{\text{eff}} = \frac{\left(\sum w_i\right)^2}{\sum w_i^2}$$
  Adjusting standard errors across every banner column to prevent artificial Type I errors.

### 3. Agency-Standard Dual Significance Testing
Supports the official 3-tier agency reporting layout seen in premier research agencies (MORES, Pulse Asia, Kantar, Nielsen):
* **Row 1:** `%` or Scale Mean value.
* **Row 2: Column Comparisons (Letters):** Pairwise two-tailed z-tests using Kish effective bases ($n_{\text{eff}}$):
  * Lowercase letters (`a, b, c...`) for **$\ge 90\%$ Confidence** ($p < 0.10$).
  * UPPERCASE letters (`A, B, C...`) for **$\ge 95\%$ / $99\%$ Confidence** ($p < 0.05$).
* **Row 3: Benchmark vs. Total Indicators (`+/++`, `-/--`):**
  * `++` / `+`: Significantly **higher** than Total ($95\%$ / $90\%$).
  * `--` / `-`: Significantly **lower** than Total ($95\%$ / $90\%$).
* **Second-Order Rao-Scott F-Tests:** Adjusts multi-select (MRCV) cross-tabs against variance-covariance eigenvalues, eliminating false chi-square significance.
* **False Discovery Rate (FDR) Control:** Benjamini-Hochberg (BH) step-up procedure by default, with Benjamini-Yekutieli (BY) fallback for dense brand imagery batteries.

### 4. Collinear Key Driver Modeling (Johnson's Relative Weights)
* Resolves extreme multicollinearity in customer satisfaction batteries without the exponential $O(2^k)$ computing bottlenecks of Shapley regressions.
* Utilizes Singular Value Decomposition (SVD) on correlation matrices to yield orthogonal variance allocations in milliseconds.

### 5. Taglish Qualitative NLP & Human Lock-Step Protocol
* **Client-Side Regex PII Masking:** Automatically scrubs Philippine mobile numbers (`09XX-XXX-XXXX`) and email addresses before text processing.
* **Morphosyntactic & Polysemy Disambiguation:** Handles Filipino verb affixes (*nag-order*, *i-refund*) and context-dependent polysemy (distinguishing *"mahal"* as price friction vs. customer affinity).
* **Human Lock-Step Verification:** Displays observed human-AI agreement rates (e.g. $88.5\%$) on audited samples and locks codeframes from background overwrite.

### 6. Automated Agency Deliverables
* **Excel Banner Books (`.xlsx` via `openpyxl`):** Programmatically compiles multi-tab workbooks containing methodology sheets, weighting summaries, bold net headers, native Excel formulas, and explicit column significance letters ($A, B, C$).
* **1-Page A4 Customer Voice Snapshot:** Generates an executive brief featuring core KPIs, verified strategic takeaways, customer delights vs. frictions with cited verbatims, and a 30-day action matrix.

---

## 🎨 Visual Identity: Ignition Red System

* **Main (Launch Red):** `#E10600` — Primary action buttons, active navigation stepper tabs, net row highlights, and key focus rings.
* **Base (Carbon Black):** `#111111` / `#181818` / `#222222` — Deep structural surfaces and glassmorphic header blur.
* **Accent (Volt Yellow):** `#FFD400` — High-contrast metric callouts, column comparison letters, and positive benchmark indicators (`++`, `+`).
* **Neutral (Off-White):** `#F5F3EF` — Clean, high-legibility typography against dark surfaces.

---

## 💻 Quick Start Guide

### macOS
1. Open Terminal and navigate to the project directory:
   ```bash
   cd ClearSight
   ```
2. Make scripts executable and compile the native Swift window:
   ```bash
   chmod +x run_mac.sh build_native.sh
   ./build_native.sh
   ```
3. Launch the desktop application:
   ```bash
   ./run_mac.sh
   ```
   *(Or double-click `Launch_ClearSight.command` directly on your Desktop).*

### Windows
1. Double-click `run_windows.bat` or execute in Command Prompt:
   ```cmd
   run_windows.bat
   ```
2. Launches the local statistical core and opens in native Microsoft Edge WebView2 App mode.

---

## ⚖️ License & Data Privacy

* Compliant with the **Philippine Data Privacy Act of 2012 (Republic Act No. 10173)** and **National Privacy Commission Advisory No. 2024-04 (AI Governance)**.
* All data processing, mathematical modeling, and verbatim parsing occur in local device memory (RAM). No raw microdata or PII is ever uploaded to a remote cloud database.

---
*Developed for Lunsad Pilipinas and the Philippine Market Research Community.*
