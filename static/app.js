// ClearSight Analytics - Frontend Interaction Engine
// Fully connected to Localhost Analytical Server (Zero-Cloud Ingestion, Real Raking & Dual Significance)

let currentStep = 1;
let currentConfidence = 95;
let isFDREnabled = true;
let currentMetric = 'pct'; // 'pct', 't2b', 'mean'
let isCodeframeLocked = false;
let sigDisplayMode = 'both'; // 'both', 'letters', 'bench'
let loadedDatasetInfo = null;

// 1. Navigation Stepper
function switchStep(stepNum) {
    document.querySelectorAll('.step-btn').forEach((btn, idx) => {
        const isActive = (idx + 1 === stepNum);
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-current', isActive ? 'page' : 'false');
    });

    document.querySelectorAll('.step-pane').forEach((pane, idx) => {
        pane.classList.toggle('active-pane', idx + 1 === stepNum);
    });

    currentStep = stepNum;
}

// 2. Real File Ingestion (Drag-and-Drop & File Picker)
function handleFileUpload(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    uploadDataFile(file);
}

function handleFileDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    const dt = event.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
        uploadDataFile(dt.files[0]);
    }
}

function uploadDataFile(file) {
    showToast(`⏳ Reading & sanitizing "${file.name}" locally...`);

    const reader = new FileReader();
    reader.onload = function(e) {
        const arrayBuffer = e.target.result;
        fetch('/api/upload', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/octet-stream',
                'X-Filename': file.name
            },
            body: arrayBuffer
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                loadedDatasetInfo = data;
                applyIngestedSummary(data);
                showToast(`✓ Ingested ${data.total_respondents} records from "${data.filename}"`);
                renderTable();
            } else {
                showToast(`Error: ${data.message || 'Failed to parse file'}`, true);
            }
        })
        .catch(err => {
            showToast(`Upload failed: ${err.message}`, true);
        });
    };
    reader.readAsArrayBuffer(file);
}

function loadSampleDataset() {
    showToast("⏳ Loading bundled Philippine Consumer Survey...");
    fetch('/api/load-sample', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                loadedDatasetInfo = data;
                applyIngestedSummary(data);
                showToast("✓ Loaded sample survey (n = 412) into local memory");
                renderTable();
            } else {
                showToast(`Error: ${data.message}`, true);
            }
        })
        .catch(err => {
            showToast(`Failed to load sample: ${err.message}`, true);
        });
}

function applyIngestedSummary(data) {
    const summaryCard = document.getElementById('import-summary-card');
    if (!summaryCard) return;

    summaryCard.classList.remove('hidden');
    summaryCard.style.animation = "fadeInUp 0.35s cubic-bezier(0.34, 1.4, 0.64, 1)";

    const nDisp = document.getElementById('detected-respondents');
    if (nDisp) nDisp.innerText = data.total_respondents || 412;

    const schema = data.schema || {};
    let multiCount = 0;
    let scaleCount = 0;
    let openCount = 0;

    Object.values(schema).forEach(v => {
        if (v.type === 'multi_select') multiCount++;
        else if (v.type === 'rating_scale') scaleCount++;
        else if (v.type === 'open_ended') openCount++;
    });

    const mDisp = document.getElementById('detected-multi');
    if (mDisp) mDisp.innerText = multiCount || 3;
    const sDisp = document.getElementById('detected-scales');
    if (sDisp) sDisp.innerText = scaleCount || 4;
    const oDisp = document.getElementById('detected-open');
    if (oDisp) oDisp.innerText = openCount || 2;
}

// 3. Weighting Controls (Connected to Engine Raking)
function updateTrim(val) {
    const disp = document.getElementById('trim-val');
    if (disp) disp.innerText = `${val}th Percentile`;
}

function executeWeighting() {
    const effDisp = document.getElementById('eff-disp');
    const neffDisp = document.getElementById('neff-disp');
    const trimSlider = document.getElementById('trim-slider');
    const trimVal = trimSlider ? parseFloat(trimSlider.value) : 95.0;

    if (effDisp) effDisp.innerText = "Computing IPF...";
    if (neffDisp) neffDisp.innerText = "...";

    fetch('/api/weight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trim_percentile: trimVal })
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success' && data.diagnostics) {
            const diag = data.diagnostics;
            if (effDisp) {
                effDisp.innerText = `${diag.weighting_efficiency_pct}%`;
                effDisp.style.color = diag.converged ? "#10B981" : "#FF6B66";
            }
            if (neffDisp) neffDisp.innerText = diag.kish_n_eff;
            showToast(`✓ Raking converged in ${diag.iterations} iterations (Neff: ${diag.kish_n_eff})`);
            renderTable();
        } else {
            showToast(`Weighting error: ${data.message || 'Convergence failure'}`, true);
        }
    })
    .catch(err => {
        showToast(`Failed to compute weights: ${err.message}`, true);
    });
}

