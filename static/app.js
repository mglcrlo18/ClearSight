// ClearSight Analytics - Frontend Interaction Engine
// Fully connected to Localhost Analytical Server (Zero-Cloud Ingestion, Real Raking & Dual Significance)

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

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
    if (stepNum === 3) {
        loadTaglishCoding();
    }
    if (stepNum === 4) {
        const snapshotFrame = document.getElementById('snapshot-frame');
        if (snapshotFrame) {
            snapshotFrame.src = '/preview-snapshot?t=' + Date.now();
        }
    }
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
                resetTraysForDataset(data);
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

// P5-06: after an upload, replace the demo stub/banners (Q1: Brand Preference, NCR, Balance Luzon...)
// with columns that exist in the new file, so the first table is real instead of "Column not found".
function resetTraysForDataset(data) {
    const schema = (data && data.schema) || {};
    const cols = Object.keys(schema).filter(c => !c.startsWith('__'));
    const stub = cols.find(c => schema[c].type === 'rating_scale') ||
                 cols.find(c => schema[c].type === 'single_select');
    const banner = cols.find(c => c !== stub && schema[c].type === 'single_select' &&
                 Array.isArray(schema[c].categories) && schema[c].categories.length >= 2 && schema[c].categories.length <= 6);
    const stubTray = document.getElementById('stub-tray');
    if (stubTray && stub) {
        stubTray.replaceChildren(createPill(stub, true));
    }
    const bannerTray = document.getElementById('banner-tray');
    if (bannerTray) {
        bannerTray.replaceChildren(createPill('Total', false));
        if (banner) {
            schema[banner].categories.forEach(cat => bannerTray.appendChild(createPill(String(cat), false)));
        }
        refreshBannerPillLabels();
    }
}

function loadSampleDataset() {
    showToast("⏳ Loading bundled Philippine Consumer Survey...");
    fetch('/api/load-sample', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                loadedDatasetInfo = data;
                applyIngestedSummary(data);
                resetTraysForDataset(data);
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
    if (mDisp) mDisp.innerText = multiCount;
    const sDisp = document.getElementById('detected-scales');
    if (sDisp) sDisp.innerText = scaleCount;
    const oDisp = document.getElementById('detected-open');
    if (oDisp) oDisp.innerText = openCount;

    if (data.schema) {
        updateVariableDrawerFromSchema(data.schema, data.columns);
    }
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

    const schema = (loadedDatasetInfo && loadedDatasetInfo.schema) || {};
    const payload = { trim_percentile: trimVal };

    // If dataset has no 'Region', look for categorical demographics like Gender or Distribution Site (CS-N04)
    if (!schema['Region']) {
        const fallbackCol = Object.keys(schema).find(c => 
            !c.startsWith('__') && 
            schema[c].type === 'single_select' && 
            schema[c].categories && 
            schema[c].categories.length >= 2 && 
            schema[c].categories.length <= 10
        );
        if (fallbackCol) {
            const targets = {};
            const cats = schema[fallbackCol].categories;
            const equalShare = parseFloat((1.0 / cats.length).toFixed(4));
            targets[fallbackCol] = {};
            cats.forEach(c => targets[fallbackCol][c] = equalShare);
            payload.targets = targets;
        }
    }

    fetch('/api/weight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
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
    fetch('/api/hygiene-filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filter_straight_liners: isStraight,
            filter_speeders: isSpeeder
        })
    })
    .then(res => res.json())
    .then(data => {
        showToast(`Active sample: ${data.active_respondents} of ${data.total_respondents} records.`);
        renderTable();
    })
    .catch(() => {
        showToast(`Hygiene rules updated: Straight-liners [${isStraight ? 'ON' : 'OFF'}], Speeders [${isSpeeder ? 'ON' : 'OFF'}]`);
    });
}

// 4. Banner and Stub Tray Helper Functions with Unlimited Columns & Category Expansion

function stripColumnLetter(name) {
    if (!name) return '';
    return name.replace(/\s*\([A-Z0-9]+\)\s*$/, '').trim();
}

function getColumnLetter(colIndex) {
    // 1 -> A, 2 -> B, ... 26 -> Z, 27 -> AA, 28 -> AB, ...
    let letter = '';
    let temp = colIndex;
    while (temp > 0) {
        let rem = (temp - 1) % 26;
        letter = String.fromCharCode(65 + rem) + letter;
        temp = Math.floor((temp - 1) / 26);
    }
    return letter;
}

const KNOWN_BANNER_CATEGORIES = {
    region: {
        keys: ['region', 'geography', 'geographic', 'probinsya', 'luzon', 'visayas', 'mindanao', 'ncr'],
        columns: ['NCR', 'Balance Luzon', 'Visayas', 'Mindanao']
    },
    age: {
        keys: ['age', 'age generation', 'generation', 'edad', 'gen z', 'millennial', 'gen x'],
        columns: ['Gen Z (18–27)', 'Millennials (28–43)', 'Gen X (44–59)']
    },
    gender: {
        keys: ['gender', 'sex', 'kasarian', 'gender (male, female)', 'male', 'female'],
        columns: ['Male', 'Female']
    },
    sec: {
        keys: ['sec', 'income', 'socioeconomic', 'socioeconomic class', 'monthly income', 'monthly income class', 'class abc', 'class d', 'class e'],
        columns: ['Class ABC', 'Class D', 'Class E']
    },
    brand: {
        keys: ['brand', 'brand preference', 'brands', 'brand option'],
        columns: ['Brand A (Premium Nanotech)', 'Brand B (Standard Market)', 'Brand C (Bio-Oil Formulation)', 'Brand D (Local Artisan Batch)']
    },
    csat: {
        keys: ['csat', 'satisfaction', 'overall csat', 'customer satisfaction'],
        columns: ['5 - Very Satisfied', '4 - Somewhat Satisfied', '3 - Neutral', '1-2 - Dissatisfied']
    },
    repurchase: {
        keys: ['repurchase', 'repurchase intent', 'intent', 'intent to repurchase'],
        columns: ['Definitely Will (5)', 'Probably Will (4)', 'Might or Might Not (3)', 'Unlikely (1-2)']
    }
};

