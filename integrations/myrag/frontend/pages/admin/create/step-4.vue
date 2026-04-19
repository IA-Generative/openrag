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
    <p class="fr-text--lg fr-mb-4w">Etape 4 sur 5 — Testez la qualite du RAG avant publication</p>

    <WizardStepper :current-step="4" />

    <div class="fr-col-8">
      <!-- Quick test -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Tester le RAG</h3>
            <div class="fr-input-group">
              <textarea class="fr-input" v-model="question" rows="2"
                        placeholder="Posez une question de test..."
                        @keydown.enter.exact.prevent="!testing && question.trim() && test()"></textarea>
            </div>
            <button class="fr-btn fr-btn--sm fr-mt-1w" @click="test" :disabled="testing || !question.trim()">
              {{ testing ? 'Test...' : 'Tester' }}
            </button>
            <div v-if="response" class="fr-mt-2w fr-p-2w myrag-md-preview" v-html="renderedResponse">
            </div>
            <div v-if="sourceNames.length" class="fr-mt-1w">
              <p class="fr-text--xs" style="color:#666;">
                Sources utilisees : {{ sourceNames.join(', ') }}
              </p>
            </div>
            <div v-if="response && !sourceNames.length" class="fr-mt-1w">
              <p class="fr-text--xs" style="color:#b34000;">
                Aucune source retrouvee — le RAG n'a pas trouve de chunks pertinents.
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Eval dataset -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">Jeu de test (optionnel)</h3>
            <p class="fr-text--sm">
              Importez un fichier JSON de questions-reponses pour evaluer la qualite du RAG.
              <a href="/exemple-evaluation.json" download class="fr-link fr-link--sm">
                Telecharger un exemple de format
              </a>
            </p>

            <details class="fr-mt-1w fr-mb-2w">
              <summary class="fr-text--xs" style="cursor:pointer;color:#666;">
                Voir le format attendu
              </summary>
              <pre class="fr-mt-1w" style="background:#f6f6f6;padding:0.8rem;border-radius:4px;font-size:0.75rem;overflow-x:auto;max-height:200px;">{
  "name": "nom-du-jeu-de-test",
  "description": "Description du jeu de test",
  "questions": [
    {
      "id": "q1",
      "question": "Votre question ici ?",
      "expected_answer": "La reponse attendue...",
      "must_cite": ["mot-cle-1", "mot-cle-2"],
      "tags": ["theme"]
    }
  ]
}</pre>
            </details>

            <div class="fr-btns-group fr-btns-group--inline fr-mt-2w">
              <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="generateDataset" :disabled="generating">
                {{ generating ? 'Generation en cours...' : 'Generer automatiquement' }}
              </button>
              <label class="fr-btn fr-btn--sm fr-btn--tertiary" style="cursor:pointer;">
                Importer un fichier JSON
                <input type="file" accept=".json" @change="importDataset" style="display:none;" />
              </label>
            </div>

            <div v-if="generating" class="fr-mt-1w">
              <p class="fr-text--xs" style="color:#666;">Le LLM analyse le contenu de la collection et genere les questions...</p>
            </div>

            <div v-if="generateError" class="fr-alert fr-alert--error fr-alert--sm fr-mt-1w">
              <p>{{ generateError }}</p>
            </div>

            <p v-if="datasetCount > 0" class="fr-text--sm fr-mt-1w" style="color:#18753c;">
              {{ datasetCount }} questions chargees
            </p>

            <!-- Preview generated dataset -->
            <div v-if="generatedDataset" class="fr-mt-2w">
              <details open>
                <summary class="fr-text--sm" style="cursor:pointer;font-weight:bold;">
                  Questions generees ({{ generatedDataset.questions.length }})
                </summary>
                <div class="fr-mt-1w" style="max-height:300px;overflow-y:auto;">
                  <div v-for="q in generatedDataset.questions" :key="q.id"
                       class="fr-p-1w fr-mb-1w" style="border-radius:4px;font-size:0.8rem;"
                       :style="q.out_of_scope ? 'background:#fff3cd;border-left:3px solid #b34000;' : 'background:#f6f6f6;'">
                    <p>
                      <strong>{{ q.id }}.</strong> {{ q.question }}
                      <span v-if="q.out_of_scope" class="fr-badge fr-badge--sm fr-badge--warning" style="margin-left:0.5rem;">hors-sujet</span>
                    </p>
                    <p v-if="q.out_of_scope" style="color:#b34000;font-style:italic;">
                      {{ q.note }}
                    </p>
                    <p v-else style="color:#666;">Reponse attendue : {{ q.expected_answer?.substring(0, 150) }}...</p>
                  </div>
                </div>
                <div class="fr-btns-group fr-btns-group--inline fr-mt-1w">
                  <button class="fr-btn fr-btn--sm" @click="downloadDataset">
                    Telecharger le JSON
                  </button>
                  <button class="fr-btn fr-btn--sm fr-btn--secondary" @click="runEval"
                          :disabled="running || !generatedDataset?.questions?.length">
                    {{ running ? `Test ${runProgress}/${generatedDataset.questions.length}...` : 'Lancer les tests' }}
                  </button>
                </div>
              </details>
            </div>

            <!-- Eval results -->
            <div v-if="evalResults.length" class="fr-mt-3w">
              <h4 class="fr-h6">
                Resultats — {{ evalScore }}/{{ evalResults.length }} reussis
                ({{ Math.round(evalScore / evalResults.length * 100) }}%)
              </h4>
              <progress :value="evalScore" :max="evalResults.length" style="width:100%;height:8px;"></progress>

              <div class="fr-mt-2w" style="max-height:400px;overflow-y:auto;">
                <div v-for="r in evalResults" :key="r.id"
                     class="fr-p-1w fr-mb-1w" style="border-radius:4px;font-size:0.8rem;"
                     :style="resultStyle(r)">
                  <p>
                    <strong>{{ r.id }}.</strong> {{ r.question }}
                    <span v-if="r.out_of_scope" class="fr-badge fr-badge--sm fr-badge--warning" style="margin-left:0.3rem;">hors-sujet</span>
                    <span class="fr-badge fr-badge--sm" style="margin-left:0.3rem;"
                          :class="r.pass ? 'fr-badge--success' : 'fr-badge--error'">
                      {{ r.pass ? 'OK' : 'KO' }}
                    </span>
                  </p>
                  <details>
                    <summary class="fr-text--xs" style="cursor:pointer;color:#666;">Detail</summary>
                    <div class="fr-mt-1v">
                      <p class="fr-text--xs"><strong>Reponse RAG :</strong></p>
                      <div class="fr-p-1v myrag-md-preview" style="max-height:150px;font-size:0.75rem;"
                           v-html="renderMd(r.response)"></div>
                      <p v-if="r.sources_found?.length" class="fr-text--xs fr-mt-1v" style="color:#666;">
                        Sources : {{ r.sources_found.join(', ') }}
                      </p>
                      <p v-if="!r.out_of_scope && r.expected_answer" class="fr-text--xs fr-mt-1v" style="color:#666;">
                        Attendu : {{ r.expected_answer.substring(0, 200) }}...
                      </p>
                      <p v-if="r.must_cite?.length" class="fr-text--xs fr-mt-1v">
                        Mots-cles attendus :
                        <span v-for="kw in r.must_cite" :key="kw" class="fr-badge fr-badge--sm fr-mr-1v"
                              :class="r.keywords_found?.includes(kw) ? 'fr-badge--success' : 'fr-badge--error'">
                          {{ kw }}
                        </span>
                      </p>
                      <p v-if="r.out_of_scope" class="fr-text--xs fr-mt-1v"
                         :style="r.pass ? 'color:#18753c;' : 'color:#b34000;'">
                        {{ r.pass
                          ? 'Le RAG a correctement refuse de repondre a cette question hors-sujet.'
                          : 'Le RAG a fabrique une reponse a une question hors-sujet — a ameliorer.' }}
                      </p>
                      <div v-if="r.out_of_scope && !r.pass" class="fr-mt-1v">
                        <p class="fr-text--xs" style="color:#666;">
                          Le system prompt de la collection devrait indiquer au LLM de refuser les questions hors-sujet.
                        </p>
                        <button v-if="!promptPatched" class="fr-btn fr-btn--sm fr-btn--tertiary fr-mt-1v"
                                @click="patchPromptGuardrail">
                          Ajouter une regle de garde au system prompt
                        </button>
                        <p v-if="promptPatched" class="fr-text--xs fr-mt-1v" style="color:#18753c;">
                          Regle ajoutee au system prompt. Relancez les tests pour verifier.
                        </p>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            </div>
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
        <NuxtLink :to="`/admin/create/step-3?collection=${collection}`" class="fr-btn fr-btn--secondary">
          ← Precedent
        </NuxtLink>
        <NuxtLink :to="`/admin/create/step-5?collection=${collection}`" class="fr-btn">
          Suivant →
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const collection = route.query.collection as string
const { get, post, patch } = useApi()

