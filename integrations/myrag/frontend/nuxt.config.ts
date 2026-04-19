export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  ssr: false,

  app: {
    head: {
      title: 'MyRAG (beta)',
      htmlAttrs: { lang: 'fr', 'data-fr-scheme': 'light' },
      link: [
        { rel: 'stylesheet', href: '/@gouvfr/dsfr/dist/dsfr.min.css' },
        { rel: 'stylesheet', href: '/@gouvfr/dsfr/dist/utility/icons/icons.min.css' },
      ],
    },
  },

  css: ['~/assets/main.css'],

  runtimeConfig: {
    public: {
      myragApiUrl: process.env.MYRAG_API_URL || 'http://localhost:8200',
      appTitle: process.env.APP_TITLE || 'MyRAG (beta)',
    },
  },
})