function resolveBannerCategory(text) {
    if (!text) return [];
    const clean = stripColumnLetter(text).trim();
    const lower = clean.toLowerCase();

    // Check if uploaded dataset schema defines discrete categories for this column
    if (loadedDatasetInfo && loadedDatasetInfo.schema) {
        for (const [colName, colMeta] of Object.entries(loadedDatasetInfo.schema)) {
            const cleanCol = colName.toLowerCase().replace(/_/g, ' ');
            if (colName.toLowerCase() === lower || cleanCol === lower) {
                if (colMeta.type === 'single_select' && Array.isArray(colMeta.categories) && colMeta.categories.length > 0) {
                    return colMeta.categories.slice(0, 25);
                }
                if (colMeta.type === 'multi_select' && Array.isArray(colMeta.options) && colMeta.options.length > 0) {
                    return colMeta.options.slice(0, 25);
                }
            }
        }
    }

    // Check predefined survey dictionary categories
    for (const cat of Object.values(KNOWN_BANNER_CATEGORIES)) {
        if (cat.keys.some(k => k === lower || lower.includes(k))) {
            return [...cat.columns];
        }
    }

    // Single custom item or specific column
    return [clean];
}

function getActiveBannerColumns() {
    const bannerTray = document.getElementById('banner-tray');
    if (!bannerTray) return ["Total", "NCR", "Balance Luzon", "Visayas", "Mindanao"];
    const pills = Array.from(bannerTray.querySelectorAll('.tag-pill'));
    if (pills.length === 0) return ["Total"];
    return pills.map(p => {
        const raw = p.getAttribute('data-name') || p.innerText.replace('×', '').trim();
        return stripColumnLetter(raw);
    }).filter(Boolean);
}

function getActiveStubs() {
    const stubTray = document.getElementById('stub-tray');
    if (!stubTray) return [];
    const pills = Array.from(stubTray.querySelectorAll('.tag-pill'));
    if (pills.length === 0) return [];
    return pills.map(p => {
        const name = p.getAttribute('data-name');
        if (name) return name.trim();
        return p.childNodes[0].nodeValue ? p.childNodes[0].nodeValue.trim() : p.innerText.replace('×', '').trim();
    }).filter(Boolean);
}

function createPill(text, isStub = false) {
    const cleanText = isStub ? text.trim() : stripColumnLetter(text.trim());
    const pill = document.createElement('span');
    pill.className = 'tag-pill';
    pill.setAttribute('data-name', cleanText);

    const textSpan = document.createElement('span');
    textSpan.className = 'pill-label';
    textSpan.textContent = cleanText + " ";
    pill.appendChild(textSpan);

    const removeBtn = document.createElement('span');
    removeBtn.className = 'pill-remove';
    removeBtn.textContent = '×';
    removeBtn.onclick = function(e) {
        if (isStub) removeStubPill(e, cleanText);
        else removeBannerPill(e, cleanText);
    };
    pill.appendChild(removeBtn);
    return pill;
}

function refreshBannerPillLabels() {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    const pills = Array.from(tray.querySelectorAll('.tag-pill'));
    let colLetterIdx = 1;

    pills.forEach((p, idx) => {
        const rawName = p.getAttribute('data-name') || p.innerText;
        const cleanName = stripColumnLetter(rawName);
        const labelSpan = p.querySelector('.pill-label');
        if (cleanName.toLowerCase() === 'total' || idx === 0) {
            p.setAttribute('data-name', 'Total');
            if (labelSpan) labelSpan.textContent = 'Total';
        } else {
            const letter = getColumnLetter(colLetterIdx++);
            p.setAttribute('data-name', cleanName);
            if (labelSpan) labelSpan.textContent = `${cleanName} (${letter})`;
        }
    });

    const badge = document.getElementById('col-count-badge');
    if (badge) {
        badge.textContent = `${pills.length} Column${pills.length === 1 ? '' : 's'}`;
    }
}

function addBannerPill(text, shouldRender = true) {
    if (!text || !text.trim()) return 0;
    const rawText = text.trim();
    const tray = document.getElementById('banner-tray');
    if (!tray) return 0;

    // Expand category into sub-items if matching
    const items = resolveBannerCategory(rawText);
    let addedCount = 0;

    items.forEach(item => {
        const cleanItem = stripColumnLetter(item);
        const existing = Array.from(tray.querySelectorAll('.tag-pill')).map(p => stripColumnLetter(p.getAttribute('data-name') || p.innerText));
        if (!existing.includes(cleanItem)) {
            tray.appendChild(createPill(cleanItem, false));
            addedCount++;
        }
    });

    refreshBannerPillLabels();
    if (shouldRender) renderTable();
    return addedCount;
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
    const cleanTarget = stripColumnLetter(name);
    const pills = Array.from(tray.querySelectorAll('.tag-pill'));
    pills.forEach(p => {
        const pName = stripColumnLetter(p.getAttribute('data-name') || p.innerText);
        if (pName === cleanTarget) tray.removeChild(p);
    });
    if (tray.querySelectorAll('.tag-pill').length === 0) {
        tray.appendChild(createPill("Total", false));
    }
    refreshBannerPillLabels();
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
    renderTable();
}

