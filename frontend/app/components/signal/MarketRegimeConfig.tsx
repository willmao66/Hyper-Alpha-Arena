import { useEffect, useState } from 'react'
import { toast } from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Save, ArrowDown, Zap, CheckCircle2, Info } from 'lucide-react'

// Types
interface RegimeConfig {
  id: number
  name: string
  is_default: boolean
  rolling_window: number
  breakout_cvd_z: number
  breakout_oi_z: number
  breakout_price_atr: number
  breakout_taker_high: number
  breakout_taker_low: number
  absorption_cvd_z: number
  absorption_price_atr: number
  trap_cvd_z: number
  trap_oi_z: number
  exhaustion_cvd_z: number
  exhaustion_rsi_high: number
  exhaustion_rsi_low: number
  stop_hunt_range_atr: number
  stop_hunt_close_atr: number
  noise_cvd_z: number
}

// Default values matching database defaults
const DEFAULT_CONFIG: Omit<RegimeConfig, 'id' | 'name' | 'is_default'> = {
  rolling_window: 48,
  breakout_cvd_z: 1.5,
  breakout_oi_z: 1.0,
  breakout_price_atr: 0.5,
  breakout_taker_high: 1.8,
  breakout_taker_low: 0.55,
  absorption_cvd_z: 1.5,
  absorption_price_atr: 0.3,
  trap_cvd_z: 1.0,
  trap_oi_z: -1.0,
  exhaustion_cvd_z: 1.0,
  exhaustion_rsi_high: 70.0,
  exhaustion_rsi_low: 30.0,
  stop_hunt_range_atr: 1.0,
  stop_hunt_close_atr: 0.3,
  noise_cvd_z: 0.5,
}

// API functions
async function fetchConfig(): Promise<RegimeConfig | null> {
  const res = await fetch('/api/market-regime/configs/list')
  if (!res.ok) throw new Error('Failed to fetch config')
  const configs: RegimeConfig[] = await res.json()
  return configs.find(c => c.is_default) || configs[0] || null
}

