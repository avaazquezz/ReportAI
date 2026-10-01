interface PageOptions {
  page: number
  itemsPerPage: number
}

/**
 * The page a server-side table is on, owned by the page component so it can jump back to page 1
 * after a create or a status change: the table used to keep showing the old page number for the
 * first page's rows, and a reload ignored the rows-per-page the user had chosen (FE-4).
 */
export function useTablePaging(fetch: (options: PageOptions) => Promise<void>) {
  const page = ref(1)
  const itemsPerPage = ref(10)

  function load(options: PageOptions) {
    page.value = options.page
    itemsPerPage.value = options.itemsPerPage
    return fetch(options)
  }

  async function reload() {
    if (page.value === 1) await fetch({ page: 1, itemsPerPage: itemsPerPage.value })
    else page.value = 1 // the table asks for page 1 itself
  }

  return { page, load, reload }
}