function addBannerFromInput() {
    const input = document.getElementById('banner-input');
    if (!input || !input.value.trim()) return;
    const parts = input.value.split(',').map(s => s.trim()).filter(Boolean);
    let totalAdded = 0;
    parts.forEach(part => {
        totalAdded += addBannerPill(part, false);
    });
    input.value = "";
    refreshBannerPillLabels();
    renderTable();
    showToast(`✓ Added ${totalAdded} banner column(s)`);
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

function addBannerPreset(type) {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;

    if (tray.querySelectorAll('.tag-pill').length === 0) {
        tray.appendChild(createPill("Total", false));
    }

    let targetItems = [];
    if (type === 'region') {
        targetItems = ["NCR", "Balance Luzon", "Visayas", "Mindanao"];
    } else if (type === 'age') {
        targetItems = ["Gen Z (18–27)", "Millennials (28–43)", "Gen X (44–59)"];
    } else if (type === 'gender') {
        targetItems = ["Male", "Female"];
    } else if (type === 'sec') {
        targetItems = ["Class ABC", "Class D", "Class E"];
    }

    targetItems.forEach(item => {
        const cleanItem = stripColumnLetter(item);
        const existing = Array.from(tray.querySelectorAll('.tag-pill')).map(p => stripColumnLetter(p.getAttribute('data-name') || p.innerText));
        if (!existing.includes(cleanItem)) {
            tray.appendChild(createPill(cleanItem, false));
        }
    });

    refreshBannerPillLabels();
    renderTable();
    showToast(`✓ Added ${type.toUpperCase()} banner columns`);
}

function setBannerPreset(type) {
    addBannerPreset(type);
}

function addAllDemographicsPreset() {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Total", false));

    const allItems = [
        "NCR", "Balance Luzon", "Visayas", "Mindanao",
        "Gen Z (18–27)", "Millennials (28–43)", "Gen X (44–59)",
        "Male", "Female",
        "Class ABC", "Class D", "Class E"
    ];

    allItems.forEach(item => tray.appendChild(createPill(item, false)));
    refreshBannerPillLabels();
    renderTable();
    showToast("✓ Stacked all 12 Demographic Banner Columns!");
}

function clearBanners() {
    const tray = document.getElementById('banner-tray');
    if (!tray) return;
    tray.innerHTML = "";
    tray.appendChild(createPill("Total", false));
    refreshBannerPillLabels();
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
    renderTable();
    showToast("Stubs cleared");
}

// 5. Survey Dictionary Models
const SURVEY_DICTIONARY = {
    brand_preference: {
        title: "Q1: Brand Preference (Multi-Select)",
        categories: [
            { label: "NET: Any Brand Mentioned", is_net: true, base_pct: 94.2 },
            { label: "Brand A (Premium Nanotech)", is_net: false, base_pct: 42.5 },
            { label: "Brand B (Standard Market)", is_net: false, base_pct: 31.1 },
            { label: "Brand C (Bio-Oil Formulation)", is_net: false, base_pct: 26.4 },
            { label: "Brand D (Local Artisan Batch)", is_net: false, base_pct: 18.2 }
        ]
    },
    csat: {
        title: "Q2: Overall Customer Satisfaction (CSAT)",
        categories: [
            { label: "NET: Top-2-Box (Satisfied/Very Satisfied)", is_net: true, base_pct: 84.2 },
            { label: "5 - Very Satisfied", is_net: false, base_pct: 48.5 },
            { label: "4 - Somewhat Satisfied", is_net: false, base_pct: 35.7 },
            { label: "3 - Neutral / Neither", is_net: false, base_pct: 10.2 },
            { label: "1-2 - Dissatisfied", is_net: false, base_pct: 5.6 },
            { label: "Mean Rating (1-5 Scale)", is_net: true, base_mean: 4.12 }
        ]
    },
    repurchase: {
        title: "Q3: Repurchase Intent (1-5 Likert)",
        categories: [
            { label: "NET: High Repurchase Intent (Top-2-Box)", is_net: true, base_pct: 78.5 },
            { label: "Definitely Will Repurchase (5)", is_net: false, base_pct: 44.2 },
            { label: "Probably Will Repurchase (4)", is_net: false, base_pct: 34.3 },
            { label: "Might or Might Not (3)", is_net: false, base_pct: 14.1 },
            { label: "Unlikely to Repurchase (1-2)", is_net: false, base_pct: 7.4 },
            { label: "Mean Intent Score (1-5 Scale)", is_net: true, base_mean: 4.02 }
        ]
    },
    age: {
        title: "Demographics: Age Generation",
        categories: [
            { label: "Generation Z (18–27)", is_net: false, base_pct: 37.4 },
            { label: "Millennials (28–43)", is_net: false, base_pct: 40.8 },
            { label: "Generation X (44–59)", is_net: false, base_pct: 21.8 }
        ]
    },
    region: {
        title: "Demographics: Geographic Region",
        categories: [
            { label: "National Capital Region (NCR)", is_net: false, base_pct: 29.1 },
            { label: "Balance Luzon", is_net: false, base_pct: 36.4 },
            { label: "Visayas", is_net: false, base_pct: 17.5 },
            { label: "Mindanao", is_net: false, base_pct: 17.0 }
        ]
    },
    sec: {
        title: "Demographics: Socioeconomic Class (SEC)",
        categories: [
            { label: "Class ABC (Upper to Upper-Middle)", is_net: false, base_pct: 19.9 },
            { label: "Class D (Middle to Lower-Middle)", is_net: false, base_pct: 59.7 },
            { label: "Class E (Low Income / Subsistence)", is_net: false, base_pct: 20.4 }
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
            { label: `NET: Positive (${stubText})`, is_net: true, base_pct: 76.5 },
            { label: "High Rating / Favorable", is_net: false, base_pct: 45.0 },
            { label: "Moderate / Neutral", is_net: false, base_pct: 31.5 },
            { label: "Low / Unfavorable", is_net: false, base_pct: 23.5 }
        ]
    };
}

function hashString(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return hash;
}

function calculateColumnBases(columns) {
    const totalN = loadedDatasetInfo ? (loadedDatasetInfo.total_respondents || 412) : 412;
    const effRatio = 0.945;
    const totalNeff = Math.round(totalN * effRatio * 10) / 10;
    const numSubCols = Math.max(1, columns.length - 1);

    return columns.map((col, idx) => {
        const clean = stripColumnLetter(col).toLowerCase();
        if (clean === 'total' || idx === 0) {
            return { n: totalN, neff: totalNeff };
        }

        let share = 0.25;
        if (clean.includes('ncr') || clean.includes('manila')) share = 0.291;
        else if (clean.includes('luzon')) share = 0.364;
        else if (clean.includes('visayas')) share = 0.175;
        else if (clean.includes('mindanao')) share = 0.170;
        else if (clean.includes('gen z') || clean.includes('18–27') || clean.includes('18-27')) share = 0.374;
        else if (clean.includes('millennial') || clean.includes('28–43') || clean.includes('28-43')) share = 0.408;
        else if (clean.includes('gen x') || clean.includes('44–59') || clean.includes('44-59')) share = 0.218;
        else if (clean === 'male' || clean.startsWith('male')) share = 0.490;
        else if (clean === 'female' || clean.startsWith('female')) share = 0.510;
        else if (clean.includes('class abc') || clean.includes('abc')) share = 0.199;
        else if (clean.includes('class d') || clean === 'd') share = 0.597;
        else if (clean.includes('class e') || clean === 'e') share = 0.204;
        else if (clean.includes('brand a')) share = 0.425;
        else if (clean.includes('brand b')) share = 0.311;
        else if (clean.includes('brand c')) share = 0.264;
        else if (clean.includes('brand d')) share = 0.182;
        else if (clean.includes('5') || clean.includes('very satisfied') || clean.includes('definitely')) share = 0.485;
        else if (clean.includes('4') || clean.includes('somewhat satisfied') || clean.includes('probably')) share = 0.357;
        else if (clean.includes('3') || clean.includes('neutral') || clean.includes('might')) share = 0.141;
        else if (clean.includes('1') || clean.includes('2') || clean.includes('dissatisfied') || clean.includes('unlikely')) share = 0.074;
        else {
            const h = Math.abs(hashString(clean)) % 100;
            share = Math.max(0.08, Math.min(0.45, 1.0 / numSubCols + (h - 50) / 500.0));
        }

        const n = Math.max(15, Math.round(totalN * share));
        const neff = Math.round(n * effRatio * 10) / 10;
        return { n, neff };
    });
}

function getColumnDelta(colName, categoryLabel, isMean) {
    const col = stripColumnLetter(colName).toLowerCase();
    const cat = categoryLabel.toLowerCase();

    // Regional deltas
    if (col.includes('ncr') || col.includes('manila')) {
        if (cat.includes('brand a') || cat.includes('nanotech')) return isMean ? 0.38 : 12.5;
        if (cat.includes('brand b')) return isMean ? -0.05 : -2.8;
        if (cat.includes('brand c')) return isMean ? -0.25 : -9.7;
        if (cat.includes('brand d')) return isMean ? -0.10 : -3.2;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? 0.35 : 7.5;
        return isMean ? 0.15 : 4.0;
    }
    if (col.includes('luzon')) {
        if (cat.includes('brand a')) return isMean ? -0.12 : -4.5;
        if (cat.includes('brand b')) return isMean ? 0.08 : 2.4;
        if (cat.includes('brand c')) return isMean ? 0.06 : 2.1;
        if (cat.includes('brand d')) return isMean ? 0.05 : 1.8;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? -0.06 : -2.2;
        return isMean ? -0.05 : -1.5;
    }
    if (col.includes('visayas')) {
        if (cat.includes('brand a')) return isMean ? -0.18 : -6.4;
        if (cat.includes('brand b')) return isMean ? -0.02 : -0.5;
        if (cat.includes('brand c')) return isMean ? 0.22 : 6.9;
        if (cat.includes('brand d')) return isMean ? 0.12 : 4.2;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? -0.12 : -3.7;
        return isMean ? 0.08 : 2.5;
    }
    if (col.includes('mindanao')) {
        if (cat.includes('brand a')) return isMean ? -0.08 : -2.3;
        if (cat.includes('brand b')) return isMean ? 0.03 : 0.9;
        if (cat.includes('brand c')) return isMean ? 0.04 : 1.4;
        if (cat.includes('brand d')) return isMean ? -0.09 : -2.8;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? 0.02 : 0.5;
        return isMean ? -0.02 : -0.8;
    }

    // Age Groups
    if (col.includes('gen z') || col.includes('18–27') || col.includes('18-27')) {
        if (cat.includes('brand a') || cat.includes('nanotech')) return isMean ? 0.42 : 14.8;
        if (cat.includes('brand b')) return isMean ? -0.15 : -5.4;
        if (cat.includes('brand c')) return isMean ? -0.12 : -4.2;
        if (cat.includes('brand d')) return isMean ? 0.25 : 8.6;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? 0.28 : 8.5;
        return isMean ? 0.20 : 6.5;
    }
    if (col.includes('millennial') || col.includes('28–43') || col.includes('28-43')) {
        if (cat.includes('brand a')) return isMean ? 0.06 : 2.2;
        if (cat.includes('brand b')) return isMean ? 0.10 : 3.5;
        if (cat.includes('brand c')) return isMean ? 0.05 : 1.8;
        if (cat.includes('brand d')) return isMean ? -0.04 : -1.5;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? 0.05 : 1.8;
        return isMean ? 0.03 : 1.0;
    }
    if (col.includes('gen x') || col.includes('44–59') || col.includes('44-59')) {
        if (cat.includes('brand a')) return isMean ? -0.45 : -16.5;
        if (cat.includes('brand b')) return isMean ? 0.24 : 8.5;
        if (cat.includes('brand c')) return isMean ? 0.20 : 7.2;
        if (cat.includes('brand d')) return isMean ? -0.14 : -5.0;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? -0.24 : -8.2;
        return isMean ? -0.18 : -6.0;
    }

    // Gender Groups
    if (col === 'male' || col.startsWith('male')) {
        if (cat.includes('brand a')) return isMean ? 0.12 : 4.5;
        if (cat.includes('brand b')) return isMean ? 0.06 : 2.0;
        if (cat.includes('brand c')) return isMean ? -0.10 : -3.6;
        if (cat.includes('brand d')) return isMean ? 0.04 : 1.5;
        return isMean ? 0.04 : 1.5;
    }
    if (col === 'female' || col.startsWith('female')) {
        if (cat.includes('brand a')) return isMean ? -0.11 : -4.2;
        if (cat.includes('brand b')) return isMean ? -0.06 : -1.8;
        if (cat.includes('brand c')) return isMean ? 0.11 : 3.9;
        if (cat.includes('brand d')) return isMean ? -0.04 : -1.2;
        return isMean ? -0.04 : -1.4;
    }

    // Socioeconomic Class (SEC)
    if (col.includes('class abc') || col.includes('abc')) {
        if (cat.includes('brand a') || cat.includes('nanotech')) return isMean ? 0.45 : 16.2;
        if (cat.includes('brand b')) return isMean ? -0.22 : -7.8;
        if (cat.includes('brand c')) return isMean ? 0.09 : 3.2;
        if (cat.includes('brand d')) return isMean ? -0.08 : -2.8;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? 0.32 : 11.2;
        return isMean ? 0.25 : 8.0;
    }
    if (col.includes('class d') || col === 'd') {
        if (cat.includes('brand a')) return isMean ? -0.06 : -2.4;
        if (cat.includes('brand b')) return isMean ? 0.12 : 4.2;
        if (cat.includes('brand c')) return isMean ? 0.03 : 1.1;
        if (cat.includes('brand d')) return isMean ? 0.04 : 1.4;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? -0.04 : -1.5;
        return isMean ? 0.01 : 0.5;
    }
    if (col.includes('class e') || col === 'e') {
        if (cat.includes('brand a')) return isMean ? -0.32 : -11.5;
        if (cat.includes('brand b')) return isMean ? 0.18 : 6.5;
        if (cat.includes('brand c')) return isMean ? -0.08 : -3.0;
        if (cat.includes('brand d')) return isMean ? 0.14 : 5.0;
        if (cat.includes('top-2-box') || cat.includes('satisfied') || cat.includes('repurchase')) return isMean ? -0.22 : -7.8;
        return isMean ? -0.15 : -5.5;
    }

    // Stable deterministic pseudo-random variance for any custom or external columns
    const hash = Math.abs(hashString(col + '_' + cat));
    const normalized = (hash % 1000) / 1000.0;
    if (isMean) {
        return (normalized * 0.5) - 0.25;
    } else {
        return (normalized * 22.0) - 11.0;
    }
}

let tabulationDebounceTimer = null;
function syncWithBackendTabulation(bannerCols, stubs) {
    if (tabulationDebounceTimer) clearTimeout(tabulationDebounceTimer);
    tabulationDebounceTimer = setTimeout(() => {
        fetch('/api/tabulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                banner_cols: bannerCols,
                stubs: stubs,
                confidence: currentConfidence,
                fdr_enabled: isFDREnabled
            })
        }).catch(() => {});
    }, 300);
}

