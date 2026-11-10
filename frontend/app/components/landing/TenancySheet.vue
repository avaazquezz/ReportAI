<script setup lang="ts">
// Sheet 4: many companies on one codebase. A quiet sheet (no motion): four rules as a list, the
// one helper every tenant-scoped route goes through (an excerpt of the real file), and the
// isolation matrix as the test runs it: every route with an id, asked by another company's user.
const { t } = useI18n()

const ITEMS = ['isolation', 'spend', 'data', 'access'] as const
// backend/tests/test_tenant_isolation.py: ID_ROUTES, the routes with an id in the OpenAPI schema.
const ROUTES_WITH_AN_ID = 29

// An excerpt of backend/app/core/scoping.py (type parameters left out for the page).
const CODE = `async def get_scoped_or_404(repo, id_, *, tenant_id):
    obj = await repo.get_by_id(id_)
    if obj is None or obj.tenant_id != tenant_id:
        raise ResourceNotFoundException()
    return obj`
</script>

<template>
  <section :id="SHEET_IDS.tenancy" class="scroll-mt-20 bg-surface-0" data-tone="light">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="tenancy" :heading="t('landing.tenancy.heading')" :plain="t('landing.tenancy.plain')" />

      <!-- grid-cols-1 (minmax(0, 1fr)): the code block scrolls inside its column instead of widening the page. -->
      <div class="mt-14 grid grid-cols-1 gap-14 lg:grid-cols-12 lg:gap-10">
        <dl class="m-0 lg:col-span-7">
          <div v-for="item in ITEMS" :key="item" class="border-t border-ink-900/20 py-6 first:border-t-2 first:border-ink-900">
            <dt class="font-plan text-[1.15rem] font-bold leading-snug tracking-[-0.01em] text-ink-900">{{ t(`landing.tenancy.items.${item}.title`) }}</dt>
            <dd class="m-0 mt-2 max-w-[62ch] font-body text-[15px] leading-relaxed text-ink-900/80">{{ t(`landing.tenancy.items.${item}.body`) }}</dd>
          </div>
        </dl>

        <div class="flex flex-col gap-10 lg:col-span-5">
          <figure class="m-0">
            <figcaption class="font-mono text-[12px] text-ink-900/60">{{ t('landing.tenancy.codeLabel') }}</figcaption>
            <pre class="m-0 mt-2 overflow-x-auto rounded-md bg-plano-950 p-4 font-mono text-[12.5px] leading-relaxed text-white/90"><code>{{ CODE }}</code></pre>
          </figure>

          <figure class="m-0">
            <p class="m-0 font-body text-[13px] font-semibold text-ink-900/70">{{ t('landing.tenancy.matrixLabel') }}</p>
            <div class="mt-3 grid grid-cols-[repeat(10,minmax(0,1fr))] gap-1" aria-hidden="true">
              <span
                v-for="n in ROUTES_WITH_AN_ID"
                :key="n"
                class="flex aspect-square items-center justify-center rounded-sm border border-approved-600/50 bg-approved-100 font-mono text-[9px] text-[#136B4F]"
              >404</span>
            </div>
            <figcaption class="mt-3 font-body text-[13.5px] leading-snug text-ink-900/75">{{ t('landing.tenancy.matrixCaption') }}</figcaption>
          </figure>

          <div class="border-l-2 border-capture-600 bg-cream-50 py-3 pl-4 pr-3">
            <p class="m-0 font-body text-[13px] font-semibold text-capture-600">{{ t('landing.sheet.why') }}</p>
            <p class="mb-0 mt-1 font-body text-[14px] leading-snug text-ink-900/85">{{ t('landing.tenancy.why') }}</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
