<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/admin">Administration</NuxtLink></li>
        <li aria-current="page">Catalogue des collections</li>
      </ol>
    </nav>

    <h1 class="fr-h3">Catalogue des collections existantes</h1>
    <p class="fr-text--lg fr-mb-2w">Avant de creer une collection, verifiez qu'elle n'existe pas deja.</p>

    <div class="fr-callout fr-callout--brown-caramel fr-mb-4w">
      <p class="fr-callout__text">
        <strong>Evitez les doublons.</strong> Dupliquer une collection degrade la qualite du RAG
        (reponses inconsistantes, cout d'indexation double, maintenance multiple).
        Preferez contacter le responsable d'une collection existante pour y contribuer.
      </p>
    </div>

    <!-- Search -->
    <div class="fr-search-bar fr-mb-4w" role="search">
      <label class="fr-label" for="search">Rechercher une collection</label>
      <input class="fr-input" id="search" type="search" v-model="search"
             placeholder="CESEDA, code civil, documentation technique..." />
      <button class="fr-btn" @click="">Rechercher</button>
    </div>

    <!-- Results -->
    <div v-if="filtered.length === 0 && search" class="fr-callout fr-mb-4w">
      <h3 class="fr-callout__title">Aucune collection trouvee pour "{{ search }}"</h3>
      <p class="fr-callout__text">Vous pouvez creer une nouvelle collection.</p>
      <NuxtLink to="/admin/create" class="fr-btn fr-mt-2w">Creer une collection</NuxtLink>
    </div>

    <div v-else>
      <div class="fr-table">
        <table>
          <thead>
            <tr>
              <th>Collection</th>
              <th>Description</th>
              <th>Source</th>
              <th>Etat</th>
              <th>Responsable</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="col in filtered" :key="col.name">
              <td>
                <NuxtLink :to="`/c/${col.name}`" class="fr-link">{{ col.name }}</NuxtLink>
              </td>
              <td>{{ col.description || '—' }}</td>
              <td>
                <span class="fr-badge fr-badge--sm">{{ col.source?.type || col.strategy }}</span>
              </td>
              <td>
                <span class="fr-badge fr-badge--sm" :class="stateBadge(col.publication?.state)">
                  {{ stateLabel(col.publication?.state) }}
                </span>
              </td>
              <td>
                <div v-if="col.contact_name">
                  {{ col.contact_name }}
                  <br v-if="col.contact_email" />
                  <a v-if="col.contact_email" :href="`mailto:${col.contact_email}?subject=Collection MyRAG : ${col.name}`"
                     class="fr-link fr-text--sm">
                    {{ col.contact_email }}
                  </a>
                </div>
                <span v-else class="fr-text--sm" style="color:#666;">Non renseigne</span>
              </td>
              <td>
                <a v-if="col.contact_email"
                   :href="`mailto:${col.contact_email}?subject=Demande d'acces a la collection ${col.name}&body=Bonjour,%0A%0AJe souhaiterais contribuer a la collection ${col.name}.%0APourriez-vous m'accorder l'acces ?%0A%0AMerci.`"
                   class="fr-btn fr-btn--sm fr-btn--tertiary fr-icon-mail-line fr-btn--icon-left">
                  Contacter
                </a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="fr-text--sm fr-mt-2w">{{ filtered.length }} collection(s) trouvee(s)</p>
    </div>

    <div class="fr-btns-group fr-mt-4w">
      <NuxtLink to="/admin/create" class="fr-btn">
        Creer une nouvelle collection
      </NuxtLink>
    </div>
  </div>
</template>

<script setup lang="ts">
const { get } = useApi()

const collections = ref<any[]>([])
const search = ref('')

const filtered = computed(() => {
  if (!search.value.trim()) return collections.value
  const q = search.value.toLowerCase()
  return collections.value.filter(c =>
    c.name?.toLowerCase().includes(q) ||
    c.description?.toLowerCase().includes(q) ||
    c.contact_name?.toLowerCase().includes(q) ||
    c.source?.type?.toLowerCase().includes(q) ||
    c.legifrance_source_id?.toLowerCase().includes(q)
  )
})

function stateBadge(state: string) {
  return {
    draft: 'fr-badge--info', published: 'fr-badge--success',
    disabled: 'fr-badge--warning', archived: '',
  }[state] || ''
}

function stateLabel(state: string) {
  return { draft: 'Brouillon', published: 'Publie', disabled: 'Desactive', archived: 'Archive' }[state] || 'Brouillon'
}

onMounted(async () => {
  try {
    const data = await get('/api/collections')
    collections.value = data.collections || []
  } catch (e) {}
})
</script>
