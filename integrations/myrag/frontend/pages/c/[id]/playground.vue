<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Playground</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Playground RAG — {{ id }}</h1>

    <div class="fr-grid-row fr-grid-row--gutters">
      <!-- Left: Chat -->
      <div class="fr-col-7">
        <div class="fr-input-group">
          <label class="fr-label" for="question">Question</label>
          <textarea id="question" class="fr-input" v-model="question" rows="3"
                    placeholder="Quelles sont les conditions pour une carte de sejour vie privee ?"></textarea>
        </div>
        <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
          <button class="fr-btn" @click="sendQuestion" :disabled="sending || !question.trim()">
            {{ sending ? 'Envoi...' : 'Envoyer' }}
          </button>
          <button class="fr-btn fr-btn--secondary" @click="clearChat">Effacer</button>
        </div>

        <!-- Response -->
        <div v-if="response" class="fr-mt-4w">
          <h3 class="fr-h5">Reponse</h3>
          <div class="fr-p-3w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;">
            {{ response }}
          </div>
        </div>
      </div>

      <!-- Right: Debug panel -->
      <div class="fr-col-5">
        <h3 class="fr-h5">Debug</h3>

        <!-- Metrics -->
        <div v-if="debug" class="fr-card fr-mb-2w">
          <div class="fr-card__body">
            <div class="fr-card__content">
              <p class="fr-text--sm">
                Retrieval: {{ debug.retrieval_time_ms }}ms |
                Chunks: {{ debug.chunks_used }}/{{ debug.chunks_total }}
              </p>
            </div>
          </div>
        </div>

        <!-- Sources -->
        <div v-if="debug && debug.chunks">
          <h4 class="fr-h6">Sources ({{ debug.chunks.length }})</h4>
          <div v-for="(chunk, i) in debug.chunks" :key="i" class="fr-mb-1w">
            <details class="fr-accordion">
              <summary class="fr-accordion__btn">
                {{ chunk.metadata?.filename || `Source ${i + 1}` }}
              </summary>
              <div class="fr-collapse">
                <p class="fr-text--sm" style="white-space:pre-wrap;">{{ chunk.content?.substring(0, 500) }}...</p>
              </div>
            </details>
          </div>
        </div>

        <!-- Mini graph -->
        <div v-if="debug && debug.graph && debug.graph.nodes">
          <h4 class="fr-h6 fr-mt-2w">Graph contextuel</h4>
          <div v-for="edge in debug.graph.edges?.slice(0, 10)" :key="`${edge.source}-${edge.target}`"
               class="fr-text--sm">
            {{ edge.source }} → {{ edge.target }}
          </div>
          <NuxtLink :to="`/c/${id}/graph`" class="fr-link fr-text--sm">Voir le graph complet</NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { post } = useApi()

const question = ref('')
const response = ref('')
const debug = ref<any>(null)
const sending = ref(false)

async function sendQuestion() {
  if (!question.value.trim()) return
  sending.value = true
  response.value = ''
  debug.value = null

  try {
    const data = await post(`/api/playground/${id}/chat`, {
      question: question.value,
    })
    response.value = data.response || ''
    debug.value = data.debug || null
  } catch (e: any) {
    response.value = `Erreur: ${e.message}`
  } finally {
    sending.value = false
  }
}

function clearChat() {
  question.value = ''
  response.value = ''
  debug.value = null
}
</script>
