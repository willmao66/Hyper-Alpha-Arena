/**
 * Binance Wallet Section - Testnet/Mainnet API key configuration
 *
 * For use in ExchangeWalletsPanel accordion.
 * Binance uses API Key + Secret instead of private key.
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Eye, EyeOff, CheckCircle, RefreshCw, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface BinanceWalletSectionProps {
  accountId: number
  accountName: string
  onStatusChange?: (env: 'testnet' | 'mainnet', configured: boolean) => void
  onWalletConfigured?: () => void
}

interface BinanceWalletData {
  id?: number
  environment: string
  maxLeverage: number
  defaultLeverage: number
  isActive: boolean
  balance?: {
    totalEquity: number
    availableBalance: number
    unrealizedPnl: number
  }
}

interface BinanceConfig {
  testnetConfigured: boolean
  mainnetConfigured: boolean
  currentEnvironment: string
  maxLeverage: number | null
  defaultLeverage: number | null
}

const API_BASE = '/api/binance'

export default function BinanceWalletSection({
  accountId,
  accountName,
  onStatusChange,
  onWalletConfigured
}: BinanceWalletSectionProps) {
  const { t } = useTranslation()
  const [config, setConfig] = useState<BinanceConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingTestnet, setTestingTestnet] = useState(false)
  const [testingMainnet, setTestingMainnet] = useState(false)

  const [editingTestnet, setEditingTestnet] = useState(false)
  const [editingMainnet, setEditingMainnet] = useState(false)
  const [showTestnetKey, setShowTestnetKey] = useState(false)
  const [showMainnetKey, setShowMainnetKey] = useState(false)

  // Form states for testnet
  const [testnetApiKey, setTestnetApiKey] = useState('')
  const [testnetSecretKey, setTestnetSecretKey] = useState('')
  const [testnetMaxLeverage, setTestnetMaxLeverage] = useState(20)
  const [testnetDefaultLeverage, setTestnetDefaultLeverage] = useState(1)

  // Form states for mainnet
  const [mainnetApiKey, setMainnetApiKey] = useState('')
  const [mainnetSecretKey, setMainnetSecretKey] = useState('')
  const [mainnetMaxLeverage, setMainnetMaxLeverage] = useState(20)
  const [mainnetDefaultLeverage, setMainnetDefaultLeverage] = useState(1)

  useEffect(() => {
    loadConfig()
  }, [accountId])

  const loadConfig = async () => {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/accounts/${accountId}/config`)
      if (res.ok) {
        const data = await res.json()
        setConfig({
          testnetConfigured: data.testnet_configured,
          mainnetConfigured: data.mainnet_configured,
          currentEnvironment: data.current_environment,
          maxLeverage: data.max_leverage,
          defaultLeverage: data.default_leverage
        })
        onStatusChange?.('testnet', data.testnet_configured)
        onStatusChange?.('mainnet', data.mainnet_configured)
      }
    } catch (error) {
      console.error('Failed to load Binance config:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWallet = async (environment: 'testnet' | 'mainnet') => {
    const apiKey = environment === 'testnet' ? testnetApiKey : mainnetApiKey
    const secretKey = environment === 'testnet' ? testnetSecretKey : mainnetSecretKey
    const maxLev = environment === 'testnet' ? testnetMaxLeverage : mainnetMaxLeverage
    const defaultLev = environment === 'testnet' ? testnetDefaultLeverage : mainnetDefaultLeverage

    if (!apiKey.trim() || !secretKey.trim()) {
      toast.error('Please enter both API Key and Secret Key')
      return
    }

    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/accounts/${accountId}/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          environment,
          apiKey,
          secretKey,
          maxLeverage: maxLev,
          defaultLeverage: defaultLev
        })
      })

      if (res.ok) {
        toast.success(`Binance ${environment} configured`)
        if (environment === 'testnet') {
          setTestnetApiKey('')
          setTestnetSecretKey('')
          setEditingTestnet(false)
        } else {
          setMainnetApiKey('')
          setMainnetSecretKey('')
          setEditingMainnet(false)
        }
        await loadConfig()
        onWalletConfigured?.()
      } else {
        const err = await res.json()
        toast.error(err.detail || 'Failed to configure')
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to configure')
    } finally {
      setLoading(false)
    }
  }

  const handleTestConnection = async (environment: 'testnet' | 'mainnet') => {
    const setTesting = environment === 'testnet' ? setTestingTestnet : setTestingMainnet
    try {
      setTesting(true)
      const res = await fetch(`${API_BASE}/accounts/${accountId}/balance?environment=${environment}`)
      if (res.ok) {
        const data = await res.json()
        toast.success(`✅ Connected! Balance: $${data.total_equity?.toFixed(2) || '0.00'}`)
      } else {
        const err = await res.json()
        toast.error(`❌ ${err.detail || 'Connection failed'}`)
      }
    } catch (error) {
      toast.error('Connection test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleDeleteWallet = async (environment: 'testnet' | 'mainnet') => {
    if (!confirm(`Delete Binance ${environment} wallet?`)) return

    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/accounts/${accountId}/wallet?environment=${environment}`, {
        method: 'DELETE'
      })
      if (res.ok) {
        toast.success(`Binance ${environment} wallet deleted`)
        await loadConfig()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error('Failed to delete wallet')
    } finally {
      setLoading(false)
    }
  }

  const renderWalletCard = (
    environment: 'testnet' | 'mainnet',
    configured: boolean,
    editing: boolean,
    setEditing: (v: boolean) => void,
    apiKey: string,
    setApiKey: (v: string) => void,
    secretKey: string,
    setSecretKey: (v: string) => void,
    maxLev: number,
    setMaxLev: (v: number) => void,
    defaultLev: number,
    setDefaultLev: (v: number) => void,
    showKey: boolean,
    setShowKey: (v: boolean) => void,
    testing: boolean
  ) => {
    const badgeVariant = environment === 'testnet' ? 'default' : 'destructive'

    return (
      <div className="p-3 border rounded-lg space-y-2">
        <div className="flex items-center justify-between">
          <Badge variant={badgeVariant} className="text-xs">
            {environment.toUpperCase()}
          </Badge>
          {configured && !editing && (
            <div className="flex gap-1">
              <Button variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="destructive" size="sm" className="h-6 px-2" onClick={() => handleDeleteWallet(environment)}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>

        {configured && !editing ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">API Key configured</span>
              <CheckCircle className="h-4 w-4 text-green-600" />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTestConnection(environment)}
              disabled={testing}
              className="w-full h-7 text-xs"
            >
              {testing ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : null}
              Test Connection
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {!configured && (
              <p className="text-xs text-yellow-600">⚠️ Not configured</p>
            )}
            <Input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="API Key"
              className="font-mono text-xs h-7"
            />
            <div className="flex gap-1">
              <Input
                type={showKey ? 'text' : 'password'}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                placeholder="Secret Key"
                className="font-mono text-xs h-7"
              />
              <Button variant="outline" size="sm" className="h-7 px-2" onClick={() => setShowKey(!showKey)}>
                {showKey ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-1">
              <Input
                type="number"
                value={maxLev}
                onChange={(e) => setMaxLev(Number(e.target.value))}
                min={1}
                max={125}
                className="h-7 text-xs"
                placeholder="Max Lev"
              />
              <Input
                type="number"
                value={defaultLev}
                onChange={(e) => setDefaultLev(Number(e.target.value))}
                min={1}
                max={maxLev}
                className="h-7 text-xs"
                placeholder="Default Lev"
              />
            </div>
            <div className="flex gap-1">
              <Button onClick={() => handleSaveWallet(environment)} disabled={loading} size="sm" className="flex-1 h-7 text-xs">
                {loading ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : null}
                Save
              </Button>
              {editing && (
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => { setEditing(false); setApiKey(''); setSecretKey('') }}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (loading && !config) {
    return (
      <div className="flex items-center justify-center py-4">
        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
      {renderWalletCard(
        'testnet', config?.testnetConfigured || false, editingTestnet, setEditingTestnet,
        testnetApiKey, setTestnetApiKey, testnetSecretKey, setTestnetSecretKey,
        testnetMaxLeverage, setTestnetMaxLeverage,
        testnetDefaultLeverage, setTestnetDefaultLeverage,
        showTestnetKey, setShowTestnetKey, testingTestnet
      )}
      {renderWalletCard(
        'mainnet', config?.mainnetConfigured || false, editingMainnet, setEditingMainnet,
        mainnetApiKey, setMainnetApiKey, mainnetSecretKey, setMainnetSecretKey,
        mainnetMaxLeverage, setMainnetMaxLeverage,
        mainnetDefaultLeverage, setMainnetDefaultLeverage,
        showMainnetKey, setShowMainnetKey, testingMainnet
      )}
    </div>
  )
}