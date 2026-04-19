<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">System Prompt</li>
      </ol>
    </nav>

    <h1 class="fr-h3">System Prompt — {{ id }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <!-- Left: Editor -->
      <div class="fr-col-6">
        <h3 class="fr-h5">Editeur</h3>

        <!-- Template selector -->
        <div class="fr-select-group fr-mb-2w">
          <label class="fr-label">Modele de base</label>
          <select class="fr-select" v-model="selectedTemplate" @change="applyTemplate">
            <option value="">-- Choisir un modele --</option>
            <option v-for="tpl in templates" :key="tpl.key" :value="tpl.key">
              {{ tpl.icon }} {{ tpl.name }}
            </option>
          </select>
        </div>

        <!-- Prompt editor -->
        <div class="fr-input-group">
          <label class="fr-label">Prompt</label>
          <textarea class="fr-input" v-model="prompt" rows="18"
                    style="font-family:monospace;font-size:0.85rem;"></textarea>
        </div>

        <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
          <button class="fr-btn" @click="savePrompt" :disabled="saving">
            {{ saving ? 'Sauvegarde...' : 'Sauvegarder' }}
          </button>
          <button class="fr-btn fr-btn--secondary" @click="resetPrompt">
            Restaurer
          </button>
        </div>

        <div v-if="saved" class="fr-alert fr-alert--success fr-mt-2w">
          <p>Prompt sauvegarde.</p>
        </div>
      </div>

      <!-- Right: Playground -->
      <div class="fr-col-6">
        <h3 class="fr-h5">Test rapide</h3>

        <div class="fr-input-group">
          <label class="fr-label">Question de test</label>
          <input class="fr-input" v-model="testQuestion"
                 placeholder="Conditions carte vie privee ?" />
        </div>

        <button class="fr-btn fr-btn--sm fr-mt-1w" @click="testPrompt" :disabled="testing">
          {{ testing ? 'Test...' : 'Tester' }}
        </button>

        <div v-if="testResponse" class="fr-mt-2w">
          <h4 class="fr-h6">Reponse</h4>
          <div class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;max-height:400px;overflow-y:auto;">
            {{ testResponse }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { get, patch } = useApi()

const prompt = ref('')
const originalPrompt = ref('')
const templates = ref<any[]>([])
const selectedTemplate = ref('')
const saving = ref(false)
const saved = ref(false)

const testQuestion = ref('')
const testResponse = ref('')
const testing = ref(false)

async function applyTemplate() {
  if (!selectedTemplate.value) return
  try {
    const tpl = await get(`/api/collections/templates/${selectedTemplate.value}`)
    prompt.value = tpl.prompt
  } catch (e) {}
}

async function savePrompt() {
  saving.value = true
  try {
    await patch(`/api/collections/${id}/system-prompt`, { system_prompt: prompt.value })
    originalPrompt.value = prompt.value
    saved.value = true
    setTimeout(() => saved.value = false, 3000)
  } catch (e) {}
  saving.value = false
}

function resetPrompt() {
  prompt.value = originalPrompt.value
}

async function testPrompt() {
  if (!testQuestion.value.trim()) return
  testing.value = true
  testResponse.value = ''
  try {
    // Call OpenRAG directly with the current prompt
    const config = useRuntimeConfig()
    const resp = await fetch(`${config.public.myragApiUrl}/api/playground/${id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: testQuestion.value, system_prompt: prompt.value }),
    })
    const data = await resp.json()
    testResponse.value = data.response || data.detail || 'Pas de reponse'
  } catch (e: any) {
    testResponse.value = `Erreur: ${e.message}`
  }
  testing.value = false
}

onMounted(async () => {
  try {
    const data = await get(`/api/collections/${id}/system-prompt`)
    prompt.value = data.system_prompt || ''
    originalPrompt.value = prompt.value

    const tplData = await get('/api/collections/templates')
    templates.value = tplData.templates || []
  } catch (e) {}
})
</script>