function updateVariableDrawerFromSchema(schema, columns) {
    const listContainer = document.getElementById('variable-list');
    if (!listContainer || !schema || Object.keys(schema).length === 0) return;

    listContainer.innerHTML = '';

    Object.entries(schema).forEach(([colName, info]) => {
        if (info.type === 'empty' || colName.startsWith('__')) return;

        const card = document.createElement('div');
        card.className = 'var-card';
        card.setAttribute('draggable', 'true');
        card.setAttribute('data-var', colName);
        card.ondragstart = drag;

        let dotColor = 'blue';
        if (info.type === 'rating_scale') dotColor = 'green';
        else if (info.type === 'multi_select') dotColor = 'purple';
        else if (info.type === 'open_ended') dotColor = 'orange';

        const header = document.createElement('div');
        header.className = 'var-card-header';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'var-card-title';
        const dotSpan = document.createElement('span');
        dotSpan.className = `pill-dot ${dotColor}`;
        titleSpan.appendChild(dotSpan);
        titleSpan.appendChild(document.createTextNode(' ' + colName));
        header.appendChild(titleSpan);

        const actions = document.createElement('div');
        actions.className = 'var-actions';

        const btnCol = document.createElement('button');
        btnCol.type = 'button';
        btnCol.className = 'var-add-btn var-add-col';
        btnCol.textContent = '+ Col';
        btnCol.title = `Add all ${colName} categories to Banners`;
        btnCol.onclick = (e) => { e.stopPropagation(); addBannerPill(colName); };
        actions.appendChild(btnCol);

        const btnRow = document.createElement('button');
        btnRow.type = 'button';
        btnRow.className = 'var-add-btn var-add-row';
        btnRow.textContent = '+ Row';
        btnRow.title = `Add ${colName} as table Stub (Row)`;
        btnRow.onclick = (e) => { e.stopPropagation(); addStubPill(colName); };
        actions.appendChild(btnRow);

        header.appendChild(actions);
        card.appendChild(header);

        const categories = info.categories || info.sample || [];
        if (categories.length > 0) {
            const chipsRow = document.createElement('div');
            chipsRow.className = 'var-chips-row';
            categories.slice(0, 5).forEach(cat => {
                const chip = document.createElement('span');
                chip.className = 'var-chip';
                chip.textContent = String(cat).substring(0, 22);
                chip.onclick = (e) => { e.stopPropagation(); addBannerPill(String(cat)); };
                chipsRow.appendChild(chip);
            });
            card.appendChild(chipsRow);
        }

        listContainer.appendChild(card);
    });
}

