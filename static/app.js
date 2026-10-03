// Sukat by Lunsad - Frontend Interaction Engine
// Handles: Stepper workflow, Drag-and-drop, Prompt-to-Table, Dual Significance Testing, and Downloads

let currentStep = 1;
let currentConfidence = 95;
let isFDREnabled = true;
let currentMetric = 'pct';
let isCodeframeLocked = false;
let sigDisplayMode = 'both'; // 'both', 'letters', 'bench'

// Table Data Source with Dual Significance
const sampleTableData = {
    brand_preference: [
        {
            label: "NET: Any Brand Mentioned",
            is_net: true,
            values: ["94.2%", "97.5%", "93.3%", "91.7%", "92.9%"],
            letters: ["-", "B C", "", "", ""],
            benchmarks: ["-", "++", "", "-", ""]
        },
        {
            label: "Brand A (Premium Nanotech)",
            is_net: false,
            values: ["42.5%", "55.0%", "38.0%", "36.1%", "40.2%"],
            letters: ["-", "B C D", "", "", ""],
            benchmarks: ["-", "++", "", "-", ""]
        },
        {
            label: "Brand B (Standard Market)",
            is_net: false,
            values: ["31.1%", "28.3%", "33.5%", "30.6%", "32.0%"],
            letters: ["-", "", "", "", ""],
            benchmarks: ["-", "", "", "", ""]
        },
        {
            label: "Brand C (Bio-Oil Formulation)",
            is_net: false,
            values: ["26.4%", "16.7%", "28.5%", "33.3%", "27.8%"],
            letters: ["-", "", "A", "A", ""],
            benchmarks: ["-", "--", "", "+", ""]
        }
    ],
    csat: [
        {
            label: "NET: Top-2-Box (T2B: Satisfied/Very Satisfied)",
            is_net: true,
            values: ["84.2%", "91.7%", "82.0%", "80.5%", "84.3%"],
            letters: ["-", "B C", "", "", ""],
            benchmarks: ["-", "++", "", "-", ""]
        },
        {
            label: "5 - Very Satisfied",
            is_net: false,
            values: ["48.5%", "60.8%", "46.0%", "43.1%", "47.1%"],
            letters: ["-", "B C D", "", "", ""],
            benchmarks: ["-", "++", "", "-", ""]
        },
        {
            label: "4 - Somewhat Satisfied",
            is_net: false,
            values: ["35.7%", "30.9%", "36.0%", "37.4%", "37.2%"],
            letters: ["-", "", "", "", ""],
            benchmarks: ["-", "", "", "", ""]
        },
        {
            label: "Mean Rating (1-5 Scale)",
            is_net: true,
            values: ["4.12", "4.48", "4.05", "3.98", "4.10"],
            letters: ["-", "B C D", "", "", ""],
            benchmarks: ["-", "++", "", "-", ""]
        }
    ]
};

// 1. Navigation Stepper
function switchStep(stepNum) {
    document.querySelectorAll('.step-btn').forEach((btn, idx) => {
        btn.classList.toggle('active', idx + 1 === stepNum);
    });

    document.querySelectorAll('.step-pane').forEach((pane, idx) => {
        pane.classList.toggle('active-pane', idx + 1 === stepNum);
    });

    currentStep = stepNum;
}

