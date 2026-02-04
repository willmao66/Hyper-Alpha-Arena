/**
 * Exchange Wallets Panel - Multi-exchange wallet configuration
 *
 * Collapsible accordion UI for managing wallets across multiple exchanges.
 * Each exchange section shows binding status badges and expands to show
 * testnet/mainnet wallet configuration.
 */

import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useTranslation } from 'react-i18next'
import HyperliquidWalletSection from './HyperliquidWalletSection'
import BinanceWalletSection from './BinanceWalletSection'

interface ExchangeWalletsPanelProps {
  accountId: number
  accountName: string
  onWalletConfigured?: () => void
}

interface ExchangeStatus {
  hyperliquid: { testnet: boolean; mainnet: boolean }
  binance: { testnet: boolean; mainnet: boolean }
}

export default function ExchangeWalletsPanel({
  accountId,
  accountName,
  onWalletConfigured
}: ExchangeWalletsPanelProps) {
  const { t } = useTranslation()
  const [openSections, setOpenSections] = useState<string[]>([])
  const [status, setStatus] = useState<ExchangeStatus>({
    hyperliquid: { testnet: false, mainnet: false },
    binance: { testnet: false, mainnet: false }
  })

  const toggleSection = (section: string) => {
    setOpenSections(prev =>
      prev.includes(section)
        ? prev.filter(s => s !== section)
        : [...prev, section]
    )
  }

  const updateStatus = (exchange: keyof ExchangeStatus, env: 'testnet' | 'mainnet', configured: boolean) => {
    setStatus(prev => ({
      ...prev,
      [exchange]: { ...prev[exchange], [env]: configured }
    }))
  }

  const renderStatusBadges = (exchangeStatus: { testnet: boolean; mainnet: boolean }) => (
    <div className="flex gap-1.5">
      <Badge
        variant={exchangeStatus.testnet ? "default" : "outline"}
        className={`text-[10px] px-1.5 py-0 h-5 ${
          exchangeStatus.testnet
            ? "bg-green-600 hover:bg-green-600"
            : "text-muted-foreground border-muted-foreground/30"
        }`}
      >
        {exchangeStatus.testnet && "✓ "}Testnet
      </Badge>
      <Badge
        variant={exchangeStatus.mainnet ? "destructive" : "outline"}
        className={`text-[10px] px-1.5 py-0 h-5 ${
          !exchangeStatus.mainnet && "text-muted-foreground border-muted-foreground/30"
        }`}
      >
        {exchangeStatus.mainnet && "✓ "}Mainnet
      </Badge>
    </div>
  )

  const renderExchangeSection = (
    exchangeKey: string,
    exchangeName: string,
    exchangeStatus: { testnet: boolean; mainnet: boolean },
    SectionComponent: React.ComponentType<any>
  ) => {
    const isOpen = openSections.includes(exchangeKey)

    return (
      <Collapsible
        key={exchangeKey}
        open={isOpen}
        onOpenChange={() => toggleSection(exchangeKey)}
        className="border rounded-lg"
      >
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center justify-between p-3 hover:bg-muted/50 transition-colors">
            <div className="flex items-center gap-2">
              {isOpen ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              <Wallet className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium text-sm">{exchangeName}</span>
            </div>
            {renderStatusBadges(exchangeStatus)}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 pt-1 border-t">
            <SectionComponent
              accountId={accountId}
              accountName={accountName}
              onStatusChange={(env: 'testnet' | 'mainnet', configured: boolean) =>
                updateStatus(exchangeKey as keyof ExchangeStatus, env, configured)
              }
              onWalletConfigured={onWalletConfigured}
            />
          </div>
        </CollapsibleContent>
      </Collapsible>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-3">
        <Wallet className="h-4 w-4 text-muted-foreground" />
        <h4 className="text-sm font-medium">{t('wallet.exchangeWallets', 'Exchange Wallets')}</h4>
      </div>

      <div className="space-y-2">
        {renderExchangeSection('hyperliquid', 'Hyperliquid', status.hyperliquid, HyperliquidWalletSection)}
        {renderExchangeSection('binance', 'Binance Futures', status.binance, BinanceWalletSection)}
      </div>
    </div>
  )
}
