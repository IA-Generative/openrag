<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li aria-current="page">Creer une collection</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Creer une collection</h1>

    <div class="fr-col-8">
      <div class="fr-input-group">
        <label class="fr-label" for="name">Nom de la collection *</label>
        <input id="name" class="fr-input" v-model="form.name" placeholder="ceseda-v4" />
      </div>

      <div class="fr-input-group fr-mt-2w">
        <label class="fr-label" for="desc">Description</label>
        <input id="desc" class="fr-input" v-model="form.description"
               placeholder="Code de l'entree et du sejour des etrangers" />
      </div>

      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Strategie de decoupage</label>
        <select class="fr-select" v-model="form.strategy">
          <option value="auto">Automatique</option>
          <option value="article">Par article (code juridique)</option>
          <option value="section">Par section (rapport)</option>
          <option value="qr">Par Q&R (FAQ)</option>
          <option value="length">Par longueur fixe</option>
        </select>
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
        <label class="fr-label">Sensibilite</label>
        <select class="fr-select" v-model="form.sensitivity">
          <option value="public">Public</option>
          <option value="internal">Interne</option>
          <option value="restricted">Restreint</option>
          <option value="confidential">Confidentiel</option>
        </select>
      </div>

      <div class="fr-select-group fr-mt-2w">
        <label class="fr-label">Portee</label>
        <select class="fr-select" v-model="form.scope">
          <option value="public">General (tous les utilisateurs)</option>
          <option value="group">Groupe (membres uniquement)</option>
          <option value="private">Prive (createur uniquement)</option>
        </select>
      </div>

      <fieldset class="fr-fieldset fr-mt-4w">
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

      <fieldset class="fr-fieldset fr-mt-4w">
        <legend class="fr-fieldset__legend">Publication</legend>
        <div class="fr-fieldset__element">
          <div class="fr-checkbox-group">
            <input type="checkbox" id="publish_now" v-model="form.publish_now" />
            <label class="fr-label" for="publish_now">Publier immediatement dans Open WebUI</label>
          </div>
        </div>
        <div v-if="form.publish_now" class="fr-fieldset__element fr-ml-4w">
          <div class="fr-radio-group">
            <input type="radio" id="pub-alias" value="alias" v-model="form.publish_mode" />
            <label class="fr-label" for="pub-alias">Alias de modele seul</label>
          </div>
          <div class="fr-radio-group">
            <input type="radio" id="pub-both" value="both" v-model="form.publish_mode" />
            <label class="fr-label" for="pub-both">Alias + Tool MyRAG</label>
          </div>
          <div class="fr-radio-group">
            <input type="radio" id="pub-tool" value="tool" v-model="form.publish_mode" />
            <label class="fr-label" for="pub-tool">Tool seul</label>
          </div>
        </div>
      </fieldset>

      <button class="fr-btn fr-mt-4w" @click="create" :disabled="creating || !form.name.trim()">
        {{ creating ? 'Creation...' : 'Creer la collection' }}
      </button>

      <div v-if="error" class="fr-alert fr-alert--error fr-mt-2w"><p>{{ error }}</p></div>
      <div v-if="created" class="fr-alert fr-alert--success fr-mt-2w">
        <p>Collection "{{ form.name }}" creee ! <NuxtLink :to="`/c/${form.name}`">Ouvrir</NuxtLink></p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { get, post } = useApi()

const form = ref({
  name: '', description: '', strategy: 'auto', sensitivity: 'public',
  prompt_template: 'generic', scope: 'group', graph_enabled: false,
  ai_summary_enabled: false,
  publish_now: false, publish_mode: 'both',
})
const templates = ref<any[]>([])
const creating = ref(false)
const created = ref(false)
const error = ref('')

async function create() {
  creating.value = true
  error.value = ''
  created.value = false
  try {
    await post('/api/collections', form.value)
    created.value = true
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
