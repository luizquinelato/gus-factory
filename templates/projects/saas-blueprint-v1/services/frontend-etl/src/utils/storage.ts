/**
 * Namespace de localStorage por porta — dev (:5178) e prod (:5177)
 * rodam na mesma origem (http://localhost) e compartilhariam as chaves
 * sem esse prefixo.
 */
const PORT = window.location.port || 'default'

function key(name: string) { return `${PORT}:${name}` }

export const storage = {
  // ── access_token (JWT curto — 5 min) ─────────────────────────
  getToken:    ()          => localStorage.getItem(key('access_token')),
  setToken:    (v: string) => localStorage.setItem(key('access_token'), v),
  removeToken: ()          => localStorage.removeItem(key('access_token')),

  // ── refresh_token (opaque — 7 dias, rotacionado a cada refresh) ──
  getRefreshToken:    ()          => localStorage.getItem(key('refresh_token')),
  setRefreshToken:    (v: string) => localStorage.setItem(key('refresh_token'), v),
  removeRefreshToken: ()          => localStorage.removeItem(key('refresh_token')),

  // ── user ─────────────────────────────────────────────────────
  getUser:    ()          => localStorage.getItem(key('user')),
  setUser:    (v: string) => localStorage.setItem(key('user'), v),
  removeUser: ()          => localStorage.removeItem(key('user')),

  // ── tenant_colors ─────────────────────────────────────────────
  getTenantColors:    ()          => localStorage.getItem(key('tenant_colors')),
  setTenantColors:    (v: string) => localStorage.setItem(key('tenant_colors'), v),
  removeTenantColors: ()          => localStorage.removeItem(key('tenant_colors')),
}
