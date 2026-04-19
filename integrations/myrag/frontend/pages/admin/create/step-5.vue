<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Creer</NuxtLink></li>
        <li aria-current="page">Publication</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Publication — {{ collection }}</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 5 sur 5 — Choisissez comment publier</p>

    <WizardStepper :current-step="5" />

    <div v-if="!collection" class="fr-alert fr-alert--warning fr-mb-4w">
      <p>Aucune collection specifiee. <NuxtLink to="/admin/create">Retour a l'etape 1</NuxtLink></p>
    </div>

    <div v-else class="fr-col-8">
      <!-- Summary -->
      <div v-if="config" class="fr-table fr-mb-4w">
        <table>
          <caption>Resume de la collection</caption>
          <tbody>
            <tr><td><strong>Nom</strong></td><td>{{ config.name || collection }}</td></tr>
            <tr><td><strong>Description</strong></td><td>{{ config.description || '—' }}</td></tr>
            <tr><td><strong>Strategie</strong></td><td>{{ config.strategy || 'auto' }}</td></tr>
            <tr><td><strong>Sensibilite</strong></td><td>{{ config.sensitivity || 'public' }}</td></tr>
            <tr v-if="config.graph_enabled"><td><strong>Graph</strong></td><td>Active</td></tr>
            <tr v-if="config.contact_name"><td><strong>Contact</strong></td><td>{{ config.contact_name }} {{ config.contact_email ? `(${config.contact_email})` : '' }}</td></tr>
          </tbody>
        </table>
      </div>

      <div v-if="configError" class="fr-alert fr-alert--info fr-alert--sm fr-mb-4w">
        <p>Configuration de la collection non trouvee. Les valeurs par defaut seront utilisees.</p>
      </div>

      <!-- Publication modes -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Modes de publication</h3>
            <fieldset class="fr-fieldset">
              <div class="fr-fieldset__element">
                <div class="fr-checkbox-group">
                  <input type="checkbox" id="alias" v-model="form.alias_enabled" />
                  <label class="fr-label" for="alias">
                    Alias de modele dans Open WebUI
                    <span class="fr-hint-text">Visible dans le dropdown de modeles OWUI</span>
                  </label>
                </div>
              </div>
              <div v-if="form.alias_enabled" class="fr-fieldset__element fr-ml-4w">
                <div class="fr-input-group">
                  <label class="fr-label">Nom affiche dans Open WebUI</label>
                  <input class="fr-input" v-model="form.alias_name" :placeholder="`MirAI ${collection}`" />
                </div>
              </div>
              <div class="fr-fieldset__element">
                <div class="fr-checkbox-group">
                  <input type="checkbox" id="tool" v-model="form.tool_enabled" />
                  <label class="fr-label" for="tool">
                    Tool MyRAG
                    <span class="fr-hint-text">Recherche + graph + articles dans OWUI</span>
                  </label>
                </div>
              </div>
              <div class="fr-fieldset__element">
                <div class="fr-checkbox-group">
                  <input type="checkbox" id="embed" v-model="form.embed_enabled" />
                  <label class="fr-label" for="embed">
                    #{{ collection }} dans le prompt
                    <span class="fr-hint-text">Les utilisateurs tapent #{{ collection }} pour activer le RAG</span>
                  </label>
                </div>
              </div>
            </fieldset>
          </div>
        </div>
      </div>

      <!-- Visibility -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Visibilite</h3>
            <fieldset class="fr-fieldset">
              <div class="fr-fieldset__element">
                <div class="fr-radio-group">
                  <input type="radio" id="v-all" value="all" v-model="form.visibility" />
                  <label class="fr-label" for="v-all">Tous les utilisateurs</label>
                </div>
              </div>
              <div class="fr-fieldset__element">
                <div class="fr-radio-group">
                  <input type="radio" id="v-group" value="group" v-model="form.visibility" />
                  <label class="fr-label" for="v-group">Membres de groupes Keycloak</label>
                </div>
              </div>
              <div v-if="form.visibility === 'group'" class="fr-fieldset__element fr-ml-4w">
                <div v-if="loadingGroups" class="fr-text--sm" style="color:#666;">Chargement des groupes...</div>
                <div v-else-if="availableGroups.length === 0">
                  <p class="fr-text--sm" style="color:#666;">Aucun groupe MyRAG trouve dans Keycloak.</p>
                  <div class="fr-input-group fr-mt-1w">
                    <label class="fr-label">
                      Creer un groupe pour cette collection
                      <span class="fr-hint-text">Convention : /myrag/{{ collection }}</span>
                    </label>
                    <div style="display:flex;gap:0.5rem;align-items:flex-start;">
                      <input class="fr-input" v-model="newGroupName" :placeholder="collection" style="flex:1;" />
                      <button class="fr-btn fr-btn--sm" @click="createGroup" :disabled="creatingGroup || !newGroupName.trim()">
                        {{ creatingGroup ? 'Creation...' : 'Creer' }}
                      </button>
                    </div>
                  </div>
                  <div v-if="groupCreated" class="fr-alert fr-alert--success fr-alert--sm fr-mt-1w">
                    <p>Groupe <strong>/myrag/{{ groupCreated }}</strong> cree. Le groupe sera visible dans
                      <a href="http://localhost:3000" target="_blank" class="fr-link">keycloak-comu</a>
                      pour gerer les membres.
                    </p>
                  </div>
                  <div v-if="groupError" class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w">
                    <p>{{ groupError }}</p>
                  </div>
                </div>
                <div v-else>
                  <p class="fr-text--sm fr-mb-1w">Selectionner les groupes autorises :</p>
                  <div v-for="g in availableGroups" :key="g.id" class="fr-checkbox-group fr-mb-1v">
                    <input type="checkbox" :id="`grp-${g.id}`" :value="g.path"
                           v-model="form.visibility_groups" />
                    <label class="fr-label" :for="`grp-${g.id}`">
                      {{ g.name }}
                      <span class="fr-hint-text">{{ g.path }}</span>
                    </label>
                  </div>
                </div>
              </div>
              <div class="fr-fieldset__element">
                <div class="fr-radio-group">
                  <input type="radio" id="v-private" value="private" v-model="form.visibility" />
                  <label class="fr-label" for="v-private">Prive (createur uniquement)</label>
                </div>
              </div>
            </fieldset>
          </div>
        </div>
      </div>

      <!-- Widget -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Integration externe</h3>
            <fieldset class="fr-fieldset">
              <div class="fr-fieldset__element">
                <div class="fr-checkbox-group">
                  <input type="checkbox" id="widget" v-model="form.widget_enabled" />
                  <label class="fr-label" for="widget">
                    Widget overlay (embed.js)
                    <span class="fr-hint-text">Integrer le chatbot dans n'importe quelle page web</span>
                  </label>
                </div>
              </div>
              <div v-if="form.widget_enabled" class="fr-fieldset__element fr-ml-4w">
                <p class="fr-text--sm fr-mb-1w">Snippet a integrer :</p>
                <pre class="fr-p-1w" style="background:#f6f6f6;border-radius:4px;font-size:0.75rem;overflow-x:auto;">&lt;script src="{{ myragUrl }}/widget/embed.js"
  data-collection="{{ collection }}"
  data-position="bottom-right"
  data-auth="keycloak"&gt;&lt;/script&gt;</pre>
                <button class="fr-btn fr-btn--sm fr-btn--tertiary fr-mt-1w" @click="copySnippet">
                  Copier le snippet
                </button>
                <span v-if="copied" class="fr-text--xs fr-ml-1w" style="color:#18753c;">Copie !</span>
              </div>
              <div class="fr-fieldset__element">
                <div class="fr-checkbox-group">
                  <input type="checkbox" id="browser" v-model="form.browser_enabled" />
                  <label class="fr-label" for="browser">
                    Extension navigateur MirAI
                    <span class="fr-hint-text">Accessible depuis le panneau lateral du navigateur</span>
                  </label>
                </div>
              </div>
              <div v-if="form.browser_enabled" class="fr-fieldset__element fr-ml-4w">
                <div class="fr-input-group">
                  <label class="fr-label">URL a configurer dans l'extension</label>
                  <input class="fr-input" :value="`${myragUrl}/widget/chat?collection=${collection}`" readonly
                         @click="($event.target as HTMLInputElement).select()" />
                </div>
              </div>
            </fieldset>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="fr-btns-group fr-btns-group--inline fr-mt-4w">
        <NuxtLink :to="`/admin/create/step-4?collection=${collection}`" class="fr-btn fr-btn--secondary">
          ← Precedent
        </NuxtLink>
        <button class="fr-btn fr-btn--tertiary" @click="saveDraft" :disabled="publishing">
          Sauvegarder en brouillon
        </button>
        <button class="fr-btn" @click="publish" :disabled="publishing">
          {{ publishing ? 'Publication...' : 'Publier la collection' }}
        </button>
      </div>

      <!-- Result message -->
      <div v-if="result" class="fr-alert fr-mt-2w" :class="resultClass">
        <p>{{ result }}</p>
        <NuxtLink v-if="published" :to="`/c/${collection}`" class="fr-link fr-mt-1w">
          Ouvrir la collection →
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const collection = route.query.collection as string
const { get, post, baseUrl: myragUrl } = useApi()

