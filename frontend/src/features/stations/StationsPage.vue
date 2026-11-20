<template>
  <PageBody
    :back="isNew ? { name: 'stations', query: listQuery } : (editing && stationId ? { name: 'stations', params: { id: stationId }, query: listQuery } : (open ? { name: 'stations', query: listQuery } : undefined))"
    :back-label="editing ? 'Back to the station' : `Back to ${listLabel.toLowerCase()}`"
    :record="open ? (editing ? `${routeId}/edit` : routeId) : null"
    :stacked="Boolean(detail) && !editing"
    :subtitle="open ? undefined : summary"
    :title="isNew ? 'New station' : (stationId ? (detail?.name ?? 'Station') : undefined)"
    :wide="!open || isNew"
  >
    <template v-if="detail" #subtitle>
      <span class="font-mono font-medium text-surface-900" translate="no">{{ detail.code }}</span>
      <StationStatusChip :status="detail.status" />
      <span class="max-md:basis-full"><span :title="detail.time_zone">{{ countryName(detail.country) }} · {{ zoneAbbreviation(detail.time_zone) }}</span><template v-if="isStaff && detail.owner_org_name"> · {{ detail.owner_org_name }}</template></span>
    </template>

    <template v-if="!open" #actions>
      <v-btn v-if="isClient" color="primary" rounded="full" :to="{ name: 'request-new' }">Report a problem</v-btn>
      <!-- Phones are for the field: adding a station is an office job, so it steps back there -->
      <v-btn
        v-else-if="canWrite"
        :class="mdAndUp ? undefined : 'text-primary'"
        :color="mdAndUp ? 'primary' : undefined"
        :prepend-icon="mdiPlus"
        rounded="full"
        :to="{ name: 'stations', params: { id: 'new' }, query: listQuery }"
        :variant="mdAndUp ? 'flat' : 'tonal'"
      >New station</v-btn>
    </template>

    <template v-else-if="detail && isClient" #actions>
      <v-btn color="primary" rounded="full" :to="{ name: 'request-new', query: { station: detail.id } }">Report a problem</v-btn>
    </template>

    <!-- Technicians and admins write stations (viewers never see these: rule 5) -->
    <template v-else-if="detail && canWrite && !editing" #actions>
      <!-- Phones: a plain text button; the page is for reading, and Edit is one tap away -->
      <v-btn
        color="primary"
        :prepend-icon="mdAndUp ? mdiPencilOutline : undefined"
        rounded="full"
        :to="{ name: 'stations', params: { id: detail.id, mode: 'edit' }, query: listQuery }"
        :variant="mdAndUp ? 'flat' : 'text'"
      >Edit</v-btn>
    </template>

    <!--
      The pane holds every filter, each a button with its count (approved "Stations pane filters",
      2026-11-20): the two lists, the problems under Needs attention, the statuses under All stations,
      then the fields that narrow both. With a station open the filters fold to one line and the
      matching stations follow. The new-station form has no pane: its map takes the width.
    -->
    <PaneContent v-if="!isNew" pin>
      <div class="flex flex-col gap-5 px-3">
        <!-- Search; phones put Scan beside it for staff on site -->
        <div class="flex items-center gap-2">
          <v-text-field
            aria-label="Search stations by code, name or ID"
            autocomplete="off"
            class="grow [&_.v-field]:shadow-none!"
            clearable
            :height="mdAndUp ? 40 : 48"
            hide-details
            :model-value="filters.q"
            name="q"
            placeholder="Code, name or ID…"
            :prepend-inner-icon="mdiMagnify"
            rounded="full"
            spellcheck="false"
            type="search"
            @update:model-value="setFilters({ q: $event ?? '' })"
          />

          <v-btn
            v-if="!mdAndUp && !open && canWrite"
            aria-label="Scan a station label"
            class="text-primary"
            :icon="mdiQrcodeScan"
            rounded="full"
            size="48"
            :to="{ name: 'scan' }"
            variant="tonal"
          />
        </div>

        <!-- From 768 px: the ledger -->
        <template v-if="mdAndUp">
          <!-- A station open: what the pane is showing, folded to one line -->
          <div v-if="open" class="flex min-h-12 items-center gap-2 rounded-card bg-surface-100 py-1 pl-3 pr-1">
            <span class="flex min-w-0 grow flex-col">
              <span class="text-xs text-surface-600">Showing</span>
              <span class="truncate font-semibold text-surface-900">{{ listLabel }}</span>
            </span>

            <span v-if="narrowing.length > 0" class="whitespace-nowrap rounded-full bg-primary-100 px-2 text-xs font-semibold text-primary-700 dark:bg-primary-800 dark:text-primary-100">+{{ narrowing.length }} more</span>

            <v-btn
              aria-controls="station-filters"
              :aria-expanded="changing"
              class="text-primary"
              height="36"
              variant="text"
              @click="changing = !changing"
            >{{ changing ? 'Done' : 'Change' }}</v-btn>
          </div>

          <div v-show="!open || changing" id="station-filters" class="flex flex-col gap-5">
            <div class="flex flex-col">
              <h3 :id="`${uid}-show`" class="m-0 px-2 pb-1.5 text-sm font-semibold text-surface-900">Show</h3>

              <div :aria-labelledby="`${uid}-show`" class="flex flex-col" role="group">
                <button
                  :aria-controls="`${uid}-attention`"
                  :aria-expanded="!folded.attention"
                  :aria-pressed="listPressed('attention')"
                  class="flex w-full items-center gap-3 rounded-card pl-3 pr-1.5 text-left font-semibold transition-colors duration-150"
                  :class="[open ? 'h-10' : 'h-12', listPressed('attention') ? pressedClass : 'text-surface-900 hover:bg-surface-100']"
                  type="button"
                  @click="onHeader('attention')"
                >
                  <v-icon :icon="mdiAlertOutline" size="20" />
                  <span class="grow">Needs attention</span>
                  <span class="font-heading font-semibold tabular-nums" :class="open ? 'text-base' : 'text-2xl'">{{ attentionTotal }}</span>
                  <v-icon class="text-surface-600 transition-transform duration-150" :class="folded.attention ? '-rotate-90' : ''" :icon="mdiChevronDown" size="20" />
                </button>

                <div
                  v-show="!folded.attention"
                  :id="`${uid}-attention`"
                  aria-label="Problems"
                  class="mb-2.5 ml-5.5 mt-0.5 flex flex-col gap-0.5 border-l border-surface-200 pl-2.5"
                  role="group"
                >
                  <button
                    v-for="p in PROBLEMS"
                    :key="p"
                    :aria-pressed="problem === p"
                    class="grid grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-card px-2.5 text-left transition-colors duration-150"
                    :class="[open ? 'min-h-10 py-1' : 'min-h-13 py-1.5', problem === p ? pressedClass : 'hover:bg-surface-100']"
                    type="button"
                    @click="setProblem(problem === p ? null : p)"
                  >
                    <v-icon :class="problemLook[p].mark" :icon="problemLook[p].icon" size="16" />
                    <span class="text-sm font-medium text-surface-900">{{ problemLook[p].label }}</span>

                    <span
                      class="col-start-3 row-span-2 row-start-1 min-w-[2ch] text-right font-heading font-semibold tabular-nums"
                      :class="[open ? 'text-base' : 'text-2xl', counts[p] === 0 ? 'text-surface-600' : 'text-surface-900']"
                    >{{ counts[p] }}</span>

                    <span v-if="!open" class="col-start-2 text-xs text-surface-600">{{ hints[p] }}</span>
                  </button>
                </div>

                <button
                  :aria-controls="`${uid}-all`"
                  :aria-expanded="!folded.all"
                  :aria-pressed="listPressed('all')"
                  class="flex w-full items-center gap-3 rounded-card pl-3 pr-1.5 text-left font-semibold transition-colors duration-150"
                  :class="[open ? 'h-10' : 'h-12', listPressed('all') ? pressedClass : 'text-surface-900 hover:bg-surface-100']"
                  type="button"
                  @click="onHeader('all')"
                >
                  <v-icon :icon="mdiFormatListBulleted" size="20" />
                  <span class="grow">All stations</span>
                  <span class="font-heading font-semibold tabular-nums" :class="open ? 'text-base' : 'text-2xl'">{{ inScope.length }}</span>
                  <v-icon class="text-surface-600 transition-transform duration-150" :class="folded.all ? '-rotate-90' : ''" :icon="mdiChevronDown" size="20" />
                </button>

                <div
                  v-show="!folded.all"
                  :id="`${uid}-all`"
                  aria-label="Status"
                  class="ml-5.5 mt-0.5 flex flex-wrap gap-1.5 border-l border-surface-200 py-1.5 pl-3"
                  role="group"
                >
                  <button
                    v-for="option in statusOptions"
                    :key="option.value"
                    :aria-pressed="filters.status === option.value"
                    class="inline-flex h-8 items-center gap-1.5 rounded-full border pl-2 pr-2.5 text-[13px] font-medium transition-colors duration-150"
                    :class="filters.status === option.value ? chipOnClass : 'border-surface-300 text-surface-900 hover:bg-surface-100'"
                    type="button"
                    @click="setStatus(filters.status === option.value ? null : option.value)"
                  >
                    <StationStatusMark :status="option.value" />
                    {{ option.label }}<span class="font-semibold tabular-nums" :class="filters.status === option.value ? '' : 'text-surface-600'">{{ option.count }}</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Organization, country, type and measures narrow both lists -->
            <details class="border-t border-surface-200 pt-2" :open="narrowOpen" @toggle="narrowOpen = ($event.target as HTMLDetailsElement).open">
              <summary class="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-card px-2 hover:bg-surface-100 [&::-webkit-details-marker]:hidden">
                <span class="text-sm font-semibold text-surface-900">Narrow both lists</span>
                <span v-if="extraFilters > 0" class="rounded-full bg-primary-100 px-2 text-xs font-semibold text-primary-700 dark:bg-primary-800 dark:text-primary-100">{{ extraFilters }} on</span>
                <v-icon class="ml-auto text-surface-600 transition-transform duration-150" :class="narrowOpen ? 'rotate-180' : ''" :icon="mdiChevronDown" size="20" />
              </summary>

              <StationFilterFields
                class="px-1 pt-3"
                :facets="facets"
                :filters="filters"
                inline
                :show-org="isStaff"
                @change="setFilters"
              />
            </details>
          </div>

          <!-- A station open: the matching stations to switch between, the open one highlighted -->
          <div v-if="open" class="flex flex-col border-t border-surface-200 pt-3">
            <div class="flex items-baseline justify-between gap-2 px-2 pb-1.5">
              <h3 class="m-0 text-sm font-semibold text-surface-900">{{ plural(switchList.length, 'station') }}</h3>
              <router-link class="inline-flex min-h-6 items-center text-sm font-medium text-primary no-underline hover:underline" :to="{ name: 'stations', query: listQuery }">See the list</router-link>
            </div>

            <p v-if="!loading && switchList.length === 0" class="m-0 px-2 text-sm text-surface-600">No stations match.</p>

            <ul v-else aria-label="Stations" class="m-0 flex list-none flex-col gap-0.5 p-0">
              <li
                v-for="row in switchList"
                :key="row.id"
                class="relative flex items-center gap-3 rounded-card px-3 py-2.5 transition-colors duration-150"
                :class="row.id === stationId ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
                :data-current="row.id === stationId ? '' : undefined"
                @click="keyPress"
                @pointercancel="release"
                @pointerdown="press"
                @pointerleave="release"
                @pointerup="release"
              >
                <span class="grid size-10 shrink-0 place-items-center rounded-card" :class="lookOf(row.status).chip">
                  <v-icon :icon="lookOf(row.status).icon" size="20" />
                </span>

                <span class="flex min-w-0 grow flex-col">
                  <span class="flex items-baseline justify-between gap-2">
                    <router-link
                      :aria-current="row.id === stationId ? 'page' : undefined"
                      class="min-w-0 truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
                      :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
                    >{{ row.name }}</router-link>

                    <span class="shrink-0 font-mono text-xs font-medium text-surface-600" translate="no">{{ row.code }}</span>
                  </span>

                  <span class="truncate text-sm text-surface-600">
                    {{ lookOf(row.status).label }} · <template v-if="isStaff">{{ row.owner_org_name }} · </template>{{ countryName(row.country) }}
                  </span>
                </span>
              </li>
            </ul>
          </div>
        </template>

        <!-- Phones: the two lists as a switch, that list's filters as chips, the rest in a sheet -->
        <template v-else-if="!open">
          <div aria-label="Lists" class="grid grid-cols-2 rounded-full border border-surface-300 p-0.5" role="group">
            <button
              v-for="list in lists"
              :key="list.view"
              :aria-pressed="view === list.view"
              class="flex h-10 items-center justify-center gap-1.5 rounded-full text-sm font-semibold transition-colors duration-150"
              :class="view === list.view ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'text-surface-700'"
              type="button"
              @click="setList(list.view)"
            >{{ list.label }}<span class="font-heading tabular-nums">{{ list.count }}</span></button>
          </div>

          <div aria-label="Show only" class="flex flex-wrap gap-1.5 pb-3" role="group">
            <template v-if="view === 'attention'">
              <button
                v-for="p in PROBLEMS"
                :key="p"
                :aria-pressed="problem === p"
                class="inline-flex h-10 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
                :class="problem === p ? chipOnClass : 'border-surface-300 text-surface-900'"
                type="button"
                @click="setProblem(problem === p ? null : p)"
              >
                <v-icon :class="problemLook[p].mark" :icon="problemLook[p].icon" size="16" />
                {{ problemLook[p].label }}<span class="font-heading font-semibold tabular-nums" :class="problem === p ? '' : 'text-surface-600'">{{ counts[p] }}</span>
              </button>
            </template>

            <template v-else>
              <button
                v-for="option in statusOptions"
                :key="option.value"
                :aria-pressed="filters.status === option.value"
                class="inline-flex h-10 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
                :class="filters.status === option.value ? chipOnClass : 'border-surface-300 text-surface-900'"
                type="button"
                @click="setStatus(filters.status === option.value ? null : option.value)"
              >
                <StationStatusMark :status="option.value" />
                {{ option.label }}<span class="font-heading font-semibold tabular-nums" :class="filters.status === option.value ? '' : 'text-surface-600'">{{ option.count }}</span>
              </button>
            </template>

            <button
              class="inline-flex h-10 items-center gap-1.5 rounded-full border border-surface-300 px-3 text-sm font-medium text-surface-900"
              type="button"
              @click="sheet = true"
            >
              <v-icon :icon="mdiFilterVariant" size="16" />
              More filters<span v-if="extraFilters" class="tabular-nums text-primary">{{ extraFilters }}</span>
            </button>
          </div>
        </template>
      </div>
    </PaneContent>

    <!-- The view: the form for a new station -->
    <StationQuickForm
      v-if="isNew"
      ref="formEl"
      :stations="stations"
      @cancel="router.push({ name: 'stations', query: listQuery })"
      @saved="saved"
    />

    <!-- The view: one station -->
    <template v-else-if="stationId">
      <FeedbackBanner v-if="detailError" :type="detailError === 'missing' ? 'info' : 'error'">{{ detailMessage }}</FeedbackBanner>

      <div v-else-if="!detail" aria-label="Loading the station…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <StationForm
        v-else-if="editing"
        :key="`${detail.id}-${formKey}`"
        ref="formEl"
        :station="detail"
        :stations="stations"
        :suggestions="suggestions"
        @cancel="router.push({ name: 'stations', params: { id: detail.id }, query: listQuery })"
        @reload="reloadDetail"
        @saved="saved"
      />

      <StationDetailView
        v-else
        :can-write="canWrite"
        :is-staff="isStaff"
        :station="detail"
        @qr-replaced="detail = $event"
      />
    </template>

    <!-- The view: the chosen list -->
    <div v-else class="flex flex-col gap-3">
      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="loading" aria-label="Loading stations…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <template v-else>
        <!-- What is shown, how many, and each narrowing with a button to remove it -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-surface-200 pb-3">
          <h2 class="m-0 font-heading text-xl font-semibold text-surface-900">{{ listLabel }}</h2>
          <span class="tabular-nums text-surface-600">{{ plural(resultCount, 'station') }}</span>

          <span
            v-for="chip in narrowing"
            :key="chip.key"
            class="inline-flex h-7 items-center gap-1 rounded-full bg-primary-50 pl-3 pr-0.5 text-[13px] font-medium text-primary-700 dark:text-primary"
          >
            {{ chip.label }}
            <button
              :aria-label="`Remove ${chip.label}`"
              class="grid size-6 place-items-center rounded-full hover:bg-primary-100 dark:hover:bg-primary-800"
              type="button"
              @click="removeNarrowing(chip.key)"
            >
              <v-icon :icon="mdiClose" size="14" />
            </button>
          </span>
        </div>

        <!-- Needs attention: what is wrong, ranked, each row with its next step -->
        <template v-if="view === 'attention'">
          <div v-if="rows.length === 0" class="flex flex-col items-center gap-2 py-10 text-center">
            <p class="m-0 text-h3 text-surface-900">{{ emptyAttention.title }}</p>
            <p class="m-0 text-surface-600">{{ emptyAttention.text }}</p>
            <button v-if="narrowing.length > 0" class="inline-flex min-h-6 items-center font-medium text-primary hover:underline" type="button" @click="clearNarrowing">Clear the filters</button>
            <button v-else class="inline-flex min-h-6 items-center font-medium text-primary hover:underline" type="button" @click="setList('all')">See all stations</button>
          </div>

          <ul v-else aria-label="Stations that need attention" class="m-0 list-none p-0">
            <li
              v-for="row in rows"
              :key="row.station.id"
              class="relative grid items-center gap-x-5 gap-y-1.5 border-t border-surface-200 py-3 first:border-t-0 md:min-h-17 md:grid-cols-[176px_minmax(0,240px)_minmax(0,1fr)_auto]"
            >
              <span>
                <span class="inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full pl-2 pr-2.5 text-xs font-medium" :class="problemLook[row.problem].chip">
                  <v-icon :icon="problemLook[row.problem].icon" size="14" />{{ problemLook[row.problem].short }}
                </span>
              </span>

              <span class="flex min-w-0 flex-col">
                <!-- The whole row opens the station; the next step sits above that link -->
                <router-link
                  class="inline-flex min-h-6 items-center truncate text-base font-medium text-surface-900 underline-offset-2 after:absolute after:inset-0 hover:underline md:text-[15px]"
                  :to="{ name: 'stations', params: { id: row.station.id }, query: listQuery }"
                >{{ row.station.name }}</router-link>

                <span class="font-mono text-[13px] font-medium text-surface-600" translate="no">{{ row.station.code }}</span>
              </span>

              <span class="flex min-w-0 flex-col">
                <span class="text-surface-900 md:text-[15px]">{{ row.fact }}</span>
                <span class="text-[13px] text-surface-600">{{ whereOf(row) }}</span>
              </span>

              <span v-if="row.next" class="relative z-1 md:justify-self-end">
                <v-btn
                  :aria-label="`${row.next.label}: ${row.station.code}`"
                  class="text-[13px] text-primary"
                  :height="mdAndUp ? 32 : 36"
                  rounded="full"
                  :to="stepTo(row.next)"
                  variant="tonal"
                >{{ row.next.label }}</v-btn>
              </span>
            </li>
          </ul>
        </template>

        <!-- All stations: the register -->
        <template v-else>
          <p v-if="stations.length === 0" class="m-0 py-8 text-center text-surface-600">
            {{ isClient ? 'Your organization has no stations here yet.' : 'No stations yet. They arrive with the station import.' }}
          </p>

          <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">
            No stations match these filters.
            <button class="font-medium text-primary hover:underline" type="button" @click="clearFilters">Clear filters</button>
          </p>

          <!-- From 768 px: a table -->
          <div v-else-if="mdAndUp" class="overflow-x-auto">
            <table class="w-full border-collapse text-sm">
              <caption class="sr-only">Stations, sorted by code</caption>

              <thead>
                <tr class="bg-surface-100 text-left">
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Code</th>
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Name</th>
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
                  <th v-if="isStaff" class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Organization</th>
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Country</th>
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Last visit</th>
                  <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Calibration</th>
                </tr>
              </thead>

              <tbody>
                <tr
                  v-for="row in shown"
                  :key="row.id"
                  class="h-13 cursor-pointer border-t border-surface-200 hover:bg-surface-50"
                  @click="openFromRow($event, row.id)"
                >
                  <td class="whitespace-nowrap px-3">
                    <router-link
                      class="font-mono font-medium text-primary no-underline hover:underline"
                      :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
                      translate="no"
                    >{{ row.code }}</router-link>
                  </td>

                  <td class="min-w-32 px-3 text-surface-900">{{ row.name }}</td>
                  <td class="px-3"><StationStatusChip :status="row.status" /></td>
                  <!-- Long names (a real one has 50 characters) truncate; the full name is the title -->
                  <td v-if="isStaff" class="max-w-36 truncate px-3 text-surface-900" :title="row.owner_org_name ?? undefined">{{ row.owner_org_name ?? '—' }}</td>
                  <td class="max-w-28 truncate px-3 text-surface-900" :title="countryName(row.country)">{{ countryName(row.country) }}</td>

                  <td class="whitespace-nowrap px-3 tabular-nums" :class="row.last_visit_at ? 'text-surface-900' : 'text-surface-600'">
                    {{ row.last_visit_at ? formatDate(row.last_visit_at, row.time_zone) : 'None yet' }}
                  </td>

                  <td class="px-3">
                    <CalibrationDueChip
                      v-if="row.next_calibration_due_at"
                      :due="row.next_calibration_due_at"
                      :state="dueState(row.next_calibration_due_at, now)"
                      :time-zone="row.time_zone"
                    />

                    <span v-else class="text-surface-600">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Phones: cards that slide up under the pinned header's curve -->
          <ul v-else aria-label="Stations" class="m-0 flex list-none flex-col gap-1 p-0">
            <StationCard
              v-for="row in shown"
              :key="row.id"
              :is-staff="isStaff"
              :now="now"
              :station="row"
              :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
            />
          </ul>
        </template>
      </template>
    </div>

    <!-- Phones: the filters that don't fit in the chip row -->
    <v-bottom-sheet v-model="sheet" aria-labelledby="filters-h">
      <div class="flex flex-col gap-5 rounded-t-card bg-surface px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-5">
        <div class="flex items-center justify-between">
          <h2 id="filters-h" class="m-0 text-h2 text-surface-900">Filters</h2>
          <v-btn class="text-primary" variant="text" @click="sheet = false">Done</v-btn>
        </div>

        <StationFilterFields :facets="facets" :filters="filters" :show-org="isStaff" @change="setFilters" />
      </div>
    </v-bottom-sheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { AttentionRow, NextStep, Problem, StationsView, Work } from './attention'
  import type { StationFilters } from './stations'
  import type { RequestSummary, StationDetail, StationStatus, StationSummary, VisitOut } from '@/api/models'
  import {
    mdiAlertOutline,
    mdiChevronDown,
    mdiClose,
    mdiFilterVariant,
    mdiFormatListBulleted,
    mdiMagnify,
    mdiPencilOutline,
    mdiPlus,
    mdiQrcodeScan,
  } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
  import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { requestsApi, stationsApi, visitsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { countryName } from '@/app/countries'
  import { formatDate, zoneAbbreviation } from '@/app/format'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import { usePaneless, usePaneSelection } from '@/app/shells/pane'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import StationStatusChip from '@/components/StationStatusChip.vue'
  import StationStatusMark from '@/components/StationStatusMark.vue'
  import { useSessionStore } from '@/stores/session'
  import {
    attentionRows,
    emptyWork,
    OPEN_REQUEST_STATUSES,
    problemCounts,
    problemFrom,
    problemLook,
    PROBLEMS,
    viewFrom,
    workFrom,
  } from './attention'
  import StationCard from './StationCard.vue'
  import StationDetailView from './StationDetailView.vue'
  import StationFilterFields from './StationFilterFields.vue'
  import StationForm from './StationForm.vue'
  import StationQuickForm from './StationQuickForm.vue'
  import {
    dueState,
    extraFilterCount,
    facetsOf,
    filtersFrom,
    lookOf,
    matches,
    matchesOthers,
    queryFrom,
    STATUSES,
    statusLook,
  } from './stations'

  // /stations and /stations/:id (AFD §3; PRD STN-5, CAL-3). Clients see their own organization's
  // stations: the server scopes every query (rule 3), this page only hides staff-only columns.
  // A few hundred stations at most (PRD §2): the page loads them all once and filters here, so the
  // filters answer at once and their counts are exact.
  const session = useSessionStore()
  const { isClient, isStaff } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const stations = ref<StationSummary[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const work = ref<Work>(emptyWork())
  const sheet = ref(false)
  const now = new Date()

  // :id is a station's ID, or "new" (the form for a new station); :mode is "edit" (STN-1, STN-2)
  const routeId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  const isNew = computed(() => routeId.value === 'new')
  const stationId = computed(() => isNew.value ? null : routeId.value)
  const editing = computed(() => route.params.mode === 'edit' && stationId.value !== null)
  /** Something is open in the view (a station or the new-station form): phones show it alone. */
  const open = computed(() => routeId.value !== null)
  usePaneSelection(() => open.value)
  // The pane holds the filters; only the new-station form fills the view (its map takes the width)
  usePaneless(() => isNew.value)
  const uid = useId()

  // Technicians and admins write stations; viewers and clients never see the buttons, and the
  // forms send them back to the list (the server refuses them anyway).
  const canWrite = computed(() => session.hasAnyRole(['technician', 'admin']))

  // --- Filters (in the URL) ---------------------------------------------------------------------

  const filters = computed(() => filtersFrom(route.query))
  const view = computed(() => viewFrom(route.query))
  const problem = computed<Problem | null>(() => problemFrom(route.query))
  /** The list's query without the station page's own (`tab`), for links back to the list. */
  // The list and problem chosen go along too; a plain /stations stays plain
  const listQuery = computed(() => ({
    ...queryFrom(filters.value),
    view: typeof route.query.view === 'string' ? view.value : undefined,
    problem: problem.value ?? undefined,
  }))
  const facets = computed(() => facetsOf(stations.value))
  const extraFilters = computed(() => extraFilterCount(filters.value))
  const others = computed(() => stations.value.filter(s => matchesOthers(s, filters.value)))
  const shown = computed(() => stations.value.filter(s => matches(s, filters.value)))
  // The form suggests what other stations already use
  const suggestions = computed(() => ({ types: facets.value.types, parameters: facets.value.parameters }))

  // The statuses under All stations; All stations itself is the list button above them
  const statusOptions = computed(() => STATUSES.map(status => ({
    value: status,
    label: statusLook[status].label,
    count: others.value.filter(s => s.status === status).length,
  })))

  // The route updates only when a navigation finishes. A second change made before then (a click on
  // a status and straight away typing a search) must build on the first, not on the old URL.
  let pendingFilters: StationFilters | null = null

  function setFilters (patch: Partial<StationFilters>): void {
    const next = { ...(pendingFilters ?? filters.value), ...patch }
    pendingFilters = next
    void router.replace({ query: { ...route.query, ...queryFrom(next) } }).finally(() => {
      if (pendingFilters === next) {
        pendingFilters = null
      }
    })
  }

  function clearFilters (): void {
    void router.replace({ query: {} })
  }

  watch([canWrite, open, editing], () => {
    if (session.ready && !canWrite.value && (isNew.value || editing.value)) {
      void router.replace(isNew.value || !stationId.value
        ? { name: 'stations', query: listQuery.value }
        : { name: 'stations', params: { id: stationId.value }, query: listQuery.value })
    }
  }, { immediate: true })

  // --- The list's header and numbers ------------------------------------------------------------

  function plural (n: number, one: string, many = `${one}s`): string {
    return `${n} ${n === 1 ? one : many}`
  }

  const summary = computed(() => {
    if (loading.value || loadError.value) {
      return undefined
    }
    const n = stations.value.length
    if (isClient.value) {
      const org = stations.value[0]?.owner_org_name
      return org ? `${org} · ${plural(n, 'station')}` : plural(n, 'station')
    }
    const countries = new Set(stations.value.map(s => s.country)).size
    return `${plural(n, 'station')} in ${plural(countries, 'country', 'countries')}`
  })

  // --- Needs attention (approved "AWS-MMS Stations redesign") ------------------------------------

  /** Search and the other filters narrow both lists; status belongs to All stations. */
  const inScope = others
  const counts = computed(() => problemCounts(inScope.value, now))
  const rows = computed<AttentionRow[]>(() => attentionRows(inScope.value, work.value, now, canWrite.value, problem.value))
  const attentionTotal = computed(() => attentionRows(inScope.value, work.value, now, false).length)

  const lists = computed(() => [
    { view: 'attention' as const, label: 'Needs attention', count: attentionTotal.value },
    { view: 'all' as const, label: 'All stations', count: inScope.value.length },
  ])

  /** The list or filter being shown, in words: the view's heading and the pane's folded line. */
  const listLabel = computed(() => {
    if (view.value === 'attention') {
      return problem.value ? problemLook[problem.value].label : 'Needs attention'
    }
    return filters.value.status ? statusLook[filters.value.status].label : 'All stations'
  })
  const resultCount = computed(() => view.value === 'attention' ? rows.value.length : shown.value.length)
  /** With a station open, the pane lists the stations of the chosen list to switch between. */
  const switchList = computed(() => view.value === 'attention' ? rows.value.map(r => r.station) : shown.value)

  // Choosing a list, a problem or a status: each belongs to one list, and choosing it opens that list
  function setList (next: StationsView): void {
    void router.replace({ query: { ...route.query, view: next, problem: undefined, status: undefined } })
  }

  function setProblem (next: Problem | null): void {
    void router.replace({ query: { ...route.query, view: 'attention', problem: next ?? undefined, status: undefined } })
  }

  function setStatus (next: StationStatus | null): void {
    void router.replace({ query: { ...route.query, view: 'all', status: next ?? undefined, problem: undefined } })
  }

  /**
   * The two lists fold from their header rows: a press on another list chooses it and opens its
   * section; a press on the list being shown folds or unfolds it, keeping its problem or status.
   */
  const folded = ref<Record<StationsView, boolean>>({ attention: false, all: false })

  function onHeader (which: StationsView): void {
    if (view.value === which) {
      folded.value[which] = !folded.value[which]
      return
    }
    folded.value[which] = false
    setList(which)
  }

  function listPressed (which: StationsView): boolean {
    return view.value === which && (which === 'attention' ? !problem.value : !filters.value.status)
  }

  const pressedClass = 'bg-primary-50 text-primary-700 shadow-[inset_0_0_0_1px] shadow-primary dark:text-primary'
  const chipOnClass = 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100'

  /** Search and the fields that narrow both lists, each shown above the rows with a way to remove it. */
  const narrowing = computed(() => {
    const f = filters.value
    const chips: { key: 'q' | 'org' | 'country' | 'type' | 'parameter', label: string }[] = []
    if (f.q.trim()) {
      chips.push({ key: 'q', label: `“${f.q.trim()}”` })
    }
    if (f.org) {
      chips.push({ key: 'org', label: facets.value.orgs.find(o => o.value === f.org)?.title ?? 'Organization' })
    }
    if (f.country) {
      chips.push({ key: 'country', label: countryName(f.country) })
    }
    if (f.type) {
      chips.push({ key: 'type', label: f.type })
    }
    if (f.parameter) {
      chips.push({ key: 'parameter', label: `Measures ${f.parameter}` })
    }
    return chips
  })

  function removeNarrowing (key: 'q' | 'org' | 'country' | 'type' | 'parameter'): void {
    setFilters(key === 'q' ? { q: '' } : { [key]: null })
  }

  function clearNarrowing (): void {
    setFilters({ q: '', org: null, country: null, type: null, parameter: null })
  }

  // A station open: the filters fold to one line until Change; the fields fold away
  const changing = ref(false)
  const narrowOpen = ref(true)
  watch(stationId, (id, was) => {
    if (!id || !was) {
      changing.value = false
    }
    narrowOpen.value = !id
    // The open station is in view in the pane's list
    void nextTick(() => document.querySelector('[data-current]')?.scrollIntoView({ block: 'nearest' }))
  }, { immediate: true })

  const hints = computed<Record<Problem, string>>(() => {
    const soon = inScope.value.filter(s => s.status !== 'decommissioned' && dueState(s.next_calibration_due_at, now) === 'due_soon').length
    const idle = inScope.value
      .filter(s => s.last_visit_at && s.status !== 'decommissioned')
      .map(s => Math.floor((now.getTime() - new Date(s.last_visit_at!).getTime()) / 86_400_000))
    const longest = Math.max(0, ...idle)
    // Never visited is not "idle" (imported stations have no visits here yet), but it is said
    const never = inScope.value.filter(s => !s.last_visit_at && s.status !== 'decommissioned').length
    return {
      offline: 'Marked offline by staff',
      degraded: 'Working, with a fault',
      overdue: soon > 0 ? `${soon} more due in 30 days` : 'None due in 30 days',
      idle: [
        counts.value.idle > 0 ? `Longest: ${longest} days` : 'None over 90 days',
        never > 0 ? `${never} never visited here` : null,
      ].filter(Boolean).join(' · '),
    }
  })

  const emptyAttention = computed(() => {
    if (narrowing.value.length > 0) {
      return { title: 'No station matches.', text: 'Choose another filter, or clear the ones above.' }
    }
    return problem.value
      ? { title: `No station is ${problemLook[problem.value].label.toLowerCase()}.`, text: 'Choose another problem, or see every station.' }
      : { title: 'Nothing needs attention.', text: 'No station is offline, degraded, overdue for calibration or unvisited for 90 days.' }
  })

  function whereOf (row: AttentionRow): string {
    const s = row.station
    const also = row.also.length > 0 ? `Also ${row.also.map(p => problemLook[p].label.toLowerCase()).join(', ')}` : null
    return [isStaff.value ? s.owner_org_name : null, countryName(s.country), row.workRef, also].filter(Boolean).join(' · ')
  }

  function stepTo (step: NextStep): object {
    switch (step.kind) {
      case 'visit': {
        return { name: 'visits', params: { id: step.id } }
      }
      case 'request': {
        return { name: 'requests', params: { id: step.id } }
      }
      default: {
        return { name: 'request-new', query: { station: step.stationId } }
      }
    }
  }

  /** Open visits and requests, so each row can say what is under way and offer its next step. */
  async function loadWork (): Promise<void> {
    try {
      const visits: VisitOut[] = []
      for (const status of ['started', 'planned']) {
        let after: string | undefined
        do {
          const page = await visitsApi.list({ status, limit: 200, after })
          visits.push(...page.items)
          after = page.next_after ?? undefined
        } while (after)
      }
      const requests: RequestSummary[] = []
      let after: string | undefined
      do {
        const page = await requestsApi.list({ status: [...OPEN_REQUEST_STATUSES], limit: 200, after })
        requests.push(...page.items)
        after = page.next_after ?? undefined
      } while (after)
      work.value = workFrom(visits, requests)
    } catch {
      work.value = emptyWork() // the rows still show the problems; only the next step falls back
    }
  }

  // --- Loading ----------------------------------------------------------------------------------

  function failure (error: unknown, what: string): string {
    return error instanceof NetworkError
      ? 'This needs a connection. It will load when you have signal.'
      : `We couldn’t load ${what}. Reload the page to try again.`
  }

  async function load (): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const all: StationSummary[] = []
      let after: string | undefined
      do {
        const page = await stationsApi.list({ limit: 500, after })
        all.push(...page.items)
        after = page.next_after ?? undefined
      } while (after)
      stations.value = all
    } catch (error) {
      loadError.value = failure(error, 'the stations')
    } finally {
      loading.value = false
    }
    if (isStaff.value) {
      await loadWork()
    }
  }

  // --- One station ------------------------------------------------------------------------------

  const detail = ref<StationDetail | null>(null)
  const detailError = ref<'missing' | 'offline' | 'failed' | null>(null)
  const detailMessage = computed(() => {
    switch (detailError.value) {
      case 'missing': {
        return 'We can’t find this station. It may have been removed, or the link may be wrong.'
      }
      case 'offline': {
        return 'This needs a connection. It will load when you have signal.'
      }
      default: {
        return 'We couldn’t load this station. Reload the page to try again.'
      }
    }
  })
  let detailAbort: AbortController | null = null

  async function fetchDetail (id: string): Promise<void> {
    detailAbort?.abort()
    detailError.value = null
    const abort = new AbortController()
    detailAbort = abort
    try {
      detail.value = await stationsApi.get(id, abort.signal)
    } catch (error) {
      if (abort.signal.aborted) {
        return
      }
      // Out of scope and missing look the same (ADR-16: 404, not 403)
      detailError.value = error instanceof ApiError && (error.status === 404 || error.status === 422)
        ? 'missing'
        : (error instanceof NetworkError ? 'offline' : 'failed')
    }
  }

  watch(stationId, id => {
    if (!id) {
      detailAbort?.abort()
      detailError.value = null
      detail.value = null
      return
    }
    if (detail.value?.id !== id) {
      detail.value = null
    }
    void fetchDetail(id)
  }, { immediate: true })

  // --- The form (STN-1, STN-2) --------------------------------------------------------------------

  // The edit form or the new-station one: both ask before unsaved changes are lost
  const formEl = ref<{ confirmLeave: () => Promise<boolean> } | null>(null)
  /** Bumped to start the edit form over with the station as it is now. */
  const formKey = ref(0)

  async function reloadDetail (): Promise<void> {
    if (stationId.value) {
      await fetchDetail(stationId.value)
      formKey.value++
    }
  }

  /** The station as saved goes into the list and its page. */
  function saved (station: StationDetail): void {
    detail.value = station
    const at = stations.value.findIndex(s => s.id === station.id)
    if (at === -1) {
      // A fresh array: sorting it in place is safe, and toSorted needs iOS 16
      // eslint-disable-next-line unicorn/no-array-sort
      stations.value = [...stations.value, station].sort((a, b) => a.code.localeCompare(b.code))
    } else {
      stations.value[at] = station
    }
    void router.push({ name: 'stations', params: { id: station.id }, query: listQuery.value })
  }

  // A form with unsaved changes asks before the person leaves it (another station, another page)
  async function allowLeave (): Promise<boolean> {
    return (await formEl.value?.confirmLeave()) ?? true
  }

  onBeforeRouteLeave(allowLeave)
  onBeforeRouteUpdate(async (to, from) => {
    // Filters in the URL change on this page without leaving the form; anything else asks
    return to.params.id === from.params.id && to.params.mode === from.params.mode ? true : await allowLeave()
  })

  onBeforeUnmount(() => detailAbort?.abort())

  // --- Rows -------------------------------------------------------------------------------------

  /** A click anywhere on a table row opens the station; the code link is the keyboard's way. */
  function openFromRow (event: MouseEvent, id: string): void {
    if ((event.target as Element).closest('a, button') || window.getSelection()?.toString()) {
      return
    }
    void router.push({ name: 'stations', params: { id }, query: listQuery.value })
  }

  function press (event: PointerEvent): void {
    if (event.button === 0) {
      pressDown(event.currentTarget as Element)
    }
  }

  function release (event: PointerEvent): void {
    pressUp(event.currentTarget as Element)
  }

  function keyPress (event: MouseEvent): void {
    if (event.detail === 0) {
      pressPulse(event.currentTarget as Element)
    }
  }

  onMounted(load)
</script>
