import { defineStore } from 'pinia'
import { ref } from 'vue'

export type LangCode = 'zh' | 'en'

const STORAGE_KEY = 'cc_locale'

export const useLocaleStore = defineStore('locale', () => {
  const stored = localStorage.getItem(STORAGE_KEY) as LangCode | null
  const lang = ref<LangCode>(stored === 'zh' ? 'zh' : 'en')

  function setLang(code: LangCode) {
    lang.value = code
    localStorage.setItem(STORAGE_KEY, code)
  }

  // Initialize with English by default
  if (!localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, 'en')
  }

  return { lang, setLang }
})
