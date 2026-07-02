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
  .field input {
    padding: 9px 10px;
    border: 1px solid #d8dfe8;
    border-radius: 6px;
    font-size: 14px;
  }
  .field input:focus { outline: 2px solid #1479b5; outline-offset: -1px; }
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
`;
