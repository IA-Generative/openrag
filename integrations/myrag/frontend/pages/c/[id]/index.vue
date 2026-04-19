<template>
  <div>
    <!-- Breadcrumb -->
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li aria-current="page">{{ id }}</li>
      </ol>
    </nav>

    <div v-if="loading" class="fr-callout"><p>Chargement...</p></div>

    <div v-else-if="collection">
      <div class="fr-grid-row fr-grid-row--gutters">
        <!-- Left: collection info -->
        <div class="fr-col-8">
          <h1 class="fr-h2">{{ collection.name }}</h1>
          <p class="fr-text--lg">{{ collection.description || 'Pas de description' }}</p>

          <!-- Badges -->
          <div class="fr-mt-2w fr-mb-4w">
            <span class="fr-badge fr-badge--info">{{ collection.strategy }}</span>
            <span class="fr-badge" :class="sensitivityBadge(collection.sensitivity)">
              {{ collection.sensitivity }}
            </span>
            <span v-if="collection.graph_enabled" class="fr-badge fr-badge--new">Graph actif</span>
            <span v-if="collection.ai_summary_enabled" class="fr-badge fr-badge--new">Resume IA</span>
            <span class="fr-badge">{{ collection.prompt_template }}</span>
          </div>

          <!-- Quick actions -->
          <div class="fr-btns-group fr-btns-group--inline fr-mb-4w">
            <NuxtLink :to="`/c/${id}/playground`" class="fr-btn fr-icon-chat-3-line fr-btn--icon-left">
              Tester le RAG
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/graph`" class="fr-btn fr-btn--secondary fr-icon-mind-map-line fr-btn--icon-left">
              Voir le graph
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/upload`" class="fr-btn fr-btn--secondary fr-icon-upload-line fr-btn--icon-left">
              Uploader
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/config`" class="fr-btn fr-btn--tertiary fr-icon-settings-5-line fr-btn--icon-left">
              Configurer
            </NuxtLink>
            <NuxtLink :to="`/c/${id}/publish`" class="fr-btn fr-btn--tertiary fr-icon-send-plane-line fr-btn--icon-left">
              Publier
            </NuxtLink>
          </div>
        </div>

        <!-- Right: quality indicator -->
        <div class="fr-col-4">
          <div class="fr-card">
            <div class="fr-card__body">
              <div class="fr-card__content">
                <h3 class="fr-card__title">Qualite</h3>
                <div class="myrag-quality-bar fr-mt-2w">
                  <div class="myrag-quality-bar__fill"
                       :class="qualityClass(feedbackStats.satisfaction_rate)"
                       :style="{ width: `${feedbackStats.satisfaction_rate * 100}%` }">
                  </div>
                </div>
                <p class="fr-text--sm fr-mt-1w">
                  {{ Math.round(feedbackStats.satisfaction_rate * 100) }}% satisfaction
                  ({{ feedbackStats.positive }} 👍 / {{ feedbackStats.negative }} 👎)
                </p>
                <p v-if="feedbackStats.pending_review > 0" class="fr-text--sm">
                  ⚠ {{ feedbackStats.pending_review }} feedback en attente
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="fr-tabs">
        <ul class="fr-tabs__list" role="tablist">
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'prompt'" @click="tab = 'prompt'">
              System Prompt
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'feedback'" @click="tab = 'feedback'">
              Feedback ({{ feedbackStats.total }})
            </button>
          </li>
          <li role="presentation">
            <button class="fr-tabs__tab" :aria-selected="tab === 'qr'" @click="tab = 'qr'">
              Cache Q&R
            </button>
          </li>
        </ul>

        <!-- Prompt tab -->
        <div v-show="tab === 'prompt'" class="fr-tabs__panel">
          <h3>System prompt actuel</h3>
          <p class="fr-text--sm fr-mb-1w">Template: {{ collection.prompt_template }}</p>
          <pre class="fr-p-2w" style="background:#f6f6f6;border-radius:4px;white-space:pre-wrap;font-size:0.85rem;max-height:400px;overflow-y:auto;">{{ collection.system_prompt }}</pre>
          <NuxtLink :to="`/c/${id}/prompt`" class="fr-btn fr-btn--sm fr-mt-2w">
            Editer le prompt
          </NuxtLink>
        </div>

        <!-- Feedback tab -->
        <div v-show="tab === 'feedback'" class="fr-tabs__panel">
          <div v-if="feedbackItems.length === 0" class="fr-callout">
            <p>Aucun feedback pour cette collection.</p>
          </div>
          <div v-else class="fr-table">
            <table>
              <thead>
                <tr><th>Question</th><th>Note</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                <tr v-for="fb in feedbackItems" :key="fb.id">
                  <td>{{ fb.question.substring(0, 80) }}...</td>
                  <td>{{ fb.rating > 0 ? '👍' : '👎' }}</td>
                  <td><span class="fr-badge fr-badge--sm">{{ fb.status }}</span></td>
                  <td>
                    <button v-if="fb.status === 'pending'" class="fr-btn fr-btn--sm fr-btn--tertiary"
                            @click="reviewFeedback(fb.id, 'reviewed')">Valider</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Q&R tab -->
        <div v-show="tab === 'qr'" class="fr-tabs__panel">
          <p class="fr-text--sm">Cache Q&R — reponses curees pour les questions frequentes.</p>
          <NuxtLink :to="`/c/${id}/config`" class="fr-btn fr-btn--sm fr-mt-2w">
            Gerer le cache Q&R
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { get, patch } = useApi()

const collection = ref<any>(null)
const feedbackStats = ref({ satisfaction_rate: 0, positive: 0, negative: 0, total: 0, pending_review: 0 })
const feedbackItems = ref<any[]>([])
const loading = ref(true)
const tab = ref('prompt')

function sensitivityBadge(s: string) {
  return { public: 'fr-badge--success', internal: 'fr-badge--info', restricted: 'fr-badge--warning', confidential: 'fr-badge--error' }[s] || ''
}

function qualityClass(rate: number) {
  if (rate >= 0.7) return 'myrag-quality-bar__fill--good'
  if (rate >= 0.4) return 'myrag-quality-bar__fill--medium'
  return 'myrag-quality-bar__fill--bad'
}

async function reviewFeedback(fbId: string, status: string) {
  await patch(`/api/feedback/${id}/${fbId}/review`, { status })
  feedbackItems.value = feedbackItems.value.map(f => f.id === fbId ? { ...f, status } : f)
}

onMounted(async () => {
  try {
    collection.value = await get(`/api/collections/${id}`)
    feedbackStats.value = await get(`/api/feedback/${id}/stats`)
    const fbData = await get(`/api/feedback/${id}`)
    feedbackItems.value = fbData.feedback || []
  } catch (e) {
    // Collection may not exist in MyRAG config
  } finally {
    loading.value = false
  }
})
</script>
