import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Whether the browser thinks it has a connection. `false` is reliable (the radio is off);
 * `true` only means a network exists, so a request can still fail and the page must handle that.
 */
export function useOnline () {
  const online = ref(typeof navigator === 'undefined' ? true : navigator.onLine)

  function update (): void {
    online.value = navigator.onLine
  }

  onMounted(() => {
    update()
    globalThis.addEventListener('online', update)
    globalThis.addEventListener('offline', update)
  })
  onBeforeUnmount(() => {
    globalThis.removeEventListener('online', update)
    globalThis.removeEventListener('offline', update)
  })

  return online
}