async function updateConfig(id: number, data: Partial<RegimeConfig>): Promise<RegimeConfig> {
  const res = await fetch(`/api/market-regime/configs/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update config')
  return res.json()
}

// Parameter input with label, default, and range
interface ParamProps {
  label: string
  value: number
  def: number
  range: string
  onChange: (v: number) => void
  step?: number
}

function Param({ label, value, def, range, onChange, step = 0.1 }: ParamProps) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-foreground font-medium">{label}</span>
      <Input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="h-6 w-16 text-xs px-1 text-center font-mono"
      />
      <span className="text-muted-foreground text-xs">def:{def} ({range})</span>
    </span>
  )
}

// Decision node component
interface DecisionNodeProps {
  title: string
  color: string
  desc: string
  isLast?: boolean
  children: React.ReactNode
}

function DecisionNode({ title, color, desc, isLast, children }: DecisionNodeProps) {
  return (
    <div className="relative">
      {/* Card row: card + description side by side */}
      <div className="flex items-center gap-4">
        <Card className={`border-l-4 ${color} w-fit`}>
          <CardContent className="min-h-[60px] py-3 px-4 flex items-center">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <span className="font-semibold text-sm min-w-[120px]">{title}</span>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                {children}
              </div>
            </div>
          </CardContent>
        </Card>
        <span className="text-sm font-medium text-green-700 dark:text-green-300 bg-green-100 dark:bg-green-900/40 px-3 py-1.5 rounded-md whitespace-nowrap">
          → {desc}
        </span>
      </div>
      {/* Arrow below - aligned with card number */}
      {!isLast && (
        <div className="flex items-center gap-1 py-2 pl-7">
          <ArrowDown className="w-3 h-3 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">Not matched</span>
        </div>
      )}
    </div>
  )
}

// Logic separator components
function And() {
  return <span className="text-muted-foreground bg-muted px-1.5 py-0.5 rounded text-xs">AND</span>
}

function Or() {
  return <span className="text-orange-500 bg-orange-500/10 px-1.5 py-0.5 rounded text-xs">OR</span>
}

function All() {
  return <span className="text-blue-500 bg-blue-500/10 px-1.5 py-0.5 rounded text-xs font-medium">[ALL]</span>
}

function Any() {
  return <span className="text-orange-500 bg-orange-500/10 px-1.5 py-0.5 rounded text-xs font-medium">[ANY]</span>
}

// Info tooltip content
function FormulaReference() {
  return (
    <div className="text-xs space-y-1 max-w-sm">
      <div className="font-semibold mb-2">Indicator Formulas:</div>
      <div><span className="font-mono">Price Range</span> = (High - Low) / ATR</div>
      <div><span className="font-mono">Close Offset</span> = |Close - Open| / ATR</div>
      <div><span className="font-mono">CVD Ratio</span> = CVD / Total Notional</div>
      <div><span className="font-mono">OI Delta</span> = Open Interest Change %</div>
      <div><span className="font-mono">Price Move</span> = (Close - Open) / ATR</div>
      <div><span className="font-mono">Taker Ratio</span> = Buy Notional / Sell Notional</div>
      <div><span className="font-mono">RSI</span> = RSI14 indicator</div>
    </div>
  )
}

export default function MarketRegimeConfig() {
  const [config, setConfig] = useState<RegimeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => { loadConfig() }, [])

  const loadConfig = async () => {
    try {
      setLoading(true)
      const data = await fetchConfig()
      setConfig(data)
    } catch {
      toast.error('Failed to load config')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!config) return
    try {
      setSaving(true)
      const updated = await updateConfig(config.id, config)
      setConfig(updated)
      toast.success('Configuration saved')
    } catch {
      toast.error('Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  const u = (field: keyof RegimeConfig, value: number) => {
    if (!config) return
    setConfig({ ...config, [field]: value })
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64">Loading configuration...</div>
  }

  if (!config) {
    return <div className="text-center text-muted-foreground">No configuration found</div>
  }

  return (
    <TooltipProvider>
      <div className="h-full overflow-y-auto">
        <div className="border-2 border-dashed border-yellow-500/50 rounded-lg p-4 bg-yellow-500/5 max-h-[calc(100vh-200px)] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-yellow-500" />
              <span className="font-semibold text-yellow-600 dark:text-yellow-400">Signal Triggered</span>
              <span className="text-xs text-muted-foreground">→ Regime Classification Flow</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="w-4 h-4 text-muted-foreground hover:text-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent side="bottom" className="p-3">
                  <FormulaReference />
                </TooltipContent>
              </Tooltip>
            </div>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              <Save className="w-4 h-4 mr-1" />{saving ? 'Saving...' : 'Save'}
            </Button>
          </div>

          {/* Decision Flow */}
          <div className="space-y-4">
            {/* 1. Stop Hunt */}
            <DecisionNode title="1. Stop Hunt" color="border-red-500" desc="Liquidity grab">
              <All />
              <Param label="Price Range >" value={config.stop_hunt_range_atr} def={1.0} range="0.5~2" onChange={v => u('stop_hunt_range_atr', v)} />
              <And />
              <Param label="Close Offset <" value={config.stop_hunt_close_atr} def={0.3} range="0.1~0.5" onChange={v => u('stop_hunt_close_atr', v)} />
            </DecisionNode>

            {/* 2. Absorption */}
            <DecisionNode title="2. Absorption" color="border-purple-500" desc="Flow absorbed">
              <All />
              <span className="text-foreground">CVD strong</span> <And />
              <span className="text-foreground">Taker extreme:</span>
              <Param label="High >" value={config.breakout_taker_high} def={1.8} range="1.5~2.5" onChange={v => u('breakout_taker_high', v)} />
              <Or />
              <Param label="Low <" value={config.breakout_taker_low} def={0.55} range="0.3~0.7" onChange={v => u('breakout_taker_low', v)} />
              <And />
              <Param label="Price Move <" value={config.absorption_price_atr} def={0.3} range="0.1~0.5" onChange={v => u('absorption_price_atr', v)} />
            </DecisionNode>

            {/* 3. Breakout */}
            <DecisionNode title="3. Breakout" color="border-green-500" desc="Trend initiation">
              <All />
              <Param label="CVD Ratio >" value={config.breakout_cvd_z} def={1.5} range="1~3" onChange={v => u('breakout_cvd_z', v)} />
              <And />
              <Param label="OI Delta >" value={config.breakout_oi_z} def={1.0} range="0.5~2" onChange={v => u('breakout_oi_z', v)} step={0.1} />
              <And />
              <Param label="Price Move >" value={config.breakout_price_atr} def={0.5} range="0.3~1" onChange={v => u('breakout_price_atr', v)} />
              <And />
              <span className="text-foreground">Taker aligned</span>
            </DecisionNode>

            {/* 4. Continuation */}
            <DecisionNode title="4. Continuation" color="border-blue-500" desc="Trend continues">
              <All />
              <span className="text-foreground">CVD: {(config.breakout_cvd_z * 0.05).toFixed(2)}~{(config.breakout_cvd_z * 0.1).toFixed(2)}</span>
              <span className="text-muted-foreground text-xs">(from Breakout)</span>
              <And />
              <span className="text-foreground">OI Delta ≥ 0</span>
              <And />
              <span className="text-foreground">Price Move &gt; {config.absorption_price_atr}</span>
              <span className="text-muted-foreground text-xs">(from Absorption)</span>
            </DecisionNode>

            {/* 5. Exhaustion */}
            <DecisionNode title="5. Exhaustion" color="border-orange-500" desc="Trend weakening">
              <All />
              <span className="text-foreground">CVD strong</span> <And />
              <span className="text-foreground">Taker extreme</span> <And />
              <span className="text-foreground">OI Delta &lt; 0</span> <And />
              <Any />
              <Param label="RSI >" value={config.exhaustion_rsi_high} def={70} range="65~80" onChange={v => u('exhaustion_rsi_high', v)} step={1} />
              <Or />
              <Param label="RSI <" value={config.exhaustion_rsi_low} def={30} range="20~35" onChange={v => u('exhaustion_rsi_low', v)} step={1} />
            </DecisionNode>

            {/* 6. Trap */}
            <DecisionNode title="6. Trap" color="border-yellow-600" desc="False breakout">
              <All />
              <span className="text-foreground">CVD strong</span> <And />
              <Param label="OI Delta <" value={config.trap_oi_z} def={-1.0} range="-2~0" onChange={v => u('trap_oi_z', v)} />
            </DecisionNode>

            {/* 7. Noise */}
            <DecisionNode title="7. Noise" color="border-gray-400" desc="No clear pattern" isLast>
              <span className="text-muted-foreground">None of the above matched</span>
            </DecisionNode>
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}
