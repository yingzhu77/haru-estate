<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type EChartsType, type EChartsCoreOption } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  AriaComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ForecastResult } from '../../api/types'
import { state } from '../../state'

use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  AriaComponent,
  CanvasRenderer,
])
const props = defineProps<{
  result: ForecastResult
  view: 'profit' | 'cash' | 'lifecycle'
}>()
const emit = defineEmits<{ inspect: [month: string, metric: string] }>()
const element = ref<HTMLDivElement>()
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined
const rows = computed(() =>
  props.view === 'lifecycle'
    ? props.result.months
    : props.result.months.filter((month) => props.result.target_months.includes(month.month)),
)

function paint() {
  if (!chart) return
  const root = getComputedStyle(document.documentElement)
  const accent = root.getPropertyValue('--accent').trim()
  const text = root.getPropertyValue('--muted').trim()
  const border = root.getPropertyValue('--border').trim()
  const cash = props.view === 'cash'
  const series = cash
    ? [
        { name: '销售回款', field: 'collections', color: accent, type: 'bar' },
        {
          name: '净现金流',
          field: 'net_cash_flow',
          color: '#36969b',
          type: 'line',
        },
        {
          name: '未覆盖资金缺口',
          field: 'uncovered_gap',
          color: '#bb7834',
          type: 'line',
        },
      ]
    : [
        { name: '确认收入', field: 'revenue', color: '#c4d6eb', type: 'bar' },
        { name: '结转成本', field: 'cogs', color: '#e4d5bd', type: 'bar' },
        { name: '管理口径利润', field: 'profit', color: accent, type: 'line' },
      ]
  const options: EChartsCoreOption = {
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    aria: {
      enabled: true,
      description: '月度预测趋势。相同数据见下方月度明细表。',
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      valueFormatter: (value: number) =>
        `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万元`,
    },
    legend: {
      top: 0,
      left: 'center',
      icon: 'roundRect',
      itemWidth: 14,
      itemHeight: 7,
      textStyle: { color: text, fontSize: 11 },
    },
    grid: {
      left: 12,
      right: 15,
      top: 49,
      bottom: props.view === 'lifecycle' ? 53 : 15,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: rows.value.map((row) => row.month),
      axisLine: { lineStyle: { color: border } },
      axisTick: { show: false },
      axisLabel: {
        color: text,
        fontSize: 11,
        formatter: (value: string) => value.slice(2),
      },
    },
    yAxis: {
      type: 'value',
      name: '万元',
      nameTextStyle: { color: text, padding: [0, 17, 0, 0] },
      axisLabel: { color: text, fontSize: 11 },
      splitLine: { lineStyle: { color: border, type: 'dashed' } },
    },
    dataZoom:
      props.view === 'lifecycle'
        ? [
            {
              type: 'slider',
              height: 17,
              bottom: 5,
              borderColor: border,
              textStyle: { color: text },
              start: 0,
              end: 100,
            },
          ]
        : [],
    series: series.map((item) => ({
      name: item.name,
      type: item.type,
      smooth: false,
      symbolSize: 7,
      barMaxWidth: 18,
      itemStyle: {
        color: item.color,
        borderRadius: item.type === 'bar' ? [3, 3, 0, 0] : 0,
      },
      lineStyle: { width: 2.5 },
      data: rows.value.map((row) => Number(row[item.field as keyof typeof row]) / 10000),
      emphasis: { focus: 'series' },
    })),
  }
  chart.setOption(options, { notMerge: true })
}
onMounted(() => {
  if (!element.value) return
  chart = init(element.value)
  chart.on('click', (params) => {
    const row = rows.value[params.dataIndex]
    if (row) emit('inspect', row.month, props.view === 'cash' ? 'net_cash_flow' : 'profit')
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value)
  paint()
})
watch(() => [props.result, props.view, state.theme], paint, { flush: 'post' })
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div
    ref="element"
    class="forecast-chart"
    role="img"
    aria-label="预测趋势图，具体数值可查月度明细表"
  />
</template>

<style scoped>
.forecast-chart {
  width: 100%;
  height: 285px;
}
</style>
