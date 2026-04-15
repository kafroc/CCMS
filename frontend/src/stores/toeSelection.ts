import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'cc_default_toe_id'

export const useToeSelectionStore = defineStore('toe-selection', () => {
  const selectedToeId = ref<string | null>(localStorage.getItem(STORAGE_KEY))

  function setSelectedToeId(toeId: string | null) {
    selectedToeId.value = toeId
    if (toeId) {
      localStorage.setItem(STORAGE_KEY, toeId)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  return { selectedToeId, setSelectedToeId }
})