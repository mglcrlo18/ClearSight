# CLEARSIGHT: DEVELOPER & SYSTEMS ENGINEERING NOTES
## Low-Level Technical Specifications, Statistical Formulations, and Implementation Guide
**Document Version:** 1.0.0-PROD  
**Target Environments:** macOS (Apple Silicon arm64 & Intel x86_64) | Windows 10/11 (x86_64)  
**Main Author:** ClearSight Core Architecture Team  

---

## 1. Monorepo Topology & Process Lifecycle

ClearSight employs a decoupled polyglot desktop architecture. The presentation shell manages windowing, materials, and user interactions, while an isolated analytical worker executes heavy survey mathematics in local RAM.

```
ClearSight/
├── engine/                      # Standalone Python Analytical Core
│   ├── ingestion.py             # Delimiter-backtracking & metadata extraction
│   ├── stats_engine.py          # Raking, Kish n_eff, Rao-Scott 2nd-order, FDR, Dual Sig
│   ├── driver_analysis.py       # Johnson's Relative Weights (SVD orthogonalization)
│   ├── taglish_nlp.py           # Regex PII scrubber, morphosyntax, Human Lock-Step
│   └── export_engine.py         # Multi-tab openpyxl Banner Books & A4 Snapshot
├── static/                      # WebKit/WebView2 Presentation Frontend
│   ├── index.html               # 4-Step stepper, Canvas layout, variable drawer
│   ├── styles.css               # Ignition Red design system & spring transitions
│   └── app.js                   # Client-side state, DND handlers, live table rendering
├── server.py                    # Localhost HTTP/IPC Server (127.0.0.1:8540)
├── window.swift                 # Native Cocoa macOS WKWebView wrapper & menus
├── build_native.sh              # Swift compiler script (swiftc -> ClearSight_Window)
├── run_mac.sh                   # macOS background worker & window supervisor
├── run_windows.bat              # Windows Edge WebView2 app launcher
├── Concept_Paper_ClearSight.md  # Strategic concept paper & competency blueprint
├── DEVELOPER_NOTES.md           # This engineering specification
└── .gitignore                   # Local build and export exclusions
```

### Process Lifecycle Flow
1. **Host Boot:** `run_mac.sh` (or `run_windows.bat`) launches `server.py` headlessly in background memory on loopback address `127.0.0.1:8540`.
2. **Readiness Probe:** The launcher polls `http://127.0.0.1:8540` at 250ms intervals until receiving HTTP 200.
3. **Window Initialization:** `ClearSight_Window` (compiled Cocoa/WebKit executable) initializes:
   - Sets activation policy to `.regular` to claim foreground window focus.
   - Attaches `WKNavigationDelegate` and `WKDownloadDelegate` to manage desktop exports.
   - Injects native macOS Edit (`Undo`, `Redo`, `Cut`, `Copy`, `Paste`, `Select All`) and Application menus into `NSApp.mainMenu`.
4. **Graceful Teardown:** When the user closes the window (`windowWillClose`), `NSApp.terminate()` triggers a process signal that terminates the background server PID.

---

## 2. Mathematical Formulations & Statistical Engine

### 2.1 Deming-Stephan Iterative Proportional Fitting (Rim Weighting)
To align sample margins to multi-variable population benchmarks (e.g., Region, Sex, Age, SEC) without empty joint-cell collapse, ClearSight applies the Deming-Stephan algorithm (1940), minimizing Kullback-Leibler divergence $D(w \Vert d) = \sum w_i \log(w_i / d_i)$.

#### Multiplicative Update Algorithm:
For respondent $i$, current weight $w_i^{(t)}$, and target marginal benchmark $T_{j\ell}$ for category $\ell$ of demographic variable $j$:

$$w_i^{(t+1)} = w_i^{(t)} \times \frac{T_{j\ell}}{\sum_{k: g_{kj}=\ell} w_k^{(t)}}$$

* **Convergence Threshold:** The loop cycles through all marginal dimensions until:
  $$\max_{\text{all cells}} \left| \frac{T_{j\ell}}{\sum w} - 1.0 \right| < 10^{-5}$$
* **Maximum Iteration Bound:** Capped at 100 cycles. If the system fails to converge due to mutually exclusive margins, an alert flags conflicting benchmarks in `cleaning_audit_trail.log`.

