<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Configuration</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Configuration — {{ id }}</h1>

    <div v-if="loading" class="fr-callout"><p>Chargement...</p></div>

    <div v-else class="fr-col-8">
      <!-- Description -->
      <div class="fr-input-group">
        <label class="fr-label">
          Description
          <span class="fr-hint-text">Ce texte apparait dans le catalogue et aide les autres utilisateurs a trouver votre collection.</span>
        </label>
        <textarea class="fr-input" v-model="form.description" rows="2"
                  placeholder="Ex: Documentation juridique sur le droit des etrangers"></textarea>
      </div>

      <!-- Type de collection (profil couple) -->
      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Type de collection (decoupage + prompt systeme)</label>
        <select class="fr-select" v-model="selectedProfile" @change="applyProfile">
          <option v-for="p in profiles" :key="p.key" :value="p.key">
            {{ p.icon }} {{ p.label }}
          </option>
        </select>
        <p class="fr-hint-text">{{ currentProfileDesc }}</p>
      </div>

      <!-- Reindex warning -->
      <div v-if="needsReindex" class="fr-alert fr-alert--warning fr-alert--sm fr-mt-2w">
        <p>
          <strong>Attention :</strong> vous avez modifie le type de collection (strategie de decoupage ou prompt).
          Les documents deja indexes ne seront pas re-decoupes automatiquement.
        </p>
        <div class="fr-btns-group fr-btns-group--inline fr-mt-1w">
          <button v-if="hasSourceFiles" class="fr-btn fr-btn--sm" @click="reindex" :disabled="reindexing">
            {{ reindexing ? 'Re-indexation...' : 'Re-indexer avec la nouvelle strategie' }}
          </button>
          <span v-else class="fr-text--sm" style="color:#666;">
            Aucun fichier source enregistre —
            <NuxtLink :to="`/c/${id}/upload`" class="fr-link">re-chargez vos documents</NuxtLink>.
          </span>
        </div>
        <div v-if="reindexResult" class="fr-mt-1w">
          <p class="fr-text--sm" style="color:#18753c;">
            Re-indexation lancee : {{ reindexResult.files_reindexed }} fichier(s) en cours de traitement.
          </p>
        </div>
      </div>

      <!-- Options -->
      <fieldset class="fr-fieldset fr-mt-2w">
        <legend class="fr-fieldset__legend">Options</legend>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="graph" v-model="form.graph_enabled" />
            <label class="fr-label" for="graph">Activer le graph de references</label>
          </div>
          <details class="fr-mt-1w fr-ml-4w">
            <summary class="fr-text--sm" style="cursor:pointer;color:#000091;">En savoir plus sur le graph</summary>
            <div class="fr-callout fr-callout--green-emeraude fr-mt-1w">
              <p class="fr-callout__text fr-text--sm">
                Le <strong>graph de references</strong> cartographie les liens entre les documents
                (renvois entre articles, references croisees). Il permet de naviguer visuellement
                et d'enrichir les reponses du RAG.
              </p>
            </div>
          </details>
        </div>
        <div v-if="form.graph_enabled" class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="ai_summary" v-model="form.ai_summary_enabled" />
            <label class="fr-label" for="ai_summary">Resume IA des articles longs dans le graph</label>
          </div>
        </div>
        <div v-if="form.ai_summary_enabled" class="fr-fieldset__element fr-ml-4w">
          <div class="fr-input-group">
            <label class="fr-label">Seuil (caracteres)</label>
            <input class="fr-input" type="number" v-model.number="form.ai_summary_threshold" min="100" />
          </div>
        </div>
      </fieldset>

      <!-- Sensibilite + Portee -->
      <div class="fr-grid-row fr-grid-row--gutters fr-mt-2w" style="align-items:flex-start;">
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">
              Sensibilite
              <span class="fr-hint-text">Niveau de classification des documents</span>
            </label>
            <select class="fr-select" v-model="form.sensitivity">
              <option value="public">Donnees ouvertes</option>
              <option value="internal">Interne au ministeriel</option>
              <option value="personal">Donnees personnelles</option>
              <option value="confidential">Confidentiel</option>
              <option value="restricted">Diffusion restreinte</option>
            </select>
          </div>
        </div>
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">
              Portee
              <span class="fr-hint-text">Qui pourra acceder a cette collection</span>
            </label>
            <select class="fr-select" v-model="form.scope">
              <option value="public">Tout le ministere</option>
              <option value="group">Un ou plusieurs groupes</option>
              <option value="private">Prive (pour evaluation)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Contact -->
      <div class="fr-input-group fr-mt-3w">
        <label class="fr-label">Responsable / contact</label>
        <input class="fr-input" v-model="form.contact_name" placeholder="Nom du responsable" />
      </div>
      <div class="fr-input-group fr-mt-1w">
        <label class="fr-label">Email de contact</label>
        <input class="fr-input" type="email" v-model="form.contact_email" placeholder="responsable@example.com" />
      </div>

      <!-- Actions -->
      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink :to="`/c/${id}`" class="fr-btn fr-btn--secondary">← Retour</NuxtLink>
        <button class="fr-btn" @click="save" :disabled="saving">
          {{ saving ? 'Sauvegarde...' : 'Sauvegarder' }}
        </button>
      </div>

      <div v-if="savedMsg" class="fr-alert fr-mt-2w" :class="savedClass">
        <p>{{ savedMsg }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { get, post, patch } = useApi()

const loading = ref(true)
const saving = ref(false)
const savedMsg = ref('')
const savedClass = ref('fr-alert--success')
const isNew = ref(false)
const selectedProfile = ref('generique')
const initialStrategy = ref('')
const initialPrompt = ref('')

const hasSourceFiles = ref(false)
const reindexing = ref(false)
const reindexResult = ref<any>(null)

const needsReindex = computed(() => {
  if (!initialStrategy.value) return false
  return form.value.strategy !== initialStrategy.value
    || form.value.prompt_template !== initialPrompt.value
})

const profiles = [
  { key: 'generique', icon: '📄', label: 'Generique', strategy: 'auto', prompt: 'generic', graph: false, desc: 'Pour tout type de document sans specialisation. Decoupage automatique.' },
  { key: 'juridique', icon: '⚖️', label: 'Juridique (codes, lois)', strategy: 'article', prompt: 'juridique', graph: true, desc: 'Decoupage par article avec hierarchie Livre/Titre/Chapitre. Citations d\'articles dans les reponses.' },
  { key: 'faq', icon: '❓', label: 'FAQ / Questions-reponses', strategy: 'qr', prompt: 'faq', graph: false, desc: 'Decoupage par question/reponse. Reponses directes avec source.' },
  { key: 'technique', icon: '🔧', label: 'Documentation technique', strategy: 'section', prompt: 'technique', graph: false, desc: 'Decoupage par section/chapitre. References croisees entre sections.' },
  { key: 'multimedia', icon: '🎬', label: 'Multimedia (images, audio, video)', strategy: 'auto', prompt: 'multimedia', graph: false, desc: 'Transcriptions audio, descriptions d\'images. Citations avec timecodes.' },
  { key: 'multi', icon: '📚', label: 'Corpus multi-thematique', strategy: 'auto', prompt: 'multi_thematique', graph: false, desc: 'Gros corpus couvrant plusieurs domaines avec des documents varies.' },
]

const currentProfileDesc = computed(() => {
  return profiles.find(p => p.key === selectedProfile.value)?.desc || ''
})

const form = ref({
  description: '',
  strategy: 'auto',
  sensitivity: 'public',
  scope: 'group',
  prompt_template: 'generic',
  graph_enabled: false,
  ai_summary_enabled: false,
  ai_summary_threshold: 1000,
  contact_name: '',
  contact_email: '',
})

function applyProfile() {
  const p = profiles.find(pr => pr.key === selectedProfile.value)
  if (p) {
    form.value.strategy = p.strategy
    form.value.prompt_template = p.prompt
    form.value.graph_enabled = p.graph
  }
}

onMounted(async () => {
  try {
    const config = await get(`/api/collections/${id}`)
    form.value = {
      description: config.description || '',
      strategy: config.strategy || 'auto',
      sensitivity: config.sensitivity || 'public',
      scope: config.scope || 'group',
      prompt_template: config.prompt_template || 'generic',
      graph_enabled: config.graph_enabled || false,
      ai_summary_enabled: config.ai_summary_enabled || false,
      ai_summary_threshold: config.ai_summary_threshold || 1000,
      contact_name: config.contact_name || '',
      contact_email: config.contact_email || '',
    }
    initialStrategy.value = form.value.strategy
    initialPrompt.value = form.value.prompt_template
    // Match profile from saved config
    const match = profiles.find(p => p.strategy === form.value.strategy && p.prompt === form.value.prompt_template)
    if (match) selectedProfile.value = match.key
  } catch {
    isNew.value = true
  }
  // Check if source files exist for reindex
  try {
    const sources = await get(`/api/ingest/${id}/sources`)
    hasSourceFiles.value = (sources.sources?.length || 0) > 0
  } catch {}

  loading.value = false
})

async function reindex() {
  reindexing.value = true
  reindexResult.value = null
  try {
    const result = await post(`/api/ingest/${id}/reindex?strategy=${form.value.strategy}&sensitivity=${form.value.sensitivity}`, {})
    reindexResult.value = result
  } catch (e: any) {
    savedMsg.value = `Erreur re-indexation: ${e.message}`
    savedClass.value = 'fr-alert--error'
  }
  reindexing.value = false
}

async function save() {
  saving.value = true
  savedMsg.value = ''
  try {
    if (isNew.value) {
      await post('/api/collections', { name: id, ...form.value })
      isNew.value = false
    } else {
      await patch(`/api/collections/${id}`, form.value)
    }
    savedMsg.value = 'Configuration sauvegardee.'
    savedClass.value = 'fr-alert--success'
  } catch (e: any) {
    savedMsg.value = `Erreur: ${e.message}`
    savedClass.value = 'fr-alert--error'
  }
  saving.value = false
  setTimeout(() => { savedMsg.value = '' }, 4000)
}
</script>
