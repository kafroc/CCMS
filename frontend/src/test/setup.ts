import { config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach } from 'vitest'

// Fresh Pinia store before every test.
beforeEach(() => {
  setActivePinia(createPinia())
})

// Silence console.error for expected validation warnings in tests.
config.global.config.warnHandler = () => {}
