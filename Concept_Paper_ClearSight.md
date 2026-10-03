# CONCEPT PAPER: CLEARSIGHT
## Zero-Cloud Survey Tabulation, Advanced Statistical Cross-Tabs & Taglish Consumer Insights Platform
**Document Classification:** Strategic Product Concept Paper & Systems Architecture  
**Target Environments:** macOS (Apple Silicon & Intel) & Windows 10/11 (x86_64)  
**Date:** October 3, 2026 (Manila)  
**Author / Organization:** ClearSight Analytics / Lunsad Pilipinas  

---

## 1. Executive Summary & Market Problem Statement

### 1.1 Overview
**ClearSight** is an agency-grade, zero-cloud desktop analytics platform engineered to resolve the severe polarization in market research tooling. It bridges the divide between overpriced Western enterprise software ($3,000–$5,000+ per user/year) and simplistic spreadsheet/survey platforms that lack valid statistical architecture.

Built as a lightweight native desktop application for **macOS and Windows**, ClearSight executes all mathematical calculations, demographic raking, significance testing, and qualitative processing locally on the user's machine. By eliminating cloud server compute overhead, ClearSight democratizes agency-grade research analytics for Philippine research agencies (MORES members), brand marketing teams, MSMEs, and academic thesis researchers at disruptive local price points (₱499 to ₱4,990) while ensuring absolute data sovereignty under the **Philippine Data Privacy Act of 2012 (Republic Act No. 10173)**.

### 1.2 Core Market Failures Addressed
1. **The Ingestion Dilemma (Google Forms Delimiter Collision):** Google Forms concatenates checkbox responses into a single string joined by comma-space (`, `). When answer options contain inherent commas (e.g., *"National Capital Region (NCR), Metro Manila"*), standard CSV parsers fragment the data across multiple columns, corrupting analytical tallies.
2. **Invalid Hypothesis Testing on Multi-Select Data:** Mainstream business tools (Excel, Power BI, Tableau) apply standard Pearson $\chi^2$ tests to "select all that apply" questions. Because respondents choose multiple categories, observations violate independence assumptions, causing artificial degrees-of-freedom inflation and false statistical significance.
3. **Weighting Distortions & Effective Base Omissions:** Standard spreadsheet formulas and basic survey tools treat weighted samples as simple headcounts, distorting standard errors. Without dynamic Kish effective sample size ($n_{\text{eff}}$) corrections, significance tests aggressively over-reject the null hypothesis (Type I error).
4. **The Multiple Comparison Fallacy:** Evaluating standard wide banner books (hundreds of intersecting pairwise z-tests) balloons Family-Wise Error Rate (FWER) to near 100%. Mainstream tools either ignore this or use draconian Bonferroni corrections that destroy statistical power.
5. **The Taglish Qualitative Bottleneck:** Open-ended consumer feedback in the Philippines is heavily code-switched (Taglish). Off-the-shelf Western NLP engines fail to parse intra-sentential morphosyntax (*nag-order*, *i-refund*) or resolve local polysemy (*mahal* as cost vs. emotion). Furthermore, unmonitored LLM coding exhibits uncalibrated self-confidence and high error rates without strict human verification.
6. **Prohibitive Pricing & Licensing Models:** Platforms with proper statistical engines (Displayr at ~₱210,800/yr, WinCross at ~₱225,600 upfront, SPSS Base + Custom Tables at ~₱12,300/mo) are economically unviable for 99.63% of Philippine enterprises and students.
7. **Cloud Data Sovereignty & RA 10173 Liability:** Transmitting raw respondent PII to third-party overseas cloud servers introduces substantial compliance friction under National Privacy Commission (NPC) Advisories 2024-04 (AI Governance) and 2024-01 (Cross-Border Transfers).

---

## 2. Platform Architecture: The Zero-Cloud Desktop Model

