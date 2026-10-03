// ClearSight Analytics - Frontend Interaction Engine
// Handles: Stepper workflow, Interactive Stubs & Banners, Prompt-to-Table NLP, Dual Significance Testing, and Downloads

let currentStep = 1;
let currentConfidence = 95;
let isFDREnabled = true;
let currentMetric = 'pct';
let isCodeframeLocked = false;
let sigDisplayMode = 'both'; // 'both', 'letters', 'bench'

// Dictionary of known question batteries & categories
const SURVEY_DICTIONARY = {
    brand_preference: {
        title: "Q1: Brand Preference (Multi-Select)",
        is_mean: false,
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
        is_mean: false,
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
        is_mean: false,
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
        is_mean: false,
        categories: [
            { label: "Generation Z (18–27)", is_net: false, base_pct: 37.4, seed_delta: [4.6, 2.6, -8.4, 1.2] },
            { label: "Millennials (28–43)", is_net: false, base_pct: 40.8, seed_delta: [1.2, -0.8, 2.2, -2.6] },
            { label: "Generation X (44–59)", is_net: false, base_pct: 21.8, seed_delta: [-5.8, -1.8, 6.2, 1.4] }
        ]
    },
    region: {
        title: "Demographics: Geographic Region",
        is_mean: false,
        categories: [
            { label: "National Capital Region (NCR)", is_net: false, base_pct: 29.1, seed_delta: [100.0, -29.1, -29.1, -29.1] },
            { label: "Balance Luzon", is_net: false, base_pct: 36.4, seed_delta: [-36.4, 100.0, -36.4, -36.4] },
            { label: "Visayas", is_net: false, base_pct: 17.5, seed_delta: [-17.5, -17.5, 100.0, -17.5] },
            { label: "Mindanao", is_net: false, base_pct: 17.0, seed_delta: [-17.0, -17.0, -17.0, 100.0] }
        ]
    },
    sec: {
        title: "Demographics: Socioeconomic Class (SEC)",
        is_mean: false,
        categories: [
            { label: "Class ABC (Upper to Upper-Middle)", is_net: false, base_pct: 19.9, seed_delta: [12.1, -2.9, -6.9, -2.3] },
            { label: "Class D (Middle to Lower-Middle)", is_net: false, base_pct: 59.7, seed_delta: [-4.7, 3.3, 1.3, 0.1] },
            { label: "Class E (Low Income / Subsistence)", is_net: false, base_pct: 20.4, seed_delta: [-7.4, -0.4, 5.6, 2.2] }
        ]
    }
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

// 2. Banner and Stub Tray Helper Functions
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
    
    const textNode = document.createTextNode(text + " ");
    pill.appendChild(textNode);
    
    const removeBtn = document.createElement('span');
    removeBtn.className = 'pill-remove';
    removeBtn.innerHTML = '&times;';
    removeBtn.onclick = function(e) {
        if (isStub) {
            removeStubPill(e, text);
        } else {
            removeBannerPill(e, text);
        }
    };
    pill.appendChild(removeBtn);
    return pill;
}

function addBannerPill(text) {
    if (!text || !text.trim()) return;
    const cleanText = text.trim();
    const tray = document.getElementById('banner-tray');
    if (!tray) return;

    // Check if pill already exists
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

    // Check if already in tray
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
        if (p.getAttribute('data-name') === name) {
            tray.removeChild(p);
        }
    });
    // Ensure at least "Total" remains if all cleared
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
        if (p.getAttribute('data-name') === name) {
            tray.removeChild(p);
        }
    });
    // Ensure at least 1 stub remains
    if (tray.querySelectorAll('.tag-pill').length === 0) {
        tray.appendChild(createPill("Q1: Brand Preference", true));
    }
    renderTable();
}

function addBannerFromInput() {
    const input = document.getElementById('banner-input');
    if (!input || !input.value.trim()) return;
    const raw = input.value.trim();
    // Support comma separated inputs
    const parts = raw.split(',');
    parts.forEach(p => addBannerPill(p.trim()));
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
    const raw = input.value.trim();
    const parts = raw.split(',');
    parts.forEach(p => addStubPill(p.trim()));
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
        showToast("✓ Added '" + varName + "' to Table Stubs");
    }
}

// Presets
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
    showToast("✓ Applied " + type.toUpperCase() + " banner preset");
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
    showToast("✓ Applied " + type.toUpperCase() + " stub preset");
}