// 6. Safe DOM-Based Table Rendering (Unlimited Columns & Collision-Free Dual Sig)
let currentTableData = null;
let isTabulating = false;

async function renderTable() {
    const table = document.getElementById('crosstab-table');
    if (!table) return;

    const bannerCols = getActiveBannerColumns();
    const stubs = getActiveStubs();

    if (!stubs || stubs.length === 0) {
        currentTableData = null;
        const thead = table.querySelector('thead');
        if (thead) thead.innerHTML = '';
        const tbody = document.getElementById('table-body');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="99" style="text-align:center; padding: 3.5rem 1.5rem; color: #64748B;">
                <div style="font-weight: 600; font-size: 1.05rem; margin-bottom: 0.5rem; color: #334155;">No Row Variable (Stub) Selected</div>
                <div style="font-size: 0.875rem; color: #64748B;">Click or drag a question from the Survey Variables drawer below, or type a stub name above.</div>
            </td></tr>`;
        }
        const anovaFootnote = document.getElementById('table-anova-note');
        if (anovaFootnote) anovaFootnote.style.display = 'none';
        return;
    }

    try {
        const response = await fetch('/api/tabulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                banner_cols: bannerCols,
                stubs: stubs,
                confidence: currentConfidence,
                fdr_enabled: isFDREnabled,
                metric: currentMetric
            })
        });

        if (!response.ok) return;
        const resData = await response.json();
        if (resData.status === 'success' && resData.table && resData.table.length > 0) {
            currentTableData = resData.table;
            renderTableFromData(resData.table);
        }
    } catch (err) {
        console.error("Tabulation fetch error:", err);
    }
}

function renderTableFromData(tables) {
    const table = document.getElementById('crosstab-table');
    if (!table || !tables || tables.length === 0) return;

    const t = tables[0];
    if (t.error) {
        const thead = table.querySelector('thead');
        if (thead) thead.innerHTML = '';
        const tbody = document.getElementById('table-body');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="99" style="text-align:center; padding: 2.5rem 1.5rem; color: #dc2626; font-weight: 500;">
                <div style="font-size: 1.05rem; margin-bottom: 0.35rem;">⚠ ${escapeHtml(t.error)}</div>
                <div style="font-size: 0.85rem; color: #64748B; font-weight: normal;">Please choose a variable from the Survey Variables drawer or check the spelling.</div>
            </td></tr>`;
        }
        const anovaFootnote = document.getElementById('table-anova-note');
        if (anovaFootnote) anovaFootnote.style.display = 'none';
        return;
    }
    const bannerCols = t.banner_cols || ['Total'];
    const colLetters = t.col_letters || ['Total'];
    const unweightedBases = t.unweighted_bases || [0];
    const weightedBases = t.weighted_bases || [0.0];
    const effectiveBases = t.effective_bases || [0.0];

    // Build thead
    const thead = table.querySelector('thead');
    if (thead) {
        thead.innerHTML = '';

        // Row 1: Header Titles
        const trHeader = document.createElement('tr');
        const thStub = document.createElement('th');
        thStub.className = 'stub-header';
        thStub.textContent = t.stub_label || 'Category / Survey Variables';
        trHeader.appendChild(thStub);

        bannerCols.forEach((col, idx) => {
            const th = document.createElement('th');
            th.textContent = col;
            if (t.small_base && t.small_base[idx]) {
                th.classList.add('small-base');
                th.title = 'Small base (Neff < 30)';
                th.textContent += ' *';
            }
            trHeader.appendChild(th);
        });
        thead.appendChild(trHeader);

        // Row 2: Column Letters
        const trLetters = document.createElement('tr');
        trLetters.className = 'meta-row';
        trLetters.appendChild(createTdText('Column Names'));
        colLetters.forEach(l => trLetters.appendChild(createTdText(l)));
        thead.appendChild(trLetters);

        // Row 3: Column Sample Size (N)
        const trN = document.createElement('tr');
        trN.className = 'meta-row';
        trN.appendChild(createTdText('Column Sample Size (N)'));
        unweightedBases.forEach(n => trN.appendChild(createTdText(String(n))));
        thead.appendChild(trN);

        // Row 4: Weighted Base (Nw)
        const trNw = document.createElement('tr');
        trNw.className = 'meta-row';
        trNw.appendChild(createTdText('Weighted Base (Nw)'));
        weightedBases.forEach(nw => trNw.appendChild(createTdText(typeof nw === 'number' ? nw.toFixed(1) : String(nw))));
        thead.appendChild(trNw);

        // Row 5: Kish Effective Base (Neff)
        const trNeff = document.createElement('tr');
        trNeff.className = 'meta-row';
        trNeff.appendChild(createTdText('Kish Effective Base (Neff)'));
        effectiveBases.forEach(ne => trNeff.appendChild(createTdText(typeof ne === 'number' ? ne.toFixed(1) : String(ne))));
        thead.appendChild(trNeff);
    }

    // Build tbody
    const tbody = document.getElementById('table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    tables.forEach(tbl => {
        if (tables.length > 1) {
            const trGroup = document.createElement('tr');
            trGroup.className = 'stub-group-header';
            const tdGroup = document.createElement('td');
            tdGroup.colSpan = (tbl.banner_cols || []).length + 1;
            tdGroup.textContent = `📁 ${tbl.title}`;
            trGroup.appendChild(tdGroup);
            tbody.appendChild(trGroup);
        }

        const rows = tbl.rows || [];
        rows.forEach(r => {
            const isNet = r.is_net;

            // Line 1: Values
            const trVal = document.createElement('tr');
            if (isNet) trVal.className = 'net-row';

            const tdLabel = document.createElement('td');
            tdLabel.className = isNet ? 'stub-cell net-label' : 'stub-cell';
            tdLabel.textContent = r.label;
            trVal.appendChild(tdLabel);

            (r.values || []).forEach(val => {
                const tdVal = document.createElement('td');
                tdVal.className = isNet ? 'val-cell net-val' : 'val-cell';
                tdVal.textContent = val;
                trVal.appendChild(tdVal);
            });
            tbody.appendChild(trVal);

            // Line 2: Column Comparison Letters
            if (sigDisplayMode === 'both' || sigDisplayMode === 'letters') {
                const trSig = document.createElement('tr');
                trSig.className = 'sig-row';
                const tdSigLbl = document.createElement('td');
                tdSigLbl.className = 'sig-label';
                tdSigLbl.textContent = '  ↳ Col Comparisons (Letters)';
                trSig.appendChild(tdSigLbl);

                (r.sig_letters || []).forEach(l => {
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
                    trSig.appendChild(td);
                });
                tbody.appendChild(trSig);
            }

            // Line 3: Benchmark vs Total (+/++, -/--)
            if (sigDisplayMode === 'both' || sigDisplayMode === 'bench') {
                const trBench = document.createElement('tr');
                trBench.className = 'sig-row';
                const tdBenchLbl = document.createElement('td');
                tdBenchLbl.className = 'sig-label';
                tdBenchLbl.textContent = '  ↳ vs. Total (+/++, -/--)';
                trBench.appendChild(tdBenchLbl);

                (r.sig_benchmarks || []).forEach(b => {
                    const td = document.createElement('td');
                    if (b && b !== '-') {
                        const span = document.createElement('span');
                        if (b === '++') span.className = 'benchmark-pos-heavy';
                        else if (b === '+') span.className = 'benchmark-pos';
                        else if (b === '--') span.className = 'benchmark-neg-heavy';
                        else if (b === '-') span.className = 'benchmark-neg';
                        span.textContent = b;
                        td.appendChild(span);
                    } else if (b === '-') {
                        const span = document.createElement('span');
                        span.style.color = '#94A3B8';
                        span.textContent = '-';
                        td.appendChild(span);
                    }
                    trBench.appendChild(td);
                });
                tbody.appendChild(trBench);
            }
        });
    });

    let anovaFootnote = document.getElementById('table-anova-note');
    if (!anovaFootnote) {
        anovaFootnote = document.createElement('div');
        anovaFootnote.id = 'table-anova-note';
        anovaFootnote.className = 'table-footnote';
        anovaFootnote.style.cssText = 'padding: 8px 12px; font-size: 0.85rem; color: #64748B; font-style: italic;';
        table.parentNode.insertBefore(anovaFootnote, table.nextSibling);
    }
    if (t.anova) {
        // P5-14: p is rounded to 4 dp server-side, so tiny p-values arrived as 0 and printed "p = 0".
        const pTxt = (Number(t.anova.p_val) < 0.0001) ? 'p < 0.0001' : `p = ${t.anova.p_val}`;
        const anovaKind = t.anova.weighted ? 'Weighted one-way ANOVA' : 'One-way ANOVA';
        anovaFootnote.textContent = `${anovaKind} F(${t.anova.df1}, ${t.anova.df2}) = ${t.anova.f_stat}, ${pTxt}`;
        anovaFootnote.style.display = 'block';
    } else {
        anovaFootnote.style.display = 'none';
    }
}

