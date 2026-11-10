import { expect, test, type Page } from '@playwright/test'

async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Login' }).click()
}

test('submitter sees a reviewer rejection with its comment', async ({ page }) => {
  const title = `Expense report ${Date.now()}`
  const comment = 'Receipts are missing for the hotel stay.'

  await login(page, 'sam.submitter@docflow.dev', 'submitter123')
  await expect(page).toHaveURL('/submit')
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('File').setInputFiles({ name: 'report.txt', mimeType: 'text/plain', buffer: Buffer.from('Q3 expenses') })
  await page.getByRole('button', { name: 'Submit' }).click()
  const samRow = page.getByRole('row').filter({ hasText: title })
  await expect(samRow.getByText('Pending')).toBeVisible()
  await page.getByRole('button', { name: 'Logout' }).click()

  await login(page, 'riya.reviewer@docflow.dev', 'reviewer123')
  await expect(page).toHaveURL('/review')
  await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: 'Reject' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Comment').fill(comment)
  await dialog.getByRole('button', { name: 'Reject' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('row').filter({ hasText: title })).toBeHidden()
  await page.getByRole('button', { name: 'Logout' }).click()

  await login(page, 'sam.submitter@docflow.dev', 'submitter123')
  await expect(samRow.getByText('Rejected')).toBeVisible()
  await samRow.getByText('Rejected').hover()
  await expect(page.getByRole('tooltip')).toHaveText(comment)
})