ClearSight rejects the centralized SaaS multi-tenant cloud model in favor of a **secure, native desktop runtime** powered by **Tauri v2 (Rust)** and an **embedded, hermetic Python 3.12+ analytical core**.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER (Tauri v2 Shell / WebKit on macOS / WebView2 on Windows)                      │
│ • Professional English UI: High-density Table Canvas, Variable Drawer, Verbatim Studio           │
│ • Kinetic & Tactile: 120Hz ProMotion spring physics, magnetic drag-and-drop, glassmorphic depth │
│ • Lightweight footprint (~25 MB bundle; ~40 MB RAM idle; zero Chromium bloat)                    │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │ (Asynchronous MessagePack local IPC)
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ PLATFORM ABSTRACTION LAYER (Rust Core)                                                           │
│ ┌───────────────────────────────────────────────┐ ┌────────────────────────────────────────────┐ │
│ │ macOS Subsystems                              │ │ Windows Subsystems                         │ │
│ │ • IPC: Unix Domain Sockets (UDS)              │ │ • IPC: Win32 Named Pipes                   │ │
│ │ • Secrets: macOS Keychain Services            │ │ • Secrets: Windows Credential Manager      │ │
│ │ • Hardware Acceleration: Apple Accelerate     │ │ • Hardware Acceleration: OpenBLAS/oneMKL   │ │
│ │ • Air-Gapped AI: Apple Silicon MLX (UMA)      │ │ • Air-Gapped AI: DirectML / ONNX Runtime   │ │
│ └───────────────────────────────────────────────┘ └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ EMBEDDED ANALYTICAL & STATISTICAL WORKER (Isolated via `uv.lock`)                                │
│ • Ingestion: Schema detector, Google Forms delimiter resolver, pyreadstat binary parser          │
│ • Survey Math: Deming-Stephan raking, Kish n_eff, Rao-Scott 2nd-order MRCV, FDR (BH/BY)         │
│ • Key Driver Analysis: Johnson's Relative Weights via SVD Orthogonalization                      │
│ • Qualitative Hub: Regex PII scrubber, Taglish normalizer, Human Lock-Step state engine          │
│ • Reporting: Native Excel openpyxl Banner Book compiler & Headless A4 PDF snapshot generator     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Architectural Highlights
* **Zero Backend Hosting Costs:** Computations execute entirely on the user's CPU and RAM. ClearSight incurs zero cloud-compute server costs, enabling sustainable high-margin local pricing.
* **Complete Data Sovereignty:** Survey microdata never leaves the local machine. SQLite running in Write-Ahead Logging (`WAL`) mode manages project caching locally.
* **Hardware Acceleration:** Vectorized matrix factorizations utilize Apple Accelerate (AMX co-processor) on macOS and OpenBLAS/AVX2 on Windows.

---

## 3. Visual Identity: The Ignition Red System

ClearSight adopts the **Ignition Red** design language—built for visual urgency, memorability, and modern desktop tactility:

* **Main (Launch Red - `#E10600`):** Represents speed, rigor, and immediate strategic action. Applied to primary call-to-actions, active workflow steps, net row tints, and glowing focus borders.
* **Base (Carbon Black - `#111111` / `#181818` / `#222222`):** Grounded in deep neutral carbon tones, providing maximum contrast, reducing visual fatigue during long analytical sessions, and supporting translucent glassmorphism (`backdrop-filter: blur(24px)`).
* **Accent (Volt Yellow - `#FFD400`):** Used for high-priority signals, KPI metrics, column letters, and statistically positive benchmark indicators (`++`, `+`).
* **Neutral (Off-White - `#F5F3EF`):** Clean, warm typography ensuring crisp readability across dense cross-tabulation grids.

---

## 4. Core Functional Engine Catalog

### Module 1: Ingestion & Delimiter Collision Engine
* Ingests Google Forms exports, Microsoft Excel (`.xlsx`), CSV, and IBM SPSS (`.sav`).
* Implements string-backtracking option-matching to parse Google Forms multi-select checkbox cells containing internal commas without data loss.
* Automatically extracts SPSS metadata (variable labels, categorical value mapping dictionaries, user-defined missing value codes).

