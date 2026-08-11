interface SnackbarState {
  text: string
  color: string
  visible: boolean
}

export function useSnackbar() {
  const state = useState<SnackbarState>('snackbar', () => ({
    text: '',
    color: 'primary',
    visible: false
  }))

  function show(text: string, color: 'success' | 'error' | 'primary' = 'primary') {
    state.value = { text, color, visible: true }
  }

  return { state, show }
}
