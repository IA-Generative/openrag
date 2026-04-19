<template>
  <nav class="fr-stepper fr-mb-4w" aria-label="Etapes de creation">
    <div class="fr-stepper__steps" :data-fr-current-step="currentStep" :data-fr-steps="4">
    </div>
    <div class="fr-grid-row fr-grid-row--gutters fr-mt-2w">
      <div v-for="(step, i) in steps" :key="i"
           class="fr-col-3"
           style="text-align:center;">
        <div :class="['myrag-step', {
          'myrag-step--active': currentStep === i + 1,
          'myrag-step--done': currentStep > i + 1,
          'myrag-step--future': currentStep < i + 1,
        }]">
          <span class="myrag-step__number">{{ i + 1 }}</span>
          <span class="myrag-step__label">{{ step }}</span>
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
defineProps<{
  currentStep: number
}>()

const steps = ['Identification', 'Donnees', 'Evaluation', 'Publication']
</script>

<style>
.myrag-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.myrag-step__number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 0.9rem;
}

.myrag-step--active .myrag-step__number {
  background: #000091;
  color: white;
}

.myrag-step--done .myrag-step__number {
  background: #18753c;
  color: white;
}

.myrag-step--future .myrag-step__number {
  background: #e5e5e5;
  color: #666;
}

.myrag-step__label {
  font-size: 0.8rem;
  color: #666;
}

.myrag-step--active .myrag-step__label {
  color: #000091;
  font-weight: bold;
}

.myrag-step--done .myrag-step__label {
  color: #18753c;
}
</style>
