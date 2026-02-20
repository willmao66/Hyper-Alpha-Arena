/**
 * HyperAiPage - Independent page for Hyper AI (three-column layout)
 * Left: Conversation list
 * Center: Chat area
 * Right: Config panel
 */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Plus,
  Send,
  Settings,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  Loader2,
  Bot
} from 'lucide-react'

interface Conversation {
  id: number
  title: string
  message_count: number
  updated_at: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  reasoning_snapshot?: string
  tool_calls_log?: string
  created_at?: string
}

interface LLMProvider {
  id: string
  name: string
  models: string[]
}

// Welcome message component
function WelcomeMessage({ nickname, t }: { nickname?: string; t: any }) {
  const greeting = nickname
    ? t('hyperAi.welcomeWithName', { name: nickname, defaultValue: `你好，${nickname}！我是 Hyper AI，你的专属交易助手。` })
    : t('hyperAi.welcomeNoName', '你好！我是 Hyper AI，Hyper Alpha Arena 的智能助手。')

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
        <Bot className="w-8 h-8 text-primary" />
      </div>
      <p className="text-lg mb-4">{greeting}</p>
      <div className="text-sm text-muted-foreground space-y-1 max-w-md">
        <p>{t('hyperAi.welcomeCapabilities', '我可以帮你：')}</p>
        <ul className="text-left list-disc list-inside space-y-1 mt-2">
          <li>{t('hyperAi.capability1', '了解系统功能和使用方法')}</li>
          <li>{t('hyperAi.capability2', '生成和优化 AI 交易策略')}</li>
          <li>{t('hyperAi.capability3', '管理 AI 交易员和钱包配置')}</li>
          <li>{t('hyperAi.capability4', '分析市场数据和交易表现')}</li>
        </ul>
        <p className="mt-4">{t('hyperAi.welcomePrompt', '有什么想了解的，直接问我就行。')}</p>
      </div>
    </div>
  )
}