### Module 2: Automated Hygiene Checklist & Audit Logger
* Flags suspicious records without destructive deletion:
  * **Speeders:** Respondents completing in $< \frac{1}{3}$ median study time.
  * **Straight-Liners:** Zero variance across Likert rating batteries.
  * **Duplicate Submissions:** Matching timestamps and demographic footprints.
* Writes every exclusion to an immutable local `cleaning_audit_trail.log`.

### Module 3: Survey Weighting & Variance Balancing Engine
* **Deming-Stephan Iterative Proportional Fitting (Rim Weighting):** Balances multidimensional demographic marginals (Region, Sex, Age, SEC) to target population benchmarks without cell-collapse bias.
* **Soft Mean-Shift Trimming:** Compresses extreme outlier weights toward the 95th percentile and redistributes residual weight smoothly across the remaining sample.
* **Dynamic Kish Effective Base ($n_{\text{eff}}$):**
  $$n_{\text{eff}} = \frac{\left(\sum w_i\right)^2}{\sum w_i^2}$$
  Calculates effective bases for every stub and banner intersection, feeding adjusted statistical power directly into all significance testing.

### Module 4: Custom Table Studio & Cross-Tabulation Canvas
* **Visual Drag-and-Drop Builder:** Drag questions into Stubs (Rows) and Banners (Columns) with magnetic snapping and tactile elevation.
* **Automatic Metric Assignment:** Auto-calculates counts, column percentages, scale means, standard deviations, Top-2-Box (T2B), and Bottom-2-Box (B2B).
* **Nesting & Custom Netting:** Group sub-attributes into custom "NET" categories and build multi-level nested banners (e.g., Region nested within Gender).
* **Conversational Prompt-to-Table:** Accepts natural language table specifications in English or Taglish (e.g., *"Cross-tabulate brand satisfaction by age group for NCR buyers only"*), mapping them directly into the visual canvas.

### Module 5: Agency-Standard Dual Significance Testing Engine
Supports the official 3-tier agency reporting layout seen in premier research agencies (MORES, Pulse Asia, Kantar, Nielsen):
* **Line 1: `%` or Scale Mean Value:** The weighted proportion or metric score.
* **Line 2: Column Comparisons (Letters):** Pairwise two-tailed z-tests using Kish effective bases ($n_{\text{eff}}$):
  * Lowercase letters (`a, b, c...`) denote significance at **$\ge 90\%$ Confidence** ($p < 0.10$).
  * UPPERCASE letters (`A, B, C...`) denote significance at **$\ge 95\%$ / $99\%$ Confidence** ($p < 0.05$).
* **Line 3: Benchmark vs. Total Indicators (`+/++`, `-/--`):**
  * `++` / `+`: Significantly **higher** than the Total column ($95\%$ / $90\%$).
  * `--` / `-`: Significantly **lower** than the Total column ($95\%$ / $90\%$).
* **Second-Order Rao-Scott Adjustments:** Corrects multi-select (MRCV) cross-tabs against variance-covariance eigenvalues, eliminating false chi-square significance.
* **False Discovery Rate (FDR) Control:** Benjamini-Hochberg (BH) step-up procedure by default, with Benjamini-Yekutieli (BY) fallback for dense brand imagery batteries.
* **Small-Base Protection:** Mutes cells where $n < 30$ or $n_{\text{eff}} < 20$, printing explicit methodological footnotes.

### Module 6: Predictive Key Driver Analysis (Johnson's Relative Weights)
* Resolves extreme multicollinearity in satisfaction driver batteries without the exponential $O(2^k)$ computing time of Shapley regressions.
* Employs Singular Value Decomposition (SVD) on correlation matrices to transform correlated predictors into orthogonal variables, squaring and projecting standardized coefficients back to calculate exact relative percentage contributions to $R^2$ in milliseconds.

