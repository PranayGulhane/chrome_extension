// Injected into the shadow root (not the page head) so it can never leak onto or be overridden by
// LinkedIn's own styles, and vice versa.
export const PANEL_STYLES = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
  .panel {
    position: fixed;
    top: 72px;
    right: 24px;
    width: 380px;
    max-height: calc(100vh - 96px);
    background: #ffffff;
    border-radius: 10px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.24);
    z-index: 2147483000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    color: #18293d;
    font-size: 14px;
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    background: #0a5c88;
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
  }
  .panel-header button {
    background: transparent;
    border: none;
    color: #ffffff;
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    padding: 0 4px;
  }
  .panel-body {
    padding: 20px 16px;
    overflow-y: auto;
  }
  .field { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
  .field label { font-size: 12px; font-weight: 600; color: #536473; }
  .field input, .field select, .field textarea {
    padding: 9px 10px;
    border: 1px solid #d8dfe8;
    border-radius: 6px;
    font-size: 14px;
    font-family: inherit;
  }
  .field textarea { resize: vertical; }
  .field input:focus, .field select:focus, .field textarea:focus { outline: 2px solid #1479b5; outline-offset: -1px; }
  .btn-primary {
    width: 100%;
    padding: 10px;
    background: #0a5c88;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
  }
  .btn-primary:disabled { opacity: 0.6; cursor: default; }
  .btn-secondary {
    width: 100%;
    padding: 10px;
    background: #eef1f5;
    color: #18293d;
    border: none;
    border-radius: 6px;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
  }
  .error-text { color: #a81e1e; font-size: 12.5px; margin: -4px 0 12px; }
  .muted { color: #536473; font-size: 13px; }
  .user-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px;
    background: #f0f7fc;
    border-radius: 6px;
    margin-bottom: 16px;
  }
  .user-row .email { font-weight: 700; }
  .user-row .role { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #536473; }
  .link-button {
    background: none;
    border: none;
    padding: 0;
    color: #0a5c88;
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
  }
  .link-button:hover { text-decoration: underline; }
  .notice-text {
    background: #fff6e0;
    color: #7a5b00;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 12.5px;
    margin: 0 0 12px;
  }
  .success-text { color: #1a7a3c; font-size: 13px; font-weight: 600; margin: 0 0 12px; }
  .field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 10px 12px;
    margin-bottom: 14px;
  }
  .field-grid-item { min-width: 0; }
  .field-grid-item label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: #536473;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 3px;
  }
  .field-grid-item div { font-size: 13.5px; overflow-wrap: break-word; }
  .tab-row { display: flex; gap: 8px; margin-bottom: 14px; }
  .tab-row button { flex: 1; }
  .tag {
    display: inline-flex;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 100px;
    white-space: nowrap;
  }
  .tag-status { background: #e0eef7; color: #0a5c88; }
  .tag-outreach { background: #eef1f5; color: #536473; }
  .tag-match { background: #e2f5e8; color: #1a7a3c; }
  .tag-warning { background: #fff6e0; color: #7a5b00; }
  .list-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px;
    border: 1px solid #d8dfe8;
    border-radius: 6px;
    margin-bottom: 6px;
    cursor: pointer;
  }
  .list-row:hover { background: #f7f9fb; }
  .modal-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 20, 30, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    z-index: 10;
  }
  .modal-card {
    background: #ffffff;
    border-radius: 10px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    width: 100%;
    max-height: 100%;
    overflow-y: auto;
    padding: 16px;
  }
  .modal-card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 12px;
  }
  .modal-card-header h3 { margin: 0; font-size: 15px; }
  .modal-card-header button {
    background: transparent;
    border: none;
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    color: #536473;
    padding: 0 2px;
  }
  .tag-platform { background: #e0eef7; color: #0a5c88; }
  .tag-external { background: #eef1f5; color: #536473; }
  .control-row {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  .control-row .field { margin-bottom: 0; flex: 1; min-width: 90px; }
  .control-row .btn-secondary, .control-row .btn-primary { width: auto; padding: 8px 12px; white-space: nowrap; }
  .filter-note { font-size: 11px; color: #8a9bb0; margin: -4px 0 10px; }
  .mail-table-wrap { overflow-x: auto; margin-bottom: 10px; }
  .mail-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  .mail-table th, .mail-table td {
    padding: 8px 8px;
    text-align: left;
    border-bottom: 1px solid #d8dfe8;
    vertical-align: top;
  }
  .mail-table th {
    font-size: 10.5px;
    font-weight: 800;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: #536473;
    cursor: pointer;
    white-space: nowrap;
    user-select: none;
  }
  .mail-table th:hover { color: #0a5c88; }
  .mail-table th.sorted { color: #0a5c88; }
  .mail-table tbody tr:hover { background: #f7f9fb; }
  .mail-table td.actions-cell { display: flex; gap: 6px; flex-wrap: wrap; }
  .mail-table td.actions-cell button {
    padding: 4px 8px;
    font-size: 11.5px;
    border-radius: 5px;
    border: 1px solid #d8dfe8;
    background: #ffffff;
    cursor: pointer;
  }
  .mail-table td.actions-cell button:hover { background: #f0f7fc; }
  .pagination-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 14px;
  }
  .pagination-row .btn-secondary { width: auto; padding: 8px 14px; }
`;
