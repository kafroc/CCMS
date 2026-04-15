import { computed } from 'vue'
import { useLocaleStore } from '@/stores/locale'
import { getMessages } from '@/locales'

export function useT() {
  const localeStore = useLocaleStore()
  return computed(() => getMessages(localeStore.lang))
}