const config = ref<any>(null)
const configError = ref(false)
const publishing = ref(false)
const published = ref(false)
const result = ref('')
const resultClass = ref('fr-alert--info')
const copied = ref(false)

const availableGroups = ref<{ id: string; name: string; path: string }[]>([])
const loadingGroups = ref(false)
const newGroupName = ref(collection || '')
const creatingGroup = ref(false)
const groupCreated = ref('')
const groupError = ref('')

const form = ref({
  alias_enabled: true,
  alias_name: collection ? `📚 ${collection}` : '',
  tool_enabled: true,
  embed_enabled: false,
  visibility: 'group',
  visibility_groups: [`/myrag/${collection}`] as string[],
  widget_enabled: false,
  browser_enabled: false,
})

async function loadGroups() {
  loadingGroups.value = true
  try {
    const groups = await get('/api/sync/groups')
    // Filter out admin groups (ending with -admin or superadmin)
    availableGroups.value = (groups || []).filter((g: any) =>
      !g.name.endsWith('-admin') && g.name !== 'superadmin'
    )
  } catch {
    availableGroups.value = []
  }
  loadingGroups.value = false
}

async function createGroup() {
  if (!newGroupName.value.trim()) return
  creatingGroup.value = true
  groupError.value = ''
  groupCreated.value = ''
  try {
    await post('/api/sync/create-group', { name: newGroupName.value.trim() })
    groupCreated.value = newGroupName.value.trim()
    form.value.visibility_groups = [`/myrag/${newGroupName.value.trim()}`]
    // Reload groups
    await loadGroups()
  } catch (e: any) {
    groupError.value = `Erreur: ${e.message}`
  }
  creatingGroup.value = false
}

watch(() => form.value.visibility, (val) => {
  if (val === 'group' && availableGroups.value.length === 0) {
    loadGroups()
  }
})

onMounted(async () => {
  try {
    config.value = await get(`/api/collections/${collection}`)
  } catch {
    configError.value = true
  }
  if (form.value.visibility === 'group') {
    loadGroups()
  }
})

function copySnippet() {
  const snippet = `<script src="${myragUrl}/widget/embed.js" data-collection="${collection}" data-position="bottom-right" data-auth="keycloak"><\/script>`
  navigator.clipboard.writeText(snippet)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

async function saveDraft() {
  try {
    await post(`/api/collections/${collection}/publish`, {
      ...form.value,
      state: 'draft',
    })
    result.value = 'Collection sauvegardee en brouillon.'
    resultClass.value = 'fr-alert--info'
  } catch {
    result.value = 'Collection sauvegardee localement (le backend n\'a pas pu etre contacte).'
    resultClass.value = 'fr-alert--info'
  }
}

async function publish() {
  publishing.value = true
  result.value = ''
  try {
    await post(`/api/collections/${collection}/publish`, {
      ...form.value,
      alias_name: form.value.alias_name || `📚 ${collection}`,
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
</script>
