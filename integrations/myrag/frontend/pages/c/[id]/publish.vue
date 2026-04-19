<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Publication</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Publication — {{ id }}</h1>

    <div v-if="pub">
      <!-- State badge -->
      <div class="fr-mb-4w">
        <span class="fr-badge fr-badge--lg" :class="stateBadge(pub.state)">
          {{ stateLabel(pub.state) }}
        </span>
        <span v-if="pub.published_at" class="fr-text--sm fr-ml-2w">
          Publie le {{ pub.published_at }} par {{ pub.published_by }}
        </span>
      </div>

      <div class="fr-grid-row fr-grid-row--gutters">
        <div class="fr-col-8">
          <!-- Mode A: Alias -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">Mode A — Alias de modele</legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input type="checkbox" id="alias" v-model="form.alias_enabled" />
                <label class="fr-label" for="alias">Publier comme modele dans Open WebUI</label>
              </div>
            </div>
            <div v-if="form.alias_enabled" class="fr-fieldset__element fr-ml-4w">
              <div class="fr-input-group">
                <label class="fr-label">Nom du modele</label>
                <input class="fr-input" v-model="form.alias_name" :placeholder="`MirAI ${id}`" />
              </div>
              <div class="fr-input-group fr-mt-1w">
                <label class="fr-label">Description</label>
                <input class="fr-input" v-model="form.alias_description" placeholder="Recherche dans le CESEDA" />
              </div>
            </div>
          </fieldset>

          <!-- Mode C: Tool -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">Mode C — Tool MyRAG</legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input type="checkbox" id="tool" v-model="form.tool_enabled" />
                <label class="fr-label" for="tool">Attacher le tool MyRAG aux modeles LLM</label>
              </div>
            </div>
            <div v-if="form.tool_enabled" class="fr-fieldset__element fr-ml-4w">
              <p class="fr-text--sm">Methodes activees :</p>
              <div v-for="m in allMethods" :key="m" class="fr-checkbox-group fr-checkbox-group--sm">
                <input type="checkbox" :id="m" :value="m" v-model="form.tool_methods" />
                <label class="fr-label" :for="m">{{ m }}</label>
              </div>
            </div>
          </fieldset>

          <!-- Mode B: Embed -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">Mode B — #collection dans le prompt</legend>
            <div class="fr-fieldset__element">
              <div class="fr-checkbox-group">
                <input type="checkbox" id="embed" v-model="form.embed_enabled" />
                <label class="fr-label" for="embed">Activer le prefixe #{{ id }} dans les prompts</label>
              </div>
            </div>
          </fieldset>

          <!-- Visibility -->
          <fieldset class="fr-fieldset fr-mb-4w">
            <legend class="fr-fieldset__legend fr-h5">Visibilite</legend>
            <div class="fr-fieldset__element">
              <div class="fr-radio-group">
                <input type="radio" id="vis-all" value="all" v-model="form.visibility" />
                <label class="fr-label" for="vis-all">Tous les utilisateurs</label>
              </div>
            </div>
            <div class="fr-fieldset__element">
              <div class="fr-radio-group">
                <input type="radio" id="vis-group" value="group" v-model="form.visibility" />
                <label class="fr-label" for="vis-group">Membres du groupe Keycloak</label>
              </div>
              <div v-if="form.visibility === 'group'" class="fr-input-group fr-ml-4w fr-mt-1w">
                <input class="fr-input" v-model="form.visibility_group" :placeholder="`myrag/${id}`" />
              </div>
            </div>
            <div class="fr-fieldset__element">
              <div class="fr-radio-group">
                <input type="radio" id="vis-users" value="users" v-model="form.visibility" />
                <label class="fr-label" for="vis-users">Utilisateurs specifiques</label>
              </div>
            </div>
          </fieldset>

          <!-- Actions -->
          <div class="fr-btns-group fr-btns-group--inline">
            <button v-if="pub.state !== 'published'" class="fr-btn" @click="publish" :disabled="publishing">
              {{ publishing ? 'Publication...' : 'Publier' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn" @click="publish" :disabled="publishing">
              {{ publishing ? 'Mise a jour...' : 'Mettre a jour' }}
            </button>
            <button v-if="pub.state === 'published'" class="fr-btn fr-btn--secondary" @click="unpublish">
              Desactiver
            </button>
            <button v-if="pub.state !== 'archived'" class="fr-btn fr-btn--tertiary" @click="archive">
              Archiver
            </button>
          </div>

          <div v-if="result" class="fr-alert fr-alert--success fr-mt-2w">
            <p>{{ result }}</p>
          </div>
        </div>

        <!-- Right: History -->
        <div class="fr-col-4">
          <h3 class="fr-h5">Historique</h3>
          <div v-if="pub.history && pub.history.length > 0">
            <div v-for="(h, i) in pub.history.slice().reverse()" :key="i" class="fr-mb-1w">
              <p class="fr-text--sm">
                <strong>{{ h.action }}</strong> — {{ h.at }}<br>
                <span v-if="h.by">par {{ h.by }}</span>
              </p>
            </div>
          </div>
          <p v-else class="fr-text--sm">Aucun historique.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { get, post } = useApi()

const pub = ref<any>(null)
const publishing = ref(false)
const result = ref('')

const allMethods = ['search_collection', 'view_article', 'explore_graph', 'browse_collection']

const form = ref({
  alias_enabled: true,
  alias_name: '',
  alias_description: '',
  tool_enabled: false,
  tool_methods: [...allMethods],
  embed_enabled: false,
  visibility: 'all',
  visibility_group: '',
})

function stateBadge(s: string) {
  return {
    draft: 'fr-badge--info',
    published: 'fr-badge--success',
    disabled: 'fr-badge--warning',
    archived: '',
  }[s] || ''
}

function stateLabel(s: string) {
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[s] || s
}

async function publish() {
  publishing.value = true
  result.value = ''
  try {
    const data = await post(`/api/collections/${id}/publish`, form.value)
    pub.value = await get(`/api/collections/${id}/publication`)
    result.value = `Publie en mode ${data.modes.alias ? 'alias' : ''}${data.modes.tool ? ' + tool' : ''}${data.modes.embed ? ' + #collection' : ''}`
  } catch (e: any) {
    result.value = `Erreur: ${e.message}`
  }
  publishing.value = false
}

async function unpublish() {
  await post(`/api/collections/${id}/unpublish`)
  pub.value = await get(`/api/collections/${id}/publication`)
}

async function archive() {
  await post(`/api/collections/${id}/archive`)
  pub.value = await get(`/api/collections/${id}/publication`)
}

onMounted(async () => {
  try {
    pub.value = await get(`/api/collections/${id}/publication`)
    if (pub.value) {
      form.value.alias_enabled = pub.value.alias_enabled
      form.value.alias_name = pub.value.alias_name || `MirAI ${id}`
      form.value.alias_description = pub.value.alias_description || ''
      form.value.tool_enabled = pub.value.tool_enabled
      form.value.tool_methods = pub.value.tool_methods || [...allMethods]
      form.value.embed_enabled = pub.value.embed_enabled
      form.value.visibility = pub.value.visibility || 'all'
      form.value.visibility_group = pub.value.visibility_group || `myrag/${id}`
    }
  } catch (e) {}
})
</script>
