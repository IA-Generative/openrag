export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  ssr: false,

  app: {
    head: {
      title: 'MyRAG (beta)',
      htmlAttrs: { lang: 'fr', 'data-fr-scheme': 'light' },
    },
  },

  css: [
    '@gouvfr/dsfr/dist/dsfr.min.css',
    '@gouvfr/dsfr/dist/utility/icons/icons.min.css',
    '~/assets/main.css',
  ],

  runtimeConfig: {
    public: {
      myragApiUrl: process.env.MYRAG_API_URL || 'http://localhost:8200',
      appTitle: process.env.APP_TITLE || 'MyRAG (beta)',
      keycloakUrl: process.env.KEYCLOAK_URL || 'http://host.docker.internal:8082',
      keycloakRealm: process.env.KEYCLOAK_REALM || 'openwebui',
      keycloakClientId: process.env.KEYCLOAK_CLIENT_ID || 'myrag-front',
      authEnabled: process.env.AUTH_ENABLED !== 'false',
    },
  },
})
