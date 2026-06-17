/* ==========================================================
   NotesMind Pro — Dashboard JavaScript
   Handles: summarize API, history, flashcards, file upload,
            output tabs, copy/export, settings modal, search.
   Theme toggle is handled in base.html.
   All API calls require login (Flask returns 401 if not).
   ========================================================== */

'use strict';

/* ──────────────────────────────────────────────────────────
   1.  STATE
────────────────────────────────────────────────────────── */
const state = {
    currentSummaryId : null,
    currentSummaryData: null,
    historyItems     : [],
    isGenerating     : false,
};

/* ──────────────────────────────────────────────────────────
   2.  DOM REFERENCES
────────────────────────────────────────────────────────── */
// Input
const textEditor         = document.getElementById('textEditor');
const documentTitle      = document.getElementById('documentTitle');
const modelSelect        = document.getElementById('modelSelect');
const generateBtn        = document.getElementById('generateBtn');
const tabTextBtn         = document.getElementById('tabTextBtn');
const tabFileBtn         = document.getElementById('tabFileBtn');
const textInputContainer = document.getElementById('textInputContainer');
const fileUploadContainer= document.getElementById('fileUploadContainer');
const fileInput          = document.getElementById('fileInput');
const dragDropZone       = document.getElementById('dragDropZone');
const selectedFileCard   = document.getElementById('selectedFileCard');
const removeFileBtn      = document.getElementById('removeFileBtn');
const fileName           = document.getElementById('fileName');
const fileSize           = document.getElementById('fileSize');
const fileTypeIcon       = document.getElementById('fileTypeIcon');
const charCount          = document.getElementById('charCount');
const wordCount          = document.getElementById('wordCount');
const readingTime        = document.getElementById('readingTime');

// Output
const outputEmptyState   = document.getElementById('outputEmptyState');
const outputLoader       = document.getElementById('outputLoader');
const outputContentWrapper = document.getElementById('outputContentWrapper');
const outputActions      = document.getElementById('outputActions');
const loaderStatus       = document.getElementById('loaderStatus');
const loaderSubstatus    = document.getElementById('loaderSubstatus');
const progressBarFill    = document.getElementById('progressBarFill');
const summaryOutput      = document.getElementById('summaryOutput');
const bulletsOutput      = document.getElementById('bulletsOutput');
const takeawaysOutput    = document.getElementById('takeawaysOutput');
const notesOutput        = document.getElementById('notesOutput');
const flashcardsContainer= document.getElementById('flashcardsContainer');

// Actions
const btnCopyAll         = document.getElementById('btnCopyAll');
const btnDownloadDropdown= document.getElementById('btnDownloadDropdown');
const downloadDropdownContent = document.getElementById('downloadDropdownContent');
const downloadMD         = document.getElementById('downloadMD');
const downloadTXT        = document.getElementById('downloadTXT');

// History / Sidebar
const historyListContainer = document.getElementById('historyListContainer');
const searchHistoryInput   = document.getElementById('searchHistoryInput');
const historySidebar       = document.getElementById('historySidebar');
const closeSidebarBtn      = document.getElementById('closeSidebarBtn');
const sidebarToggleBtn     = document.getElementById('sidebarToggleBtn');

// Settings Modal
const settingsModal        = document.getElementById('settingsModal');
const openSettingsBtn      = document.getElementById('openSettingsBtn');
const closeSettingsBtn     = document.getElementById('closeSettingsBtn');
const hfTokenInput         = document.getElementById('hfTokenInput');
const toggleTokenVisibility= document.getElementById('toggleTokenVisibility');
const defaultModelSelect   = document.getElementById('defaultModelSelect');
const saveSettingsBtn      = document.getElementById('saveSettingsBtn');

/* ──────────────────────────────────────────────────────────
   3.  INITIALISE
────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadHistory();
    bindEvents();
});

/* ──────────────────────────────────────────────────────────
   4.  SETTINGS  (localStorage)
────────────────────────────────────────────────────────── */
function loadSettings() {
    const token = localStorage.getItem('hf_token') || '';
    let model = localStorage.getItem('hf_model') || 'meta-llama/Meta-Llama-3-8B-Instruct';
    
    // If the browser still holds the unsupported Mistral model, auto-migrate it
    if (model.includes('Mistral') || model.includes('zephyr')) {
        model = 'meta-llama/Meta-Llama-3-8B-Instruct';
        localStorage.setItem('hf_model', model);
    }
    
    if (hfTokenInput)       hfTokenInput.value = token;
    if (modelSelect)        modelSelect.value  = model;
    if (defaultModelSelect) defaultModelSelect.value = model;
}

