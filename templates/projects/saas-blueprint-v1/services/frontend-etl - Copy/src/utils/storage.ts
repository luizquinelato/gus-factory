/**
 * storage.ts — ETL Frontend
 * Namespace por porta (3344 prod / 3345 dev) — mesma estratégia do frontend principal.
 * Evita colisão de chaves no localStorage quando ambos rodam em localhost.
 */
const PORT = window.location.port || 'default'

function key(name: string) { return `${PORT}:${name}` }

export const storage = {
  getToken:    ()          => localStorage.getItem(key('access_token')),
  setToken:    (v: string) => localStorage.setItem(key('access_token'), v),
  removeToken: ()          => localStorage.removeItem(key('access_token')),

  getUser:    ()          => localStorage.getItem(key('user')),
  setUser:    (v: string) => localStorage.setItem(key('user'), v),
  removeUser: ()          => localStorage.removeItem(key('user')),

  getTenantColors:    ()          => localStorage.getItem(key('tenant_colors')),
  setTenantColors:    (v: string) => localStorage.setItem(key('tenant_colors'), v),
  removeTenantColors: ()          => localStorage.removeItem(key('tenant_colors')),

  clear: () => {
    storage.removeToken()
    storage.removeUser()
    storage.removeTenantColors()
  },
}