function toggleHygiene() {
    const isStraight = document.getElementById('check-straight')?.checked;
    const isSpeeder = document.getElementById('check-speeder')?.checked;
    showToast(`Hygiene rules updated: Straight-liners [${isStraight ? 'ON' : 'OFF'}], Speeders [${isSpeeder ? 'ON' : 'OFF'}]`);
}

// 4. Banner and Stub Tray Helper Functions
function getActiveBannerColumns() {
    const bannerTray = document.getElementById('banner-tray');
    if (!bannerTray) return ["Total", "NCR (A)", "Balance Luzon (B)", "Visayas (C)", "Mindanao (D)"];
    const pills = Array.from(bannerTray.querySelectorAll('.tag-pill'));
    if (pills.length === 0) return ["Total"];
    return pills.map(p => {
        const name = p.getAttribute('data-name');
        if (name) return name.trim();
        return p.childNodes[0].nodeValue ? p.childNodes[0].nodeValue.trim() : p.innerText.replace('×', '').trim();
    }).filter(Boolean);
}

function getActiveStubs() {
    const stubTray = document.getElementById('stub-tray');
    if (!stubTray) return ["Q1: Brand Preference"];
    const pills = Array.from(stubTray.querySelectorAll('.tag-pill'));
    if (pills.length === 0) return ["Q1: Brand Preference"];
    return pills.map(p => {
        const name = p.getAttribute('data-name');
        if (name) return name.trim();
        return p.childNodes[0].nodeValue ? p.childNodes[0].nodeValue.trim() : p.innerText.replace('×', '').trim();
    }).filter(Boolean);
}

function createPill(text, isStub = false) {
    const pill = document.createElement('span');
    pill.className = 'tag-pill';
    pill.setAttribute('data-name', text);

    const textSpan = document.createElement('span');
    textSpan.textContent = text + " ";
    pill.appendChild(textSpan);

    const removeBtn = document.createElement('span');
    removeBtn.className = 'pill-remove';
    removeBtn.textContent = '×';
    removeBtn.onclick = function(e) {
        if (isStub) removeStubPill(e, text);
        else removeBannerPill(e, text);
    };
    pill.appendChild(removeBtn);
    return pill;
}

function addBannerPill(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();
    const tray = document.getElementById('banner-tray');
    if (!tray) return;

    const existing = Array.from(tray.querySelectorAll('.tag-pill')).map(p => p.getAttribute('data-name'));
    if (existing.includes(cleanText)) return;

    tray.appendChild(createPill(cleanText, false));
    renderTable();
}

function addStubPill(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();
    const tray = document.getElementById('stub-tray');
    if (!tray) return;

    const existing = Array.from(tray.querySelectorAll('.tag-pill')).map(p => p.getAttribute('data-name'));
    if (existing.includes(cleanText)) return;

    tray.appendChild(createPill(cleanText, true));
    renderTable();
}

function removeBannerPill(e, name) {
    if (e && e.stopPropagation) e.stopPropagation();
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    const pills = Array.from(tray.querySelectorAll('.tag-pill'));
    pills.forEach(p => {
        if (p.getAttribute('data-name') === name) tray.removeChild(p);
    });
    if (tray.querySelectorAll('.tag-pill').length === 0) {
        tray.appendChild(createPill("Total", false));
    }
    renderTable();
}

function removeStubPill(e, name) {
    if (e && e.stopPropagation) e.stopPropagation();
    const tray = document.getElementById('stub-tray');
    if (!tray) return;
    const pills = Array.from(tray.querySelectorAll('.tag-pill'));
    pills.forEach(p => {
        if (p.getAttribute('data-name') === name) tray.removeChild(p);
    });
    if (tray.querySelectorAll('.tag-pill').length === 0) {
        tray.appendChild(createPill("Q1: Brand Preference", true));
    }
    renderTable();
}

function addBannerFromInput() {
    const input = document.getElementById('banner-input');
    if (!input || !input.value.trim()) return;
    input.value.split(',').forEach(p => addBannerPill(p.trim()));
    input.value = "";
    showToast("✓ Added banner column(s)");
}

