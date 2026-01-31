import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  getHyperliquidAvailableSymbols,
  getHyperliquidWatchlist,
  updateHyperliquidWatchlist,
} from '@/lib/api'
import type { HyperliquidSymbolMeta } from '@/lib/api'
import DataCoverageHeatmap from './DataCoverageHeatmap'
import ExchangeIcon from '@/components/exchange/ExchangeIcon'

interface StorageStats {
  exchange: string
  total_size_mb: number
  tables: Record<string, number>
  retention_days: number
  symbol_count: number
  estimated_per_symbol_per_day_mb: number
}

export default function SettingsPage() {
  const { t, i18n } = useTranslation()
  const [activeTab, setActiveTab] = useState('watchlist')

  // Language state
  const currentLang = i18n.language === 'zh' ? 'zh' : 'en'

  // Watchlist state
  const [availableSymbols, setAvailableSymbols] = useState<HyperliquidSymbolMeta[]>([])
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([])
  const [maxWatchlistSymbols, setMaxWatchlistSymbols] = useState(10)
  const [watchlistLoading, setWatchlistLoading] = useState(true)
  const [watchlistSaving, setWatchlistSaving] = useState(false)
  const [watchlistError, setWatchlistError] = useState<string | null>(null)
  const [watchlistSuccess, setWatchlistSuccess] = useState<string | null>(null)

  // Storage stats state - per exchange
  const [storageStats, setStorageStats] = useState<Record<string, StorageStats>>({})
  const [storageLoading, setStorageLoading] = useState(false)
  const [retentionDays, setRetentionDays] = useState<Record<string, string>>({
    hyperliquid: '365',
    binance: '365',
  })
  const [retentionSaving, setRetentionSaving] = useState(false)
  const [retentionError, setRetentionError] = useState<string | null>(null)
  const [retentionSuccess, setRetentionSuccess] = useState<string | null>(null)

  // Backfill state - per exchange
  const [backfillStatus, setBackfillStatus] = useState<Record<string, {
    status: string
    progress: number
    task_id?: number
    symbols?: string[]
    error_message?: string
  }>>({})
  const [backfillStarting, setBackfillStarting] = useState<Record<string, boolean>>({})
  // Track if we just completed a backfill (for one-time success message)
  const [backfillJustCompleted, setBackfillJustCompleted] = useState<Record<string, boolean>>({})

  // Determine current exchange from active tab
  const currentExchange = activeTab === 'hyperliquid-data' ? 'hyperliquid' : activeTab === 'binance-data' ? 'binance' : null

  const toggleLanguage = (lang: 'en' | 'zh') => {
    i18n.changeLanguage(lang)
  }

  const fetchWatchlist = useCallback(async () => {
    setWatchlistLoading(true)
    setWatchlistError(null)
    try {
      const [available, watchlist] = await Promise.all([
        getHyperliquidAvailableSymbols(),
        getHyperliquidWatchlist(),
      ])
      setAvailableSymbols(available.symbols || [])
      setMaxWatchlistSymbols(watchlist.max_symbols ?? 10)
      setWatchlistSymbols(watchlist.symbols || [])
    } catch (err) {
      setWatchlistError(err instanceof Error ? err.message : 'Failed to load watchlist')
    } finally {
      setWatchlistLoading(false)
    }
  }, [])

  const fetchStorageStats = useCallback(async (exchange: string) => {
    setStorageLoading(true)
    try {
      const res = await fetch(`/api/system/storage-stats?exchange=${exchange}`)
      if (res.ok) {
        const data: StorageStats = await res.json()
        setStorageStats((prev) => ({ ...prev, [exchange]: data }))
        setRetentionDays((prev) => ({ ...prev, [exchange]: data.retention_days.toString() }))
      }
    } catch (err) {
      console.error('Failed to fetch storage stats:', err)
    } finally {
      setStorageLoading(false)
    }
  }, [])

  // Load watchlist on mount
  useEffect(() => {
    fetchWatchlist()
  }, [fetchWatchlist])

  // Load storage stats when exchange data tab is active
  useEffect(() => {
    if (currentExchange && !storageStats[currentExchange]) {
      fetchStorageStats(currentExchange)
    }
  }, [currentExchange, storageStats, fetchStorageStats])

  // Fetch backfill status for an exchange
  const fetchBackfillStatus = useCallback(async (exchange: string) => {
    try {
      const res = await fetch(`/api/system/${exchange}/backfill/status`)
      if (res.ok) {
        const data = await res.json()
        setBackfillStatus(prev => {
          const prevStatus = prev[exchange]?.status
          // Track completion for one-time message
          if ((prevStatus === 'running' || prevStatus === 'pending') && data.status === 'completed') {
            setBackfillJustCompleted(p => ({ ...p, [exchange]: true }))
          }
          return { ...prev, [exchange]: data }
        })
      }
    } catch (err) {
      console.error(`Failed to fetch ${exchange} backfill status:`, err)
    }
  }, [])

  // Use ref to track if polling should continue
  const pollingRef = useRef<Record<string, boolean>>({})

  useEffect(() => {
    if (currentExchange) {
      // Initial fetch
      fetchBackfillStatus(currentExchange)
      pollingRef.current[currentExchange] = true

      // Poll while running - use functional update to get latest status
      const interval = setInterval(async () => {
        const res = await fetch(`/api/system/${currentExchange}/backfill/status`)
        if (res.ok) {
          const data = await res.json()
          setBackfillStatus(prev => {
            const prevStatus = prev[currentExchange]?.status
            // Track completion for one-time message
            if ((prevStatus === 'running' || prevStatus === 'pending') && data.status === 'completed') {
              setBackfillJustCompleted(p => ({ ...p, [currentExchange]: true }))
            }
            return { ...prev, [currentExchange]: data }
          })
          // Stop polling if completed or failed
          if (data.status !== 'running' && data.status !== 'pending') {
            pollingRef.current[currentExchange] = false
          }
        }
      }, 2000)

      return () => {
        clearInterval(interval)
        pollingRef.current[currentExchange] = false
      }
    }
  }, [activeTab, currentExchange, fetchBackfillStatus])

  const handleStartBackfill = async (exchange: string) => {
    setBackfillStarting(prev => ({ ...prev, [exchange]: true }))
    setBackfillJustCompleted(prev => ({ ...prev, [exchange]: false }))
    try {
      const res = await fetch(`/api/system/${exchange}/backfill`, { method: 'POST' })
      if (res.ok) {
        await fetchBackfillStatus(exchange)
      } else {
        const data = await res.json()
        alert(data.detail || 'Failed to start backfill')
      }
    } catch (err) {
      console.error('Failed to start backfill:', err)
    } finally {
      setBackfillStarting(prev => ({ ...prev, [exchange]: false }))
    }
  }

  const toggleWatchlistSymbol = (symbol: string) => {
    const symbolUpper = symbol.toUpperCase()
    setWatchlistError(null)
    setWatchlistSuccess(null)
    setWatchlistSymbols((prev) => {
      if (prev.includes(symbolUpper)) {
        return prev.filter((s) => s !== symbolUpper)
      }
      if (prev.length >= maxWatchlistSymbols) {
        setWatchlistError(t('settings.maxSymbolsReached', `Maximum ${maxWatchlistSymbols} symbols`))
        return prev
      }
      return [...prev, symbolUpper]
    })
  }

  const handleSaveWatchlist = async () => {
    setWatchlistSaving(true)
    setWatchlistError(null)
    setWatchlistSuccess(null)
    try {
      await updateHyperliquidWatchlist(watchlistSymbols)
      setWatchlistSuccess(t('settings.watchlistSaved', 'Watchlist saved'))
    } catch (err) {
      setWatchlistError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setWatchlistSaving(false)
    }
  }

  const handleSaveRetention = async () => {
    if (!currentExchange) return
    const days = parseInt(retentionDays[currentExchange], 10)
    if (isNaN(days) || days < 7 || days > 730) {
      setRetentionError(t('settings.retentionRange', 'Must be between 7 and 730 days'))
      return
    }
    setRetentionSaving(true)
    setRetentionError(null)
    setRetentionSuccess(null)
    try {
      const res = await fetch('/api/system/retention-days', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days, exchange: currentExchange }),
      })
      if (!res.ok) throw new Error('Failed to update')
      setRetentionSuccess(t('settings.retentionSaved', 'Retention updated'))
      const stats = storageStats[currentExchange]
      if (stats) {
        setStorageStats((prev) => ({
          ...prev,
          [currentExchange]: { ...stats, retention_days: days },
        }))
      }
    } catch (err) {
      setRetentionError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setRetentionSaving(false)
    }
  }

  return (
    <div className="p-6 h-[calc(100vh-64px)] flex flex-col overflow-hidden">
      {/* Language Settings - Compact row with border */}
      <div className="flex items-center gap-3 mb-6 shrink-0 p-4 border rounded-lg bg-card">
        <span className="text-sm font-medium">{t('settings.language', 'Language')}</span>
        <select
          value={currentLang}
          onChange={(e) => toggleLanguage(e.target.value as 'en' | 'zh')}
          className="border rounded px-2 py-1 text-sm bg-background"
        >
          <option value="en">English</option>
          <option value="zh">中文</option>
        </select>
      </div>

      {/* Tabs: Watchlist | Hyperliquid Data | Binance Data */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
        <TabsList className="grid w-full grid-cols-3 max-w-lg shrink-0">
          <TabsTrigger value="watchlist">{t('settings.watchlist', 'Watchlist')}</TabsTrigger>
          <TabsTrigger value="hyperliquid-data" className="flex items-center gap-1.5">
            <ExchangeIcon exchangeId="hyperliquid" size={16} />
            Hyperliquid
          </TabsTrigger>
          <TabsTrigger value="binance-data" className="flex items-center gap-1.5">
            <ExchangeIcon exchangeId="binance" size={16} />
            Binance
          </TabsTrigger>
        </TabsList>

        {/* Watchlist Tab */}
        <TabsContent value="watchlist" className="mt-4 flex-1 min-h-0 flex flex-col">
          <Card className="flex flex-col flex-1 min-h-0">
            <CardHeader className="shrink-0">
              <CardTitle>{t('settings.watchlist', 'Watchlist')}</CardTitle>
              <CardDescription>
                {t('settings.watchlistDesc', 'Select symbols for market data collection and AI analysis')}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto min-h-0">
              {watchlistLoading ? (
                <div className="text-muted-foreground">{t('common.loading', 'Loading...')}</div>
              ) : (
                <>
                  <div className="text-sm text-muted-foreground mb-3">
                    {t('settings.selectedCount', 'Selected')}: {watchlistSymbols.length} / {maxWatchlistSymbols}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {availableSymbols.map((sym) => {
                      const isSelected = watchlistSymbols.includes(sym.name.toUpperCase())
                      return (
                        <Button
                          key={sym.name}
                          variant={isSelected ? 'default' : 'outline'}
                          size="sm"
                          onClick={() => toggleWatchlistSymbol(sym.name)}
                        >
                          {sym.name}
                        </Button>
                      )
                    })}
                  </div>
                </>
              )}
            </CardContent>
            <CardFooter className="shrink-0 border-t pt-4 flex items-center gap-3">
              <Button
                onClick={handleSaveWatchlist}
                disabled={watchlistSaving || watchlistLoading}
              >
                {watchlistSaving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
              </Button>
              {watchlistError && (
                <span className="text-red-500 text-sm">{watchlistError}</span>
              )}
              {watchlistSuccess && (
                <span className="text-green-500 text-sm">{watchlistSuccess}</span>
              )}
            </CardFooter>
          </Card>
        </TabsContent>

        {/* Hyperliquid Data Tab */}
        <TabsContent value="hyperliquid-data" className="mt-4 flex-1 min-h-0 flex flex-col">
          <Card className="flex flex-col flex-1 min-h-0">
            <CardHeader className="shrink-0">
              <CardTitle className="flex items-center gap-2">
                <ExchangeIcon exchangeId="hyperliquid" size={24} />
                {t('settings.dataCollection', 'Data Collection')}
              </CardTitle>
              <CardDescription>
                {t('settings.dataCollectionDesc', 'Market flow data storage statistics')}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto min-h-0 space-y-6">
              {storageLoading ? (
                <div className="text-muted-foreground">{t('common.loading', 'Loading...')}</div>
              ) : storageStats['hyperliquid'] ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.currentStorage', 'Current Storage')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['hyperliquid'].total_size_mb} MB</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.collectedSymbols', 'Collected Symbols')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['hyperliquid'].symbol_count}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.retentionDays', 'Retention Days')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['hyperliquid'].retention_days}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.maxStorageEstimate', 'Max Storage Estimate')}
                      </div>
                      <div className="text-xl font-semibold">
                        {(watchlistSymbols.length * parseInt(retentionDays['hyperliquid'] || '365', 10) * storageStats['hyperliquid'].estimated_per_symbol_per_day_mb).toFixed(1)} MB
                      </div>
                    </div>
                  </div>
                  <div className="pt-4 border-t">
                    <div className="text-sm font-medium mb-2">
                      {t('settings.setRetention', 'Set Retention Period')}
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        value={retentionDays['hyperliquid'] || '365'}
                        onChange={(e) => setRetentionDays((prev) => ({ ...prev, hyperliquid: e.target.value }))}
                        className="w-24"
                        min={7}
                        max={730}
                      />
                      <span className="text-sm text-muted-foreground">{t('settings.days', 'days')}</span>
                      <Button onClick={handleSaveRetention} disabled={retentionSaving} size="sm">
                        {retentionSaving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
                      </Button>
                    </div>
                    {retentionError && <div className="text-red-500 text-sm mt-2">{retentionError}</div>}
                    {retentionSuccess && <div className="text-green-500 text-sm mt-2">{retentionSuccess}</div>}
                    <div className="text-xs text-muted-foreground mt-1">
                      {t('settings.retentionHint', 'Data older than this will be automatically cleaned up (7-730 days)')}
                    </div>
                  </div>
                  {/* Hyperliquid Backfill Section */}
                  <div className="pt-4 border-t">
                    <div className="text-sm font-medium mb-2">
                      {t('settings.backfillHistory', 'Backfill Historical Data')}
                    </div>
                    <div className="text-xs text-muted-foreground mb-3">
                      {t('settings.hyperliquidBackfillDesc', 'K-lines (~5000 records, ~3.5 days per symbol)')}
                    </div>
                    {backfillStatus['hyperliquid']?.status === 'running' || backfillStatus['hyperliquid']?.status === 'pending' ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary transition-all duration-300"
                              style={{ width: `${backfillStatus['hyperliquid']?.progress || 0}%` }}
                            />
                          </div>
                          <span className="text-sm font-medium">{backfillStatus['hyperliquid']?.progress || 0}%</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {t('settings.backfillRunning', 'Backfilling')} {backfillStatus['hyperliquid']?.symbols?.join(', ')}...
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Button
                          onClick={() => handleStartBackfill('hyperliquid')}
                          disabled={backfillStarting['hyperliquid']}
                          size="sm"
                          variant="outline"
                        >
                          {backfillStarting['hyperliquid'] ? t('common.loading', 'Loading...') : t('settings.startBackfill', 'Start Backfill')}
                        </Button>
                        {backfillJustCompleted['hyperliquid'] && (
                          <div className="text-xs text-green-500">
                            {t('settings.backfillCompleted', 'Last backfill completed successfully')}
                          </div>
                        )}
                        {backfillStatus['hyperliquid']?.status === 'failed' && backfillStatus['hyperliquid']?.task_id && (
                          <div className="text-xs text-red-500">
                            {t('settings.backfillFailed', 'Last backfill failed')}: {backfillStatus['hyperliquid']?.error_message}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground">{t('settings.noData', 'No data available')}</div>
              )}
              <div className="pt-4 border-t">
                <div className="text-sm font-medium mb-3">{t('settings.marketFlowCoverage', 'Market Flow Coverage')}</div>
                <DataCoverageHeatmap exchange="hyperliquid" dataType="market_flow" />
              </div>
              <div className="pt-4 border-t">
                <div className="text-sm font-medium mb-3">{t('settings.klineCoverage', 'K-line Coverage')}</div>
                <DataCoverageHeatmap exchange="hyperliquid" dataType="klines" />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Binance Data Tab */}
        <TabsContent value="binance-data" className="mt-4 flex-1 min-h-0 flex flex-col">
          <Card className="flex flex-col flex-1 min-h-0">
            <CardHeader className="shrink-0">
              <CardTitle className="flex items-center gap-2">
                <ExchangeIcon exchangeId="binance" size={24} />
                {t('settings.dataCollection', 'Data Collection')}
              </CardTitle>
              <CardDescription>
                {t('settings.dataCollectionDesc', 'Market flow data storage statistics')}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto min-h-0 space-y-6">
              {storageLoading ? (
                <div className="text-muted-foreground">{t('common.loading', 'Loading...')}</div>
              ) : storageStats['binance'] ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.currentStorage', 'Current Storage')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['binance'].total_size_mb} MB</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.collectedSymbols', 'Collected Symbols')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['binance'].symbol_count}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.retentionDays', 'Retention Days')}
                      </div>
                      <div className="text-xl font-semibold">{storageStats['binance'].retention_days}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">
                        {t('settings.maxStorageEstimate', 'Max Storage Estimate')}
                      </div>
                      <div className="text-xl font-semibold">
                        {(watchlistSymbols.length * parseInt(retentionDays['binance'] || '365', 10) * storageStats['binance'].estimated_per_symbol_per_day_mb).toFixed(1)} MB
                      </div>
                    </div>
                  </div>
                  <div className="pt-4 border-t">
                    <div className="text-sm font-medium mb-2">
                      {t('settings.setRetention', 'Set Retention Period')}
                    </div>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        value={retentionDays['binance'] || '365'}
                        onChange={(e) => setRetentionDays((prev) => ({ ...prev, binance: e.target.value }))}
                        className="w-24"
                        min={7}
                        max={730}
                      />
                      <span className="text-sm text-muted-foreground">{t('settings.days', 'days')}</span>
                      <Button onClick={handleSaveRetention} disabled={retentionSaving} size="sm">
                        {retentionSaving ? t('common.saving', 'Saving...') : t('common.save', 'Save')}
                      </Button>
                    </div>
                    {retentionError && <div className="text-red-500 text-sm mt-2">{retentionError}</div>}
                    {retentionSuccess && <div className="text-green-500 text-sm mt-2">{retentionSuccess}</div>}
                    <div className="text-xs text-muted-foreground mt-1">
                      {t('settings.retentionHint', 'Data older than this will be automatically cleaned up (7-730 days)')}
                    </div>
                  </div>
                  {/* Backfill Section */}
                  <div className="pt-4 border-t">
                    <div className="text-sm font-medium mb-2">
                      {t('settings.backfillHistory', 'Backfill Historical Data')}
                    </div>
                    <div className="text-xs text-muted-foreground mb-3">
                      {t('settings.backfillDesc', 'K-lines (25h), OI (30d), Funding Rate (365d), Long/Short Ratio (30d)')}
                    </div>
                    {backfillStatus['binance']?.status === 'running' || backfillStatus['binance']?.status === 'pending' ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary transition-all duration-300"
                              style={{ width: `${backfillStatus['binance']?.progress || 0}%` }}
                            />
                          </div>
                          <span className="text-sm font-medium">{backfillStatus['binance']?.progress || 0}%</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {t('settings.backfillRunning', 'Backfilling')} {backfillStatus['binance']?.symbols?.join(', ')}...
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Button
                          onClick={() => handleStartBackfill('binance')}
                          disabled={backfillStarting['binance']}
                          size="sm"
                          variant="outline"
                        >
                          {backfillStarting['binance'] ? t('common.loading', 'Loading...') : t('settings.startBackfill', 'Start Backfill')}
                        </Button>
                        {backfillJustCompleted['binance'] && (
                          <div className="text-xs text-green-500">
                            {t('settings.backfillCompleted', 'Last backfill completed successfully')}
                          </div>
                        )}
                        {backfillStatus['binance']?.status === 'failed' && backfillStatus['binance']?.task_id && (
                          <div className="text-xs text-red-500">
                            {t('settings.backfillFailed', 'Last backfill failed')}: {backfillStatus['binance']?.error_message}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-muted-foreground">{t('settings.noData', 'No data available')}</div>
              )}
              <div className="pt-4 border-t">
                <div className="text-sm font-medium mb-3">{t('settings.marketFlowCoverage', 'Market Flow Coverage')}</div>
                <DataCoverageHeatmap exchange="binance" dataType="market_flow" />
              </div>
              <div className="pt-4 border-t">
                <div className="text-sm font-medium mb-3">{t('settings.klineCoverage', 'K-line Coverage')}</div>
                <DataCoverageHeatmap exchange="binance" dataType="klines" />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}