// 2. Render Table with Dual Significance Rows
function renderTable() {
    const tbody = document.getElementById('table-body');
    if (!tbody) return;
    tbody.innerHTML = "";

    const activeRows = (currentMetric === 't2b' || currentMetric === 'mean') 
        ? sampleTableData.csat 
        : sampleTableData.brand_preference;

    activeRows.forEach(row => {
        // Line 1: Primary Value Row
        const trVal = document.createElement('tr');
        if (row.is_net) trVal.className = 'net-row';
        
        let valHtml = `<td>${row.label}</td>`;
        row.values.forEach((v, idx) => {
            const hasSig = (row.letters[idx] && row.letters[idx] !== '-') || (row.benchmarks[idx] && row.benchmarks[idx] !== '-');
            const cellClass = hasSig ? 'sig-cell' : '';
            valHtml += `<td class="${cellClass}"><b>${v}</b></td>`;
        });
        trVal.innerHTML = valHtml;
        tbody.appendChild(trVal);

        // Line 2: Sig Test 1 - Column Comparison Letters (a, b, c / A, B, C)
        if (sigDisplayMode === 'both' || sigDisplayMode === 'letters') {
            const trLetters = document.createElement('tr');
            trLetters.className = 'sig-row';
            let letHtml = `<td class="sig-label">  ↳ Col Comparisons (Letters)</td>`;
            row.letters.forEach(l => {
                let badge = "";
                if (l && l !== '-') {
                    badge = `<span class="sig-badge">${l}</span>`;
                } else if (l === '-') {
                    badge = `<span style="color: #64748B;">-</span>`;
                }
                letHtml += `<td>${badge}</td>`;
            });
            trLetters.innerHTML = letHtml;
            tbody.appendChild(trLetters);
        }

        // Line 3: Sig Test 2 - Total Benchmark Indicators (+/++, -/--)
        if (sigDisplayMode === 'both' || sigDisplayMode === 'bench') {
            const trBench = document.createElement('tr');
            trBench.className = 'sig-row';
            let benchHtml = `<td class="sig-label">  ↳ vs. Total (+/++, -/--)</td>`;
            row.benchmarks.forEach(b => {
                let tag = "";
                if (b.includes('++')) {
                    tag = `<span class="benchmark-pos-heavy">++</span>`;
                } else if (b.includes('+')) {
                    tag = `<span class="benchmark-pos">+</span>`;
                } else if (b.includes('--')) {
                    tag = `<span class="benchmark-neg-heavy">--</span>`;
                } else if (b.includes('-') && b !== '-') {
                    tag = `<span class="benchmark-neg">-</span>`;
                } else if (b === '-') {
                    tag = `<span style="color: #64748B;">-</span>`;
                }
                benchHtml += `<td>${tag}</td>`;
            });
            trBench.innerHTML = benchHtml;
            tbody.appendChild(trBench);
        }
    });
}

function setSigDisplayMode(mode) {
    sigDisplayMode = mode;
    document.getElementById('btn-sig-both').classList.toggle('active-toggle', mode === 'both');
    document.getElementById('btn-sig-letters').classList.toggle('active-toggle', mode === 'letters');
    document.getElementById('btn-sig-bench').classList.toggle('active-toggle', mode === 'bench');
    renderTable();
}

function setConfidence(conf) {
    currentConfidence = conf;
    document.querySelectorAll('.control-cluster:nth-child(2) .pill-toggle').forEach(btn => {
        btn.classList.toggle('active-toggle', btn.innerText.includes(conf.toString()));
    });
    renderTable();
}

function setMetric(metric) {
    currentMetric = metric;
    document.querySelectorAll('.control-cluster:nth-child(3) .pill-toggle').forEach(btn => {
        btn.classList.remove('active-toggle');
    });
    event.target.classList.add('active-toggle');
    renderTable();
}

// 3. Ingestion Simulation
function loadSampleDataset() {
    const summaryCard = document.getElementById('import-summary-card');
    summaryCard.classList.remove('hidden');
    summaryCard.style.animation = "fadeInUp 0.35s cubic-bezier(0.34, 1.4, 0.64, 1)";
    renderTable();
}

// 4. Weighting Controls
function updateTrim(val) {
    document.getElementById('trim-val').innerText = val + "th Percentile";
}

function executeWeighting() {
    const eff = document.getElementById('eff-disp');
    const neff = document.getElementById('neff-disp');
    eff.innerText = "Recalculating...";
    setTimeout(() => {
        eff.innerText = "94.8%";
        neff.innerText = "390.5";
        eff.style.color = "#10B981";
    }, 280);
}

