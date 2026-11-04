import { InfoCircleOutlined, UndoOutlined } from '@ant-design/icons'
import { Button, Card, DatePicker, Flex, InputNumber, Select, Space, Tag, Tooltip } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useMeta } from '../api/hooks'
import { isOwnScope } from '../auth/access'
import { useAuth } from '../auth/session'
import { fmtPeriodLabel, fmtRange } from '../lib/format'
import { useDebouncedValue } from '../lib/useDebounced'
import { vi } from '../lib/vi'
import { UNMAPPED } from '../lib/zones'
import { clampToData, EMPTY_FILTERS, type Preset, presetRange } from '../store/filters'
import { useFilters } from '../store/useFilters'

const DATE_FMT = 'DD/MM/YYYY'

function opts(values: string[]) {
  return values.map((v) => ({ value: v, label: v }))
}

/** Bộ lọc toàn cục (PLAN §8.0): khoảng ngày + preset, đầu mối, loại GPU, cụm, quản lý bằng, ngưỡng T. Đồng bộ URL. */
export function FilterBar() {
  const [f, setFilters] = useFilters()
  const { data: meta } = useMeta()
  const me = useAuth()
  const ownOnly = isOwnScope(me) // đầu mối phạm vi own: bộ lọc đầu mối khóa ở chính mình (backend cũng áp phạm vi)
  const defaultT = Number(meta?.settings.default_threshold ?? 40)
  const [t, setT] = useDebouncedValue<number | null>(f.threshold ?? null, (v) =>
    setFilters({ threshold: v === null || v === defaultT ? undefined : v }),
  )

  const today = dayjs().format('YYYY-MM-DD')
  const dataEnd = meta?.data_range.end ?? today
  const mk = (p: Preset, anchor: string): [Dayjs, Dayjs] => {
    const [a, b] = presetRange(p, anchor)
    return [dayjs(a), dayjs(b)]
  }
  const presets = [
    { label: vi.filters.last4w, value: mk('4w', dataEnd) },
    ...(meta?.periods ?? [])
      .filter((p) => p.start && p.end)
      .slice(0, 8) // file tuần: 8 kỳ gần nhất là đủ cho preset
      .map((p) => ({
        label: vi.filters.periodPreset(fmtPeriodLabel(p.label)),
        value: [dayjs(p.start), dayjs(p.end)] as [Dayjs, Dayjs],
      })),
    { label: vi.filters.thisMonth, value: mk('this_month', today) },
    { label: vi.filters.lastMonth, value: mk('last_month', today) },
    { label: vi.filters.lastN(3), value: mk('3m', dataEnd) },
    { label: vi.filters.lastN(6), value: mk('6m', dataEnd) },
    { label: vi.filters.lastN(12), value: mk('12m', dataEnd) },
  ]
  const def = meta?.default_range
  const shown: [Dayjs, Dayjs] | null =
    f.start && f.end ? [dayjs(f.start), dayjs(f.end)] : def?.start && def.end ? [dayjs(def.start), dayjs(def.end)] : null
  const clamped = clampToData(f.start, f.end, meta?.data_range.start, meta?.data_range.end)

  return (
    <Card size="small" styles={{ body: { padding: '10px 12px' } }}>
      <Flex wrap gap={8} align="center">
        <DatePicker.RangePicker
          format={DATE_FMT}
          value={shown}
          presets={presets}
          allowClear={Boolean(f.start)}
          onChange={(v) =>
            setFilters(
              v && v[0] && v[1]
                ? { start: v[0].format('YYYY-MM-DD'), end: v[1].format('YYYY-MM-DD') }
                : { start: undefined, end: undefined },
            )
          }
          aria-label={vi.filters.range}
        />
        <Tooltip title={vi.filters.calendarNote}>
          <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
        </Tooltip>
        {!f.start && def?.start && def.end && <Tag color="blue">{vi.filters.viewingDefault(fmtRange(def.start, def.end))}</Tag>}
        {clamped && <Tag color="gold">{vi.filters.clamped(fmtRange(clamped[0], clamped[1]))}</Tag>}
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          style={{ minWidth: 170 }}
          placeholder={`${vi.filters.owner}: ${vi.filters.all}`}
          value={ownOnly ? [me.owner_key ?? ''] : f.owner}
          disabled={ownOnly}
          onChange={(v: string[]) => setFilters({ owner: v })}
          options={ownOnly ? opts([me.owner_key ?? '']) : [...opts(meta?.owners ?? []), { value: UNMAPPED, label: vi.filters.unmapped }]}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          style={{ minWidth: 150 }}
          placeholder={`${vi.filters.gpuModel}: ${vi.filters.all}`}
          value={f.gpu_model}
          onChange={(v: string[]) => setFilters({ gpu_model: v })}
          options={opts(meta?.gpu_models ?? [])}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          style={{ minWidth: 130 }}
          placeholder={`${vi.filters.cluster}: ${vi.filters.all}`}
          value={f.cluster}
          onChange={(v: string[]) => setFilters({ cluster: v })}
          options={opts(meta?.clusters ?? [])}
        />
        <Select
          mode="multiple"
          allowClear
          maxTagCount="responsive"
          style={{ minWidth: 160 }}
          placeholder={`${vi.filters.managedBy}: ${vi.filters.all}`}
          value={f.managed_by}
          onChange={(v: string[]) => setFilters({ managed_by: v })}
          options={opts(meta?.managed_by ?? [])}
        />
        <Space.Compact>
          <Button disabled tabIndex={-1} style={{ color: 'inherit', cursor: 'default' }}>
            {vi.filters.threshold}
          </Button>
          <InputNumber
            min={0}
            max={100}
            step={5}
            value={t ?? defaultT}
            onChange={(v) => setT(typeof v === 'number' ? v : null)}
            addonAfter="%"
            style={{ width: 110 }}
            aria-label={vi.filters.threshold}
          />
        </Space.Compact>
        <Button
          icon={<UndoOutlined />}
          onClick={() => setFilters({ ...EMPTY_FILTERS, start: undefined, end: undefined, threshold: undefined })}
        >
          {vi.filters.reset}
        </Button>
      </Flex>
    </Card>
  )
}