### Module 7: Localized Taglish Qualitative Engine & AI Guardrails
* **Strict Division of Labor:** The AI model is strictly quarantined from numerical calculations; all figures originate from the deterministic statistical core.
* **Pre-Transmission PII Scrubber:** Client-side regex masks Philippine mobile numbers (`09XX-XXX-XXXX`), emails, and names before any verbatim text leaves the machine.
* **Taglish Affix & Polysemy Disambiguation:** Resolves code-switched morphosyntax (*nag-order*, *i-refund*) and distinguishes context-dependent polysemy (*mahal* as price friction vs. affection).
* **Human Lock-Step Protocol:** Generates a preliminary English thematic codebook, requires the researcher to audit a 10% calibration sample, computes the **Observed Human-AI Agreement Rate**, and locks the taxonomy.
* **Two-Way Evidence Pinning:** Every English summary sentence anchors to an exact table coordinate, and every qualitative theme links to its source verbatim IDs.

### Module 8: Document & Export Synthesis Engine
* **Agency-Grade Excel Banner Book (`openpyxl`):** Compiles multi-tab `.xlsx` workbooks containing a Methodology/Weighting cover sheet, bold net headers, native Excel formulas, and the 3-line dual significance notation directly in cells.
* **1-Page A4 Customer Voice Snapshot:** Generates a formatted executive PDF containing core KPIs, statistically verified highlights, friction vs. delight qualitative themes with quoted verbatims, and a 30-day action matrix.
* **Academic Chapter 4 Tables:** Formats tables to standard academic thesis specifications with editable interpretation templates.

---

## 5. Linguistic Specification

* **Primary Interface & Deliverables:** **100% Professional English.** All menus, table headers, statistical annotations, exported Excel workbooks, PowerPoint slides, and Snapshot PDFs are generated in standard business English.
* **Ingestion & Prompt Recognition:** **Native Taglish Detection.** The underlying NLP pipeline parses code-switched Filipino-English respondent verbatims and translates them into standardized English codeframes, while the natural language table assistant understands conversational queries in English, Tagalog, or Taglish.

---

