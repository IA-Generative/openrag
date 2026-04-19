/**
 * Keycloak OIDC authentication composable.
 * Uses PKCE flow (Authorization Code + PKCE) client-side.
 */
import { UserManager, WebStorageStateStore } from 'oidc-client-ts'

let _userManager: UserManager | null = null

function getUserManager() {
  if (_userManager) return _userManager

  const config = useRuntimeConfig()
  const keycloakUrl = config.public.keycloakUrl || 'http://host.docker.internal:8082'
  const keycloakRealm = config.public.keycloakRealm || 'openwebui'
  const clientId = config.public.keycloakClientId || 'openwebui'
  const redirectUri = `${window.location.origin}/auth/callback`

  _userManager = new UserManager({
    authority: `${keycloakUrl}/realms/${keycloakRealm}`,
    client_id: clientId,
    redirect_uri: redirectUri,
    post_logout_redirect_uri: window.location.origin,
    response_type: 'code',
    scope: 'openid email profile',
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true,
  })

  return _userManager
}

export function useAuth() {
  const user = useState<any>('auth-user', () => null)
  const loading = useState('auth-loading', () => true)

  async function init() {
    loading.value = true
    const mgr = getUserManager()

    try {
      // Check if returning from login callback
      if (window.location.pathname === '/auth/callback') {
        const signedinUser = await mgr.signinRedirectCallback()
        user.value = signedinUser
        // Remove query params from URL
        window.history.replaceState({}, '', '/')
        loading.value = false
        return
      }

      // Check existing session
      const existingUser = await mgr.getUser()
      if (existingUser && !existingUser.expired) {
        user.value = existingUser
        loading.value = false
        return
      }

      // No session — redirect to Keycloak
      await mgr.signinRedirect()
    } catch (e) {
      console.error('Auth error:', e)
      // If OIDC fails (e.g., Keycloak not configured), allow unauthenticated access
      loading.value = false
    }
  }

  async function logout() {
    const mgr = getUserManager()
    await mgr.signoutRedirect()
  }

  function getAccessToken(): string | null {
    return user.value?.access_token || null
  }

  function getUserName(): string {
    if (!user.value?.profile) return ''
    return user.value.profile.preferred_username
      || user.value.profile.name
      || user.value.profile.email
      || ''
  }

  function getUserGroups(): string[] {
    return user.value?.profile?.groups || []
  }

  return { user, loading, init, logout, getAccessToken, getUserName, getUserGroups }
}
