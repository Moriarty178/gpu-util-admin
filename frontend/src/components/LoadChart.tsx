import { useMemo } from 'react'
import type { Granularity } from '../api/types'
import { fmtDate, fmtInt, fmtPct } from '../lib/format'
import { vi } from '../lib/vi'
import { SERIES, ZONE_META, type Zone } from '../lib/zones'
import { EChart, type EChartsOption } from './EChart'

export interface LoadPoint {
  date: string
  gpu: number
  mem: number
  n_servers?: number
  zone?: Zone
}

interface Props {
  points: LoadPoint[]
  threshold: number
  vtnetT: number
  granularity: Granularity
  /** Dải vùng theo ngày (trang Server) — vùng lấy từ API, không tự tính. */
  zoneStrip?: boolean
  fileName?: string
  height?: number
}

function bucketLabel(date: string, g: Granularity): string {
  const d = fmtDate(date)
  if (g === 'week') return vi.chart.weekOf(d)
  if (g === 'month') return vi.chart.monthOf(d.slice(3))
  return d
}

/** Biểu đồ GPU% / VRAM% + markLine T (nét đứt) & ngưỡng VTNet (chấm), dataZoom, tải PNG (PLAN §8.0). */
export function LoadChart({ points, threshold, vtnetT, granularity, zoneStrip, fileName, height = 380 }: Props) {
  const option = useMemo<EChartsOption>(() => {
    const labels = points.map((p) => bucketLabel(p.date, granularity))
    const strip = Boolean(zoneStrip)
    const mainBottom = strip ? 110 : 70
    const grids: object[] = [{ left: 48, right: 24, top: 40, bottom: mainBottom }]
    const xAxes: object[] = [{ type: 'category', data: labels, boundaryGap: false, gridIndex: 0 }]
    const yAxes: object[] = [
      { type: 'value', min: 0, max: 100, gridIndex: 0, axisLabel: { formatter: '{value}%' } },
    ]
    const series: object[] = [
      {
        name: vi.chart.gpu,
        type: 'line',
        data: points.map((p) => p.gpu),
        showSymbol: points.length <= 40,
        lineStyle: { width: 2, color: SERIES.gpu },
        itemStyle: { color: SERIES.gpu },
        markLine: {
          symbol: 'none',
          silent: true,
          data: [
            {
              yAxis: threshold,
              lineStyle: { type: 'dashed', color: SERIES.threshold, width: 1.5 },
              label: { formatter: vi.chart.threshold(threshold), position: 'insideEndTop' },
            },
            {
              yAxis: vtnetT,
              lineStyle: { type: 'dotted', color: SERIES.vtnet, width: 1.5 },
              label: { formatter: vi.chart.vtnet(vtnetT), position: 'insideEndBottom' },
            },
          ],
        },
      },
      {
        name: vi.chart.mem,
        type: 'line',
        data: points.map((p) => p.mem),
        showSymbol: points.length <= 40,
        lineStyle: { width: 2, color: SERIES.mem },
        itemStyle: { color: SERIES.mem },
      },
    ]
    if (strip) {
      grids.push({ left: 48, right: 24, height: 14, bottom: 62 })
      xAxes.push({ type: 'category', data: labels, gridIndex: 1, show: false })
      yAxes.push({ type: 'value', gridIndex: 1, show: false, max: 1 })
      series.push({
        name: vi.chart.zoneStrip,
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        barCategoryGap: 0,
        data: points.map((p) => ({ value: 1, itemStyle: { color: p.zone ? ZONE_META[p.zone].color : '#d9d9d9' } })),
        tooltip: { show: false },
      })
    }
    return {
      animation: false,
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      legend: { data: [vi.chart.gpu, vi.chart.mem], top: 6, left: 'center' },
      tooltip: {
        trigger: 'axis',
        formatter: (raw: unknown) => {
          const items = (Array.isArray(raw) ? raw : [raw]) as Array<{ dataIndex: number }>
          const p = points[items[0]?.dataIndex ?? 0]
          if (!p) return ''
          const lines = [
            `<b>${bucketLabel(p.date, granularity)}</b>`,
            `${vi.chart.gpu}: <b>${fmtPct(p.gpu)}</b>`,
            `${vi.chart.mem}: <b>${fmtPct(p.mem)}</b>`,
          ]
          if (p.n_servers !== undefined) lines.push(`${vi.chart.nServers}: ${fmtInt(p.n_servers)}`)
          if (p.zone) lines.push(`${vi.matrix.zone}: ${ZONE_META[p.zone].label}`)
          return lines.join('<br/>')
        },
      },
      dataZoom: [
        // lăn chuột = cuộn trang; Ctrl + lăn = phóng to (tránh "kẹt" khi cuộn qua biểu đồ)
        { type: 'inside', xAxisIndex: strip ? [0, 1] : [0], zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false },
        { type: 'slider', xAxisIndex: strip ? [0, 1] : [0], bottom: 12, height: 22 },
      ],
      toolbox: {
        right: 16,
        feature: { saveAsImage: { title: vi.chart.savePng, name: fileName ?? 'tai_gpu', pixelRatio: 2 } },
      },
      series,
    }
  }, [points, threshold, vtnetT, granularity, zoneStrip, fileName])

  return <EChart option={option} height={height} />
}
