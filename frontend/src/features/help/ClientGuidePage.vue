<template>
  <!-- The guide's contents sit on the split panel's dark side from md up (PublicShell `wide`) -->
  <Teleport defer to="#public-aside">
    <nav aria-label="Guide contents" class="flex flex-col gap-3">
      <p class="m-0 text-xs font-medium uppercase tracking-wider text-primary-200">In this guide</p>

      <ol class="m-0 flex list-none flex-col gap-0.5 p-0">
        <li v-for="(section, index) in SECTIONS" :key="section.id">
          <router-link
            :aria-current="index === current ? 'location' : undefined"
            class="flex items-baseline gap-3.5 rounded-lg px-3 py-2 text-[0.9375rem] leading-snug text-white no-underline hover:bg-white/10"
            :class="index === current ? 'bg-white/10 shadow-[inset_2px_0_0_var(--color-primary-200)]' : ''"
            replace
            :to="{ hash: `#${section.id}` }"
          >
            <span class="w-5 shrink-0 font-mono text-xs text-primary-200">{{ index + 1 }}</span>{{ section.title }}
          </router-link>
        </li>
      </ol>
    </nav>
  </Teleport>

  <article class="flex flex-col">
    <details class="mb-6 rounded-lg border border-surface-200 bg-surface-0 md:hidden">
      <summary class="flex min-h-12 cursor-pointer items-center px-4 font-medium">Contents</summary>

      <ol class="m-0 flex flex-col pb-3 pl-9 pr-4">
        <li v-for="section in SECTIONS" :key="section.id">
          <router-link class="block min-h-10 py-2 text-primary" replace :to="{ hash: `#${section.id}` }" @click="closeContents">
            {{ section.title }}
          </router-link>
        </li>
      </ol>
    </details>

    <p class="m-0 mb-3 text-sm font-medium uppercase tracking-wider text-surface-600">Client guide</p>

    <h1 class="m-0 mb-4 text-balance font-heading text-3xl font-medium leading-tight text-surface-900 md:text-4xl">
      Looking after your weather stations with us
    </h1>

    <p class="m-0 mb-8 max-w-[60ch] text-lg text-surface-600">
      {{ APP_NAME }} is where you tell us about a problem at one of your stations, follow the work while we fix it, and
      sign it off when it is done. This guide takes about ten minutes to read.
    </p>

    <div class="mb-4 grid border-y border-surface-300 sm:grid-cols-3">
      <div v-for="(role, index) in ROLES" :key="role.title" class="py-3 sm:py-4" :class="index > 0 ? 'border-t border-surface-200 sm:border-l sm:border-t-0 sm:pl-4' : 'sm:pr-4'">
        <h2 class="m-0 mb-1 font-heading text-[0.9375rem] font-medium">{{ role.title }}</h2>
        <p class="m-0 text-sm text-surface-600">{{ role.text }}</p>
      </div>
    </div>

    <p class="m-0 text-sm text-surface-600">
      You see only your own organization's stations, requests and reports. Nobody from another organization can see yours.
    </p>

    <section :id="SECTIONS[0]!.id" :aria-labelledby="`${SECTIONS[0]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[0]!.id}-h`" :number="1" :title="SECTIONS[0]!.title" />
      <p class="m-0">You need an up-to-date browser and an internet connection. It works on a computer, a tablet or a phone.</p>

      <ol :class="stepsClass">
        <GuideStep :n="1">Open the invitation email from {{ APP_NAME }} and click the link in it. The link works for <b>7 days</b>.</GuideStep>
        <GuideStep :n="2">Choose a password of at least 12 characters, then click <b>Save</b>.</GuideStep>
        <GuideStep :n="3">You are signed in and land on your dashboard. Bookmark the page so you can find it again.</GuideStep>
      </ol>

      <p :class="tipClass">
        <b>Link expired?</b> Open it anyway and click <b>Send a new link</b>. <b>Forgot your password later?</b> Click
        <router-link class="text-primary underline underline-offset-2" :to="{ name: 'forgot-password' }">Forgot password?</router-link> on the Log in page.
      </p>
    </section>

    <section :id="SECTIONS[1]!.id" :aria-labelledby="`${SECTIONS[1]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[1]!.id}-h`" :number="2" :title="SECTIONS[1]!.title" />
      <p class="m-0">Start from your dashboard, your list of requests or a station's page. Starting from a station fills it in for you.</p>

      <ol :class="stepsClass">
        <GuideStep :n="1">Click <b>Report a problem</b>.</GuideStep>
        <GuideStep :n="2">Pick the station, or several if the same problem affects them all.</GuideStep>
        <GuideStep :n="3">Give it a short title and describe what you see: which readings are wrong, since when, anything you have already tried.</GuideStep>
        <GuideStep :n="4">Choose a category ({{ categoryList }}) and how urgent it is ({{ priorityRange }}).</GuideStep>
        <GuideStep :n="5">Add photos or PDFs if they help, then click <b>Submit</b>.</GuideStep>
      </ol>

      <p :class="tipClass">
        Your request gets a reference such as <span class="font-mono text-[0.9em]" translate="no">MR-2026-0042</span>.
        Quote it whenever you talk to us about the request.
      </p>
    </section>

    <section :id="SECTIONS[2]!.id" :aria-labelledby="`${SECTIONS[2]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[2]!.id}-h`" :number="3" :title="SECTIONS[2]!.title" />

      <p class="m-0">
        Each request shows its status at the top and updates by itself, so you never need to reload. On the request you can
        also see who is working on it, when the visits are planned, and write comments to the team. You can change a comment
        for 15 minutes after you post it.
      </p>

      <div class="mt-4 overflow-x-auto">
        <table class="w-full border-collapse text-[0.9375rem]">
          <thead>
            <tr>
              <th v-for="heading in ['Status', 'What it means', 'What you can do']" :key="heading" class="border-b border-surface-300 pb-2.5 pr-3 text-left text-xs font-medium uppercase tracking-wider text-surface-600" scope="col">
                {{ heading }}
              </th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="row in STATUS_ROWS" :key="row.status">
              <td class="w-px whitespace-nowrap border-b border-surface-200 py-3 pr-3 align-top"><RequestStatusChip :status="row.status" /></td>
              <td class="border-b border-surface-200 py-3 pr-3 align-top">{{ row.means }}</td>

              <td class="border-b border-surface-200 py-3 align-top text-sm text-surface-600">
                <router-link v-if="row.status === 'client_review'" class="text-primary" replace :to="{ hash: '#review' }">{{ row.can }}</router-link>
                <template v-else>{{ row.can }}</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section :id="SECTIONS[3]!.id" :aria-labelledby="`${SECTIONS[3]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[3]!.id}-h`" :number="4" :title="SECTIONS[3]!.title" />
      <p class="m-0">When the work is done we email you. Your answer tells us the work is finished, or that something still needs attention.</p>

      <ol :class="stepsClass">
        <GuideStep :n="1">Click <b>Review the work</b> in the email, or <b>Review and sign off</b> on the request.</GuideStep>
        <GuideStep :n="2">Read the visit reports and look at the photos.</GuideStep>

        <GuideStep :n="3">
          If you are satisfied, click <b>Accept work</b>, type your full name, draw your signature, tick the statement and click
          <b>Sign and accept</b>. The request closes and we make a close-out report.
        </GuideStep>

        <GuideStep :n="4">If something is not right, click <b>Reject</b>, say what is wrong, and click <b>Send</b>. The same team picks it up again.</GuideStep>
      </ol>

      <ol aria-label="What happens if you do not answer" class="m-0 mt-4 grid list-none overflow-hidden rounded-lg border border-surface-300 bg-surface-0 p-0 sm:grid-cols-5">
        <li
          v-for="(step, index) in REVIEW_CLOCK"
          :key="step.day"
          class="grid grid-cols-[4.5rem_1fr] gap-2 p-3 sm:block"
          :class="index > 0 ? 'border-t border-surface-200 sm:border-l sm:border-t-0' : ''"
        >
          <span class="font-mono text-sm font-medium tabular-nums sm:mb-1 sm:block" :class="index === REVIEW_CLOCK.length - 1 ? 'text-success' : 'text-primary'">Day {{ step.day }}</span>
          <span class="text-sm text-surface-600">{{ step.label }}</span>
        </li>
      </ol>

      <p :class="tipClass">
        If you do not answer within 30 days, the request closes by itself and the close-out report says so. If we correct a
        report while you are reviewing, you will see <b>“A corrected report is on its way”</b> and the 30 days start again.
      </p>
    </section>

    <section :id="SECTIONS[4]!.id" :aria-labelledby="`${SECTIONS[4]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[4]!.id}-h`" :number="5" :title="SECTIONS[4]!.title" />

      <p class="m-0">
        You can add your organization's own report to any request, at any time. Open the request, go to the Reports tab and
        click <b>Add a client report</b>. Then choose one of these:
      </p>

      <ol :class="stepsClass">
        <GuideStep :n="1"><b>Upload a PDF</b>: one file up to 25 MB, with a title and a date.</GuideStep>

        <GuideStep :n="2">
          <b>Fill in the online form</b>: a summary, notes for each station, data-quality notes and up to 10 photos (JPEG or
          PNG). It saves as you type and stays private to you until you submit it. We turn it into a PDF.
        </GuideStep>
      </ol>

      <p :class="tipClass">Once you click <b>Submit</b>, the report cannot be changed. Add a new one if something needs correcting.</p>
    </section>

    <section :id="SECTIONS[5]!.id" :aria-labelledby="`${SECTIONS[5]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[5]!.id}-h`" :number="6" :title="SECTIONS[5]!.title" />

      <p class="m-0">
        <b>Stations</b> lists your stations and their status. <b>Map</b> shows where they are. A station's page shows its open
        requests, its past reports and the documents we have shared with you, such as manuals and calibration certificates.
      </p>

      <p class="m-0">
        Each station has a printed label with a QR code. Point your phone's camera at it and tap the link: the station's page
        opens (sign in first if asked), and <b>Report a problem</b> is right there.
      </p>
    </section>

    <section :id="SECTIONS[6]!.id" :aria-labelledby="`${SECTIONS[6]!.id}-h`" :class="sectionClass">
      <GuideHeading :id="`${SECTIONS[6]!.id}-h`" :number="7" :title="SECTIONS[6]!.title" />

      <p class="m-0">
        The bell at the top of the app lists what has changed on your requests: a status change, a planned visit, a new
        comment, work ready for review. We also email you about the steps that need you, such as review and sign-off.
      </p>

      <p class="m-0">
        To choose which emails you get, open <b>My profile</b> from the menu with your initials and go to
        <b>Email preferences</b>. Emails about your account and your password are always sent. Please keep
        <b>Work is ready for your review</b> on: the request closes by itself 30 days after the work is ready.
      </p>
    </section>

    <section aria-labelledby="help-h" class="mt-16 flex flex-col gap-2 border-t border-surface-300 pt-6">
      <h2 id="help-h" class="m-0 font-heading text-xl font-medium">Need help?</h2>

      <p class="m-0 text-surface-600">
        Write a comment on the request: the team working on it sees it straight away. Quote the reference, for example
        <span class="font-mono text-[0.9em]" translate="no">MR-2026-0042</span>, if you write to us another way.
      </p>

      <p class="m-0 text-surface-600">
        Cannot sign in? Use <router-link class="text-primary underline underline-offset-2" :to="{ name: 'forgot-password' }">Forgot password?</router-link>
        first. If that does not help, contact the person at our team who invited you.
      </p>

      <div class="mt-3">
        <v-btn v-if="session.user" color="primary" :to="{ name: 'dashboard' }">Go to your dashboard</v-btn>
        <v-btn v-else color="primary" :to="{ name: 'login' }">Log in</v-btn>
      </div>
    </section>
  </article>
