<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li aria-current="page">Creer une collection</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Creer une collection</h1>
    <p class="fr-text--lg fr-mb-2w">Etape 1 sur 5 — D'ou viennent vos documents ?</p>

    <div class="fr-callout fr-mb-4w">
      <p class="fr-callout__text">
        Avant de creer une collection, consultez le
        <NuxtLink to="/admin/catalog" class="fr-link">catalogue des collections existantes</NuxtLink>
        pour eviter les doublons et contribuer aux efforts en cours.
      </p>
    </div>

    <WizardStepper :current-step="1" />

    <div class="myrag-card-grid">
      <div v-for="src in sources" :key="src.key"
           :class="['fr-card', {
             'fr-card--shadow': selected === src.key,
             'fr-enlarge-link': !src.soon,
           }]"
           @click="!src.soon && (selected = src.key)"
           :style="src.soon ? 'opacity:0.5;cursor:not-allowed;' : 'cursor:pointer;'">
        <div class="fr-card__body">
          <div class="fr-card__content">
            <h3 class="fr-card__title">
              <span>{{ src.icon }} {{ src.name }}</span>
            </h3>
            <p class="fr-card__desc">{{ src.description }}</p>
            <div class="fr-card__start">
              <span v-if="src.soon" class="fr-badge fr-badge--sm fr-badge--grey">Bientot disponible</span>
              <span v-if="src.refresh && !src.soon" class="fr-badge fr-badge--sm fr-badge--new">Refresh auto</span>
              <span v-if="!src.soon" class="fr-badge fr-badge--sm fr-badge--info">{{ src.strategy }}</span>
            </div>
          </div>
        </div>
        <div v-if="selected === src.key && !src.soon" class="fr-card__header" style="background:#000091;padding:4px;text-align:center;">
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
    prompt_template: 'juridique',
  },
  {
    key: 'file',
    icon: '📄',
    name: 'Fichier unique',
    description: 'Upload un fichier (PDF, MD, TXT, DOCX, images, audio). Detection automatique du type.',
    refresh: false,
    strategy: 'auto',
    prompt_template: 'generic',
  },
  {
    key: 'directory',
    icon: '📁',
    name: 'Repertoire local',
    description: 'Upload un dossier ou un ZIP contenant plusieurs fichiers a indexer ensemble.',
    refresh: false,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
  },
  {
    key: 'drive',
    icon: '☁️',
    name: 'Suite Numerique Drive',
    description: 'Connecter un dossier Drive (Suite Numerique). Synchronisation automatique des modifications.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
  },
  {
    key: 'nextcloud',
    icon: '📦',
    name: 'Nextcloud',
    description: 'Connecter un dossier Nextcloud via l\'API OCS. Synchronisation automatique.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
  },
  {
    key: 'resana',
    icon: '🗂️',
    name: 'Resana',
    description: 'Connecter un espace Resana. Synchronisation automatique des documents.',
    refresh: true,
    strategy: 'auto',
    prompt_template: 'multi_thematique',
    soon: true,
  },
  {
    key: 'website',
    icon: '🌐',
    name: 'Indexation de site',
    description: 'Crawler un site web ou un intranet pour indexer ses pages. Suivi des modifications.',
    refresh: true,
    strategy: 'section',
    prompt_template: 'multi_thematique',
    soon: true,
  },
]

function next() {
  router.push(`/admin/create/step-2?source=${selected.value}`)
}
</script>