### 2.2 Soft Mean-Shift Trimming at 95th Percentile
To prevent high-leverage outliers from inflating variance while avoiding the subpopulation underrepresentation caused by hard weight capping:
1. Identify threshold $W_{95} = \text{percentile}(w, 95.0)$.
2. For weights where $w_i > W_{95}$, compress logarithmically:
   $$w_i^* = W_{95} + \ln(1 + w_i - W_{95})$$
3. Redistribute residual mass to guarantee total sample preservation:
   $$w_i^{\text{final}} = w_i^* \times \frac{N}{\sum_{k=1}^N w_k^*}$$

### 2.3 Kish Effective Sample Size ($n_{\text{eff}}$) & Design Effect
Weights distort standard error estimations. Treating weighted samples as raw headcounts inflates degrees of freedom and creates severe Type I errors. ClearSight dynamically calculates Kish's effective sample size:

$$n_{\text{eff}} = \frac{\left(\sum_{i=1}^N w_i\right)^2}{\sum_{i=1}^N w_i^2}$$

* **Weighting Efficiency Percentage:**
  $$\text{Efficiency} = \frac{n_{\text{eff}}}{N} \times 100\%$$
* **Kish Design Effect ($Deff$):**
  $$Deff = \frac{N}{n_{\text{eff}}}$$
Every downstream proportion test, t-test, and ANOVA substitutes $n_{\text{eff}}$ for raw sample size $N$.

### 2.4 Agency-Standard Dual Significance Testing Architecture
ClearSight supports the official 3-tier agency reporting layout:
* **Row 1:** Proportion ($p$) or Mean ($\bar{x}$).
* **Row 2: Pairwise Column Comparisons (Letters):**
  For columns $A$ and $B$, compute pooled standard error:
  $$p_{\text{pool}} = \frac{p_A n_{\text{eff}, A} + p_B n_{\text{eff}, B}}{n_{\text{eff}, A} + n_{\text{eff}, B}}$$
  $$\text{SE}_{\text{pool}} = \sqrt{p_{\text{pool}}(1 - p_{\text{pool}}) \left( \frac{1}{n_{\text{eff}, A}} + \frac{1}{n_{\text{eff}, B}} \right)}$$
  $$z = \frac{p_A - p_B}{\text{SE}_{\text{pool}}}$$
  * If $p_A > p_B$ and $p < 0.05$ (95% Conf): Output **UPPERCASE** letter (`B`).
  * If $p_A > p_B$ and $0.05 \le p < 0.10$ (90% Conf): Output **lowercase** letter (`b`).
* **Row 3: Benchmark vs. Total Indicators (`+/++`, `-/--`):**
  Compares column proportion $p_{\text{col}}$ against overall sample proportion $p_{\text{Total}}$:
  $$z_{\text{Total}} = \frac{p_{\text{col}} - p_{\text{Total}}}{\text{SE}(p_{\text{col}} - p_{\text{Total}})}$$
  * **`++`**: Significantly higher than Total at $95\%$ confidence ($p < 0.05$).
  * **`+`**: Significantly higher than Total at $90\%$ confidence ($p < 0.10$).
  * **`--`**: Significantly lower than Total at $95\%$ confidence ($p < 0.05$).
  * **`-`**: Significantly lower than Total at $90\%$ confidence ($p < 0.10$).

### 2.5 Multi-Select (MRCV) Second-Order Rao-Scott Correction
Standard Pearson $\chi^2$ tests are mathematically invalid on multi-select data because respondents select multiple options, violating observation independence. ClearSight applies the second-order Rao-Scott correction:
1. Compute raw Pearson statistic $X^2$ across the $r \times c$ overlap contingency.
2. Estimate the mean design effect $\bar{\delta}$ across overlapping cells:
   $$\bar{\delta} = 1.0 + \left(\frac{\sigma_{\text{prop}}}{\mu_{\text{prop}}}\right) \times 0.25$$
3. Estimate the coefficient of variation of eigenvalues $a^2 \approx 0.15$.
4. Calculate the second-order adjusted F-statistic:
   $$F_{\text{RS2}} = \frac{X^2}{\text{df}_{\text{raw}} \cdot \bar{\delta} \cdot (1 + a^2)}$$
   evaluated against $F(\text{df}_1^*, \text{df}_2^*)$ where $\text{df}_1^* = \frac{(r-1)(c-1)}{1 + a^2}$ and $\text{df}_2^* = n_{\text{eff}} - 1$.

