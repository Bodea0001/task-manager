export const auth = {
  login: {
    title: 'Sign in',
    description: 'Continue to your tasks and assistant.',
    submit: 'Sign in',
    submitting: 'Signing in',
    noAccount: 'New to Task Manager?',
    registerLink: 'Create an account',
  },
  register: {
    title: 'Create an account',
    description: 'Set up your Task Manager workspace.',
    submit: 'Create account',
    submitting: 'Creating account',
    hasAccount: 'Already have an account?',
    loginLink: 'Sign in',
  },
  fields: {
    email: 'Email',
    password: 'Password',
    firstName: 'First name',
    lastName: 'Last name',
    middleName: 'Middle name',
    optional: 'optional',
    showPassword: 'Show password',
    hidePassword: 'Hide password',
    passwordHint: 'Use at least 8 characters without spaces at the edges.',
  },
  errors: {
    invalidCredentials: 'The email or password is incorrect.',
    emailExists: 'An account with this email already exists.',
    rateLimited: 'Too many attempts. Wait briefly and try again.',
    rateLimited_one: 'Too many attempts. Try again in {{count}} second.',
    rateLimited_few: 'Too many attempts. Try again in {{count}} seconds.',
    rateLimited_many: 'Too many attempts. Try again in {{count}} seconds.',
    rateLimited_other: 'Too many attempts. Try again in {{count}} seconds.',
    registrationLimit:
      'No more accounts can be created from this network.',
    protectionUnavailable:
      'Sign-in and registration are temporarily unavailable. Try again later.',
    invalidClientAddress:
      'The request could not be verified. Reload the page and try again.',
    validation: 'Check the entered information and try again.',
    unavailable: 'The server is unavailable. Check the connection and try again.',
    generic: 'The request could not be completed. Try again.',
  },
  validation: {
    passwordWhitespace: 'Password cannot start or end with a space.',
  },
  session: {
    loading: 'Restoring your session',
    unavailableTitle: 'The session could not be restored',
    unavailableMessage: 'Check the connection and try again.',
  },
  account: {
    title: 'Account',
    description: 'Update your profile details and manage the current session.',
    emailVerified: 'Verified',
    emailUnverified: 'Not verified',
    verificationBenefits:
      'Email verification is required to create recurring tasks and increases the assistant request limit.',
    signedInAs: 'Signed in as {{email}}',
    save: 'Save changes',
    saving: 'Saving changes',
    saved: 'Profile changes saved.',
    signOut: 'Sign out',
  },
} as const
