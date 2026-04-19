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

    <!-- Duplicate warning -->
    <div v-if="duplicateWarning" class="fr-alert fr-alert--warning fr-mb-4w">
      <h3 class="fr-alert__title">Collection similaire detectee</h3>
      <p>{{ duplicateWarning.message }}</p>
      <div v-if="duplicateWarning.existing" class="fr-mt-2w">
        <p><strong>Collection existante :</strong> {{ duplicateWarning.existing.name }}
          <span v-if="duplicateWarning.existing.description"> — {{ duplicateWarning.existing.description }}</span>
        </p>
        <p v-if="duplicateWarning.existing.contact_name">
          <strong>Responsable :</strong> {{ duplicateWarning.existing.contact_name }}
          <a v-if="duplicateWarning.existing.contact_email"
             :href="`mailto:${duplicateWarning.existing.contact_email}?subject=Demande d'acces a la collection ${duplicateWarning.existing.name}&body=Bonjour,%0A%0AJe souhaitais creer une collection similaire (${form.name}).%0APourriez-vous m'accorder l'acces a la votre pour federer nos efforts ?%0A%0AMerci.`"
             class="fr-link">
            📧 {{ duplicateWarning.existing.contact_email }}
          </a>
        </p>
      </div>
      <div class="fr-callout fr-callout--brown-caramel fr-mt-2w">
        <p class="fr-callout__text">
          <strong>Pourquoi eviter les doublons ?</strong> Dupliquer une collection degrade la qualite des reponses
          (sources contradictoires), double le cout d'indexation et de maintenance, et disperse les efforts
          d'amelioration (feedback, evaluation, prompt). Preferez contribuer a la collection existante.
        </p>
      </div>
      <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
        <NuxtLink :to="`/c/${duplicateWarning.existing?.name}`" class="fr-btn fr-btn--secondary">
          Voir la collection existante
        </NuxtLink>
        <button class="fr-btn fr-btn--tertiary" @click="duplicateWarning = null">
          Je veux quand meme creer la mienne
        </button>
      </div>
    </div>

    <div class="fr-col-8">
      <div class="fr-input-group" :class="nameStatus === 'taken' ? 'fr-input-group--error' : nameStatus === 'available' ? 'fr-input-group--valid' : ''">
        <label class="fr-label" for="name">
          Nom de la collection *
          <span class="fr-hint-text">Identifiant unique, en minuscules, sans espaces (ex: droit-etrangers, faq-rh, doc-technique-v2)</span>
        </label>
        <div style="display:flex;gap:0.5rem;align-items:flex-start;">
          <input id="name" class="fr-input" v-model="form.name" placeholder="un-nom-clair-et-unique"
                 @blur="checkDuplicates" @input="nameStatus = ''" style="flex:1;" />
          <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="checkNameAvailability" :disabled="!form.name.trim()">
            Verifier
          </button>
        </div>
        <p v-if="nameStatus === 'available'" class="fr-valid-text">✓ Ce nom est disponible</p>
        <p v-if="nameStatus === 'taken'" class="fr-error-text">Ce nom est deja utilise</p>
        <div v-if="nameSuggestion" class="fr-mt-1w" style="display:flex;align-items:center;gap:0.5rem;">
          <span class="fr-text--sm" style="color:#666;">Suggestion :</span>
          <code class="fr-text--sm">{{ nameSuggestion }}</code>
          <button class="fr-btn fr-btn--sm fr-btn--tertiary" @click="form.name = nameSuggestion; nameSuggestion = ''; checkNameAvailability()">
            Utiliser
          </button>
        </div>
      </div>

      <div class="fr-input-group fr-mt-2w">
        <label class="fr-label" for="desc">
          Description
          <span class="fr-hint-text">Decrivez le contenu et l'objectif de cette collection. Ce texte apparaitra dans le catalogue et aidera les autres utilisateurs a trouver votre collection.</span>
        </label>
        <textarea id="desc" class="fr-input" v-model="form.description" rows="2"
               :placeholder="descPlaceholders[source] || 'Ex: Documentation juridique sur le droit des etrangers, mise a jour quotidiennement depuis Legifrance.'"></textarea>
      </div>

      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Type de collection (decoupage + prompt systeme)</label>
        <select class="fr-select" v-model="selectedProfile" @change="applyProfile">
          <option v-for="p in profiles" :key="p.key" :value="p.key">
            {{ p.icon }} {{ p.label }}
          </option>
        </select>
        <p class="fr-hint-text">{{ currentProfileDesc }}</p>
      </div>

      <fieldset class="fr-fieldset fr-mt-2w">
        <legend class="fr-fieldset__legend">Options</legend>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="graph" v-model="form.graph_enabled"
                   @change="onGraphToggle" />
            <label class="fr-label" for="graph">Activer le graph de references</label>
          </div>
          <details class="fr-mt-1w fr-ml-4w">
            <summary class="fr-text--sm" style="cursor:pointer;color:#000091;">En savoir plus sur le graph</summary>
            <div class="fr-callout fr-callout--green-emeraude fr-mt-1w">
              <p class="fr-callout__text fr-text--sm">
                Le <strong>graph de references</strong> cartographie les liens entre les documents de votre collection
                (par exemple, les renvois entre articles d'un code juridique).
                Il permet de naviguer visuellement dans les relations entre documents
                et d'enrichir les reponses du RAG avec le contexte des documents lies.
              </p>
              <p class="fr-callout__text fr-text--sm fr-mt-1w">
                <strong>Quand l'activer ?</strong>
              </p>
              <ul class="fr-text--sm">
                <li>✅ Codes juridiques (references croisees entre articles)</li>
                <li>✅ Documentation technique avec renvois entre sections</li>
                <li>✅ Corpus de normes ou specifications liees entre elles</li>
                <li>❌ Pas utile pour les FAQ, fichiers independants, ou corpus sans liens internes</li>
              </ul>
            </div>
          </details>
        </div>
        <div v-if="form.graph_enabled" class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="ai_summary" v-model="form.ai_summary_enabled" />
            <label class="fr-label" for="ai_summary">Resume IA des articles longs dans le graph</label>
          </div>
          <details class="fr-mt-1w fr-ml-4w">
            <summary class="fr-text--sm" style="cursor:pointer;color:#000091;">En savoir plus</summary>
            <div class="fr-callout fr-mt-1w">
              <p class="fr-callout__text fr-text--sm">
                Quand un article est tres long, le graph affiche un <strong>resume genere par l'IA</strong>
                pour ameliorer la lisibilite. <strong>L'article original n'est jamais modifie</strong> —
                le RAG utilise toujours le texte integral.
              </p>
            </div>
          </details>
        </div>
      </fieldset>

      <div class="fr-grid-row fr-grid-row--gutters fr-mt-2w" style="align-items:flex-start;">
        <div class="fr-col-6">
          <div class="fr-select-group">
            <label class="fr-label">
              Sensibilite
              <span class="fr-hint-text">Niveau de classification des documents de la collection</span>
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

          <!-- Group selector when scope = group -->
          <div v-if="form.scope === 'group'" class="fr-mt-2w">
            <label class="fr-label">
              Groupes autorises
              <span class="fr-hint-text">Recherchez parmi vos groupes Keycloak</span>
            </label>
            <div style="display:flex;gap:0.5rem;">
              <input class="fr-input" v-model="groupSearch" placeholder="Rechercher un groupe..."
                     @input="searchGroups" style="flex:1;" />
            </div>

            <!-- Search results -->
            <div v-if="groupResults.length > 0" class="fr-mt-1w"
                 style="border:1px solid var(--border-default-grey);border-radius:4px;max-height:150px;overflow-y:auto;">
              <button v-for="g in groupResults" :key="g.id"
                      class="fr-text--sm"
                      style="display:block;width:100%;text-align:left;padding:0.5rem 0.75rem;border:none;background:none;cursor:pointer;"
                      @mouseover="$event.target.style.background='#f6f6f6'"
                      @mouseleave="$event.target.style.background='none'"
                      @click="addGroup(g)">
                {{ g.path || g.name }}
              </button>
            </div>

            <!-- Selected groups -->
            <div v-if="form.scope_groups.length > 0" class="fr-mt-1w" style="display:flex;flex-wrap:wrap;gap:0.5rem;">
              <span v-for="(g, i) in form.scope_groups" :key="i"
                    class="fr-tag fr-tag--sm fr-tag--dismiss"
                    @click="form.scope_groups.splice(i, 1)">
                {{ g }}
              </span>
            </div>
            <p v-else class="fr-text--sm fr-mt-1w" style="color:#666;">Aucun groupe selectionne</p>
          </div>

          <!-- Private info -->
          <div v-if="form.scope === 'private'" class="fr-mt-1w">
            <p class="fr-text--sm" style="color:#666;">
              Seul vous pourrez voir et utiliser cette collection. Utile pour tester
              avant de publier a un groupe ou au ministere.
            </p>
          </div>
        </div>
      </div>

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
const { getUserName, user } = useAuth()

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

// Group search
const groupSearch = ref('')
const groupResults = ref<any[]>([])
const userGroups = ref<any[]>([])

async function searchGroups() {
  if (!groupSearch.value.trim()) {
    groupResults.value = []
    return
  }
  const q = groupSearch.value.toLowerCase()
  groupResults.value = userGroups.value.filter(g =>
    (g.name || '').toLowerCase().includes(q) ||
    (g.path || '').toLowerCase().includes(q)
  ).filter(g => !form.value.scope_groups.includes(g.path || g.name))
}

function addGroup(g: any) {
  const name = g.path || g.name
  if (!form.value.scope_groups.includes(name)) {
    form.value.scope_groups.push(name)
  }
  groupSearch.value = ''
  groupResults.value = []
}

function onGraphToggle() {
  if (!form.value.graph_enabled) {
    form.value.ai_summary_enabled = false
  }
}

// Profils couples : strategie + prompt + options
const profiles = [
  { key: 'juridique', icon: '⚖️', label: 'Code juridique (articles + citations)', strategy: 'article', prompt: 'juridique', graph: true, desc: 'Decoupage par article avec hierarchie Livre/Titre/Chapitre. Le LLM cite les numeros d\'articles.' },
  { key: 'faq', icon: '❓', label: 'FAQ / Questions-reponses', strategy: 'qr', prompt: 'faq', graph: false, desc: 'Decoupage par question-reponse. Le LLM donne des reponses directes avec la source.' },
  { key: 'rapport', icon: '📊', label: 'Rapport / Document structure', strategy: 'section', prompt: 'technique', graph: false, desc: 'Decoupage par section (titres markdown). Le LLM cite les sections et pages.' },
  { key: 'corpus', icon: '📚', label: 'Corpus multi-documents', strategy: 'auto', prompt: 'multi_thematique', graph: false, desc: 'Detection automatique du type. Le LLM croise les sources de plusieurs documents.' },
  { key: 'multimedia', icon: '🎬', label: 'Multimedia (images, audio, video)', strategy: 'auto', prompt: 'multimedia', graph: false, desc: 'Transcriptions audio, descriptions d\'images. Le LLM cite les timecodes et fichiers.' },
  { key: 'generique', icon: '📄', label: 'Generique (detection automatique)', strategy: 'auto', prompt: 'generic', graph: false, desc: 'Decoupage et prompt automatiques. Adapte a tout type de document.' },
]

const defaultProfile: Record<string, string> = {
  legifrance: 'juridique', file: 'generique', directory: 'corpus',
  drive: 'corpus', nextcloud: 'corpus', resana: 'corpus',
}

const selectedProfile = ref(defaultProfile[source] || 'generique')
const currentProfileDesc = computed(() => profiles.find(p => p.key === selectedProfile.value)?.desc || '')

function applyProfile() {
  const p = profiles.find(pr => pr.key === selectedProfile.value)
  if (p) {
    form.value.strategy = p.strategy
    form.value.prompt_template = p.prompt
    form.value.graph_enabled = p.graph
  }
}

const initProfile = profiles.find(p => p.key === (defaultProfile[source] || 'generique'))

const form = ref({
  name: '', description: '',
  strategy: initProfile?.strategy || 'auto',
  sensitivity: 'public',
  prompt_template: initProfile?.prompt || 'generic',
  scope: 'group',
  graph_enabled: initProfile?.graph || false,
  ai_summary_enabled: false,
  contact_name: '', contact_email: '',
  scope_groups: [] as string[],
})

const templates = ref<any[]>([])
const allCollections = ref<any[]>([])
const creating = ref(false)
const error = ref('')
const duplicateWarning = ref<any>(null)
const nameStatus = ref('')  // '' | 'available' | 'taken'
const nameSuggestion = ref('')

function checkNameAvailability() {
  if (!form.value.name.trim()) return
  const name = form.value.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
  form.value.name = name  // normalize

  const exists = allCollections.value.some(c => c.name.toLowerCase() === name)
  if (exists) {
    nameStatus.value = 'taken'
    // Generate suggestion by appending version number
    let suffix = 2
    while (allCollections.value.some(c => c.name.toLowerCase() === `${name}-v${suffix}`)) {
      suffix++
    }
    nameSuggestion.value = `${name}-v${suffix}`
  } else {
    nameStatus.value = 'available'
    nameSuggestion.value = ''
  }
}

async function checkDuplicates() {
  if (!form.value.name.trim()) return
  const name = form.value.name.toLowerCase()

  // Check for similar names
  const similar = allCollections.value.find(c => {
    const n = c.name.toLowerCase()
    return n === name
      || n.includes(name)
      || name.includes(n)
      || (source === 'legifrance' && c.source?.type === 'legifrance')
  })

  if (similar) {
    duplicateWarning.value = {
      message: similar.name.toLowerCase() === name
        ? `Une collection "${similar.name}" existe deja.`
        : `Une collection similaire "${similar.name}" existe deja.`,
      existing: similar,
    }
  } else {
    duplicateWarning.value = null
  }
}

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
    const [tplData, colData] = await Promise.all([
      get('/api/collections/templates'),
      get('/api/collections'),
    ])
    templates.value = tplData.templates || []
    allCollections.value = colData.collections || []
  } catch (e) {}

  // Load user groups from Keycloak (via auth profile)
  if (user.value?.profile?.groups) {
    userGroups.value = user.value.profile.groups.map((g: string) => ({ name: g.split('/').pop(), path: g }))
  }

  // Pre-fill contact from session
  if (user.value?.profile) {
    const p = user.value.profile
    if (!form.value.contact_name) {
      form.value.contact_name = p.name || p.preferred_username || ''
    }
    if (!form.value.contact_email) {
      form.value.contact_email = p.email || ''
    }
  }
})
</script>