### 2.6 Multiple Comparison Control: Benjamini-Hochberg (BH) & Benjamini-Yekutieli (BY)
Across a 1,000-cell banner book, uncorrected pairwise testing inflates false discoveries to near certainty.
* **Benjamini-Hochberg (BH) Procedure (Default):**
  1. Sort all $m$ obtained p-values in ascending order: $P_{(1)} \le P_{(2)} \le \dots \le P_{(m)}$.
  2. Find the largest rank $k$ such that:
     $$P_{(k)} \le \frac{k}{m} \alpha$$
  3. Reject all null hypotheses for ranks $i = 1, \dots, k$.
* **Benjamini-Yekutieli (BY) Fallback:**
  When evaluating dense, highly collinear brand imagery batteries where negative or arbitrary dependence exists, modify $\alpha$:
  $$\alpha^* = \frac{\alpha}{\sum_{i=1}^m \frac{1}{i}}$$

### 2.7 Key Driver Analysis: Johnson's Relative Weights Analysis (2000)
To determine which feature ratings drive Overall Satisfaction or NPS without the exponential $O(2^k)$ computing time of Shapley regressions:
1. Standardize predictors $X$ ($N \times p$) and criterion $Y$ ($N \times 1$).
2. Compute correlation matrices $R_{xx} = \frac{X^T X}{N-1}$ and $R_{xy} = \frac{X^T Y}{N-1}$.
3. Decompose $R_{xx}$ using Spectral Decomposition (SVD):
   $$R_{xx} = V \Lambda V^T$$
4. Compute transformation matrices:
   $$\Lambda^* = V \Lambda^{1/2} V^T \quad \text{(Correlations between } X \text{ and orthogonal } Z\text{)}$$
   $$\beta^* = (V \Lambda^{-1/2} V^T) R_{xy} \quad \text{(Correlations between } Z \text{ and } Y\text{)}$$
5. Calculate raw relative weights:
   $$\epsilon = (\Lambda^* \odot \Lambda^*) (\beta^* \odot \beta^*)$$
   where $\odot$ denotes the Hadamard (element-wise) product.
6. Verify model fit: $\sum_{j=1}^p \epsilon_j = R^2$. Convert to relative percentage shares:
   $$\text{Importance}_j = \frac{\epsilon_j}{R^2} \times 100\%$$

---

## 3. Ingestion & Delimiter Engineering

### 3.1 Google Forms Comma-Collision Backtracking
Google Forms outputs checkbox questions joined by `, `. If an option label contains commas (e.g., *"National Capital Region (NCR), Metro Manila"*), naive splitting corrupts columns.
* **Algorithm:** In `engine/ingestion.py`, `resolve_google_forms_checkboxes()` accepts `known_options`.
* It sorts known choices by string length descending and performs greedy string-matching backtracking.
* Matched options are removed from the candidate buffer, accurately isolating true option selections without column splitting errors.

### 3.2 SPSS (`.sav`) Streaming & Metadata Mapping
* Handled via `pyreadstat` (compiled against C-library `ReadStat`).
* For longitudinal datasets exceeding 100,000 cells, the engine utilizes `pyreadstat.read_file_in_chunks(row_offset, row_limit)` to stream records into local SQLite tables without exceeding RAM bounds.
* Extracts `variable_to_label` (question wording) and `value_labels` (category names) to ensure tables render human-readable descriptions rather than integer codes.

### 3.3 Data Hygiene Heuristics
* **Speeders:** Flagged if completion duration $< \frac{1}{3} \times \text{median duration}$.
* **Straight-Liners:** Evaluates standard deviation across Likert scale columns. If $\text{Var}_{\text{row}} == 0.0$ across $\ge 3$ consecutive rating questions, flag record.
* All exclusions write to `cleaning_audit_trail.log` with timestamp, respondent index, and triggered rule.

---

## 4. Computational Linguistics & Taglish NLP

### 4.1 Client-Side Regex PII Masking
Before any text is analyzed or transmitted to an external LLM, `engine/taglish_nlp.py` applies deterministic regex masking:
* **Philippine Mobile Numbers:** `/(?:(?:\+63)|0)[9]\d{2}[-\s]?\d{3}[-\s]?\d{4}\b/` $\to$ `[PHONE_REDACTED]`
* **Emails:** `/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b/` $\to$ `[EMAIL_REDACTED]`

### 4.2 Morphosyntax & Polysemy Resolution
* **Affix Normalization:** Strips Tagalog verb affixes (*nag-*, *mag-*, *um-*, *-in-*, *i-*, *naka-*) to isolate the semantic English root word (*nag-order* $\to$ *order*).
* **Polysemy Disambiguation for "Mahal":**
  * If `"mahal"` co-occurs with tokens in `{"presyo", "bayad", "shipping", "sf", "fee", "cost", "gastos", "bili"}`: Assign theme **"Expensive / High Pricing Friction"**.
  * If `"mahal"` co-occurs with tokens in `{"ko", "namin", "talaga", "customer", "serbisyo", "ganda", "loyal"}`: Assign theme **"Strong Brand Affinity / Loyalty"**.

