<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li aria-current="page">Creer une collection</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Creer une collection</h1>
    <p class="fr-text--lg fr-mb-4w">Etape 1 sur 5 — D'ou viennent vos documents ?</p>

    <WizardStepper :current-step="1" />

    <div class="myrag-card-grid">
      <div v-for="src in sources" :key="src.key"
           :class="['fr-card', 'fr-enlarge-link', { 'fr-card--shadow': selected === src.key }]"
           @click="selected = src.key"
           style="cursor:pointer;">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">
              <span>{{ src.icon }} {{ src.name }}</span>
            </h3>
            <p class="fr-card__desc">{{ src.description }}</p>
            <div class="fr-card__start">
              <span v-if="src.refresh" class="fr-badge fr-badge--sm fr-badge--new">Refresh auto</span>
              <span class="fr-badge fr-badge--sm fr-badge--info">{{ src.strategy }}</span>
            </div>
          </div>
        </div>
        <div v-if="selected === src.key" class="fr-card__header" style="background:#000091;padding:4px;text-align:center;">
          <span style="color:white;font-size:0.8rem;font-weight:bold;">✓ Selectionne</span>
        </div>
      </div>
    </div>

    <div class="fr-btns-group fr-btns-group--right fr-mt-4w">
      <button class="fr-btn" @click="next" :disabled="!selected">
        Suivant →
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
const router = useRouter()
const selected = ref('')

const sources = [
  {
    key: 'legifrance',
    icon: '⚖️',
    name: 'Legifrance',
    description: 'Code, loi, ordonnance depuis l\'API PISTE. Decoupage automatique par article avec hierarchie.',
    refresh: true,
    strategy: 'article',
  },
  {
    key: 'file',
    icon: '📄',
    name: 'Fichier unique',
    description: 'Upload un fichier (PDF, MD, TXT, DOCX, images, audio). Detection automatique du type.',
    refresh: false,
    strategy: 'auto',
  },
  {
    key: 'directory',
    icon: '📁',
    name: 'Repertoire local',
    description: 'Upload un dossier ou un ZIP contenant plusieurs fichiers a indexer ensemble.',
    refresh: false,
    strategy: 'auto',
  },
  {
    key: 'drive',
    icon: '☁️',
    name: 'Suite Numerique Drive',
    description: 'Connecter un dossier Drive (Suite Numerique). Synchronisation automatique des modifications.',
    refresh: true,
    strategy: 'auto',
  },
  {
    key: 'nextcloud',
    icon: '📦',
    name: 'Nextcloud',
    description: 'Connecter un dossier Nextcloud via l\'API OCS. Synchronisation automatique.',
    refresh: true,
    strategy: 'auto',
  },
  {
    key: 'resana',
    icon: '🗂️',
    name: 'Resana',
    description: 'Connecter un espace Resana. Synchronisation automatique des documents.',
    refresh: true,
    strategy: 'auto',
  },
]

function next() {
  router.push(`/admin/create/step-2?source=${selected.value}`)
}
</script>