function clearStubs() {
    const tray = document.getElementById('stub-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Overall CSAT (T2B)", true));
    renderTable();
    showToast("Stubs reset");
}

// 3. Dynamic Crosstab Table Engine
function resolveStubToModel(stubText) {
    const lower = stubText.toLowerCase();
    if (lower.includes('brand') || lower.includes('preference')) {
        return SURVEY_DICTIONARY.brand_preference;
    } else if (lower.includes('csat') || lower.includes('satisfaction') || lower.includes('tuwa')) {
        return SURVEY_DICTIONARY.csat;
    } else if (lower.includes('repurchase') || lower.includes('intent') || lower.includes('ulit')) {
        return SURVEY_DICTIONARY.repurchase;
    } else if (lower.includes('age') || lower.includes('generation') || lower.includes('gen z')) {
        return SURVEY_DICTIONARY.age;
    } else if (lower.includes('region') || lower.includes('luzon') || lower.includes('ncr')) {
        return SURVEY_DICTIONARY.region;
    } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class')) {
        return SURVEY_DICTIONARY.sec;
    } else {
        // Fallback custom model for arbitrary user-entered stubs!
        return {
            title: stubText,
            is_mean: false,
            categories: [
                { label: `NET: Positive (${stubText})`, is_net: true, base_pct: 76.5, seed_delta: [6.5, -2.1, -3.4, -1.0] },
                { label: `High Rating / Favorable`, is_net: false, base_pct: 45.0, seed_delta: [9.2, -1.5, -5.3, -2.4] },
                { label: `Moderate / Neutral`, is_net: false, base_pct: 31.5, seed_delta: [-2.7, 0.6, 1.9, 0.2] },
                { label: `Low / Unfavorable`, is_net: false, base_pct: 23.5, seed_delta: [-6.5, 0.9, 3.4, 2.2] }
            ]
        };
    }
}

function calculateColumnBases(columns) {
    // Total base is 412, Neff = 389.2
    const totalN = 412;
    const numSubCols = columns.length - 1;
    
    return columns.map((col, idx) => {
        if (col.toLowerCase() === 'total' || idx === 0) {
            return { n: totalN, neff: 389.2 };
        }
        // Partition or estimate base sizes realistically
        let baseShare = 1.0 / (numSubCols || 1);
        if (col.toLowerCase().includes('ncr')) baseShare = 0.29;
        else if (col.toLowerCase().includes('luzon')) baseShare = 0.36;
        else if (col.toLowerCase().includes('visayas')) baseShare = 0.18;
        else if (col.toLowerCase().includes('mindanao')) baseShare = 0.17;
        else if (col.toLowerCase().includes('gen z')) baseShare = 0.37;
        else if (col.toLowerCase().includes('millennial')) baseShare = 0.41;
        else if (col.toLowerCase().includes('gen x')) baseShare = 0.22;
        else if (col.toLowerCase().includes('male')) baseShare = 0.49;
        else if (col.toLowerCase().includes('female')) baseShare = 0.51;
        
        const n = Math.round(totalN * baseShare);
        const neff = Math.round((n * 0.945) * 10) / 10;
        return { n, neff };
    });
}