async function loadTaglishCoding() {
    const grid = document.getElementById('codeframe-grid');
    if (!grid) return;

    try {
        const res = await fetch('/api/code-open-ends', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!res.ok) {
            grid.innerHTML = '<div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: #dc2626; background: #FEF2F2; border-radius: 8px;"><b>Coding Notice:</b> Qualitative analysis failed or no open-ended column detected.</div>';
            return;
        }
        const data = await res.json();
        if (data.status === 'success' && data.codeframe) {
            renderTaglishCodeframe(data);
            if (data.coder === 'v2') {
                loadReviewQueue();
            }
        } else {
            grid.innerHTML = '<div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: #64748B;">No open-ended responses found to code.</div>';
        }
    } catch (err) {
        console.error("Taglish coding error:", err);
        grid.innerHTML = `<div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: #dc2626;">Error loading qualitative analysis: ${escapeHtml(err.message)}</div>`;
    }
}

function renderTaglishCodeframe(data) {
    const grid = document.getElementById('codeframe-grid');
    if (!grid) return;
    grid.innerHTML = '';

    const codeframe = data.codeframe || [];
    const total = data.total_analyzed || 0;

    const agreementElem = document.getElementById('agreement-score');
    if (agreementElem) {
        agreementElem.textContent = data.agreement
            ? `Observed agreement ${data.agreement.observed_agreement_pct}% on ${data.agreement.audited_count} reviewed answers (κ = ${data.agreement.cohens_kappa})`
            : 'Heuristic Qualitative Coder (Preview)';
    }

    codeframe.forEach(item => {
        const card = document.createElement('div');
        card.className = 'code-item';

        const titleDiv = document.createElement('div');
        titleDiv.className = 'code-title';

        const bTheme = document.createElement('b');
        bTheme.textContent = item.theme;

        const spanPct = document.createElement('span');
        spanPct.className = 'code-pct';
        spanPct.textContent = `${item.prevalence_pct.toFixed(1)}% (${item.count})`;

        titleDiv.appendChild(bTheme);
        titleDiv.appendChild(spanPct);
        card.appendChild(titleDiv);

        const quoteDiv = document.createElement('div');
        quoteDiv.className = 'code-quote';
        if (item.evidence_samples && item.evidence_samples.length > 0) {
            const s = item.evidence_samples[0];
            quoteDiv.textContent = `"${s.quote}" [Resp #${s.response_id}]`;
        } else {
            quoteDiv.textContent = 'No verbatims matching theme.';
        }
        card.appendChild(quoteDiv);

        grid.appendChild(card);
    });
}

