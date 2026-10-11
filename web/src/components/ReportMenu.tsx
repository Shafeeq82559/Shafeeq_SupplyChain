import { motion } from 'motion/react'
import { useState } from 'react'
import type { Analysis, Overrides } from '../api'
import { buildReportHtml, downloadFile, printReport, reportName } from '../report'
import { rise } from './motionkit'

const I = {
  pdf: <path d="M6 9V3h12v6M6 17H4v-6h16v6h-2M7 14h10v7H7z" />,
  data: <path d="M8 8l-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" />,
}

export function ReportMenu({ a, used }: { a: Analysis; used: Overrides }) {
  const [done, setDone] = useState<string | null>(null)
  const flash = (m: string) => { setDone(m); window.setTimeout(() => setDone(null), 2200) }
  const html = () => buildReportHtml(a, used)

  return (
    <motion.div className="reportbar" {...rise(0)}>
      <span className="reportbar-title">Take this briefing with you</span>
      <div className="reportbar-actions">
        <button className="btn soft" onClick={() => { printReport(html()); flash('Choose "Save as PDF" in the print dialog') }}>
          <svg viewBox="0 0 24 24">{I.pdf}</svg>Save as PDF
        </button>
        <button className="btn soft" onClick={() => { downloadFile(`${reportName(a)}.json`, JSON.stringify(a, null, 2), 'application/json'); flash('Data downloaded') }}>
          <svg viewBox="0 0 24 24">{I.data}</svg>Raw data
        </button>
      </div>
      <span className="reportbar-flash" role="status">{done}</span>
    </motion.div>
  )
}
