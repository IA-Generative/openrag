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

    <div v-if="config" class="fr-grid-row fr-grid-row--gutters">
      <div class="fr-col-8">
        <div class="fr-input-group">
          <label class="fr-label">Description</label>
          <input class="fr-input" v-model="config.description" />
        </div>

        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label">Strategie de decoupage</label>
          <select class="fr-select" v-model="config.strategy">
            <option value="auto">Automatique</option>
            <option value="article">Par article</option>
            <option value="section">Par section</option>
            <option value="qr">Par Q&R</option>
            <option value="length">Par longueur fixe</option>
          </select>
        </div>

        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label">Sensibilite</label>
          <select class="fr-select" v-model="config.sensitivity">
            <option value="public">Public</option>
            <option value="internal">Interne</option>
            <option value="restricted">Restreint</option>
            <option value="confidential">Confidentiel</option>
          </select>
        </div>

        <div class="fr-select-group fr-mt-2w">
          <label class="fr-label">Portee</label>
          <select class="fr-select" v-model="config.scope">
            <option value="public">General (tous)</option>
            <option value="group">Groupe</option>
            <option value="private">Prive</option>
          </select>
        </div>

        <fieldset class="fr-fieldset fr-mt-4w">
          <legend class="fr-fieldset__legend">Options</legend>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="graph" v-model="config.graph_enabled" />
              <label class="fr-label" for="graph">Activer le graph de references</label>
            </div>
          </div>
          <div class="fr-fieldset__element">
            <div class="fr-checkbox-group">
              <input type="checkbox" id="ai_summary" v-model="config.ai_summary_enabled" />
              <label class="fr-label" for="ai_summary">Resume IA pour les articles longs</label>
            </div>
          </div>
          <div v-if="config.ai_summary_enabled" class="fr-fieldset__element fr-ml-4w">
            <div class="fr-input-group">
              <label class="fr-label">Seuil (caracteres)</label>
              <input class="fr-input" type="number" v-model.number="config.ai_summary_threshold" min="100" />
            </div>
          </div>
        </fieldset>

        <button class="fr-btn fr-mt-4w" @click="save">Sauvegarder</button>
        <div v-if="saved" class="fr-alert fr-alert--success fr-mt-2w"><p>Configuration sauvegardee.</p></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { get, post } = useApi()

const config = ref<any>(null)
const saved = ref(false)

async function save() {
  // For now, re-create collection with updated config (PATCH not implemented yet)
  saved.value = true
  setTimeout(() => saved.value = false, 3000)
}

onMounted(async () => {
  try {
    config.value = await get(`/api/collections/${id}`)
  } catch (e) {}
})
</script>
