<template>
  <div>
    <!-- DSFR Header -->
    <header role="banner" class="fr-header">
      <div class="fr-header__body">
        <div class="fr-container">
          <div class="fr-header__body-row">
            <div class="fr-header__brand fr-enlarge-link">
              <div class="fr-header__brand-top">
                <div class="fr-header__logo">
                  <p class="fr-logo">MyRAG<br><small>(beta)</small></p>
                </div>
              </div>
              <div class="fr-header__service">
                <NuxtLink to="/" class="fr-header__service-title">
                  {{ config.public.appTitle }}
                </NuxtLink>
                <p class="fr-header__service-tagline">Recherche augmentee dans vos collections</p>
              </div>
            </div>
            <div class="fr-header__tools">
              <div class="fr-header__tools-links">
                <ul class="fr-btns-group">
                  <li>
                    <NuxtLink to="/admin" class="fr-btn fr-icon-settings-5-line fr-btn--sm">
                      Admin
                    </NuxtLink>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="fr-header__menu">
        <div class="fr-container">
          <nav class="fr-nav" role="navigation" aria-label="Navigation principale">
            <ul class="fr-nav__list">
              <li class="fr-nav__item">
                <NuxtLink to="/" class="fr-nav__link" :aria-current="route.path === '/' ? 'page' : undefined">
                  Collections
                </NuxtLink>
              </li>
              <li class="fr-nav__item">
                <NuxtLink to="/admin" class="fr-nav__link" :aria-current="route.path.startsWith('/admin') ? 'page' : undefined">
                  Administration
                </NuxtLink>
              </li>
            </ul>
          </nav>
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main id="main-content" class="fr-container fr-mt-4w fr-mb-8w">
      <slot />
    </main>

    <!-- DSFR Footer -->
    <footer class="fr-footer" role="contentinfo">
      <div class="fr-container">
        <div class="fr-footer__body">
          <div class="fr-footer__brand fr-enlarge-link">
            <p class="fr-logo">MyRAG (beta)</p>
          </div>
          <div class="fr-footer__content">
            <p class="fr-footer__content-desc">
              Front augmente DSFR pour OpenRAG — Recherche et analyse documentaire assistee par IA.
            </p>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
const config = useRuntimeConfig()
const route = useRoute()
</script>