import { marked } from 'marked'

const question = ref('')
const response = ref('')
const sourceNames = ref<string[]>([])
const testing = ref(false)
const datasetCount = ref(0)
const generating = ref(false)
const generateError = ref('')
const generatedDataset = ref<any>(null)
const running = ref(false)
const promptPatched = ref(false)
const runProgress = ref(0)
const evalResults = ref<any[]>([])
const evalScore = computed(() => evalResults.value.filter(r => r.pass).length)

const renderedResponse = computed(() => {
  if (!response.value) return ''
  return marked.parse(response.value, { breaks: true }) as string
})

async function test() {
  testing.value = true
  response.value = ''
  sourceNames.value = []
  try {
    const data = await post(`/api/playground/${collection}/chat`, { question: question.value })
    response.value = data.response || 'Pas de reponse'
    sourceNames.value = data.source_names || []
  } catch (e: any) { response.value = `Erreur: ${e.message}` }
  testing.value = false
}

async function generateDataset() {
  generating.value = true
  generateError.value = ''
  generatedDataset.value = null
  try {
    const data = await post(`/api/playground/${collection}/generate-eval`, {})
    if (data.questions && data.questions.length > 0) {
      generatedDataset.value = data
      datasetCount.value = data.questions.length
    } else {
      generateError.value = data.error || 'Aucune question generee. Reessayez.'
    }
  } catch (e: any) {
    generateError.value = `Erreur: ${e.message}`
  }
  generating.value = false
}