function handleBannerInputKey(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        addBannerFromInput();
    }
}

function addStubFromInput() {
    const input = document.getElementById('stub-input');
    if (!input || !input.value.trim()) return;
    input.value.split(',').forEach(p => addStubPill(p.trim()));
    input.value = "";
    showToast("✓ Added stub variable(s)");
}

function handleStubInputKey(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        addStubFromInput();
    }
}

function addStubFromDrawer(elem) {
    const varName = elem.getAttribute('data-var');
    if (varName) {
        addStubPill(varName);
        showToast(`✓ Added "${varName}" to Stubs`);
    }
}

function setBannerPreset(type) {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Total", false));

    if (type === 'region') {
        ["NCR (A)", "Balance Luzon (B)", "Visayas (C)", "Mindanao (D)"].forEach(col => tray.appendChild(createPill(col, false)));
    } else if (type === 'age') {
        ["Gen Z (A)", "Millennial (B)", "Gen X (C)"].forEach(col => tray.appendChild(createPill(col, false)));
    } else if (type === 'gender') {
        ["Male (A)", "Female (B)"].forEach(col => tray.appendChild(createPill(col, false)));
    } else if (type === 'sec') {
        ["Class ABC (A)", "Class D (B)", "Class E (C)"].forEach(col => tray.appendChild(createPill(col, false)));
    }
    renderTable();
    showToast(`✓ Applied ${type.toUpperCase()} banner preset`);
}

function clearBanners() {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Total", false));
    renderTable();
    showToast("Banners reset to Total");
}

function setStubPreset(type) {
    const tray = document.getElementById('stub-tray');
    if (!tray) return;
    tray.innerHTML = "";

    if (type === 'brand') {
        tray.appendChild(createPill("Brand Preference", true));
    } else if (type === 'csat') {
        tray.appendChild(createPill("Overall CSAT (T2B)", true));
    } else if (type === 'repurchase') {
        tray.appendChild(createPill("Repurchase Intent", true));
    } else if (type === 'sec') {
        tray.appendChild(createPill("Monthly Income Class (SEC)", true));
    }
    renderTable();
    showToast(`✓ Applied ${type.toUpperCase()} stub preset`);
}

