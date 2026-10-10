import { useState } from 'react'
import { api, useFetch } from '../api'
import { useFilters } from '../filters'
import { pct } from '../format'
import { PageHead, Status } from '../components/ui'

const BOOKS = [
  ['historical', '1. Historical log', 'Past contracts with actual closure dates. Calibrates how early customers exit.'],
  ['assets', '2. Asset book', 'Live loans. Scored by the asset (pre-closure) model on upload.'],
  ['liabilities', '3. Liability book', 'Live deposits and borrowings. Scored by the liability (early exit) model on upload.'],
]

function Upload({ book, label, note, onDone }) {
  const [file, setFile] = useState(null)
  const [state, setState] = useState({})

  async function send(e) {
    e.preventDefault()
    const form = new FormData()
    form.append('file', file)
    setState({ busy: true })
    try {
      setState({ result: await api.post(`/api/ingest/${book}`, form) })
      onDone()
    } catch (error) {
      setState({ error })
    }
  }

  const r = state.result
  return (
    <form className="upload" onSubmit={send}>
      <div>
        <strong>{label}</strong>
        <small>{note}</small>
      </div>
      <input type="file" accept=".csv,.xlsx" onChange={e => setFile(e.target.files[0])} aria-label={`${label} file`} />
      <button disabled={!file || state.busy}>{state.busy ? 'Uploading…' : 'Upload'}</button>
      {state.error && <p className="error">{state.error.message}</p>}
      {r && (
        <div className="result">
          <p className={r.batch.rows_rejected ? 'warn' : 'ok'}>{r.message} (run date {r.batch.run_date})</p>
          {r.predictions && <p className="muted small">{r.predictions}</p>}
          {r.errors_preview.length > 0 && (
            <table className="grid compact">
              <thead><tr><th>Row</th><th>Transaction</th><th>Column</th><th>Problem</th></tr></thead>
              <tbody>
                {r.errors_preview.map((e, i) => (
                  <tr key={i}><td className="num">{e.row_number}</td><td className="mono">{e.transaction_id}</td><td>{e.column_name}</td><td>{e.message}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </form>
  )
}

const metric = v => (v === undefined || v === null ? '–' : v.toFixed(3))

export default function Data() {
  const { reloadDates, runDate } = useFilters()
  const batches = useFetch('/api/ingest/batches', { limit: 10 })
  const models = useFetch('/api/ml/models')
  const [job, setJob] = useState({})

  const refresh = () => { reloadDates(); batches.reload() }

  async function run(name, call) {
    setJob({ busy: name })
    try {
      const result = await call()
      setJob({ done: name === 'train' ? 'Models retrained and all run dates re-scored.' : `${result.predicted} transactions re-scored for ${result.run_date}.` })
      models.reload()
      reloadDates()
    } catch (error) {
      setJob({ error })
    }
  }

  return (
    <>
      <PageHead title="Data and models" note="Each upload is validated row by row, stored, and the live books are scored by the behavioral model straight away. The run date is read from the file name (DDMMYYYY)." />

      <section>
        <h2>Upload files</h2>
        {BOOKS.map(([book, label, note]) => <Upload key={book} book={book} label={label} note={note} onDone={refresh} />)}
      </section>

      <section>
        <div className="sectionhead">
          <h2>Behavioral models</h2>
          <div className="inline">
            <button onClick={() => run('predict', () => api.post('/api/ml/predict', undefined, { run_date: runDate }))} disabled={!!job.busy || !runDate}>
              {job.busy === 'predict' ? 'Scoring…' : 'Re-score run date'}
            </button>
            <button className="primary" onClick={() => run('train', () => api.post('/api/ml/train'))} disabled={!!job.busy}>
              {job.busy === 'train' ? 'Training…' : 'Retrain from history'}
            </button>
          </div>
        </div>
        {job.error && <p className="error">{job.error.message}</p>}
        {job.done && <p className="ok">{job.done}</p>}
        <Status loading={models.loading && !models.data} error={models.error} />
        {models.data && (
          <table className="grid">
            <thead>
              <tr><th>Model</th><th>Predicts</th><th className="r">Threshold</th><th className="r">ROC-AUC</th><th className="r">Accuracy</th><th className="r">Rows</th><th>Trained</th></tr>
            </thead>
            <tbody>
              {models.data.map(m => (
                <tr key={m.book}>
                  <td>{m.book === 'asset' ? 'Asset model' : 'Liability model'}<small>Logistic regression</small></td>
                  <td>{m.book === 'asset' ? 'Loan pre-closure' : 'Deposit early exit'}</td>
                  <td className="r num">{m.available ? pct(m.threshold) : <span className="neg">missing</span>}</td>
                  <td className="r num">{metric(m.metrics?.roc_auc)}</td>
                  <td className="r num">{metric(m.metrics?.accuracy)}</td>
                  <td className="r num">{m.training_rows?.toLocaleString() ?? '–'}</td>
                  <td className="num">{m.trained_at ? m.trained_at.slice(0, 16).replace('T', ' ') : 'Shipped with the project'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>Recent uploads</h2>
        <Status loading={batches.loading && !batches.data} error={batches.error} />
        {batches.data?.length > 0 && (
          <table className="grid">
            <thead><tr><th>File</th><th>Book</th><th>Run date</th><th className="r">Accepted</th><th className="r">Rejected</th><th>Status</th></tr></thead>
            <tbody>
              {batches.data.map(b => (
                <tr key={b.id}>
                  <td>{b.file_name}</td><td>{b.book}</td><td className="num">{b.run_date}</td>
                  <td className="r num">{b.rows_accepted.toLocaleString()}</td><td className="r num">{b.rows_rejected}</td>
                  <td>{b.status.replaceAll('_', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}
