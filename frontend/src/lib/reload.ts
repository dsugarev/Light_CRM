/** Load the current page again (a route error's retry). Its own module so tests can mock it. */
export function reloadPage(): void {
  window.location.reload()
}