// ---------------------------------------------------------------------------
// Coder v2 Needs-review queue. All server text is rendered with textContent /
// option.text (never innerHTML), so verbatims cannot inject markup (CWE-79).
// ---------------------------------------------------------------------------
async function loadReviewQueue() {
    const box = document.getElementById('coder-review');
    if (!box) return;
    try {
        const res = await fetch('/api/coder/review-queue');
        if (!res.ok) { box.hidden = true; return; }
        const data = await res.json();
        renderReviewQueue(box, data);
    } catch (err) {
        box.hidden = true;
    }
}

function renderReviewQueue(box, data) {
    box.replaceChildren();
    const items = (data && data.items) || [];
    if (!items.length) { box.hidden = true; return; }
    box.hidden = false;
    const head = document.createElement('div');
    head.className = 'coder-review-head';
    head.textContent = `Needs review: ${data.count} answer(s). Pick the right theme and sentiment; corrections stay on this computer and teach the coder.`;
    box.appendChild(head);
    const options = data.options || [];
    items.slice(0, 20).forEach(item => {
        const row = document.createElement('div');
        row.className = 'coder-review-row';
        const q = document.createElement('div');
        q.className = 'coder-review-text';
        q.textContent = `#${item.response_id}: "${item.text}"`;
        const meta = document.createElement('div');
        meta.className = 'coder-review-meta';
        meta.textContent = `Coder: ${(item.themes || []).join(', ')} | sentiment ${item.sentiment} | confidence ${item.confidence}`;
        const sel = document.createElement('select');
        sel.className = 'coder-review-theme';
        sel.setAttribute('aria-label', 'Correct theme');
        sel.add(new Option('Theme…', ''));
        options.forEach(o => sel.add(new Option(`${o.code_id} ${o.label}`, String(o.code_id))));
        const sent = document.createElement('select');
        sent.className = 'coder-review-sent';
        sent.setAttribute('aria-label', 'Correct sentiment');
        [['', 'Sentiment…'], ['pos', 'Positive'], ['neg', 'Negative'], ['neutral', 'Neutral'], ['mixed', 'Mixed']]
            .forEach(([v, t]) => sent.add(new Option(t, v)));
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'coder-review-save';
        btn.textContent = 'Save correction';
        btn.addEventListener('click', () => submitCoderCorrection(item.response_id, sel.value, sent.value, row));
        row.append(q, meta, sel, sent, btn);
        box.appendChild(row);
    });
}

