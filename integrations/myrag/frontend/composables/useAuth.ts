/**
 * Keycloak OIDC authentication composable.
 * Uses oidc-client-ts with PKCE flow.
 */

export function useAuth() {
  const config = useRuntimeConfig()
  const user = useState<any>('auth-user', () => null)
  const loading = useState('auth-loading', () => true)
  const authError = useState('auth-error', () => '')

  async function init() {
    // Skip auth if disabled or server-side
    if (!config.public.authEnabled || import.meta.server) {
      loading.value = false
      return
    }

    loading.value = true
    authError.value = ''

    try {
      const { UserManager, WebStorageStateStore } = await import('oidc-client-ts')

      const keycloakUrl = config.public.keycloakUrl || 'http://host.docker.internal:8082'
      const keycloakRealm = config.public.keycloakRealm || 'openwebui'
      const clientId = config.public.keycloakClientId || 'myrag-front'
      const origin = window.location.origin
      const redirectUri = `${origin}/auth/callback`

      const mgr = new UserManager({
        authority: `${keycloakUrl}/realms/${keycloakRealm}`,
        client_id: clientId,
        redirect_uri: redirectUri,
        post_logout_redirect_uri: origin,
        response_type: 'code',
        scope: 'openid email profile',
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
        automaticSilentRenew: true,
      })

      // Case 1: returning from Keycloak callback
      if (window.location.pathname === '/auth/callback') {
        try {
          const signed = await mgr.signinRedirectCallback()
          user.value = {
            access_token: signed.access_token,
            profile: signed.profile,
          }
          window.history.replaceState({}, '', '/')
          loading.value = false
          return
        } catch (cbError: any) {
          console.error('OIDC callback error:', cbError)
          authError.value = `Callback error: ${cbError.message}`
          // Clear stale state and retry login
          await mgr.removeUser()
          window.sessionStorage.clear()
          await mgr.signinRedirect()
          return
        }
      }

      // Case 2: check existing session
      try {
        const existingUser = await mgr.getUser()
        if (existingUser && !existingUser.expired) {
          user.value = {
            access_token: existingUser.access_token,
            profile: existingUser.profile,
          }
          loading.value = false
          return
        }
      } catch (e) {
        // Session invalid, clear and redirect
        await mgr.removeUser()
      }

      // Case 3: no session — redirect to Keycloak
      await mgr.signinRedirect()

    } catch (e: any) {
      console.error('Auth init error:', e)
      authError.value = e.message || 'Authentication error'
      loading.value = false
    }
  }

  async function logout() {
    try {
      const { UserManager, WebStorageStateStore } = await import('oidc-client-ts')
      const keycloakUrl = config.public.keycloakUrl
      const keycloakRealm = config.public.keycloakRealm
      const mgr = new UserManager({
        authority: `${keycloakUrl}/realms/${keycloakRealm}`,
        client_id: config.public.keycloakClientId,
        redirect_uri: window.location.origin,
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
      await mgr.signoutRedirect()
    } catch (e) {
      window.sessionStorage.clear()
      window.location.href = '/'
    }
  }

  function getAccessToken(): string | null {
    return user.value?.access_token || null
  }

  function getUserName(): string {
    const p = user.value?.profile
    if (!p) return ''
    return p.preferred_username || p.name || p.email || ''
  }

  function getUserGroups(): string[] {
    return user.value?.profile?.groups || []
  }

  return { user, loading, authError, init, logout, getAccessToken, getUserName, getUserGroups }
}
