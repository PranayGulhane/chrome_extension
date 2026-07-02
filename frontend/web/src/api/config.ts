// Must be "localhost", not "127.0.0.1" — even though they're the same machine, browsers treat
// them as different sites for SameSite cookie purposes. The auth cookies are SameSite=Strict
// (see backend/core/security.py), so if this doesn't match the hostname the web app itself runs
// on (also localhost, per Vite's default dev server), the browser will set the cookie on login
// but then refuse to send it back on the very next request — silent-looking 401s on /auth/me.
//
// TODO: point at the deployed backend once one exists, and add the deployed web app's origin to
// backend/core/config.py's cors_origins (currently defaults to this dev port only).
export const API_BASE_URL = "http://localhost:8123";
