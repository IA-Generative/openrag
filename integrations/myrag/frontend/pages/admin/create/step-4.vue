<template>
  <div>
    <h1 class="fr-h3">Publication — {{ collection }}</h1>
    <WizardStepper :current-step="4" />

    <div class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-8">
        <!-- Summary card -->
        <div class="fr-card fr-mb-4w">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <h3 class="fr-card__title">Resume de la collection</h3>
              <dl>
                <dt>Nom</dt><dd>{{ config?.name }}</dd>
                <dt>Description</dt><dd>{{ config?.description || '—' }}</dd>
                <dt>Strategie</dt><dd>{{ config?.strategy }}</dd>
                <dt>Prompt</dt><dd>{{ config?.prompt_template }}</dd>
                <dt>Sensibilite</dt><dd>{{ config?.sensitivity }}</dd>
                <dt>Graph</dt><dd>{{ config?.graph_enabled ? '✅' : '❌' }}</dd>
              </dl>
            </div>
          </div>
        </div>

        <!-- Publication modes -->
        <fieldset class="fr-fieldset fr-mb-4w">
          <legend class="fr-fieldset__legend fr-h5">Modes de publication</legend>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="alias" v-model="form.alias_enabled" />
              <label class="fr-label" for="alias">Alias de modele dans Open WebUI</label>
            </div>
          </div>
          <div v-if="form.alias_enabled" class="fr-fieldset__element fr-ml-4w">
            <div class="fr-input-group">
              <label class="fr-label">Nom du modele</label>
              <input class="fr-input" v-model="form.alias_name" :placeholder="`MirAI ${collection}`" />
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="tool" v-model="form.tool_enabled" />
              <label class="fr-label" for="tool">Tool MyRAG (recherche + graph + articles)</label>
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="embed" v-model="form.embed_enabled" />
              <label class="fr-label" for="embed">#{{ collection }} dans le prompt</label>
            </div>
          </div>
        </fieldset>

        <!-- Visibility -->
        <fieldset class="fr-fieldset fr-mb-4w">
          <legend class="fr-fieldset__legend fr-h5">Visibilite</legend>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input type="radio" id="v-all" value="all" v-model="form.visibility" />
              <label class="fr-label" for="v-all">Tous les utilisateurs</label>
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-radio-group">
              <input type="radio" id="v-group" value="group" v-model="form.visibility" />
              <label class="fr-label" for="v-group">Membres du groupe Keycloak</label>
            </div>
          </div>
        </fieldset>

        <!-- Widget & browser extension -->
        <fieldset class="fr-fieldset fr-mb-4w">
          <legend class="fr-fieldset__legend fr-h5">Integration externe</legend>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="widget" v-model="form.widget_enabled" />
              <label class="fr-label" for="widget">Widget overlay (embed.js)</label>
            </div>
          </div>
          <div v-if="form.widget_enabled" class="fr-fieldset__element fr-ml-4w">
            <p class="fr-text--sm fr-mb-1w">Snippet a integrer dans votre application :</p>
            <div class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;font-family:monospace;font-size:0.75rem;word-break:break-all;">
              &lt;script src="{{ myragUrl }}/widget/embed.js" data-collection="{{ collection }}" data-position="bottom-right" data-auth="keycloak"&gt;&lt;/script&gt;
            </div>
            <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-mt-1w" @click="copySnippet">
              Copier le snippet
            </button>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="browser" v-model="form.browser_enabled" />
              <label class="fr-label" for="browser">Extension navigateur MirAI</label>
            </div>
          </div>
          <div v-if="form.browser_enabled" class="fr-fieldset__element fr-ml-4w">
            <div class="fr-input-group">
              <label class="fr-label">URL du service (pour l'extension)</label>
              <input class="fr-input" :value="`${myragUrl}/widget/chat?collection=${collection}`" readonly />
            </div>
            <p class="fr-text--sm fr-mt-1w">Configurez cette URL dans l'extension navigateur MirAI (Settings > MyRAG).</p>
          </div>
        </fieldset>

        <!-- Actions -->
        <div class="fr-btns-group fr-btns-group--inline">
          <NuxtLink :to="`/admin/create/step-3?collection=${collection}`" class="fr-btn fr-btn--secondary">
            ← Precedent
          </NuxtLink>
          <button class="fr-btn fr-btn--tertiary" @click="saveDraft">
            Sauvegarder en brouillon
          </button>
          <button class="fr-btn" @click="publish" :disabled="publishing">
            {{ publishing ? 'Publication...' : 'Publier la collection →' }}
          </button>
        </div>

        <div v-if="result" class="fr-alert fr-mt-2w" :class="resultClass">
          <p>{{ result }}</p>
          <NuxtLink v-if="published" :to="`/c/${collection}`" class="fr-link">Ouvrir la collection</NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const runtimeConfig = useRuntimeConfig()
const collection = route.query.collection as string
const { get, post, baseUrl: myragUrl } = useApi()

const config = ref<any>(null)
const publishing = ref(false)
const published = ref(false)
const result = ref('')
const resultClass = ref('fr-alert--info')

const form = ref({
  alias_enabled: true,
  alias_name: '',
  tool_enabled: true,
  embed_enabled: false,
  visibility: 'group',
  widget_enabled: false,
  browser_enabled: false,
})

function copySnippet() {
  const snippet = `<script src="${myragUrl}/widget/embed.js" data-collection="${collection}" data-position="bottom-right" data-auth="keycloak"><\/script>`
  navigator.clipboard.writeText(snippet)
}

async function saveDraft() {
  result.value = 'Collection sauvegardee en brouillon.'
  resultClass.value = 'fr-alert--info'
}

async function publish() {
  publishing.value = true
  try {
    await post(`/api/collections/${collection}/publish`, {
      ...form.value,
      alias_name: form.value.alias_name || `MirAI ${collection}`,
    })
    result.value = 'Collection publiee avec succes !'
    resultClass.value = 'fr-alert--success'
    published.value = true
  } catch (e: any) {
    result.value = `Erreur: ${e.message}`
    resultClass.value = 'fr-alert--error'
  }
  publishing.value = false
}

onMounted(async () => {
  try { config.value = await get(`/api/collections/${collection}`) } catch (e) {}
})
</script>
