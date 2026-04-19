<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin/create">Creer</NuxtLink></li>
        <li aria-current="page">Evaluation</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Mesure d'evaluation — {{ collection }}</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 3 sur 4 — Optionnel mais recommande</p>

    <WizardStepper :current-step="3" />

    <div class="fr-col-8">
      <p class="fr-text--lg fr-mb-4w">Testez la qualite du RAG avant publication.</p>

      <!-- Quick test -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Test rapide</h3>
            <div class="fr-input-group">
              <input class="fr-input" v-model="question" placeholder="Posez une question de test..." />
            </div>
            <button class="fr-btn fr-btn--sm fr-mt-1w" @click="test" :disabled="testing || !question.trim()">
              {{ testing ? 'Test...' : 'Tester' }}
            </button>
            <div v-if="response" class="fr-mt-2w fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;">
              {{ response }}
            </div>
          </div>
        </div>
      </div>

      <!-- Eval dataset -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Jeu de test (optionnel)</h3>
            <p class="fr-text--sm">Importez un fichier JSON de questions-reponses pour evaluer le RAG.</p>
            <input type="file" class="fr-upload" accept=".json" @change="importDataset" />
            <p class="fr-text--sm fr-mt-1w">{{ datasetCount }} questions chargees</p>
          </div>
        </div>
      </div>

      <div class="fr-callout fr-mb-4w">
        <p class="fr-callout__text">
          Cette etape est optionnelle. Vous pourrez evaluer la collection
          a tout moment depuis la page Evaluation.
        </p>
      </div>

      <!-- Navigation -->
      <div class="fr-btns-group fr-btns-group--inline">
        <NuxtLink :to="`/admin/create/step-2?collection=${collection}`" class="fr-btn fr-btn--secondary">
          ← Precedent
        </NuxtLink>
        <NuxtLink :to="`/admin/create/step-4?collection=${collection}`" class="fr-btn">
          Suivant →
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const collection = route.query.collection as string
const { post } = useApi()

const question = ref('')
const response = ref('')
const testing = ref(false)
const datasetCount = ref(0)

async function test() {
  testing.value = true
  response.value = ''
  try {
    const data = await post(`/api/playground/${collection}/chat`, { question: question.value })
    response.value = data.response || 'Pas de reponse'
  } catch (e: any) { response.value = `Erreur: ${e.message}` }
  testing.value = false
}

async function importDataset(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const text = await file.text()
  const data = JSON.parse(text)
  await post(`/api/collections/${collection}/eval/dataset`, data)
  datasetCount.value = data.length
}
</script>
