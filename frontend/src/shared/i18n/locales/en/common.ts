export const common = {
  appName: 'Task Manager',
  actions: {
    cancel: 'Cancel',
    retry: 'Try again',
    refreshTasks: 'Refresh tasks',
    returnToTasks: 'Return to Tasks',
  },
  errors: {
    supportDetails: 'Technical details',
    requestId: 'Request ID: {{requestId}}',
  },
  network: {
    offlineTitle: 'You are offline',
    offlineMessage: 'Reconnect to restore your session and continue working.',
    offlineNotice: 'Offline. Changes cannot be saved until the connection returns.',
  },
  language: {
    title: 'Language',
    description: 'Choose the language used by the application interface.',
    english: 'English',
    russian: 'Russian',
  },
  theme: {
    title: 'Appearance',
    description: 'Choose a light, dark, or system-matched appearance.',
    light: 'Light',
    dark: 'Dark',
    system: 'System',
  },
  validation: {
    summary: 'Review the highlighted fields and try again.',
    required: 'Complete this field.',
    invalidEmail: 'Enter a valid email address.',
    invalidValue: 'Enter a valid value.',
    invalidDateTime: 'Enter a complete date and time.',
    tooShort: 'Enter at least {{count}} characters.',
    tooLong: 'Enter no more than {{count}} characters.',
  },
  dateTime: {
    done: 'Done',
    hours: 'Hours',
    minutes: 'Minutes',
    month: 'Month',
  },
  unsavedChanges: {
    title: 'Discard unsaved changes?',
    message: 'Changes made on this screen have not been saved.',
    stay: 'Keep editing',
    discard: 'Discard changes',
  },
  pages: {
    calendar: {
      title: 'Calendar',
      description:
        'Review deadlines and scheduled work by month, week, or timeline.',
      emptyTitle: 'Calendar is not connected',
      emptyMessage:
        'Scheduled tasks and recurring occurrences will appear here.',
    },
    recurring: {
      title: 'Recurring tasks',
      description:
        'Review recurring task templates, rules, and upcoming instances.',
      emptyTitle: 'Recurring tasks are not connected',
      emptyMessage:
        'Recurring task definitions and their next occurrences will appear here.',
    },
    chat: {
      title: 'Chat',
      description: 'Conversations, execution plans, and assistant results.',
      emptyTitle: 'Chat is not connected',
      emptyMessage:
        'Conversation history and agent progress will appear here.',
    },
    settings: {
      title: 'Settings',
      description: 'Account details and application preferences.',
    },
    notFound: {
      title: 'Page not found',
      description: 'The requested view does not exist.',
    },
  },
} as const