function downloadDataset() {
  if (!generatedDataset.value) return
  const blob = new Blob([JSON.stringify(generatedDataset.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${collection}-evaluation.json`
  a.click()
  URL.revokeObjectURL(url)
}

function renderMd(text: string): string {
  if (!text) return ''
  return marked.parse(text, { breaks: true }) as string
}

function resultStyle(r: any): string {
  if (r.out_of_scope) return r.pass
    ? 'background:#d4edda;border-left:3px solid #18753c;'
    : 'background:#fff3cd;border-left:3px solid #b34000;'
  return r.pass
    ? 'background:#d4edda;border-left:3px solid #18753c;'
    : 'background:#f8d7da;border-left:3px solid #ce0500;'
}

const GUARDRAIL_RULE = `

## Regle de garde
Si la question de l'utilisateur ne concerne pas le contenu de cette collection, reponds poliment que tu ne disposes pas d'informations sur ce sujet et invite l'utilisateur a reformuler sa question en lien avec le contenu de la collection.`

async function patchPromptGuardrail() {
  try {
    let currentPrompt = ''
    try {
      const config = await get(`/api/collections/${collection}`)
      currentPrompt = config?.system_prompt || ''
    } catch { /* collection may not have a config yet */ }

    if (currentPrompt.includes('Regle de garde')) {
      promptPatched.value = true
      return
    }

    await patch(`/api/collections/${collection}/system-prompt`, {
      system_prompt: currentPrompt + GUARDRAIL_RULE,
    })
    promptPatched.value = true
  } catch (e: any) {
    generateError.value = `Erreur lors de la mise a jour du prompt: ${e.message}`
  }
}

async function runEval() {
  if (!generatedDataset.value?.questions?.length) return
  running.value = true
  runProgress.value = 0
  evalResults.value = []

  for (const q of generatedDataset.value.questions) {
    runProgress.value++
    try {
      const data = await post(`/api/playground/${collection}/chat`, { question: q.question })
      const resp = (data.response || '').toLowerCase()
      const sourcesFound = data.source_names || []

      let pass = false
      const keywordsFound: string[] = []

      if (q.out_of_scope) {
        // For out-of-scope: pass if the RAG says it can't answer / has no info
        const refusalPatterns = [
          'pas pu trouver', 'pas d\'information', 'ne dispose pas',
          'pas de donnee', 'hors du champ', 'ne peux pas repondre',
          'aucune information', 'pas en mesure', 'ne figure pas',
          'ne concerne pas', 'n\'ai pas', 'ne sais pas',
        ]
        pass = refusalPatterns.some(p => resp.includes(p)) || sourcesFound.length === 0
      } else {
        // For normal questions: check keywords are cited in the response
        if (q.must_cite?.length) {
          for (const kw of q.must_cite) {
            if (resp.includes(kw.toLowerCase())) {
              keywordsFound.push(kw)
            }
          }
          pass = keywordsFound.length >= Math.ceil(q.must_cite.length / 2)
        } else {
          // No must_cite: pass if we got sources
          pass = sourcesFound.length > 0 && resp.length > 50
        }
      }

      evalResults.value.push({
        ...q,
        response: data.response,
        sources_found: sourcesFound,
        keywords_found: keywordsFound,
        pass,
      })
    } catch (e: any) {
      evalResults.value.push({
        ...q,
        response: `Erreur: ${e.message}`,
        sources_found: [],
        keywords_found: [],
        pass: false,
      })
    }
  }

  running.value = false
}

async function importDataset(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const text = await file.text()
  try {
    const data = JSON.parse(text)
    generatedDataset.value = data
    datasetCount.value = data.questions?.length || 0
  } catch {
    generateError.value = 'Fichier JSON invalide.'
  }
}
</script>

<style scoped>
.myrag-md-preview {
  background: #f6f6f6;
  border-radius: 4px;
  font-size: 0.85rem;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
}

.myrag-md-preview :deep(h1),
.myrag-md-preview :deep(h2),
.myrag-md-preview :deep(h3) {
  font-size: 1rem;
  margin: 0.8rem 0 0.4rem;
}

.myrag-md-preview :deep(p) {
  margin: 0.4rem 0;
}

.myrag-md-preview :deep(ul),
.myrag-md-preview :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.4rem 0;
}

.myrag-md-preview :deep(code) {
  background: #e3e3e3;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  font-size: 0.8rem;
}

.myrag-md-preview :deep(pre) {
  background: #e3e3e3;
  padding: 0.8rem;
  border-radius: 4px;
  overflow-x: auto;
}

.myrag-md-preview :deep(pre code) {
  background: none;
  padding: 0;
}

.myrag-md-preview :deep(strong) {
  font-weight: 700;
}

.myrag-md-preview :deep(blockquote) {
  border-left: 3px solid #000091;
  padding-left: 0.8rem;
  margin: 0.4rem 0;
  color: #555;
}
</style>