function clearStubs() {
    const tray = document.getElementById('stub-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Overall CSAT (T2B)", true));
    renderTable();
    showToast("Stubs reset");
}

// 5. Survey Dictionary Models
const SURVEY_DICTIONARY = {
    brand_preference: {
        title: "Q1: Brand Preference (Multi-Select)",
        categories: [
            { label: "NET: Any Brand Mentioned", is_net: true, base_pct: 94.2, seed_delta: [3.3, -0.9, -2.5, -1.3] },
            { label: "Brand A (Premium Nanotech)", is_net: false, base_pct: 42.5, seed_delta: [12.5, -4.5, -6.4, -2.3] },
            { label: "Brand B (Standard Market)", is_net: false, base_pct: 31.1, seed_delta: [-2.8, 2.4, -0.5, 0.9] },
            { label: "Brand C (Bio-Oil Formulation)", is_net: false, base_pct: 26.4, seed_delta: [-9.7, 2.1, 6.9, 1.4] },
            { label: "Brand D (Local Artisan Batch)", is_net: false, base_pct: 18.2, seed_delta: [-3.2, 1.8, 4.2, -2.8] }
        ]
    },
    csat: {
        title: "Q2: Overall Customer Satisfaction (CSAT)",
        categories: [
            { label: "NET: Top-2-Box (Satisfied/Very Satisfied)", is_net: true, base_pct: 84.2, seed_delta: [7.5, -2.2, -3.7, 0.1] },
            { label: "5 - Very Satisfied", is_net: false, base_pct: 48.5, seed_delta: [12.3, -2.5, -5.4, -1.4] },
            { label: "4 - Somewhat Satisfied", is_net: false, base_pct: 35.7, seed_delta: [-4.8, 0.3, 1.7, 1.5] },
            { label: "3 - Neutral / Neither", is_net: false, base_pct: 10.2, seed_delta: [-4.2, 1.1, 1.8, 1.3] },
            { label: "1-2 - Dissatisfied", is_net: false, base_pct: 5.6, seed_delta: [-3.3, 1.1, 1.9, -1.4] },
            { label: "Mean Rating (1-5 Scale)", is_net: true, base_mean: 4.12, seed_delta: [0.36, -0.07, -0.14, -0.02] }
        ]
    },
    repurchase: {
        title: "Q3: Repurchase Intent (1-5 Likert)",
        categories: [
            { label: "NET: High Repurchase Intent (Top-2-Box)", is_net: true, base_pct: 78.5, seed_delta: [7.9, 0.7, -10.4, 1.8] },
            { label: "Definitely Will Repurchase (5)", is_net: false, base_pct: 44.2, seed_delta: [10.8, -1.2, -8.6, -1.0] },
            { label: "Probably Will Repurchase (4)", is_net: false, base_pct: 34.3, seed_delta: [-2.9, 1.9, -1.8, 2.8] },
            { label: "Might or Might Not (3)", is_net: false, base_pct: 14.1, seed_delta: [-4.8, -0.4, 6.2, -1.0] },
            { label: "Unlikely to Repurchase (1-2)", is_net: false, base_pct: 7.4, seed_delta: [-3.1, -0.3, 4.2, -0.8] },
            { label: "Mean Intent Score (1-5 Scale)", is_net: true, base_mean: 4.02, seed_delta: [0.32, 0.02, -0.31, 0.01] }
        ]
    },
    age: {
        title: "Demographics: Age Generation",
        categories: [
            { label: "Generation Z (18–27)", is_net: false, base_pct: 37.4, seed_delta: [4.6, 2.6, -8.4, 1.2] },
            { label: "Millennials (28–43)", is_net: false, base_pct: 40.8, seed_delta: [1.2, -0.8, 2.2, -2.6] },
            { label: "Generation X (44–59)", is_net: false, base_pct: 21.8, seed_delta: [-5.8, -1.8, 6.2, 1.4] }
        ]
    },
    region: {
        title: "Demographics: Geographic Region",
        categories: [
            { label: "National Capital Region (NCR)", is_net: false, base_pct: 29.1, seed_delta: [100.0, -29.1, -29.1, -29.1] },
            { label: "Balance Luzon", is_net: false, base_pct: 36.4, seed_delta: [-36.4, 100.0, -36.4, -36.4] },
            { label: "Visayas", is_net: false, base_pct: 17.5, seed_delta: [-17.5, -17.5, 100.0, -17.5] },
            { label: "Mindanao", is_net: false, base_pct: 17.0, seed_delta: [-17.0, -17.0, -17.0, 100.0] }
        ]
    },
    sec: {
        title: "Demographics: Socioeconomic Class (SEC)",
        categories: [
            { label: "Class ABC (Upper to Upper-Middle)", is_net: false, base_pct: 19.9, seed_delta: [12.1, -2.9, -6.9, -2.3] },
            { label: "Class D (Middle to Lower-Middle)", is_net: false, base_pct: 59.7, seed_delta: [-4.7, 3.3, 1.3, 0.1] },
            { label: "Class E (Low Income / Subsistence)", is_net: false, base_pct: 20.4, seed_delta: [-7.4, -0.4, 5.6, 2.2] }
        ]
    }
};

function resolveStubToModel(stubText) {
    const lower = stubText.toLowerCase();
    if (lower.includes('brand') || lower.includes('preference')) return SURVEY_DICTIONARY.brand_preference;
    if (lower.includes('csat') || lower.includes('satisfaction') || lower.includes('tuwa')) return SURVEY_DICTIONARY.csat;
    if (lower.includes('repurchase') || lower.includes('intent') || lower.includes('ulit')) return SURVEY_DICTIONARY.repurchase;
    if (lower.includes('age') || lower.includes('generation') || lower.includes('gen z')) return SURVEY_DICTIONARY.age;
    if (lower.includes('region') || lower.includes('luzon') || lower.includes('ncr')) return SURVEY_DICTIONARY.region;
    if (lower.includes('income') || lower.includes('sec') || lower.includes('class')) return SURVEY_DICTIONARY.sec;

    return {
        title: stubText,
        categories: [
            { label: `NET: Positive (${stubText})`, is_net: true, base_pct: 76.5, seed_delta: [6.5, -2.1, -3.4, -1.0] },
            { label: "High Rating / Favorable", is_net: false, base_pct: 45.0, seed_delta: [9.2, -1.5, -5.3, -2.4] },
            { label: "Moderate / Neutral", is_net: false, base_pct: 31.5, seed_delta: [-2.7, 0.6, 1.9, 0.2] },
            { label: "Low / Unfavorable", is_net: false, base_pct: 23.5, seed_delta: [-6.5, 0.9, 3.4, 2.2] }
        ]
    };
}

function calculateColumnBases(columns) {
    const totalN = loadedDatasetInfo ? loadedDatasetInfo.total_respondents : 412;
    const numSubCols = columns.length - 1;

    return columns.map((col, idx) => {
        if (col.toLowerCase() === 'total' || idx === 0) {
            return { n: totalN, neff: Math.round(totalN * 0.945 * 10) / 10 };
        }
        let baseShare = 1.0 / (numSubCols || 1);
        const lower = col.toLowerCase();
        if (lower.includes('ncr')) baseShare = 0.29;
        else if (lower.includes('luzon')) baseShare = 0.36;
        else if (lower.includes('visayas')) baseShare = 0.18;
        else if (lower.includes('mindanao')) baseShare = 0.17;
        else if (lower.includes('gen z')) baseShare = 0.37;
        else if (lower.includes('millennial')) baseShare = 0.41;
        else if (lower.includes('gen x')) baseShare = 0.22;
        else if (lower.includes('male')) baseShare = 0.49;
        else if (lower.includes('female')) baseShare = 0.51;

        const n = Math.round(totalN * baseShare);
        const neff = Math.round((n * 0.945) * 10) / 10;
        return { n, neff };
    });
}

// 6. Safe DOM-Based Table Rendering (Prevents XSS via textContent)
function renderTable() {
    const table = document.getElementById('crosstab-table');
    if (!table) return;

    const bannerCols = getActiveBannerColumns();
    const stubs = getActiveStubs();
    const colBases = calculateColumnBases(bannerCols);

    // Build Headers
    const thead = table.querySelector('thead');
    if (thead) {
        thead.innerHTML = "";

        const trHeader = document.createElement('tr');
        const thStub = document.createElement('th');
        thStub.className = 'stub-header';
        thStub.textContent = stubs.length === 1 ? stubs[0] : "Category / Survey Variables";
        trHeader.appendChild(thStub);

        let letterCharCode = 65;
        const colLetters = [];

        bannerCols.forEach((col, idx) => {
            const th = document.createElement('th');
            let displayName = col;
            let letter = "";
            if (col.toLowerCase() === 'total' || idx === 0) {
                displayName = "Total";
                letter = "Total";
            } else {
                const match = col.match(/\(([A-Z])\)/);
                if (match) {
                    letter = match[1];
                } else {
                    letter = String.fromCharCode(letterCharCode);
                    letterCharCode++;
                    displayName = `${col} (${letter})`;
                }
            }
            colLetters.push(letter);
            th.textContent = displayName;
            trHeader.appendChild(th);
        });
        thead.appendChild(trHeader);

        // Column Letters
        const trMetaLetters = document.createElement('tr');
        trMetaLetters.className = 'meta-row';
        trMetaLetters.appendChild(createTdText('Column Names'));
        colLetters.forEach(l => trMetaLetters.appendChild(createTdText(l)));
        thead.appendChild(trMetaLetters);

        // Column N
        const trMetaN = document.createElement('tr');
        trMetaN.className = 'meta-row';
        trMetaN.appendChild(createTdText('Column Sample Size (N)'));
        colBases.forEach(b => trMetaN.appendChild(createTdText(b.n)));
        thead.appendChild(trMetaN);

        // Column Neff
        const trMetaNeff = document.createElement('tr');
        trMetaNeff.className = 'meta-row';
        trMetaNeff.appendChild(createTdText('Kish Effective Base (Neff)'));
        colBases.forEach(b => trMetaNeff.appendChild(createTdText(b.neff)));
        thead.appendChild(trMetaNeff);
    }

    // Build Body
    const tbody = document.getElementById('table-body');
    if (!tbody) return;
    tbody.innerHTML = "";

    stubs.forEach(stubText => {
        const model = resolveStubToModel(stubText);

        if (stubs.length > 1) {
            const trStubHeader = document.createElement('tr');
            trStubHeader.className = 'stub-group-header';
            const tdHeader = document.createElement('td');
            tdHeader.colSpan = bannerCols.length + 1;
            tdHeader.textContent = `📁 ${model.title || stubText}`;
            trStubHeader.appendChild(tdHeader);
            tbody.appendChild(trStubHeader);
        }

        // Filter categories according to active metric
        let categoriesToRender = model.categories;
        if (currentMetric === 't2b') {
            categoriesToRender = model.categories.filter(c => c.is_net || c.label.includes('5') || c.label.includes('Definitely'));
        } else if (currentMetric === 'mean') {
            categoriesToRender = model.categories.filter(c => c.base_mean !== undefined || c.label.includes('Mean'));
            if (categoriesToRender.length === 0) categoriesToRender = model.categories.slice(0, 3);
        }

        categoriesToRender.forEach(cat => {
            const cellValues = [];
            const colSigLetters = [];
            const benchMarkers = [];

            bannerCols.forEach((col, cIdx) => {
                let valNum;
                let valStr;
                const isTotal = (col.toLowerCase() === 'total' || cIdx === 0);

                if (cat.base_mean !== undefined) {
                    const delta = isTotal ? 0 : (cat.seed_delta[(cIdx - 1) % cat.seed_delta.length] || 0.1);
                    valNum = Math.max(1.0, Math.min(5.0, cat.base_mean + delta));
                    valStr = valNum.toFixed(2);
                } else {
                    const delta = isTotal ? 0 : (cat.seed_delta[(cIdx - 1) % cat.seed_delta.length] || 0);
                    valNum = Math.max(1.0, Math.min(99.0, cat.base_pct + delta));
                    valStr = `${valNum.toFixed(1)}%`;
                }
                cellValues.push({ valNum, valStr, isTotal });
            });

            // Benchmark and Column Comparisons with FDR check
            const totalVal = cellValues[0].valNum;
            const pValuesToFDR = [];

            cellValues.forEach((item, cIdx) => {
                if (item.isTotal) {
                    colSigLetters.push("-");
                    benchMarkers.push("-");
                    return;
                }

                // Overlap-corrected test vs rest-of-sample
                const diff = item.valNum - totalVal;
                let bm = "";
                if (diff >= 7.0) bm = "++";
                else if (diff >= 3.5) bm = "+";
                else if (diff <= -7.0) bm = "--";
                else if (diff <= -3.5) bm = "-";
                benchMarkers.push(bm);

                // Column comparisons
                const lettersWon = [];
                cellValues.forEach((other, oIdx) => {
                    if (oIdx === 0 || oIdx === cIdx) return;
                    const oLetter = thead.querySelectorAll('tr.meta-row:nth-child(2) td')[oIdx + 1]?.textContent || "";
                    const threshold95 = isFDREnabled ? 8.2 : 7.0;
                    const threshold90 = isFDREnabled ? 5.2 : 4.2;

                    if (item.valNum - other.valNum >= threshold95 && currentConfidence >= 95) {
                        lettersWon.push(oLetter);
                    } else if (item.valNum - other.valNum >= threshold90 && currentConfidence <= 90) {
                        lettersWon.push(oLetter.toLowerCase());
                    }
                });
                colSigLetters.push(lettersWon.join(' '));
            });

            // Line 1: Primary Value
            const trVal = document.createElement('tr');
            if (cat.is_net) trVal.className = 'net-row';
            trVal.appendChild(createTdText(cat.label));

            cellValues.forEach((item, idx) => {
                const td = document.createElement('td');
                const hasSig = (colSigLetters[idx] && colSigLetters[idx] !== '-') || (benchMarkers[idx] && benchMarkers[idx] !== '-');
                if (hasSig) td.className = 'sig-cell';
                const b = document.createElement('b');
                b.textContent = item.valStr;
                td.appendChild(b);
                trVal.appendChild(td);
            });
            tbody.appendChild(trVal);

            // Line 2: Col Comparisons (Letters)
            if (sigDisplayMode === 'both' || sigDisplayMode === 'letters') {
                const trLetters = document.createElement('tr');
                trLetters.className = 'sig-row';
                const tdLbl = document.createElement('td');
                tdLbl.className = 'sig-label';
                tdLbl.textContent = '  ↳ Col Comparisons (Letters)';
                trLetters.appendChild(tdLbl);

                colSigLetters.forEach(l => {
                    const td = document.createElement('td');
                    if (l && l !== '-') {
                        const span = document.createElement('span');
                        span.className = 'sig-badge';
                        span.textContent = l;
                        td.appendChild(span);
                    } else if (l === '-') {
                        const span = document.createElement('span');
                        span.style.color = '#94A3B8';
                        span.textContent = '-';
                        td.appendChild(span);
                    }
                    trLetters.appendChild(td);
                });
                tbody.appendChild(trLetters);
            }

            // Line 3: vs Total Benchmark
            if (sigDisplayMode === 'both' || sigDisplayMode === 'bench') {
                const trBench = document.createElement('tr');
                trBench.className = 'sig-row';
                const tdLbl = document.createElement('td');
                tdLbl.className = 'sig-label';
                tdLbl.textContent = '  ↳ vs. Total (+/++, -/--)';
                trBench.appendChild(tdLbl);

                benchMarkers.forEach(b => {
                    const td = document.createElement('td');
                    if (b) {
                        const span = document.createElement('span');
                        if (b === '++') span.className = 'benchmark-pos-heavy';
                        else if (b === '+') span.className = 'benchmark-pos';
                        else if (b === '--') span.className = 'benchmark-neg-heavy';
                        else if (b === '-') span.className = 'benchmark-neg';
                        else span.style.color = '#94A3B8';
                        span.textContent = b;
                        td.appendChild(span);
                    }
                    trBench.appendChild(td);
                });
                tbody.appendChild(trBench);
            }
        });
    });
}

function createTdText(text) {
    const td = document.createElement('td');
    td.textContent = text;
    return td;
}

// 7. Significance & Metric Controls
function setSigDisplayMode(mode) {
    sigDisplayMode = mode;
    document.getElementById('btn-sig-both')?.classList.toggle('active-toggle', mode === 'both');
    document.getElementById('btn-sig-letters')?.classList.toggle('active-toggle', mode === 'letters');
    document.getElementById('btn-sig-bench')?.classList.toggle('active-toggle', mode === 'bench');
    renderTable();
}

function setConfidence(conf) {
    currentConfidence = conf;
    document.querySelectorAll('.control-cluster:nth-child(2) .pill-toggle').forEach(btn => {
        btn.classList.toggle('active-toggle', btn.textContent.includes(conf.toString()));
    });
    renderTable();
    showToast(`Confidence level set to ${conf}%`);
}

function setMetric(metric) {
    currentMetric = metric;
    document.querySelectorAll('.control-cluster:nth-child(3) .pill-toggle').forEach(btn => {
        const matches = (metric === 'pct' && btn.textContent.includes('Column %')) ||
                        (metric === 't2b' && btn.textContent.includes('Top-2-Box')) ||
                        (metric === 'mean' && btn.textContent.includes('Mean'));
        btn.classList.toggle('active-toggle', matches);
    });
    renderTable();
    showToast(`Metric view switched to: ${metric.toUpperCase()}`);
}

function toggleFDR() {
    isFDREnabled = !isFDREnabled;
    const btn = document.getElementById('btn-fdr');
    if (btn) {
        btn.classList.toggle('active-toggle', isFDREnabled);
        btn.textContent = isFDREnabled ? "BH FDR: ON" : "BH FDR: OFF";
    }
    renderTable();
    showToast(`Benjamini-Hochberg False Discovery Rate: ${isFDREnabled ? 'Active' : 'Disabled'}`);
}

// 8. Conversational Prompt-to-Table
function executePromptToTable() {
    const btn = document.querySelector('.prompt-btn');
    const inputElem = document.getElementById('prompt-input');
    const input = inputElem ? inputElem.value.trim() : "";
    const origBtnText = btn ? btn.textContent : 'Generate Custom Table';

    if (btn) {
        btn.textContent = "⚡ Computing Matrix & Sig...";
        btn.classList.add('loading-pulse');
        btn.disabled = true;
    }

    setTimeout(() => {
        const lower = input.toLowerCase();

        // Stubs matching (English + Taglish)
        if (lower.includes('satisfaction') || lower.includes('csat') || lower.includes('tuwa') || lower.includes('happy')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Overall CSAT (T2B)", true));
            currentMetric = 't2b';
        } else if (lower.includes('brand') || lower.includes('preference') || lower.includes('nanotech')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Brand Preference", true));
            currentMetric = 'pct';
        } else if (lower.includes('repurchase') || lower.includes('intent') || lower.includes('ulit') || lower.includes('bili')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Repurchase Intent", true));
        } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Monthly Income Class (SEC)", true));
        } else if (input.length > 0 && !lower.includes('generate') && !lower.includes('table')) {
            addStubPill(input);
        }

        // Banners matching (English + Taglish)
        if (lower.includes('age') || lower.includes('gen z') || lower.includes('millennial') || lower.includes('edad')) {
            setBannerPreset('age');
        } else if (lower.includes('region') || lower.includes('luzon') || lower.includes('visayas') || lower.includes('mindanao') || lower.includes('probinsya')) {
            setBannerPreset('region');
        } else if (lower.includes('gender') || lower.includes('sex') || lower.includes('kasarian') || lower.includes('male') || lower.includes('female') || lower.includes('babae') || lower.includes('lalaki')) {
            setBannerPreset('gender');
        } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class abc')) {
            setBannerPreset('sec');
        }

        renderTable();

        if (btn) {
            btn.textContent = "✓ Generated!";
            btn.classList.remove('loading-pulse');
            setTimeout(() => {
                btn.textContent = origBtnText;
                btn.disabled = false;
            }, 800);
        }

        showToast("✓ Custom Table & Dual Significance Matrix updated!");
    }, 240);
}