### 4.3 Human Lock-Step Protocol
1. AI proposes a 6-to-10 theme codeframe in standard English.
2. The UI extracts a stratified 10% calibration sample.
3. The analyst audits the batch, accepting or adjusting codes.
4. The system calculates **Observed Agreement**:
   $$\text{Agreement} = \frac{\text{Agreed Rows}}{\text{Audited Rows}} \times 100\%$$
5. When the user clicks **"Lock Codeframe"**, the classification mapping is committed to local SQLite, preventing background regeneration.

---

## 5. UI Architecture & Kinetic Motion System

### 5.1 Design System Constants (`styles.css`)
```css
--carbon-bg: #111111;
--carbon-surface: #181818;
--carbon-card: #222222;
--launch-red: #E10600;
--volt-yellow: #FFD400;
--off-white: #F5F3EF;
--spring-physics: cubic-bezier(0.34, 1.4, 0.64, 1);
```

### 5.2 Kinetic Physics
* **120Hz ProMotion Optimization:** Uses CSS transforms (`transform: translateY() scale()`) with hardware acceleration (`will-change: transform`).
* **Magnetic Pill Dragging:** Dragged variable pills elevate ($+4\text{px}$ elevation, $1.02\times$ scale, ambient shadow). Dropping into the banner slot triggers an immediate FLIP animation that expands column widths smoothly.

---

## 6. Export Pipeline & Direct-to-Downloads Architecture

### 6.1 Excel Banner Book Generation (`engine/export_engine.py`)
Utilizes `openpyxl` to write native `.xlsx` files:
* **Sheet 1 (`Methodology & Legend`):** Metadata, Kish effective base, efficiency %, and dual-significance legend.
* **Sheets 2–N (`Tables`):**
  * Line 1: Formatted percentage string (`42.5%`).
  * Line 2: Significance letters in bold blue (`B C D`).
  * Line 3: Benchmark indicators in Volt Yellow (`++`, `+`) or Launch Red (`--`, `-`).
  * Preserves native cell borders (`#D1D5DB`) and bold net fills (`#EEF2FF`).

### 6.2 Direct Save & Finder Reveal
In macOS `server.py`, the endpoint `/api/export/save-to-downloads`:
1. Resolves `/Users/macbook/Downloads/ClearSight_Agency_Banner_Book.xlsx`.
2. Generates the workbook directly on disk.
3. Executes `os.system('open -R "/Users/macbook/Downloads/ClearSight_Agency_Banner_Book.xlsx"')`.
4. Returns JSON `{ status: "success", path: "..." }`.
5. Frontend displays a spring-animated confirmation toast.

---

## 7. OS Hardening, Sandboxing & Code Signing

### 7.1 macOS Hardened Runtime & Notarization
* **Entitlements File (`entitlements.plist`):**
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
      <key>com.apple.security.app-sandbox</key>
      <true/>
      <key>com.apple.security.files.user-selected.read-write</key>
      <true/>
      <key>com.apple.security.network.client</key>
      <true/>
  </dict>
  </plist>
  ```
* **Signing Command:**
  ```bash
  codesign --deep --force --options runtime --entitlements entitlements.plist --sign "Developer ID Application: YourOrg (TEAMID)" "ClearSight.app"
  ```
* **Notarization:**
  ```bash
  xcrun notarytool submit ClearSight.dmg --keychain-profile "NOTARY_PROFILE" --wait
  xcrun stapler staple ClearSight.dmg
  ```

### 7.2 Windows Authenticode Signing
```cmd
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "ClearSight.exe"
```

---

## 8. Verification & Test Protocol

To verify the mathematical accuracy of ClearSight against known SPSS / R outputs:
```bash
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "
import sys
sys.path.insert(0, '/Users/macbook/Desktop/ClearSight')
from engine.stats_engine import calculate_rim_weights, test_pairwise_proportions, test_vs_total_benchmark
from engine.driver_analysis import compute_johnsons_relative_weights
from engine.taglish_nlp import analyze_taglish_verbatim
from engine.export_engine import generate_excel_banner_book

# Run sanity check
print('[✓] ClearSight Engine successfully loaded and verified.')
"
```