function saveSettings() {
    const token = hfTokenInput?.value.trim() || '';
    const model = defaultModelSelect?.value || 'mistralai/Mistral-7B-Instruct-v0.3';
    localStorage.setItem('hf_token', token);
    localStorage.setItem('hf_model', model);
    if (modelSelect) modelSelect.value = model;
    closeModal(settingsModal);
    showToast('Configuration saved!', 'success');
}

/* ──────────────────────────────────────────────────────────
   5.  HISTORY  (sidebar)
────────────────────────────────────────────────────────── */
async function loadHistory() {
    try {
        const res  = await fetch('/api/history');
        // 401 = not logged in, handled by Flask redirect
        if (res.status === 401) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.success) {
            state.historyItems = data.history;
            renderHistory(data.history);
        }
    } catch (err) {
        console.warn('History load failed:', err);
    }
}

function renderHistory(items) {
    if (!historyListContainer) return;
    if (!items.length) {
        historyListContainer.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-folder-open"></i>
                <p>No summaries yet</p>
                <span>Generate your first one →</span>
            </div>`;
        return;
    }
    historyListContainer.innerHTML = items.map(item => `
        <div class="history-item" data-id="${item.id}" id="histItem-${item.id}">
            <div class="history-item-header">
                <span class="history-item-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</span>
                <button class="history-item-delete" data-id="${item.id}" title="Delete" aria-label="Delete summary">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
            <div class="history-item-meta">
                <span><i class="fa-solid fa-align-left"></i> ${item.word_count ?? 0} words</span>
                <span><i class="fa-regular fa-clock"></i> ${item.reading_time ?? 0} min</span>
            </div>
        </div>
    `).join('');

    // Bind click events
    historyListContainer.querySelectorAll('.history-item').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target.closest('.history-item-delete')) return;
            loadSummaryDetail(el.dataset.id);
        });
    });
    historyListContainer.querySelectorAll('.history-item-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            confirmDelete(btn.dataset.id);
        });
    });
}

function filterHistory(query) {
    const q = query.toLowerCase();
    const filtered = state.historyItems.filter(i => i.title.toLowerCase().includes(q));
    renderHistory(filtered);
}

async function loadSummaryDetail(id) {
    try {
        const res  = await fetch(`/api/history/${id}`);
        if (!res.ok) { showToast('Failed to load summary.', 'error'); return; }
        const data = await res.json();
        if (data.success) {
            state.currentSummaryId   = id;
            state.currentSummaryData = data.data;
            displayOutput(data.data);
            setActiveHistoryItem(id);
        }
    } catch (err) {
        showToast('Error loading summary.', 'error');
    }
}

function setActiveHistoryItem(id) {
    historyListContainer?.querySelectorAll('.history-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === String(id));
    });
}

async function confirmDelete(id) {
    if (!confirm('Delete this summary? This cannot be undone.')) return;
    try {
        const res = await fetch(`/api/history/${id}`, { method: 'DELETE' });
        if (!res.ok) { showToast('Delete failed.', 'error'); return; }
        state.historyItems = state.historyItems.filter(i => i.id !== id);
        renderHistory(state.historyItems);
        if (state.currentSummaryId === id) {
            resetOutput();
            state.currentSummaryId = null;
            state.currentSummaryData = null;
        }
        showToast('Summary deleted.', 'info');
    } catch (err) {
        showToast('Error deleting summary.', 'error');
    }
}

/* ──────────────────────────────────────────────────────────
   6.  GENERATE SUMMARY
────────────────────────────────────────────────────────── */
async function handleGenerate() {
    if (state.isGenerating) return;

    const isTextMode = !textInputContainer?.classList.contains('hidden');
    const textVal    = textEditor?.value.trim() || '';
    const titleVal   = documentTitle?.value.trim() || '';
    const model      = modelSelect?.value || 'mock';
    const token      = localStorage.getItem('hf_token') || '';

    // Validate
    if (isTextMode && !textVal) {
        showToast('Please paste some text first.', 'error'); return;
    }
    if (!isTextMode && !fileInput?.files?.length) {
        showToast('Please select a file to upload.', 'error'); return;
    }

    state.isGenerating = true;
    generateBtn.disabled = true;
    generateBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing…';

    showLoader();
    startProgressAnimation();

    const formData = new FormData();
    formData.append('title', titleVal);
    formData.append('model_name', model === 'mock' ? 'mock' : model);
    formData.append('api_token', model === 'mock' ? 'mock' : token);

    if (isTextMode) {
        formData.append('text', textVal);
    } else {
        formData.append('file', fileInput.files[0]);
    }

    try {
        setLoaderStatus('Sending to AI…', 'Connecting to inference API');
        const res  = await fetch('/api/summarize', { method: 'POST', body: formData });
        if (res.status === 401) { window.location.href = '/login'; return; }
        const data = await res.json();

        if (data.success) {
            state.currentSummaryId   = data.data.id;
            state.currentSummaryData = data.data;
            displayOutput(data.data);
            await loadHistory();
            setActiveHistoryItem(data.data.id);
            showToast('Insights generated!', 'success');
        } else {
            showToast(data.error || 'Summarisation failed.', 'error');
            resetOutput();
        }
    } catch (err) {
        showToast('Network error. Please try again.', 'error');
        resetOutput();
    } finally {
        state.isGenerating = false;
        generateBtn.disabled = false;
        generateBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Insights';
    }
}

/* ──────────────────────────────────────────────────────────
   7.  DISPLAY OUTPUT
────────────────────────────────────────────────────────── */
function displayOutput(data) {
    hideLoader();
    show(outputContentWrapper);
    hide(outputEmptyState);
    show(outputActions);

    // Summary
    summaryOutput.textContent = data.summary || 'No summary available.';

    // Markdown sections
    if (typeof marked !== 'undefined') {
        bulletsOutput.innerHTML   = marked.parse(data.bullet_points  || '_No data_');
        takeawaysOutput.innerHTML = marked.parse(data.takeaways      || '_No data_');
        notesOutput.innerHTML     = marked.parse(data.study_notes    || '_No data_');
    } else {
        bulletsOutput.textContent   = data.bullet_points  || '';
        takeawaysOutput.textContent = data.takeaways      || '';
        notesOutput.textContent     = data.study_notes    || '';
    }

    // Flashcards
    renderFlashcards(data.flashcards || []);

    // Switch to summary tab
    switchOutputTab('summary');
}

function resetOutput() {
    hideLoader();
    show(outputEmptyState);
    hide(outputContentWrapper);
    hide(outputActions);
}

/* ──────────────────────────────────────────────────────────
   8.  FLASHCARDS
────────────────────────────────────────────────────────── */
function renderFlashcards(cards) {
    if (!flashcardsContainer) return;
    if (!cards.length) {
        flashcardsContainer.innerHTML = '<p style="color:var(--text-muted);font-size:.85rem;">No flashcards generated.</p>';
        return;
    }
    flashcardsContainer.innerHTML = cards.map((card, i) => `
        <div class="flashcard" id="flashcard-${i}" role="button" tabindex="0" aria-label="Flashcard ${i+1}, click to flip">
            <div class="flashcard-inner">
                <div class="flashcard-front">
                    <div class="flashcard-label">Question</div>
                    <div class="flashcard-text">${escapeHtml(card.question || '')}</div>
                </div>
                <div class="flashcard-back">
                    <div class="flashcard-label">Answer</div>
                    <div class="flashcard-text">${escapeHtml(card.answer || '')}</div>
                </div>
            </div>
        </div>
    `).join('');

    flashcardsContainer.querySelectorAll('.flashcard').forEach(card => {
        card.addEventListener('click',   () => card.classList.toggle('flipped'));
        card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') card.classList.toggle('flipped'); });
    });
}

/* ──────────────────────────────────────────────────────────
   9.  OUTPUT TABS
────────────────────────────────────────────────────────── */
function switchOutputTab(tabName) {
    document.querySelectorAll('.out-tab-btn').forEach(btn => {
        const active = btn.dataset.tab === tabName;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', active);
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === `pane-${tabName}`);
    });
}

/* ──────────────────────────────────────────────────────────
   10. FILE UPLOAD
────────────────────────────────────────────────────────── */
function handleFileSelected(file) {
    if (!file) return;
    const ext  = file.name.split('.').pop().toLowerCase();
    const size = (file.size / 1024 / 1024).toFixed(2);

    fileName.textContent  = file.name;
    fileSize.textContent  = `${size} MB`;
    fileTypeIcon.className = ext === 'pdf'
        ? 'fa-regular fa-file-pdf file-type-icon'
        : 'fa-regular fa-file-lines file-type-icon';

    hide(dragDropZone);
    show(selectedFileCard);

    if (documentTitle && !documentTitle.value.trim()) {
        documentTitle.value = file.name.replace(/\.[^.]+$/, '');
    }
}

function clearFileSelection() {
    fileInput.value = '';
    show(dragDropZone);
    hide(selectedFileCard);
}

/* ──────────────────────────────────────────────────────────
   11. COPY & EXPORT
────────────────────────────────────────────────────────── */
function copyAll() {
    const d = state.currentSummaryData;
    if (!d) return;
    const text = [
        `TITLE: ${d.title}`,
        `STATS: ${d.word_count} words | ${d.reading_time} min read`,
        '',
        `SUMMARY:\n${d.summary}`,
        '',
        `BULLET POINTS:\n${d.bullet_points}`,
        '',
        `KEY TAKEAWAYS:\n${d.takeaways}`,
        '',
        `STUDY NOTES:\n${d.study_notes}`,
    ].join('\n');
    navigator.clipboard.writeText(text)
        .then(() => showToast('Copied to clipboard!', 'success'))
        .catch(() => showToast('Copy failed.', 'error'));
}

function exportSummary(format) {
    if (!state.currentSummaryId) { showToast('No summary to export.', 'error'); return; }
    window.location.href = `/api/export/${state.currentSummaryId}/${format}`;
}

/* ──────────────────────────────────────────────────────────
   12. LOADER HELPERS
────────────────────────────────────────────────────────── */
const loaderSteps = [
    { status: 'Extracting content…',    sub: 'Parsing document structure',        pct: 15 },
    { status: 'Analysing text…',        sub: 'Identifying key concepts',          pct: 35 },
    { status: 'Generating summary…',    sub: 'Running AI inference',              pct: 55 },
    { status: 'Building flashcards…',   sub: 'Creating Q&A pairs',               pct: 75 },
    { status: 'Finalising output…',     sub: 'Structuring study materials',       pct: 90 },
];

let _loaderTimer = null;

function startProgressAnimation() {
    let step = 0;
    setLoaderProgress(loaderSteps[0]);
    _loaderTimer = setInterval(() => {
        step = Math.min(step + 1, loaderSteps.length - 1);
        setLoaderProgress(loaderSteps[step]);
        if (step === loaderSteps.length - 1) clearInterval(_loaderTimer);
    }, 1800);
}

function setLoaderProgress({ status, sub, pct } = {}) {
    if (loaderStatus)    loaderStatus.textContent    = status || '';
    if (loaderSubstatus) loaderSubstatus.textContent = sub    || '';
    if (progressBarFill) progressBarFill.style.width = `${pct || 0}%`;
}

function setLoaderStatus(status, sub) {
    if (loaderStatus)    loaderStatus.textContent    = status;
    if (loaderSubstatus) loaderSubstatus.textContent = sub;
}

function showLoader() {
    hide(outputEmptyState);
    hide(outputContentWrapper);
    hide(outputActions);
    show(outputLoader);
}

function hideLoader() {
    clearInterval(_loaderTimer);
    hide(outputLoader);
    if (progressBarFill) progressBarFill.style.width = '0%';
}

/* ──────────────────────────────────────────────────────────
   13. TEXT STATS
────────────────────────────────────────────────────────── */
function updateTextStats() {
    const text  = textEditor?.value || '';
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    const mins  = Math.max(1, Math.ceil(words / 200));
    if (charCount)   charCount.textContent   = `${text.length} characters`;
    if (wordCount)   wordCount.textContent   = `${words} words`;
    if (readingTime) readingTime.textContent = `${words > 0 ? mins : 0} min read`;
}

/* ──────────────────────────────────────────────────────────
   14. TOAST NOTIFICATIONS
────────────────────────────────────────────────────────── */
function showToast(message, type = 'info') {
    const icons = { success: 'fa-circle-check', error: 'fa-circle-exclamation', info: 'fa-circle-info' };
    const toast = document.createElement('div');
    toast.className = `flash-msg flash-${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
        <button class="flash-close" aria-label="Dismiss">&times;</button>`;
    toast.querySelector('.flash-close').addEventListener('click', () => toast.remove());

    let container = document.getElementById('flashContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'flashContainer';
        container.className = 'flash-container';
        document.body.appendChild(container);
    }
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 400); }, 4000);
}

/* ──────────────────────────────────────────────────────────
   15. MODAL HELPERS
────────────────────────────────────────────────────────── */
function openModal(modal) {
    modal?.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}
function closeModal(modal) {
    modal?.classList.add('hidden');
    document.body.style.overflow = '';
}

/* ──────────────────────────────────────────────────────────
   16. DOM HELPERS
────────────────────────────────────────────────────────── */
function show(el) { el?.classList.remove('hidden'); }
function hide(el) { el?.classList.add('hidden'); }
function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ──────────────────────────────────────────────────────────
   17. EVENT BINDINGS
────────────────────────────────────────────────────────── */
function bindEvents() {
    // Generate
    generateBtn?.addEventListener('click', handleGenerate);

    // Text stats
    textEditor?.addEventListener('input', updateTextStats);

    // Input tabs
    tabTextBtn?.addEventListener('click', () => {
        tabTextBtn.classList.add('active');
        tabFileBtn.classList.remove('active');
        show(textInputContainer);
        hide(fileUploadContainer);
    });
    tabFileBtn?.addEventListener('click', () => {
        tabFileBtn.classList.add('active');
        tabTextBtn.classList.remove('active');
        hide(textInputContainer);
        show(fileUploadContainer);
    });

    // File input
    fileInput?.addEventListener('change', () => {
        if (fileInput.files[0]) handleFileSelected(fileInput.files[0]);
    });
    removeFileBtn?.addEventListener('click', clearFileSelection);

    // Drag & Drop
    dragDropZone?.addEventListener('dragover', (e) => { e.preventDefault(); dragDropZone.classList.add('drag-over'); });
    dragDropZone?.addEventListener('dragleave', () => dragDropZone.classList.remove('drag-over'));
    dragDropZone?.addEventListener('drop', (e) => {
        e.preventDefault();
        dragDropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) {
            // Transfer to fileInput
            const dt = new DataTransfer();
            dt.items.add(file);
            fileInput.files = dt.files;
            handleFileSelected(file);
        }
    });

    // Output tabs
    document.querySelectorAll('.out-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchOutputTab(btn.dataset.tab));
    });

    // Copy all
    btnCopyAll?.addEventListener('click', copyAll);

    // Download dropdown
    btnDownloadDropdown?.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = downloadDropdownContent?.classList.toggle('open');
        btnDownloadDropdown.setAttribute('aria-expanded', open);
    });
    document.addEventListener('click', () => {
        downloadDropdownContent?.classList.remove('open');
        btnDownloadDropdown?.setAttribute('aria-expanded', 'false');
    });
    downloadMD?.addEventListener('click',  () => exportSummary('markdown'));
    downloadTXT?.addEventListener('click', () => exportSummary('text'));

    // Settings modal
    openSettingsBtn?.addEventListener('click',  () => openModal(settingsModal));
    closeSettingsBtn?.addEventListener('click', () => closeModal(settingsModal));
    settingsModal?.addEventListener('click', (e) => { if (e.target === settingsModal) closeModal(settingsModal); });
    saveSettingsBtn?.addEventListener('click', saveSettings);

    // Token visibility
    toggleTokenVisibility?.addEventListener('click', () => {
        const show = hfTokenInput?.type === 'password';
        if (hfTokenInput) hfTokenInput.type = show ? 'text' : 'password';
        toggleTokenVisibility.querySelector('i').className = show ? 'fa-solid fa-eye-slash' : 'fa-solid fa-eye';
    });

    // History search
    searchHistoryInput?.addEventListener('input', () => filterHistory(searchHistoryInput.value));

    // Mobile sidebar
    sidebarToggleBtn?.addEventListener('click',  () => historySidebar?.classList.toggle('open'));
    closeSidebarBtn?.addEventListener('click',   () => historySidebar?.classList.remove('open'));

    // Escape closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal(settingsModal);
            downloadDropdownContent?.classList.remove('open');
        }
    });
}