## 6. Skills & Competencies Required for Project Success

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               CORE PROJECT COMPETENCY MATRIX                                     │
├──────────────────────────────────┬───────────────────────────────────────────────────────────────┤
│ COMPETENCY DOMAIN                │ SPECIFIC TECHNICAL SKILLSETS & DELIVERABLES                   │
├──────────────────────────────────┼───────────────────────────────────────────────────────────────┤
│ 1. Applied Survey Statistics     │ • Survey sample weighting (IPF/Raking, soft mean-shift trim)  │
│    & Psychometrics               │ • Variance estimation & Kish effective sample size (n_eff)    │
│                                  │ • MRCV hypothesis testing (SPMI, Rao-Scott 2nd-order F-tests) │
│                                  │ • Dual significance testing (Column letters + Total benchmark)│
│                                  │ • Multiple testing adjustments (Benjamini-Hochberg/Yekutieli) │
│                                  │ • Johnson's Relative Weights & MaxDiff Hierarchical Bayes     │
├──────────────────────────────────┼───────────────────────────────────────────────────────────────┤
│ 2. Native Systems Engineering    │ • Tauri v2 host development & asynchronous Tokio IPC          │
│    (Rust & Desktop Architecture) │ • Hermetic standalone Python runtime bundling via `uv`        │
│                                  │ • Unix Domain Sockets (macOS) & Win32 Named Pipes (Windows)   │
│                                  │ • Apple Accelerate & OpenBLAS/MKL linear algebra compilation  │
│                                  │ • Apple Hardened Runtime, Gatekeeper notarytool, Authenticode │
├──────────────────────────────────┼───────────────────────────────────────────────────────────────┤
│ 3. Computational Linguistics     │ • Taglish morphosyntactic tokenization & affix normalization  │
│    & Localized NLP Engineering   │ • Contextual polysemy disambiguation algorithms               │
│                                  │ • Client-side regex PII sanitization pipelines                │
│                                  │ • On-device small model acceleration (Apple MLX & DirectML)   │
│                                  │ • Inter-coder agreement metrics (Observed Agreement / Kappa)  │
├──────────────────────────────────┼───────────────────────────────────────────────────────────────┤
│ 4. High-Density MR UI/UX         │ • React / TypeScript high-throughput canvas design            │
│    & Export Automation           │ • Virtualized tabular data rendering for massive banner books   │
│                                  │ • Programmatic multi-tab Excel styling via `openpyxl`         │
│                                  │ • Headless A4 executive PDF compilation (Typst / WebKit)      │
├──────────────────────────────────┼───────────────────────────────────────────────────────────────┤
│ 5. Philippine Regulatory & GTM   │ • Data Privacy Act (RA 10173) & NPC AI Advisory compliance    │
│    Commercial Strategy           │ • Local payment gateway integration (GCash, Maya, PayMongo)   │
│                                  │ • MORES agency pilot benchmarking & academic thesis alignment │
└──────────────────────────────────┴───────────────────────────────────────────────────────────────┘
```

---

## 7. Commercial Model & Unit Economics

| Tier | Price Point | Target Market | Key Deliverables & Quotas |
| :--- | :--- | :--- | :--- |
| **Estudyante** | **₱499** / project (60 days) | Undergrad & Graduate Thesis Students | 1 dataset up to 1,000 respondents, basic tables, sig tests, Chapter 4 academic table exports, 300 AI-coded open-ends. |
| **Negosyo** | **₱1,490** / month | Brand Marketing Teams, SMEs, Lunsad Clients | 3 active survey workspaces, full rim weighting, PowerPoint charts, 1-page Customer Voice Snapshot, 2,000 AI-coded open-ends/mo. |
| **Ahensya** | **₱4,990** / user / month (or ₱49,900/year) | MORES Research Agencies, Freelance Analysts | Unlimited datasets, full Excel Banner Books with dual significance rows, trackers, MaxDiff modeling, free client viewer seats, 10,000 AI-coded open-ends/mo. |
| **Institusyon** | From **₱150,000** / year | LGUs, Universities, Enterprise Research Centers | Multi-seat site license, 100% offline air-gapped installer, DPA compliance package, on-premise training. |

### Unit Economics Advantage
Because all core statistics and Excel compiles occur on the user's desktop hardware, server hosting costs are virtually zero. The only variable marginal cost is third-party LLM API consumption for open-ended qualitative coding (averaging $< \$0.01$ per response), yielding projected gross margins exceeding **88–92%** across paid subscription tiers.

---

## 8. Phased Implementation Roadmap

```
PHASE 1: Core Desktop Ingestion & Tabulation Engine (Weeks 1–3)
├── Setup: Tauri v2 + embedded Python (uv) monorepo for macOS and Windows
├── Ingestion: Google Forms comma resolver, CSV, Excel, and SPSS .sav parsers
├── Hygiene: Speeders, straight-liners, and audit trail logging to local SQLite
└── UI: Drag-and-drop Stub & Banner Studio with real-time base counts

PHASE 2: Advanced Statistical Core & Excel Banner Books (Weeks 4–6)
├── Weighting: Deming-Stephan raking with soft mean-shift trimming
├── Variance: Kish effective base (n_eff) calculation across all banner columns
├── Significance: 2nd-order Rao-Scott MRCV adjustments & Benjamini-Hochberg FDR
├── Dual Sig: Implementation of Column Letters + Total Benchmark (+/++, -/--) rows
└── Export: Multi-tab formatted Excel Banner Books via openpyxl

PHASE 3: Taglish Qualitative Hub, Human Lock-Step & Snapshots (Weeks 7–8)
├── NLP: Client-side regex PII scrubber & Taglish affix normalizer
├── AI Guardrails: English codeframe generation, 10% human lock-step, evidence pinning
├── Offline AI: Apple Silicon MLX and Windows DirectML local inference fallback
└── Export: 1-Page A4 Customer Voice Snapshot PDF generator

PHASE 4: OS Hardening, Notarization & Commercial Pilot (Weeks 9–10)
├── macOS: Developer ID signing, Hardened Runtime, universal lipo, xcrun notarytool
├── Windows: WiX Toolset (.msi), NSIS installer, Authenticode code signing
├── Billing: Local payment rails (GCash, Maya, PayMongo) integration
└── Pilot Launch: 2 local research agencies, 5 SME brand teams, 1 university research lab
```
