import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  testMatch: 'student-responsive.spec.ts',
  use: { ...base.use, baseURL: 'http://127.0.0.1:4174' },
  projects: [
    { name: 'phone-small', use: { viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true } },
    { name: 'phone', use: { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true } },
    { name: 'phone-landscape', use: { viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true } },
    { name: 'tablet', use: { viewport: { width: 768, height: 1024 }, hasTouch: true } },
    { name: 'tablet-landscape', use: { viewport: { width: 1024, height: 768 }, hasTouch: true } },
    { name: 'tablet-large', use: { viewport: { width: 820, height: 1180 }, hasTouch: true } },
    { name: 'tablet-large-landscape', use: { viewport: { width: 1180, height: 820 }, hasTouch: true } },
    { name: 'desktop', testMatch: ['student-responsive.spec.ts', 'stage4.spec.ts'], use: { viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: 'pnpm exec vite preview --host 127.0.0.1 --port 4174 --strictPort',
    url: 'http://127.0.0.1:4174', reuseExistingServer: false,
  },
})