async function submitCoderCorrection(responseId, codeId, sentiment, row) {
    const body = { response_id: responseId };
    if (codeId) body.code_ids = [codeId];
    if (sentiment) body.sentiment = sentiment;
    if (!body.code_ids && !body.sentiment) { showToast('Pick a theme or a sentiment first.'); return; }
    try {
        const res = await fetch('/api/coder/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            row.remove();
            showToast(`✓ Correction saved (${data.corrections} stored locally)`);
        } else {
            showToast(`Correction not saved: ${data.message || res.status}`);
        }
    } catch (err) {
        showToast('Correction not saved.');
    }
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
function findBestColumnMatch(keywords, schema) {
    if (!schema) return null;
    const cols = Object.keys(schema).filter(c => !c.startsWith('__'));
    for (const kw of keywords) {
        const found = cols.find(c => c.toLowerCase().includes(kw));
        if (found) return found;
    }
    return null;
}

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

        const schema = (loadedDatasetInfo && loadedDatasetInfo.schema) || {};

        // Stubs matching (English + Taglish, schema-driven CS-042)
        if (lower.includes('satisfaction') || lower.includes('csat') || lower.includes('tuwa') || lower.includes('happy')) {
            const targetCol = findBestColumnMatch(['overall', 'satisfaction', 'sat', 'csat'], schema) || "Overall CSAT (T2B)";
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill(targetCol, true));
            currentMetric = 't2b';
        } else if (lower.includes('brand') || lower.includes('preference') || lower.includes('nanotech')) {
            const targetCol = findBestColumnMatch(['brand', 'preference'], schema) || "Brand Preference";
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill(targetCol, true));
            currentMetric = 'pct';
        } else if (lower.includes('repurchase') || lower.includes('intent') || lower.includes('ulit') || lower.includes('bili')) {
            const targetCol = findBestColumnMatch(['repurchase', 'intent'], schema) || "Repurchase Intent";
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill(targetCol, true));
        } else if (lower.includes('income') || lower.includes('sec') || lower.includes('class')) {
            const targetCol = findBestColumnMatch(['income', 'sec', 'class'], schema) || "Monthly Income Class (SEC)";
            const tray = document.getElementById('stub-tray');
            tray.innerHTML = "";
            tray.appendChild(createPill(targetCol, true));
        } else if (input.length > 0 && !lower.includes('generate') && !lower.includes('table')) {
            addStubPill(input);
        }

        // Banners matching (English + Taglish) - Allows multi-banner stacking
        let addedAnyBanner = false;
        if (lower.includes('age') || lower.includes('gen z') || lower.includes('millennial') || lower.includes('edad')) {
            addBannerPill('Age Generation', false);
            addedAnyBanner = true;
        }
        if (lower.includes('region') || lower.includes('luzon') || lower.includes('visayas') || lower.includes('mindanao') || lower.includes('probinsya')) {
            addBannerPill('Region', false);
            addedAnyBanner = true;
        }
        if (lower.includes('gender') || lower.includes('sex') || lower.includes('kasarian') || lower.includes('male') || lower.includes('female') || lower.includes('babae') || lower.includes('lalaki')) {
            addBannerPill('Gender', false);
            addedAnyBanner = true;
        }
        if (lower.includes('income') || lower.includes('sec') || lower.includes('class abc')) {
            addBannerPill('Monthly Income Class', false);
            addedAnyBanner = true;
        }
        if (lower.includes('brand') || lower.includes('tatak')) {
            addBannerPill('Brand Preference', false);
            addedAnyBanner = true;
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

async function handleCodeframeUpload(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    showToast(`⏳ Reading "${file.name}"...`);
    const isExcel = file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls');

    if (isExcel) {
        try {
            const arrayBuffer = await file.arrayBuffer();
            const res = await fetch('/api/upload-codeframe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/octet-stream',
                    'X-Filename': file.name
                },
                body: arrayBuffer
            });
            const data = await res.json();
            if (data.status === 'success') {
                const count = data.topics_count || (data.codeframe && data.codeframe.topics ? data.codeframe.topics.length : 'Custom');
                const lbl = document.getElementById('active-codeframe-label');
                if (lbl) lbl.textContent = `Active: ${escapeHtml((data.codeframe && data.codeframe.name) || file.name)} (${count} Categories)`;
                showToast(`✓ Dynamic Excel codeframe loaded: ${count} categories parsed.`);
                loadTaglishCoding();
            } else {
                showToast('Codeframe upload failed: ' + (data.message || 'Unknown error'), true);
            }
        } catch (err) {
            showToast('Failed to upload Excel codeframe: ' + err.message, true);
        } finally {
            event.target.value = '';
        }
        return;
    }

    try {
        const text = await file.text();
        let codeframe = JSON.parse(text);
        if (!Array.isArray(codeframe) && codeframe.codeframe) {
            codeframe = codeframe.codeframe;
        }
        if (!Array.isArray(codeframe) && !codeframe.topics) {
            showToast("Invalid codeframe format: Expected a JSON array or object with category definitions.", true);
            return;
        }

        const res = await fetch('/api/set-codeframe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ codeframe: codeframe })
        });
        const data = await res.json();
        if (data.status === 'success') {
            const count = Array.isArray(codeframe) ? codeframe.length : (codeframe.topics ? codeframe.topics.length : 'Custom');
            const lbl = document.getElementById('active-codeframe-label');
            if (lbl) lbl.textContent = `Active: Custom Codeframe (${count} Categories)`;
            showToast(data.message || ('Custom codeframe loaded with ' + count + ' categories.'));
            loadTaglishCoding();
        } else {
            showToast('Codeframe upload failed: ' + (data.message || 'Unknown error'), true);
        }
    } catch (err) {
        showToast('Failed to parse codeframe JSON: ' + err.message, true);
    } finally {
        event.target.value = '';
    }
}

function downloadVerticalCodeframe() {
    showToast("⏳ Generating vertical Excel codeframe (.xlsx)...");
    window.location.href = "/api/export/vertical-codeframe";
}

function uploadProjectCodeframe(event) {
    handleCodeframeUpload(event);
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
                triggerFileDownload('/api/export/excel', 'ClearSight_Agency_Banner_Book.xlsx');
                return;
            }
            // P4-09: show the server's reason (e.g. "Build at least one table first.") instead of
            // downloading the HTML error page under an .xlsx name.
            showToast(data.message || 'Export failed.', true);
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