</template>

<script lang="ts" setup>
  import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { APP_NAME } from '@/app/brand'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import { CATEGORIES, PRIORITIES } from '@/features/requests/requests'
  import { useSessionStore } from '@/stores/session'
  import { currentSection, REVIEW_CLOCK, SECTIONS, STATUS_ROWS } from './clientGuide'
  import GuideHeading from './GuideHeading.vue'
  import GuideStep from './GuideStep.vue'

  // The client guide (W23-5): public, read signed in or not; the invitation email links here.
  const session = useSessionStore()
  const route = useRoute()

  const ROLES = [
    { title: 'You report', text: 'A problem at one or more of your stations, with photos if you have them.' },
    { title: 'We do the work', text: 'We approve it, send a technician and write a visit report.' },
    { title: 'You sign off', text: 'You read the reports and accept the work, or send it back.' },
  ] as const

  const sectionClass = 'flex scroll-mt-4 flex-col gap-4 pt-12 md:pt-14'
  const stepsClass = 'm-0 flex list-none flex-col p-0'
  const tipClass = 'm-0 rounded-lg border border-surface-300 bg-surface-0 px-4 py-3 text-[0.9375rem]'

  const categoryList = computed(() => listOf(CATEGORIES.map(c => c.label)))
  const priorityRange = computed(() => `${PRIORITIES[0]!.label} to ${PRIORITIES.at(-1)!.label}`)

  function listOf (words: readonly string[]): string {
    return words.length < 2 ? words.join('') : `${words.slice(0, -1).join(', ')} or ${words.at(-1)}`
  }

  // Which section is being read, for the contents on the dark side
  const current = ref(0)
  function onScroll (): void {
    const tops = SECTIONS.map(s => document.querySelector(`#${s.id}`)?.getBoundingClientRect().top ?? Number.POSITIVE_INFINITY)
    current.value = currentSection(tops, window.innerHeight * 0.35)
  }

  /*
    The router scrolls to a section when a contents link changes the hash (scrollBehavior, meta
    `wide`). Opening the guide cold at /help/client#section can mount the page after that, so
    the first mount goes there itself.
  */
  async function jump (hash: string): Promise<void> {
    await nextTick()
    const target = hash ? document.querySelector<HTMLElement>(hash) : null
    if (!target) {
      return
    }
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' })
  }

  function closeContents (event: MouseEvent): void {
    const details = (event.currentTarget as HTMLElement).closest('details')
    if (details) {
      details.open = false
    }
  }

  onMounted(() => {
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    if (route.hash) {
      void jump(route.hash)
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('scroll', onScroll)
  })
</script>
