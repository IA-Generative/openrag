<template>
  <div>
    <nav role="navigation" class="fr-breadcrumb" aria-label="vous etes ici">
      <ol class="fr-breadcrumb__list">
        <li><NuxtLink class="fr-breadcrumb__link" to="/">Collections</NuxtLink></li>
        <li><NuxtLink class="fr-breadcrumb__link" :to="`/c/${id}`">{{ id }}</NuxtLink></li>
        <li aria-current="page">Graph</li>
      </ol>
    </nav>
    <h1 class="fr-h3">Graph de references — {{ id }}</h1>
    <iframe :src="`${baseUrl}/graph?corpus_id=${id}`"
            style="width:100%;height:80vh;border:1px solid #e5e5e5;border-radius:4px;"
            allowfullscreen></iframe>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { baseUrl } = useApi()
</script>