function toggleHygiene() {}

// 5. Drag & Drop
function drag(ev) {
    ev.dataTransfer.setData("text/plain", ev.target.getAttribute("data-var"));
}
function allowDrop(ev) {
    ev.preventDefault();
}
function dropBanner(ev) {
    ev.preventDefault();
    const dataVar = ev.dataTransfer.getData("text/plain");
    const tray = document.getElementById('banner-tray');
    const newPill = document.createElement("span");
    newPill.className = "tag-pill";
    newPill.innerText = dataVar;
    tray.appendChild(newPill);
    renderTable();
}
function dropStub(ev) {
    ev.preventDefault();
    const dataVar = ev.dataTransfer.getData("text/plain");
    const tray = document.getElementById('stub-tray');
    tray.innerHTML = "";
    const newPill = document.createElement("span");
    newPill.className = "tag-pill";
    newPill.innerText = dataVar;
    tray.appendChild(newPill);
    renderTable();
}

// 6. Conversational Prompt-to-Table
function executePromptToTable() {
    const input = document.getElementById('prompt-input').value.trim();
    if (!input) return;
    
    const bannerTray = document.getElementById('banner-tray');
    const stubTray = document.getElementById('stub-tray');
    
    if (input.toLowerCase().includes('satisfaction') || input.toLowerCase().includes('csat')) {
        stubTray.innerHTML = `<span class="tag-pill">Overall CSAT (T2B)</span>`;
        setMetric('t2b');
    }
    
    if (input.toLowerCase().includes('age') || input.toLowerCase().includes('gen z')) {
        bannerTray.innerHTML = `
            <span class="tag-pill">Total</span>
            <span class="tag-pill">Gen Z (A)</span>
            <span class="tag-pill">Millennial (B)</span>
            <span class="tag-pill">Gen X (C)</span>
        `;
    }
    renderTable();
}

// 7. Human Lock-Step Protocol
function toggleLock() {
    isCodeframeLocked = !isCodeframeLocked;
    const btn = document.getElementById('lock-btn');
    if (isCodeframeLocked) {
        btn.innerText = "🔒 Codeframe Locked (Audit Ready)";
        btn.style.background = "#10B981";
        btn.style.color = "#FFFFFF";
    } else {
        btn.innerText = "🔓 Unlock for Review";
        btn.style.background = "rgba(16, 185, 129, 0.2)";
        btn.style.color = "#10B981";
    }
}

// 8. Reliable Desktop Downloads (With Direct Save to ~/Downloads & Finder Reveal)
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.innerText = message;
    toast.className = 'toast-notification ' + (isError ? 'toast-error' : 'toast-success');
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4500);
}

function downloadExcel() {
    const btn = document.getElementById('btn-dl-excel');
    const origText = btn.innerText;
    btn.innerText = "⏳ Generating Banner Book...";
    btn.disabled = true;

    // Call native direct save endpoint (writes directly to ~/Downloads and reveals in Finder)
    fetch('/api/export/save-to-downloads')
        .then(res => res.json())
        .then(data => {
            btn.innerText = origText;
            btn.disabled = false;
            if (data.status === 'success') {
                showToast("✓ Saved directly to ~/Downloads & revealed in Finder!");
            } else {
                // Fallback to browser direct streaming
                window.location.href = '/api/export/excel';
            }
        })
        .catch(err => {
            btn.innerText = origText;
            btn.disabled = false;
            // Fallback link trigger
            window.location.href = '/api/export/excel';
            showToast("✓ Downloading via direct stream...");
        });
}

function downloadSnapshot() {
    window.open("/preview-snapshot", "_blank");
}

function downloadThesisTables() {
    alert("Chapter 4 Academic Tables generated in accordance with Philippine University specifications.");
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
    renderTable();
});
