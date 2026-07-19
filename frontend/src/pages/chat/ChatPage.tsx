import { useAuth } from '@/features/auth/AuthProvider'
import { ChatWorkspace } from '@/features/chat/ChatWorkspace'

export function ChatPage() {
  const auth = useAuth()
  return (
    <ChatWorkspace
      mode="page"
      emailVerified={auth.user()?.email_verified === true}
    />
  )
}
