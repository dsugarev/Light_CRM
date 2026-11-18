import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// Test strategy 4, journey 7: a user asks the assistant a pipeline question and gets a
// streamed answer with record links; with the provider failing, the CRM still works.
// The stack runs with docker-compose.e2e.yml: the real LiteLLM client calls the scripted
// provider server (app.llm.fake_server) through LLM_API_BASE, with production settings.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    open: 'Assistant',
    input: 'Your question',
    send: 'Send',
    pipelineQuestion: 'Show the open pipeline by stage',
    stageHeader: 'Stage',
    firstStage: 'Prospecting',
    dealsQuestion: 'Which opportunities do we have?',
    dealsHeading: 'I found these opportunities:',
    askAbout: 'Ask about this opportunity',
    saveAsNote: 'Save as note',
    saveNote: 'Save note',
    saved: 'Saved as a note on the record.',
    failure: 'The assistant is not available right now.',
    close: 'Close the assistant',
    leads: 'Leads',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    open: 'Асистент',
    input: 'Вашият въпрос',
    send: 'Изпрати',
    pipelineQuestion: 'Покажи отворената фуния по етапи',
    stageHeader: 'Етап',
    firstStage: 'Проучване',
    dealsQuestion: 'Какви възможности имаме?',
    dealsHeading: 'Намерих тези възможности:',
    askAbout: 'Питай за тази възможност',
    saveAsNote: 'Запази като бележка',
    saveNote: 'Запази бележката',
    saved: 'Запазено като бележка към записа.',
    failure: 'Асистентът не е достъпен в момента.',
    close: 'Затвори асистента',
    leads: 'Потенциални клиенти',
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Assistant in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-AI-01..04, 07 streamed answers with links, a saved draft, a provider failure', async ({
      page,
    }, testInfo) => {
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name.slice(0, 1)}${language}`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      const status = await page.request.get('/api/v1/assistant/status')
      const enabled = ((await status.json()) as { enabled: boolean }).enabled
      test.skip(!enabled && !process.env.CI, 'Start the stack with docker-compose.e2e.yml')

      // A fresh opportunity to look at (fictional data).
      const headers = { 'X-Requested-With': 'XMLHttpRequest' }
      const org = await page.request.post('/api/v1/organizations', {
        headers,
        data: { name: `Асистент ${token} ООД`, confirm_duplicate: true },
      })
      expect(org.status()).toBe(201)
      const opp = await page.request.post('/api/v1/opportunities', {
        headers,
        data: {
          name: `AI deal ${token}`,
          organization_id: ((await org.json()) as { id: string }).id,
          amount: '1000.00',
        },
      })
      expect(opp.status()).toBe(201)
      const oppId = ((await opp.json()) as { id: string }).id

      // FR-AI-01, 02: a pipeline question, answered from pipeline_summary, streamed.
      await page.getByRole('button', { name: ui.open, exact: true }).click()
      const panel = page.getByRole('complementary', { name: ui.open })
      await panel.getByRole('textbox', { name: ui.input }).fill(ui.pipelineQuestion)
      await panel.getByRole('button', { name: ui.send }).click()
      await expect(panel.getByRole('columnheader', { name: ui.stageHeader })).toBeVisible()
      await expect(panel.getByRole('cell', { name: ui.firstStage })).toBeVisible()
      await expect(panel.getByRole('button', { name: ui.send })).toBeVisible() // answer complete
      await panel.getByRole('button', { name: ui.close }).click()

      // FR-AI-03, 04: on the opportunity's page, with it as context, then saved as a note.
      await page.goto(`/opportunities/${oppId}`)
      await expect(page.getByRole('heading', { name: `AI deal ${token}` })).toBeVisible()
      await page.getByRole('button', { name: ui.open, exact: true }).click()
      await expect(panel.getByRole('checkbox', { name: ui.askAbout })).toBeChecked()
      await panel.getByRole('textbox', { name: ui.input }).fill(ui.dealsQuestion)
      await panel.getByRole('button', { name: ui.send }).click()
      await expect(panel.getByText(ui.dealsHeading)).toBeVisible()
      await expect(panel.getByRole('button', { name: ui.send })).toBeVisible()
      const firstLink = panel.getByRole('log').getByRole('link').first()
      await expect(firstLink).toHaveAttribute('href', /^\/opportunities\/[0-9a-f-]{36}$/)
      await panel.getByRole('button', { name: ui.saveAsNote }).click()
      await panel.getByRole('button', { name: ui.saveNote }).click()
      await expect(page.getByText(ui.saved)).toBeVisible()
      await panel.getByRole('button', { name: ui.close }).click()
      await expect(page.getByText(ui.dealsHeading).first()).toBeVisible() // on the timeline

      // FR-AI-07: the provider fails; the chat says so and the CRM keeps working.
      await page.getByRole('button', { name: ui.open, exact: true }).click()
      await panel.getByRole('textbox', { name: ui.input }).fill(`#fail ${token}`)
      await panel.getByRole('button', { name: ui.send }).click()
      await expect(panel.getByRole('alert')).toContainText(ui.failure)
      await panel.getByRole('button', { name: ui.close }).click()
      await page.getByRole('link', { name: ui.leads, exact: true }).click()
      await expect(page).toHaveURL(/\/leads$/)
      await expect(page.getByRole('table')).toBeVisible()
    })
  })
}
