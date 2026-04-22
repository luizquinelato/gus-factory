import React, { useState, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Eye, EyeSlash } from '@phosphor-icons/react'
import QuantumBackground from '../components/QuantumBackground'
import { useAuth } from '../contexts/AuthContext'
import apiClient from '../services/apiClient'

/* ─── Animação rise (card sobe ao aparecer) ─── */
const riseKeyframes = `
  @keyframes rise {
    from { opacity: 0; transform: translateY(32px); }
    to   { opacity: 1; transform: translateY(0);    }
  }
`

export default function LoginPage() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { login } = useAuth()

  // ?etl=1 → usuário veio do ETL; o path desejado está no sessionStorage do ETL
  const isEtlRedirect = new URLSearchParams(location.search).get('etl') === '1'

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  const emailRef = useRef<HTMLInputElement>(null)
  const passRef  = useRef<HTMLInputElement>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)

      if (isEtlRedirect) {
        // Gera OTT e abre a raiz do ETL — o ETL lê o sessionStorage para o deep link
        const { data } = await apiClient.post<{ ott: string; etl_url: string }>('/auth/ott')
        window.location.href = `${data.etl_url}?ott=${data.ott}`
        return
      }

      navigate('/', { replace: true })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        'Email ou senha inválidos.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  function handleInputFocus(ref: React.RefObject<HTMLInputElement | null>) {
    if (ref.current) ref.current.style.borderColor = '#1D4ED8'
  }
  function handleInputBlur(ref: React.RefObject<HTMLInputElement | null>) {
    if (ref.current) ref.current.style.borderColor = 'rgba(255,255,255,0.15)'
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '1rem 1.25rem',
    fontSize: '1rem',
    color: '#fff',
    background: 'rgba(255,255,255,0.07)',
    border: '1.5px solid rgba(255,255,255,0.15)',
    borderRadius: '12px',
    outline: 'none',
    transition: 'border-color .2s',
  }

  return (
    <div style={{ position: 'relative', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <style>{riseKeyframes}</style>
      <QuantumBackground />

      <div style={{ position: 'relative', zIndex: 10, width: '100%', maxWidth: 440, animation: 'rise .55s cubic-bezier(.22,1,.36,1) both' }}>

        {/* ── Logo ── */}
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 80, height: 80, borderRadius: 20, marginBottom: 16,
            background: 'linear-gradient(135deg, #1D4ED8, #1A1D2E)',
            boxShadow: '0 0 30px rgba(29,78,216,0.6)',
          }}>
            <img src="/favicon.svg" alt="logo" style={{ width: 48, height: 48 }} />
          </div>
          <h1 style={{ fontSize: '2.2rem', fontWeight: 800, color: '#fff', margin: 0, letterSpacing: '0.04em' }}>SAAS BLUEPRINT V1</h1>
          <p style={{ color: '#94a3b8', marginTop: 6, fontSize: '.95rem' }}>Plataforma SaaS Multi-Tenant</p>
        </div>

        {/* ── Card ── */}
        <div style={{
          background: 'rgba(255,255,255,0.08)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: 24,
          padding: '2.5rem',
          boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
        }}>
          <h2 style={{ color: '#fff', fontSize: '1.5rem', fontWeight: 700, margin: '0 0 6px' }}>Bem-vindo de volta</h2>
          <p style={{ color: '#94a3b8', fontSize: '.9rem', marginBottom: '2rem' }}>Entre com suas credenciais para continuar</p>

          {error && (
            <div style={{ marginBottom: 16, padding: '12px 16px', borderRadius: 12, fontSize: '.875rem', color: '#fca5a5', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.35)' }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ display: 'block', color: '#cbd5e1', fontSize: '.85rem', marginBottom: 6, fontWeight: 500 }}>Email</label>
              <input
                ref={emailRef}
                type="email" required value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seu@email.com"
                style={inputStyle}
                onFocus={() => handleInputFocus(emailRef)}
                onBlur={() => handleInputBlur(emailRef)}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#cbd5e1', fontSize: '.85rem', marginBottom: 6, fontWeight: 500 }}>Senha</label>
              <div style={{ position: 'relative' }}>
                <input
                  ref={passRef}
                  type={showPass ? 'text' : 'password'} required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  style={{ ...inputStyle, paddingRight: '3rem' }}
                  onFocus={() => handleInputFocus(passRef)}
                  onBlur={() => handleInputBlur(passRef)}
                />
                <button type="button" onClick={() => setShowPass((v) => !v)}
                  style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex' }}>
                  {showPass ? <EyeSlash size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading}
              style={{
                marginTop: 8,
                padding: '1rem',
                borderRadius: 12,
                border: 'none',
                fontSize: '1rem',
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                background: loading ? 'rgba(100,100,100,0.4)' : 'linear-gradient(135deg, #1D4ED8, #1A1D2E)',
                color: loading ? '#aaa' : '#FFFFFF',
                boxShadow: loading ? 'none' : '0 4px 24px rgba(29,78,216,0.5)',
                transition: 'opacity .2s',
                opacity: loading ? 0.7 : 1,
              }}>
              {loading ? 'Entrando...' : 'Entrar'}
            </button>
          </form>

          <p style={{ textAlign: 'center', color: '#475569', fontSize: '.8rem', marginTop: '1.5rem' }}>
            SaaS Blueprint V1 · Multi-Tenant SaaS Platform
          </p>
        </div>
      </div>
    </div>
  )
}