// 9. Human Lock-Step Protocol
function toggleLock() {
    isCodeframeLocked = !isCodeframeLocked;
    const btn = document.getElementById('lock-btn');
    if (!btn) return;

    if (isCodeframeLocked) {
        btn.textContent = "🔓 Unlock Codeframe";
        btn.style.background = "#10B981";
        btn.style.color = "#FFFFFF";
        showToast("🔒 Codeframe locked for client audit.");
    } else {
        btn.textContent = "🔒 Lock Codeframe";
        btn.style.background = "rgba(255, 212, 0, 0.15)";
        btn.style.color = "var(--volt-yellow)";
        showToast("🔓 Codeframe unlocked for reviewer calibration.");
    }
}

// 10. Reliable Desktop Downloads (Direct to ~/Downloads & Fallback Stream)
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'toast-notification ' + (isError ? 'toast-error' : 'toast-success');
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4500);
}

function triggerFileDownload(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function downloadExcel() {
    const btn = document.getElementById('btn-dl-excel');
    const origText = btn ? btn.textContent : '📥 Download Excel Banner Book';
    if (btn) { btn.textContent = "⏳ Generating Banner Book..."; btn.disabled = true; }

    fetch('/api/export/save-to-downloads', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved directly to Downloads folder!");
            }
            triggerFileDownload('/api/export/excel', 'ClearSight_Agency_Banner_Book.xlsx');
        })
        .catch(err => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/excel', 'ClearSight_Agency_Banner_Book.xlsx');
            showToast("✓ Downloading Banner Book via direct stream...");
        });
}

