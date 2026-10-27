<template>
  <ModalSheet v-model="open" labelledby="sg-h" max-width="520" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div>
        <h2 id="sg-h" class="m-0 text-h3 text-surface-900">Sign the report</h2>

        <p class="m-0 mt-1 text-sm text-surface-700">
          <span class="font-mono" translate="no">{{ number }}</span> v{{ version }} · signing as {{ lead ? 'the lead' : 'attending' }}
        </p>
      </div>

      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

      <FormField id="sg-name" label="Full name">
        <v-text-field
          id="sg-name"
          v-model="name"
          autocomplete="name"
          :error-messages="nameError"
          :maxlength="120"
          name="name"
        />
      </FormField>

      <div class="flex flex-col gap-2">
        <span id="sg-pad-l" class="text-label text-surface-900">Your signature</span>

        <!-- The pad is a canvas; touch-action none keeps an iPhone from scrolling or zooming while a finger draws -->
        <div ref="box" class="relative h-36 touch-none rounded-card border border-dashed border-surface-500 bg-surface-50">
          <canvas
            ref="canvas"
            aria-describedby="sg-pad-h"
            aria-labelledby="sg-pad-l"
            class="absolute inset-0 size-full touch-none"
            role="img"
          />

          <span aria-hidden="true" class="pointer-events-none absolute inset-x-4 bottom-7 border-b border-surface-500" />
          <span v-if="empty" aria-hidden="true" class="pointer-events-none absolute inset-0 grid place-items-center text-sm text-surface-600">Sign here</span>
        </div>

        <div class="flex items-center justify-between gap-2">
          <span id="sg-pad-h" class="text-xs text-surface-600">Draw with your finger or a mouse. The typed name above is kept with it.</span>
          <v-btn size="small" variant="text" @click="clear()">Clear</v-btn>
        </div>

        <!-- Drawing is not possible for everyone: the typed name can stand as the signature (keyboard and screen reader users) -->
        <v-btn
          id="sg-typed"
          class="self-start"
          size="small"
          variant="outlined"
          @click="useTyped()"
        >Use my typed name as my signature</v-btn>

        <p v-if="padError" class="m-0 text-sm text-error" role="alert">{{ padError }}</p>
      </div>

      <v-checkbox
        v-model="attested"
        density="comfortable"
        hide-details
        :label="attestation"
      />

      <p v-if="attestError" class="m-0 -mt-2 text-sm text-error" role="alert">{{ attestError }}</p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn :disabled="busy" variant="outlined" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">Sign</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type SignaturePad from 'signature_pad'
  import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'

  // The signature dialog (W17, RPT-4, TRD 11.3). signature_pad is imported here, when the dialog
  // opens, and kept out of the precache (`globIgnores`): signing needs a connection anyway
  // (OFF-10). The drawing and the typed name live in this component's memory until the server has
  // answered; nothing is written to the device. The canvas is sized from devicePixelRatio when the
  // dialog opens; rotating the phone while it is open would blur it, so the size is taken once and
  // the pad is cleared if the window is resized.
  const props = defineProps<{
    number: string
    version: number
    lead: boolean
    /** The sentence the server stores with the signature, shown exactly as it is stored. */
    attestation: string
    busy: boolean
    /** What the last try said, or null. */
    failure: string | null
    /** The name to suggest (the person's own). */
    suggest: string
  }>()

  const EXPORT_WIDTH = 900

  const emit = defineEmits<{ sign: [name: string, image: string] }>()
  const open = defineModel<boolean>({ required: true })

  const box = ref<HTMLElement | null>(null)
  const canvas = ref<HTMLCanvasElement | null>(null)
  const name = ref('')
  const attested = ref(false)
  const empty = ref(true)
  // The signature is the typed name drawn onto the pad, not a drawing by hand
  const typed = ref(false)
  const nameError = ref('')
  const padError = ref('')
  const attestError = ref('')
  let pad: SignaturePad | null = null
  let width = 0

  async function start (): Promise<void> {
    name.value = props.suggest
    attested.value = false
    nameError.value = ''
    padError.value = ''
    attestError.value = ''
    empty.value = true
    await nextTick()
    // The dialog's content is mounted a tick after `open` turns true
    await new Promise(resolve => requestAnimationFrame(resolve))
    if (!canvas.value || !box.value) {
      return
    }
    const { default: Pad } = await import('signature_pad')
    size()
    pad = new Pad(canvas.value, { penColor: '#14213d', minWidth: 0.8, maxWidth: 2.4 })
    pad.addEventListener('beginStroke', () => {
      empty.value = false
      padError.value = ''
    })
    globalThis.addEventListener('resize', onResize)
  }

  function size (): void {
    const el = canvas.value
    const holder = box.value
    if (!el || !holder) {
      return
    }
    const ratio = Math.max(globalThis.devicePixelRatio || 1, 1)
    width = holder.clientWidth
    el.width = holder.clientWidth * ratio
    el.height = holder.clientHeight * ratio
    el.getContext('2d')?.scale(ratio, ratio)
  }

  // A drawing is not stretched into a different size: clear it and say so
  function onResize (): void {
    if (box.value && box.value.clientWidth !== width) {
      size()
      pad?.clear()
      empty.value = true
    }
  }

  function clear (): void {
    pad?.clear()
    empty.value = true
    typed.value = false
    padError.value = ''
  }

  // The name, in an italic face, on the baseline of the pad: the same PNG the server takes from a drawing
  function useTyped (): void {
    const el = canvas.value
    const text = name.value.trim()
    if (!el || !pad) {
      return
    }
    if (text.length < 2) {
      nameError.value = 'Type your full name.'
      document.querySelector<HTMLInputElement>('#sg-name')?.focus()
      return
    }
    pad.clear()
    const context = el.getContext('2d')
    if (!context) {
      return
    }
    const ratio = Math.max(globalThis.devicePixelRatio || 1, 1)
    const height = el.height / ratio
    context.save()
    context.fillStyle = '#14213d'
    context.font = `italic 600 ${Math.min(44, Math.round(width / Math.max(text.length, 12) * 1.7))}px "Google Sans", "Roboto Flex", serif`
    context.textBaseline = 'alphabetic'
    context.fillText(text, 16, height - 36, width - 32)
    context.restore()
    typed.value = true
    empty.value = false
    padError.value = ''
    nameError.value = ''
  }

  function stop (): void {
    globalThis.removeEventListener('resize', onResize)
    pad?.off()
    pad = null
  }

  // The server takes at most 1200 x 600 px and 100 KB: a phone's canvas at three times the pixel
  // ratio is bigger, so the drawing is shrunk to at most EXPORT_WIDTH wide before it is sent
  function exportPng (uri: string): string {
    const source = canvas.value
    if (!source || source.width <= EXPORT_WIDTH) {
      return uri
    }
    const small = document.createElement('canvas')
    small.width = EXPORT_WIDTH
    small.height = Math.round(source.height * EXPORT_WIDTH / source.width)
    const context = small.getContext('2d')
    if (!context) {
      return uri
    }
    context.drawImage(source, 0, 0, small.width, small.height)
    return small.toDataURL('image/png')
  }

  function submit (): void {
    nameError.value = name.value.trim().length < 2 ? 'Type your full name.' : ''
    padError.value = !pad || (!typed.value && pad.isEmpty()) ? 'Draw your signature, or use your typed name.' : ''
    attestError.value = attested.value ? '' : 'Tick the box to confirm.'
    if (nameError.value || padError.value || attestError.value || !pad) {
      // The first problem gets the focus (a screen reader hears it, a keyboard continues from it)
      const first = nameError.value ? '#sg-name' : (padError.value ? '#sg-typed' : '.v-checkbox input')
      document.querySelector<HTMLElement>(first)?.focus()
      return
    }
    emit('sign', name.value.trim(), exportPng(pad.toDataURL('image/png')))
  }

  watch(open, isOpen => {
    if (isOpen) {
      void start()
    } else {
      stop()
    }
  })

  onBeforeUnmount(stop)
</script>