export default function HyperAiPage() {
  const { t, i18n } = useTranslation()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConvId, setCurrentConvId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [providers, setProviders] = useState<LLMProvider[]>([])
  const [profile, setProfile] = useState<any>(null)
  const [nickname, setNickname] = useState<string>('')
  const [showConfig, setShowConfig] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Get current language
  const currentLang = i18n.language?.startsWith('zh') ? 'zh' : 'en'

  useEffect(() => {
    fetchConversations()
    fetchProviders()
    fetchProfile()
  }, [])

  useEffect(() => {
    if (currentConvId) {
      fetchMessages(currentConvId)
    }
  }, [currentConvId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const fetchConversations = async () => {
    try {
      const res = await fetch('/api/hyper-ai/conversations')
      const data = await res.json()
      setConversations(data.conversations || [])
    } catch (e) {
      console.error('Failed to fetch conversations:', e)
    }
  }

  const fetchMessages = async (convId: number) => {
    try {
      const res = await fetch(`/api/hyper-ai/conversations/${convId}/messages`)
      const data = await res.json()
      setMessages(data.messages || [])
    } catch (e) {
      console.error('Failed to fetch messages:', e)
    }
  }

  const fetchProviders = async () => {
    try {
      const res = await fetch('/api/hyper-ai/providers')
      const data = await res.json()
      setProviders(data.providers || [])
    } catch (e) {
      console.error('Failed to fetch providers:', e)
    }
  }

  const fetchProfile = async () => {
    try {
      const res = await fetch('/api/hyper-ai/profile')
      const data = await res.json()
      setProfile(data)
      if (data.nickname) {
        setNickname(data.nickname)
      }
    } catch (e) {
      console.error('Failed to fetch profile:', e)
    }
  }

  const handleNewConversation = () => {
    // Lazy creation: just clear current state, don't create in DB yet
    setCurrentConvId(null)
    setMessages([])
  }

  const handleSend = async () => {
    if (!inputValue.trim() || sending) return

    const userMessage = inputValue.trim()
    setInputValue('')
    setSending(true)
    setStreamingContent('')

    // Add user message to UI immediately
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    try {
      const res = await fetch('/api/hyper-ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          conversation_id: currentConvId,
          lang: currentLang
        })
      })

      const data = await res.json()
      if (data.task_id) {
        // Poll for streaming response
        pollTaskResponse(data.task_id, data.conversation_id)
        if (!currentConvId) {
          setCurrentConvId(data.conversation_id)
        }
      }
    } catch (e) {
      console.error('Failed to send message:', e)
      setSending(false)
    }
  }

  const pollTaskResponse = async (taskId: string, convId: number) => {
    const eventSource = new EventSource(`/api/ai-stream/${taskId}`)
    let content = ''

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'content') {
          content += data.text || ''
          setStreamingContent(content)
        } else if (data.type === 'done') {
          eventSource.close()
          setMessages(prev => [...prev, { role: 'assistant', content }])
          setStreamingContent('')
          setSending(false)
          fetchConversations()
        } else if (data.type === 'error') {
          eventSource.close()
          setSending(false)
        }
      } catch (e) {
        console.error('Failed to parse SSE:', e)
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex h-full">
      {/* Left: Conversation List */}
      <div className="w-64 border-r flex flex-col">
        <div className="p-3 border-b">
          <Button onClick={handleNewConversation} className="w-full" size="sm">
            <Plus className="w-4 h-4 mr-2" />
            {t('hyperAi.newChat', 'New Chat')}
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {conversations.map(conv => (
              <button
                key={conv.id}
                onClick={() => setCurrentConvId(conv.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  currentConvId === conv.id
                    ? 'bg-secondary text-secondary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                }`}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{conv.title}</span>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {conv.message_count} {t('hyperAi.messages', 'messages')}
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Center: Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {messages.length === 0 && !streamingContent ? (
          <WelcomeMessage nickname={nickname} t={t} />
        ) : (
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-4 max-w-3xl mx-auto">
              {messages.map((msg, idx) => (
                <MessageBubble key={idx} message={msg} />
              ))}
              {streamingContent && (
                <MessageBubble message={{ role: 'assistant', content: streamingContent }} streaming />
              )}
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>
        )}

        {/* Input Area */}
        <div className="p-4 border-t">
          <div className="max-w-3xl mx-auto flex gap-2 items-end">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('hyperAi.inputPlaceholder', 'Type a message...')}
              disabled={sending}
              className="flex-1 min-h-[80px] max-h-[200px] rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-y"
              rows={3}
            />
            <Button onClick={handleSend} disabled={!inputValue.trim() || sending} className="h-[80px] px-4">
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2 max-w-3xl mx-auto">
            {t('common.keyboardHintCtrlEnter', 'Press Ctrl+Enter (Cmd+Enter on Mac) to send')}
          </p>
        </div>
      </div>

      {/* Right: Config Panel */}
      {showConfig && (
        <div className="w-72 border-l p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-medium flex items-center gap-2">
              <Settings className="w-4 h-4" />
              {t('hyperAi.configTitle', 'Hyper AI Config')}
            </h3>
          </div>

          {profile && (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-muted-foreground">Provider:</span>
                <span className="ml-2">{profile.llm_provider || 'Not configured'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Model:</span>
                <span className="ml-2">{profile.llm_model || '-'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Status:</span>
                <span className={`ml-2 ${profile.llm_configured ? 'text-green-600' : 'text-yellow-600'}`}>
                  {profile.llm_configured ? 'Connected' : 'Not configured'}
                </span>
              </div>
            </div>
          )}

          <div className="pt-4 border-t">
            <h4 className="text-sm font-medium text-muted-foreground mb-2">
              {t('hyperAi.skills', 'Skills')}
            </h4>
            <p className="text-xs text-muted-foreground">
              {t('hyperAi.skillsComingSoon', 'Coming soon...')}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// Message bubble component
function MessageBubble({ message, streaming }: { message: Message; streaming?: boolean }) {
  const [showReasoning, setShowReasoning] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted'
        }`}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>
        {streaming && (
          <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
        )}
        {message.reasoning_snapshot && (
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex items-center gap-1 text-xs mt-2 opacity-60 hover:opacity-100"
          >
            {showReasoning ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Reasoning
          </button>
        )}
        {showReasoning && message.reasoning_snapshot && (
          <div className="mt-2 text-xs opacity-70 border-t pt-2">
            {message.reasoning_snapshot}
          </div>
        )}
      </div>
    </div>
  )
}
