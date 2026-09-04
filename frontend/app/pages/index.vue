<script setup lang="ts">
const { t } = useI18n()

useSeoMeta({
  description: () => t('landing.seo.description'),
  ogTitle: () => t('landing.seo.title'),
  ogDescription: () => t('landing.seo.description'),
  ogType: 'website'
})
</script>

<template>
  <div>
    <LandingHeroSection />
    <LandingFactStrip />
    <LandingRealDemoSection />
    <LandingHowItWorksSection />
    <LandingUseCasesSection />
    <LandingDifferentiatorSection />
    <LandingTemplateFidelitySection />
    <LandingApprovalSection />
    <LandingOnboardingSection />
    <LandingFaqSection />
    <LandingFinalCtaSection />
  </div>
</template>
