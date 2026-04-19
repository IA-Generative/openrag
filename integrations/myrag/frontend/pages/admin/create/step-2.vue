<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Creer</NuxtLink></li>
        <li aria-current="page">Identification</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Identification de la collection</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 2 sur 5 — Source : {{ sourceLabel }}</p>

    <WizardStepper :current-step="2" />

    <div class="fr-col-8">
      <div class="fr-input-group">
        <label class="fr-label" for="name">Nom de la collection *</label>
        <input id="name" class="fr-input" v-model="form.name" placeholder="ceseda-v4" />
      </div>

      <div class="fr-input-group fr-mt-2w">
        <label class="fr-label" for="desc">Description</label>
        <textarea id="desc" class="fr-input" v-model="form.description" rows="2"
               :placeholder="descPlaceholders[source] || 'Description'"></textarea>
      </div>

      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Prompt systeme de la collection</label>
        <select class="fr-select" v-model="form.prompt_template">
          <option v-for="tpl in templates" :key="tpl.key" :value="tpl.key">
            {{ tpl.icon }} {{ tpl.name }}
          </option>
        </select>
      </div>

      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Strategie de decoupage</label>
        <select class="fr-select" v-model="form.strategy">
          <option value="auto">Automatique (detection du type)</option>
          <option value="article">Par article (code juridique)</option>
          <option value="section">Par section (rapport)</option>
          <option value="qr">Par Q&R (FAQ)</option>
          <option value="length">Par longueur fixe</option>
        </select>
      </div>

      <div class="fr-grid-row fr-grid-row--gutters fr-mt-2w">
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">Sensibilite</label>
            <select class="fr-select" v-model="form.sensitivity">
              <option value="public">Public</option>
              <option value="internal">Interne</option>
              <option value="restricted">Restreint</option>
              <option value="confidential">Confidentiel</option>
            </select>
          </div>
        </div>
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">Portee</label>
            <select class="fr-select" v-model="form.scope">
              <option value="public">General (tous)</option>
              <option value="group">Groupe</option>
              <option value="private">Prive</option>
            </select>
          </div>
        </div>
      </div>

      <fieldset class="fr-fieldset fr-mt-3w">
        <legend class="fr-fieldset__legend">Options</legend>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="graph" v-model="form.graph_enabled" />
            <label class="fr-label" for="graph">Activer le graph de references</label>
          </div>
        </div>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="ai_summary" v-model="form.ai_summary_enabled" />
            <label class="fr-label" for="ai_summary">Resume IA pour les articles longs</label>
          </div>
        </div>
      </fieldset>

      <div class="fr-input-group fr-mt-3w">
        <label class="fr-label">Responsable / contact</label>
        <input class="fr-input" v-model="form.contact_name" placeholder="Nom du responsable" />
      </div>
      <div class="fr-input-group fr-mt-1w">
        <label class="fr-label">Email de contact</label>
        <input class="fr-input" type="email" v-model="form.contact_email" placeholder="responsable@example.com" />
      </div>

      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink to="/admin/create" class="fr-btn fr-btn--secondary">← Precedent</NuxtLink>
        <button class="fr-btn" @click="createAndNext" :disabled="creating || !form.name.trim()">
          {{ creating ? 'Creation...' : 'Suivant →' }}
        </button>
      </div>

      <div v-if="error" class="fr-alert fr-alert--error fr-mt-2w"><p>{{ error }}</p></div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const router = useRouter()
const { get, post } = useApi()

const source = (route.query.source as string) || 'file'

const sourceLabels: Record<string, string> = {
  legifrance: '⚖️ Legifrance', file: '📄 Fichier unique', directory: '📁 Repertoire',
  drive: '☁️ Drive', nextcloud: '📦 Nextcloud', resana: '🗂️ Resana',
}
const sourceLabel = sourceLabels[source] || source

const descPlaceholders: Record<string, string> = {
  legifrance: 'Code de l\'entree et du sejour des etrangers',
  file: 'Description du document', directory: 'Description du corpus',
  drive: 'Dossier Drive a synchroniser', nextcloud: 'Dossier Nextcloud', resana: 'Espace Resana',
}

const defaultStrategies: Record<string, string> = {
  legifrance: 'article', file: 'auto', directory: 'auto',
  drive: 'auto', nextcloud: 'auto', resana: 'auto',
}
const defaultTemplates: Record<string, string> = {
  legifrance: 'juridique', file: 'generic', directory: 'multi_thematique',
  drive: 'multi_thematique', nextcloud: 'multi_thematique', resana: 'multi_thematique',
}

const form = ref({
  name: '', description: '',
  strategy: defaultStrategies[source] || 'auto',
  sensitivity: 'public',
  prompt_template: defaultTemplates[source] || 'generic',
  scope: 'group',
  graph_enabled: source === 'legifrance',
  ai_summary_enabled: false,
  contact_name: '', contact_email: '',
})

const templates = ref<any[]>([])
const creating = ref(false)
const error = ref('')

async function createAndNext() {
  creating.value = true
  error.value = ''
  try {
    await post('/api/collections', form.value)
    router.push(`/admin/create/step-3?collection=${form.value.name}&source=${source}`)
  } catch (e: any) {
    error.value = e.message
  }
  creating.value = false
}

onMounted(async () => {
  try {
    const data = await get('/api/collections/templates')
    templates.value = data.templates || []
  } catch (e) {}
})
</script>
