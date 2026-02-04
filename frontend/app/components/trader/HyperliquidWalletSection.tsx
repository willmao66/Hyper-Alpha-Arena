/**
 * Hyperliquid Wallet Section - Testnet/Mainnet wallet configuration
 *
 * Extracted from WalletConfigPanel for use in ExchangeWalletsPanel accordion.
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Wallet, Eye, EyeOff, CheckCircle, RefreshCw, Trash2 } from 'lucide-react'
import {
  getAccountWallet,
  configureAccountWallet,
  testWalletConnection,
  deleteAccountWallet,
} from '@/lib/hyperliquidApi'
import { approveBuilder, type UnauthorizedAccount } from '@/lib/api'
import { copyToClipboard } from '@/lib/utils'
import { AuthorizationModal } from '@/components/hyperliquid'
import { useTranslation } from 'react-i18next'

interface HyperliquidWalletSectionProps {
  accountId: number
  accountName: string
  onStatusChange?: (env: 'testnet' | 'mainnet', configured: boolean) => void
  onWalletConfigured?: () => void
}

interface WalletData {
  id?: number
  walletAddress?: string
  maxLeverage: number
  defaultLeverage: number
  balance?: {
    totalEquity: number
    availableBalance: number
    marginUsagePercent: number
  }
}

type InputType = 'empty' | 'valid_key' | 'key_no_prefix' | 'wallet_address' | 'invalid'

function detectInputType(input: string): InputType {
  const trimmed = input.trim()
  if (!trimmed) return 'empty'
  const withoutPrefix = trimmed.startsWith('0x') ? trimmed.slice(2) : trimmed
  if (!/^[0-9a-fA-F]+$/.test(withoutPrefix)) return 'invalid'
  if (withoutPrefix.length === 64) {
    return trimmed.startsWith('0x') ? 'valid_key' : 'key_no_prefix'
  }
  if (withoutPrefix.length === 40) return 'wallet_address'
  return 'invalid'
}

function formatPrivateKey(input: string): string {
  const trimmed = input.trim()
  if (!trimmed) return ''
  const withoutPrefix = trimmed.startsWith('0x') ? trimmed.slice(2) : trimmed
  if (withoutPrefix.length === 64 && /^[0-9a-fA-F]+$/.test(withoutPrefix)) {
    return '0x' + withoutPrefix
  }
  return trimmed
}

export default function HyperliquidWalletSection({
  accountId,
  accountName,
  onStatusChange,
  onWalletConfigured
}: HyperliquidWalletSectionProps) {
  const { t } = useTranslation()
  const [testnetWallet, setTestnetWallet] = useState<WalletData | null>(null)
  const [mainnetWallet, setMainnetWallet] = useState<WalletData | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingTestnet, setTestingTestnet] = useState(false)
  const [testingMainnet, setTestingMainnet] = useState(false)

  const [editingTestnet, setEditingTestnet] = useState(false)
  const [editingMainnet, setEditingMainnet] = useState(false)
  const [showTestnetKey, setShowTestnetKey] = useState(false)
  const [showMainnetKey, setShowMainnetKey] = useState(false)

  const [testnetPrivateKey, setTestnetPrivateKey] = useState('')
  const [testnetMaxLeverage, setTestnetMaxLeverage] = useState(3)
  const [testnetDefaultLeverage, setTestnetDefaultLeverage] = useState(1)
  const [testnetInputWarning, setTestnetInputWarning] = useState<string | null>(null)

  const [mainnetPrivateKey, setMainnetPrivateKey] = useState('')
  const [mainnetMaxLeverage, setMainnetMaxLeverage] = useState(3)
  const [mainnetDefaultLeverage, setMainnetDefaultLeverage] = useState(1)
  const [mainnetInputWarning, setMainnetInputWarning] = useState<string | null>(null)

  const [unauthorizedAccounts, setUnauthorizedAccounts] = useState<UnauthorizedAccount[]>([])
  const [authModalOpen, setAuthModalOpen] = useState(false)

  useEffect(() => {
    loadWalletInfo()
  }, [accountId])

  const loadWalletInfo = async () => {
    try {
      setLoading(true)
      const info = await getAccountWallet(accountId)

      const hasTestnet = !!info.testnetWallet
      const hasMainnet = !!info.mainnetWallet

      if (info.testnetWallet) {
        setTestnetWallet(info.testnetWallet)
        setTestnetMaxLeverage(info.testnetWallet.maxLeverage)
        setTestnetDefaultLeverage(info.testnetWallet.defaultLeverage)
      } else {
        setTestnetWallet(null)
      }

      if (info.mainnetWallet) {
        setMainnetWallet(info.mainnetWallet)
        setMainnetMaxLeverage(info.mainnetWallet.maxLeverage)
        setMainnetDefaultLeverage(info.mainnetWallet.defaultLeverage)
      } else {
        setMainnetWallet(null)
      }

      onStatusChange?.('testnet', hasTestnet)
      onStatusChange?.('mainnet', hasMainnet)
    } catch (error) {
      console.error('Failed to load wallet info:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWallet = async (environment: 'testnet' | 'mainnet') => {
    const rawPrivateKey = environment === 'testnet' ? testnetPrivateKey : mainnetPrivateKey
    const maxLeverage = environment === 'testnet' ? testnetMaxLeverage : mainnetMaxLeverage
    const defaultLeverage = environment === 'testnet' ? testnetDefaultLeverage : mainnetDefaultLeverage

    if (!rawPrivateKey.trim()) {
      toast.error('Please enter a private key')
      return
    }

    const privateKey = formatPrivateKey(rawPrivateKey)
    const inputType = detectInputType(privateKey)

    if (inputType === 'wallet_address') {
      toast.error('You entered a wallet ADDRESS, not a private key.')
      return
    }
    if (inputType !== 'valid_key') {
      toast.error('Invalid private key format.')
      return
    }

    try {
      setLoading(true)
      const result = await configureAccountWallet(accountId, {
        privateKey,
        maxLeverage,
        defaultLeverage,
        environment
      })

      if (result.success) {
        toast.success(`${environment} wallet configured`)

        if (result.requires_authorization && result.walletAddress) {
          setUnauthorizedAccounts([{
            account_id: accountId,
            account_name: accountName,
            wallet_address: result.walletAddress,
            max_fee: 0,
            required_fee: 30
          }])
          setAuthModalOpen(true)
        }

        if (environment === 'testnet') {
          setTestnetPrivateKey('')
          setEditingTestnet(false)
        } else {
          setMainnetPrivateKey('')
          setEditingMainnet(false)
        }

        await loadWalletInfo()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to configure wallet')
    } finally {
      setLoading(false)
    }
  }

  const handleTestConnection = async (environment: 'testnet' | 'mainnet') => {
    const setTesting = environment === 'testnet' ? setTestingTestnet : setTestingMainnet
    try {
      setTesting(true)
      const result = await testWalletConnection(accountId)
      if (result.success && result.connection === 'successful') {
        toast.success(`✅ Connection successful! Balance: $${result.accountState?.totalEquity.toFixed(2)}`)
      } else {
        toast.error(`❌ Connection failed: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Connection test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleDeleteWallet = async (environment: 'testnet' | 'mainnet') => {
    if (!confirm(`Delete ${environment} wallet?`)) return

    try {
      setLoading(true)
      const result = await deleteAccountWallet(accountId, environment)
      if (result.success) {
        toast.success(`${environment} wallet deleted`)
        await loadWalletInfo()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete wallet')
    } finally {
      setLoading(false)
    }
  }

  const renderWalletCard = (
    environment: 'testnet' | 'mainnet',
    wallet: WalletData | null,
    editing: boolean,
    setEditing: (v: boolean) => void,
    privateKey: string,
    setPrivateKey: (v: string) => void,
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
          {wallet && !editing && (
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

        {wallet && !editing ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 px-2 py-1 bg-muted rounded text-xs truncate">
                {wallet.walletAddress}
              </code>
              <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
            </div>
            {wallet.balance && (
              <div className="grid grid-cols-3 gap-1 text-xs">
                <div>
                  <div className="text-muted-foreground">Balance</div>
                  <div className="font-medium">${wallet.balance.totalEquity.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Available</div>
                  <div className="font-medium">${wallet.balance.availableBalance.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Leverage</div>
                  <div className="font-medium">{wallet.maxLeverage}x</div>
                </div>
              </div>
            )}
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
            {!wallet && (
              <p className="text-xs text-yellow-600">⚠️ Not configured</p>
            )}
            <div className="flex gap-1">
              <Input
                type={showKey ? 'text' : 'password'}
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="Private key (0x...)"
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
                max={50}
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
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => { setEditing(false); setPrivateKey('') }}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (loading && !testnetWallet && !mainnetWallet) {
    return (
      <div className="flex items-center justify-center py-4">
        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
        {renderWalletCard(
          'testnet', testnetWallet, editingTestnet, setEditingTestnet,
          testnetPrivateKey, setTestnetPrivateKey,
          testnetMaxLeverage, setTestnetMaxLeverage,
          testnetDefaultLeverage, setTestnetDefaultLeverage,
          showTestnetKey, setShowTestnetKey, testingTestnet
        )}
        {renderWalletCard(
          'mainnet', mainnetWallet, editingMainnet, setEditingMainnet,
          mainnetPrivateKey, setMainnetPrivateKey,
          mainnetMaxLeverage, setMainnetMaxLeverage,
          mainnetDefaultLeverage, setMainnetDefaultLeverage,
          showMainnetKey, setShowMainnetKey, testingMainnet
        )}
      </div>

      <AuthorizationModal
        isOpen={authModalOpen}
        onClose={() => { setAuthModalOpen(false); setUnauthorizedAccounts([]) }}
        unauthorizedAccounts={unauthorizedAccounts}
        onAuthorizationComplete={() => { setAuthModalOpen(false); setUnauthorizedAccounts([]) }}
      />
    </>
  )
}