// Prints the user manuals' HTML (made by scripts/build-manual-pdfs.sh) to PDF with the
// Chromium that Playwright installs for the end-to-end tests.
// Usage: node scripts/manual-pdf.mjs <input.html> <output.pdf> "<footer title>"
import { chromium } from '@playwright/test'
import { pathToFileURL } from 'node:url'

const [input, output, title] = process.argv.slice(2)
if (!input || !output) {
  console.error('usage: node scripts/manual-pdf.mjs <input.html> <output.pdf> "<title>"')
  process.exit(2)
}
const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(pathToFileURL(input).href, { waitUntil: 'load' })
const footer = `<div style="font-size:8px;width:100%;padding:0 16mm;color:#6a5a51;display:flex;justify-content:space-between;font-family:Arial,sans-serif">
  <span>${title ?? 'Light CRM'}</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`
await page.pdf({
  path: output,
  format: 'A4',
  printBackground: true,
  preferCSSPageSize: true,
  displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: footer,
  outline: true,
  tagged: true,
})
await browser.close()
console.log(`wrote ${output}`)