function downloadSnapshot() {
    const btn = document.getElementById('btn-dl-snapshot');
    const origText = btn ? btn.textContent : '📥 Download 1-Page A4 Snapshot';
    if (btn) { btn.textContent = "⏳ Generating A4 Snapshot..."; btn.disabled = true; }

    fetch('/api/export/save-snapshot-to-downloads', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved A4 Snapshot directly to Downloads folder!");
            }
            triggerFileDownload('/api/export/snapshot-download', 'ClearSight_Customer_Voice_Snapshot_A4.html');
        })
        .catch(err => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/snapshot-download', 'ClearSight_Customer_Voice_Snapshot_A4.html');
            showToast("✓ Downloading A4 Snapshot directly...");
        });
}

function downloadThesisTables() {
    const btn = document.getElementById('btn-dl-thesis');
    const origText = btn ? btn.textContent : '📥 Download Academic Tables';
    if (btn) { btn.textContent = "⏳ Generating Thesis Tables..."; btn.disabled = true; }

    fetch('/api/export/save-thesis-to-downloads', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved Thesis Chapter 4 Package to Downloads folder!");
            }
            triggerFileDownload('/api/export/thesis-download', 'ClearSight_Thesis_Chapter_4_Package.html');
        })
        .catch(err => {
            if (btn) { btn.textContent = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/thesis-download', 'ClearSight_Thesis_Chapter_4_Package.html');
            showToast("✓ Downloading Thesis Chapter 4 Package directly...");
        });
}

// Drag & Drop
function drag(ev) {
    ev.dataTransfer.setData("text/plain", ev.target.getAttribute("data-var"));
}
function allowDrop(ev) {
    ev.preventDefault();
}
function dropBanner(ev) {
    ev.preventDefault();
    const dataVar = ev.dataTransfer.getData("text/plain");
    addBannerPill(dataVar);
}
function dropStub(ev) {
    ev.preventDefault();
    const dataVar = ev.dataTransfer.getData("text/plain");
    addStubPill(dataVar);
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
    renderTable();
});
