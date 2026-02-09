/**
 * Binance Rebate Ineligible Modal
 *
 * Shown when a user tries to bind a Binance mainnet account that is not
 * eligible for API broker rebate (already has referral or registered before broker).
 */

import React from 'react'
import { createPortal } from 'react-dom'
import { X, ExternalLink, Crown, UserPlus, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from 'react-i18next'

interface RebateIneligibleModalProps {
  isOpen: boolean
  onClose: () => void
  rebateInfo?: {
    rebate_working: boolean
    is_new_user: boolean
  }
}

const BinanceLogo = () => (
  <svg width="24" height="24" viewBox="0 0 126.61 126.61" fill="none" xmlns="http://www.w3.org/2000/svg" className="inline-block mx-1">
    <g fill="#F3BA2F">
      <path d="M38.73,53.2l24.59-24.58,24.6,24.6,14.3-14.31L63.32,0,24.42,38.9Z"/>
      <path d="M0,63.31l14.3-14.31,14.31,14.31L14.3,77.61Z"/>
      <path d="M38.73,73.41l24.59,24.59,24.6-24.6,14.31,14.29h0L63.32,126.61,24.41,87.7l-.01-.01Z"/>
      <path d="M97.99,63.31l14.3-14.31,14.32,14.31-14.31,14.3Z"/>
      <path d="M77.83,63.3l-14.51-14.52-10.73,10.73-1.24,1.23-2.54,2.54,14.51,14.53,14.51-14.51h0Z"/>
    </g>
  </svg>
)

export default function RebateIneligibleModal({
  isOpen,
  onClose,
  rebateInfo
}: RebateIneligibleModalProps) {
  const { t } = useTranslation()

  if (!isOpen) return null

  const handleSubscribe = () => {
    window.open('https://www.akooi.com/#pricing-section', '_blank')
  }

  const handleRegisterNew = () => {
    window.open('https://www.binance.com/en/join?ref=HYPERSVIP', '_blank')
  }

  const handleHyperliquid = () => {
    window.open('https://app.hyperliquid.xyz/join/HYPERSVIP', '_blank')
  }

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative bg-background border rounded-lg shadow-lg w-[900px] max-w-[95vw] mx-4 overflow-hidden">
        <div className="p-6 border-b">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold flex items-center gap-1">
              <BinanceLogo />
              <span>{t('binance.rebateCheck', 'Account Verification')}</span>
            </h2>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-8 w-8 p-0 flex-shrink-0 ml-2"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="p-6 space-y-4">
          <div className="p-4 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
            <p className="text-sm text-amber-800 dark:text-amber-200">
              {t(
                'binance.rebateIneligibleMessage',
                'This account is already linked to another referral relationship and cannot enjoy the trading benefits of this platform.'
              )}
            </p>
          </div>

          <p className="text-sm text-muted-foreground">
            {t(
              'binance.rebateIneligibleOptions',
              'You can choose one of the following options to continue:'
            )}
          </p>

          <div className="grid grid-cols-3 gap-4">
            {/* Option 1: Subscribe - Recommended */}
            <button
              onClick={handleSubscribe}
              className="p-4 border-2 border-primary rounded-lg hover:bg-primary/5 transition-colors text-left group"
            >
              <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 bg-primary/10 rounded-lg group-hover:bg-primary/20 transition-colors">
                    <Crown className="h-5 w-5 text-primary" />
                  </div>
                  <span className="text-xs px-2 py-0.5 bg-primary text-primary-foreground rounded-full">
                    {t('common.recommended', 'Recommended')}
                  </span>
                </div>
                <span className="font-semibold">
                  {t('binance.subscribePremium', 'Subscribe to Premium')}
                </span>
                <p className="text-sm text-muted-foreground mt-1 flex-1">
                  {t('binance.subscribeDescription', 'Unlock all features and enjoy zero service fees')}
                </p>
                <div className="flex items-center gap-1 text-xs text-primary mt-2">
                  <ExternalLink className="h-3 w-3" />
                  <span>akooi.com</span>
                </div>
              </div>
            </button>

            {/* Option 2: Register new account (unverified only) */}
            <button
              onClick={handleRegisterNew}
              className="p-4 border rounded-lg hover:bg-muted/50 transition-colors text-left group"
            >
              <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 bg-muted rounded-lg group-hover:bg-muted/80 transition-colors">
                    <UserPlus className="h-5 w-5 text-muted-foreground" />
                  </div>
                </div>
                <span className="font-semibold">
                  {t('binance.registerNew', 'Register New Account')}
                </span>
                <p className="text-sm text-muted-foreground mt-1 flex-1">
                  {t('binance.registerDescription', 'For users who have NOT completed KYC. Register with our referral link to get 5% fee rebate.')}
                </p>
                <div className="flex items-center gap-1 text-xs text-yellow-600 mt-2">
                  <ExternalLink className="h-3 w-3" />
                  <span>binance.com</span>
                </div>
              </div>
            </button>

            {/* Option 3: Trade on Hyperliquid */}
            <button
              onClick={handleHyperliquid}
              className="p-4 border rounded-lg hover:bg-muted/50 transition-colors text-left group"
            >
              <div className="flex flex-col h-full">
                <div className="flex items-center gap-2 mb-2">
                  <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg group-hover:bg-green-200 dark:group-hover:bg-green-900/50 transition-colors">
                    <Zap className="h-5 w-5 text-green-600" />
                  </div>
                </div>
                <span className="font-semibold">
                  {t('binance.tradeHyperliquid', 'Trade on Hyperliquid')}
                </span>
                <p className="text-sm text-muted-foreground mt-1 flex-1">
                  {t('binance.hyperliquidDescription', 'Use our #1 DEX integration with no KYC required and lower fees.')}
                </p>
                <div className="flex items-center gap-1 text-xs text-green-600 mt-2">
                  <ExternalLink className="h-3 w-3" />
                  <span>hyperliquid.xyz</span>
                </div>
              </div>
            </button>
          </div>

          {/* Footer tip */}
          <div className="p-3 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-xs text-blue-700 dark:text-blue-300 text-center">
              💡 {t('binance.supportTip', 'Subscribing to Premium or registering through our referral links helps support platform development.')}
            </p>
          </div>
        </div>

      </div>
    </div>,
    document.body
  )
}