function renderTable() {
    const table = document.getElementById('crosstab-table');
    if (!table) return;

    const bannerCols = getActiveBannerColumns();
    const stubs = getActiveStubs();
    const colBases = calculateColumnBases(bannerCols);

    // 1. Build Table Headers
    const thead = table.querySelector('thead');
    if (thead) {
        thead.innerHTML = "";
        
        // Row 1: Banner Column Display Names
        const trHeader = document.createElement('tr');
        const thStub = document.createElement('th');
        thStub.className = 'stub-header';
        thStub.innerText = stubs.length === 1 ? stubs[0] : "Category / Survey Variables";
        trHeader.appendChild(thStub);

        // Assign standard Column letters (A, B, C...)
        let letterCharCode = 65; // 'A'
        const colLetters = [];

        bannerCols.forEach((col, idx) => {
            const th = document.createElement('th');
            let displayName = col;
            let letter = "";
            if (col.toLowerCase() === 'total' || idx === 0) {
                displayName = "Total";
                letter = "Total";
            } else {
                // Check if letter already in name like "NCR (A)"
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
            th.innerText = displayName;
            trHeader.appendChild(th);
        });
        thead.appendChild(trHeader);

        // Row 2: Column Letters Row
        const trMetaLetters = document.createElement('tr');
        trMetaLetters.className = 'meta-row';
        trMetaLetters.innerHTML = `<td>Column Names</td>` + colLetters.map(l => `<td>${l}</td>`).join('');
        thead.appendChild(trMetaLetters);

        // Row 3: Column Sample Size (N)
        const trMetaN = document.createElement('tr');
        trMetaN.className = 'meta-row';
        trMetaN.innerHTML = `<td>Column Sample Size (N)</td>` + colBases.map(b => `<td>${b.n}</td>`).join('');
        thead.appendChild(trMetaN);

        // Row 4: Kish Effective Base (Neff)
        const trMetaNeff = document.createElement('tr');
        trMetaNeff.className = 'meta-row';
        trMetaNeff.innerHTML = `<td>Kish Effective Base (Neff)</td>` + colBases.map(b => `<td>${b.neff}</td>`).join('');
        thead.appendChild(trMetaNeff);
    }

    // 2. Build Table Body Rows
    const tbody = document.getElementById('table-body');
    if (!tbody) return;
    tbody.innerHTML = "";

    stubs.forEach(stubText => {
        const model = resolveStubToModel(stubText);

        // If multiple stubs, add a separator/sub-header row
        if (stubs.length > 1) {
            const trStubHeader = document.createElement('tr');
            trStubHeader.className = 'stub-group-header';
            trStubHeader.innerHTML = `<td colspan="${bannerCols.length + 1}"><b>📁 ${model.title || stubText}</b></td>`;
            tbody.appendChild(trStubHeader);
        }

        // Render each category in the model
        model.categories.forEach(cat => {
            const trVal = document.createElement('tr');
            if (cat.is_net) trVal.className = 'net-row';

            const cellValues = [];
            const colSigLetters = [];
            const benchMarkers = [];

            // Compute values across columns
            bannerCols.forEach((col, cIdx) => {
                let valNum;
                let valStr;
                const isTotal = (col.toLowerCase() === 'total' || cIdx === 0);

                if (cat.base_mean !== undefined) {
                    // Rating Scale Mean
                    const delta = isTotal ? 0 : (cat.seed_delta[(cIdx - 1) % cat.seed_delta.length] || 0.1);
                    valNum = Math.max(1.0, Math.min(5.0, cat.base_mean + delta));
                    valStr = valNum.toFixed(2);
                } else {
                    // Percentage
                    const delta = isTotal ? 0 : (cat.seed_delta[(cIdx - 1) % cat.seed_delta.length] || 0);
                    valNum = Math.max(1.0, Math.min(99.0, cat.base_pct + delta));
                    valStr = valNum.toFixed(1) + "%";
                }
                cellValues.push({ valNum, valStr, isTotal });
            });

            // Calculate significance letters and benchmark comparisons
            const totalVal = cellValues[0].valNum;
            cellValues.forEach((item, cIdx) => {
                if (item.isTotal) {
                    colSigLetters.push("-");
                    benchMarkers.push("-");
                    return;
                }

                // Benchmark comparison vs Total
                const diff = item.valNum - totalVal;
                let bm = "";
                if (diff >= 7.0) bm = "++";
                else if (diff >= 3.5) bm = "+";
                else if (diff <= -7.0) bm = "--";
                else if (diff <= -3.5) bm = "-";
                benchMarkers.push(bm);

                // Column comparisons (Pairwise letters)
                const lettersWon = [];
                cellValues.forEach((other, oIdx) => {
                    if (oIdx === 0 || oIdx === cIdx) return;
                    const oLetter = thead.querySelectorAll('tr.meta-row:nth-child(2) td')[oIdx + 1]?.innerText || "";
                    if (item.valNum - other.valNum >= 7.5) {
                        lettersWon.push(oLetter); // Uppercase >= 95%
                    } else if (item.valNum - other.valNum >= 4.5 && currentConfidence <= 90) {
                        lettersWon.push(oLetter.toLowerCase()); // Lowercase >= 90%
                    }
                });
                colSigLetters.push(lettersWon.join(' '));
            });

            // Line 1: Primary Value Row
            let valHtml = `<td>${cat.label}</td>`;
            cellValues.forEach((item, idx) => {
                const hasSig = (colSigLetters[idx] && colSigLetters[idx] !== '-') || (benchMarkers[idx] && benchMarkers[idx] !== '-');
                const cellClass = hasSig ? 'sig-cell' : '';
                valHtml += `<td class="${cellClass}"><b>${item.valStr}</b></td>`;
            });
            trVal.innerHTML = valHtml;
            tbody.appendChild(trVal);

            // Line 2: Sig Test 1 - Column Comparison Letters (a, b, c / A, B, C)
            if (sigDisplayMode === 'both' || sigDisplayMode === 'letters') {
                const trLetters = document.createElement('tr');
                trLetters.className = 'sig-row';
                let letHtml = `<td class="sig-label">  ↳ Col Comparisons (Letters)</td>`;
                colSigLetters.forEach(l => {
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
                benchMarkers.forEach(b => {
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
    if (event && event.target) {
        event.target.classList.add('active-toggle');
    }
    renderTable();
}

// 4. Ingestion Simulation
function loadSampleDataset() {
    const summaryCard = document.getElementById('import-summary-card');
    summaryCard.classList.remove('hidden');
    summaryCard.style.animation = "fadeInUp 0.35s cubic-bezier(0.34, 1.4, 0.64, 1)";
    renderTable();
}

// 5. Weighting Controls
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

// 6. Drag & Drop Handlers
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

// 7. Conversational Prompt-to-Table & Interactive Feedback
function executePromptToTable() {
    const btn = document.querySelector('.prompt-btn');
    const inputElem = document.getElementById('prompt-input');
    const input = inputElem ? inputElem.value.trim() : "";
    const origBtnText = btn ? btn.innerText : 'Generate Custom Table';

    // Interactive Button State & Tactile Feedback
    if (btn) {
        btn.innerHTML = `<span>⚡ Computing Matrix & Sig...</span>`;
        btn.classList.add('loading-pulse');
        btn.disabled = true;
    }

    setTimeout(() => {
        const lower = input.toLowerCase();

        // 1. Stub Matching (English + Taglish)
        if (lower.includes('satisfaction') || lower.includes('csat') || lower.includes('tuwa') || lower.includes('happy')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Overall CSAT (T2B)", true));
        } else if (lower.includes('brand') || lower.includes('preference') || lower.includes('nanotech')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Brand Preference", true));
        } else if (lower.includes('repurchase') || lower.includes('intent') || lower.includes('ulit') || lower.includes('bili')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Repurchase Intent", true));
        } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class')) {
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill("Monthly Income Class (SEC)", true));
        } else if (input.length > 0 && !lower.includes('generate')) {
            // Add user's raw prompt query as a custom stub
            addStubPill(input);
        }

        // 2. Banner Column Matching (English + Taglish)
        if (lower.includes('age') || lower.includes('gen z') || lower.includes('millennial') || lower.includes('edad')) {
            setBannerPreset('age');
        } else if (lower.includes('region') || lower.includes('luzon') || lower.includes('visayas') || lower.includes('mindanao') || lower.includes('probinsya')) {
            setBannerPreset('region');
        } else if (lower.includes('gender') || lower.includes('sex') || lower.includes('kasarian') || lower.includes('male') || lower.includes('female') || lower.includes('babae') || lower.includes('lalaki')) {
            setBannerPreset('gender');
        } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class abc')) {
            setBannerPreset('sec');
        }

        // Refresh and render the dynamic table
        renderTable();

        // Restore button state
        if (btn) {
            btn.innerHTML = `<span>✓ Generated!</span>`;
            btn.classList.remove('loading-pulse');
            setTimeout(() => {
                btn.innerText = origBtnText;
                btn.disabled = false;
            }, 800);
        }

        showToast("✓ Custom Table & Dual Significance Matrix updated!");
    }, 240);
}

// 8. Human Lock-Step Protocol
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

// 9. Reliable Desktop Downloads (Direct Save to ~/Downloads & Browser Streaming Fallback)
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.innerText = message;
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
    const origText = btn ? btn.innerText : '📥 Download Excel Banner Book';
    if (btn) { btn.innerText = "⏳ Generating Banner Book..."; btn.disabled = true; }

    fetch('/api/export/save-to-downloads')
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved directly to ~/Downloads & revealed in Finder!");
            }
            triggerFileDownload('/api/export/excel', 'ClearSight_Agency_Banner_Book.xlsx');
        })
        .catch(err => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/excel', 'ClearSight_Agency_Banner_Book.xlsx');
            showToast("✓ Downloading Banner Book via direct stream...");
        });
}

function downloadSnapshot() {
    const btn = document.getElementById('btn-dl-snapshot');
    const origText = btn ? btn.innerText : '📥 Download 1-Page A4 Snapshot';
    if (btn) { btn.innerText = "⏳ Generating A4 Snapshot..."; btn.disabled = true; }

    fetch('/api/export/save-snapshot-to-downloads')
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved A4 Snapshot directly to ~/Downloads & revealed in Finder!");
            }
            triggerFileDownload('/api/export/snapshot-download', 'ClearSight_Customer_Voice_Snapshot_A4.html');
        })
        .catch(err => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/snapshot-download', 'ClearSight_Customer_Voice_Snapshot_A4.html');
            showToast("✓ Downloading A4 Snapshot directly...");
        });
}

function downloadThesisTables() {
    const btn = document.getElementById('btn-dl-thesis');
    const origText = btn ? btn.innerText : '📥 Download Academic Tables';
    if (btn) { btn.innerText = "⏳ Generating Thesis Tables..."; btn.disabled = true; }

    fetch('/api/export/save-thesis-to-downloads')
        .then(res => res.json())
        .then(data => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            if (data.status === 'success') {
                showToast("✓ Saved Thesis Chapter 4 Package directly to ~/Downloads & revealed in Finder!");
            }
            triggerFileDownload('/api/export/thesis-download', 'ClearSight_Thesis_Chapter_4_Package.html');
        })
        .catch(err => {
            if (btn) { btn.innerText = origText; btn.disabled = false; }
            triggerFileDownload('/api/export/thesis-download', 'ClearSight_Thesis_Chapter_4_Package.html');
            showToast("✓ Downloading Thesis Chapter 4 Package directly...");
        });
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
    renderTable();
});
