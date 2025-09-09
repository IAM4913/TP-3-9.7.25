import { useState } from 'react'
import axios from 'axios'

// Use VITE_API_URL in production (Vercel), fall back to /api for local proxy
const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api'
const api = axios.create({ baseURL: API_BASE })

export function App() {
    const [file, setFile] = useState<File | null>(null)
    const [s3Key, setS3Key] = useState<string | null>(null)
    const [preview, setPreview] = useState<any>(null)
    const [status, setStatus] = useState<string>("")

    // Config state
    const [planningWhse, setPlanningWhse] = useState<string>('ZAC')
    const [allowMultiStop, setAllowMultiStop] = useState<boolean>(false) // per MVP: off
    const [weights, setWeights] = useState({
        texas_max: 52000,
        texas_min: 47000,
        other_max: 48000,
        other_min: 44000,
        load_target_pct: 0.98,
    })

    // Results
    const [trucks, setTrucks] = useState<any[]>([])
    const [assignments, setAssignments] = useState<any[]>([])
    const [sections, setSections] = useState<Record<string, number[]>>({})
    const [metrics, setMetrics] = useState<any>(null)

    async function presignAndUpload(f: File) {
        try {
            setStatus('Presigning...')
            const presign = await api.post('/upload/presign', {
                filename: f.name,
                content_type: f.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }, { timeout: 10000 })
            const { key, presigned } = presign.data

            setStatus('Uploading to S3...')
            const formData = new FormData()
            Object.entries(presigned.fields).forEach(([k, v]) => formData.append(k, v as string))
            formData.append('Content-Type', f.type)
            formData.append('file', f)
            const uploadResp = await fetch(presigned.url, { method: 'POST', body: formData })
            if (!uploadResp.ok) {
                const text = await uploadResp.text()
                throw new Error(`S3 upload failed: ${uploadResp.status} ${text}`)
            }

            setS3Key(key)
            setStatus('Generating preview...')
            const pv = await api.post('/upload/preview', { s3_key: key }, { timeout: 15000 })
            setPreview(pv.data)
            setStatus('Uploaded and previewed')
        } catch (err: any) {
            const msg = err?.response?.data?.detail || err?.message || String(err)
            setStatus(`Error: ${msg}`)
            console.error('Upload/Preview error', err)
        }
    }

    async function runOptimize() {
        if (!s3Key) return
        setStatus('Optimizing...')
    const resp = await api.post('/optimize', {
            s3_key: s3Key,
            planning_whse: planningWhse,
            allow_multi_stop: allowMultiStop,
            weight_config: weights,
        })
        setTrucks(resp.data.trucks)
        setAssignments(resp.data.assignments)
        setSections(resp.data.sections)
        setMetrics(resp.data.metrics)
        setStatus('Optimization complete')
    }

    async function download(path: string, filename: string, body: any) {
        const resp = await api.post(path, body, { responseType: 'blob' })
        const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(a.href)
    }

    return (
        <div className="p-6 space-y-4">
            <h1 className="text-2xl font-semibold">Truck Planner</h1>

            <input type="file" accept=".xlsx" onChange={(e) => {
                const f = e.target.files?.[0] || null
                setFile(f)
            }} />

            <button
                className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
                disabled={!file}
                onClick={() => file && presignAndUpload(file)}
            >Upload & Preview</button>

            {status && <div className="text-sm text-gray-600">{status}</div>}

            <div className="grid grid-cols-2 gap-4 max-w-xl">
                <label className="block">
                    <span className="text-sm">Planning Whse</span>
                    <input className="mt-1 w-full border rounded px-2 py-1" value={planningWhse} onChange={e => setPlanningWhse(e.target.value)} />
                </label>
                <label className="flex items-end gap-2">
                    <input type="checkbox" checked={allowMultiStop} onChange={e => setAllowMultiStop(e.target.checked)} disabled />
                    <span className="text-sm">Allow multi-stop (disabled in MVP)</span>
                </label>
                <label className="block">
                    <span className="text-sm">TX Max</span>
                    <input type="number" className="mt-1 w-full border rounded px-2 py-1" value={weights.texas_max}
                        onChange={e => setWeights(w => ({ ...w, texas_max: Number(e.target.value) }))} />
                </label>
                <label className="block">
                    <span className="text-sm">TX Min</span>
                    <input type="number" className="mt-1 w-full border rounded px-2 py-1" value={weights.texas_min}
                        onChange={e => setWeights(w => ({ ...w, texas_min: Number(e.target.value) }))} />
                </label>
                <label className="block">
                    <span className="text-sm">Other Max</span>
                    <input type="number" className="mt-1 w-full border rounded px-2 py-1" value={weights.other_max}
                        onChange={e => setWeights(w => ({ ...w, other_max: Number(e.target.value) }))} />
                </label>
                <label className="block">
                    <span className="text-sm">Other Min</span>
                    <input type="number" className="mt-1 w-full border rounded px-2 py-1" value={weights.other_min}
                        onChange={e => setWeights(w => ({ ...w, other_min: Number(e.target.value) }))} />
                </label>
            </div>

            <div className="flex items-center gap-3">
                <button
                    className="px-4 py-2 bg-emerald-600 text-white rounded disabled:opacity-50"
                    disabled={!s3Key || !preview || (preview?.missingRequiredColumns?.length ?? 0) > 0}
                    onClick={runOptimize}
                >Run Optimization</button>

                <button
                    className="px-4 py-2 bg-gray-700 text-white rounded disabled:opacity-50"
                    disabled={!s3Key}
                    onClick={() => s3Key && download('/export/trucks', 'truck_optimization_results.xlsx', { s3_key: s3Key })}
                >Export Standard</button>

                <button
                    className="px-4 py-2 bg-gray-700 text-white rounded disabled:opacity-50"
                    disabled={!s3Key}
                    onClick={() => s3Key && download('/export/dh-load-list', 'dh_load_list.xlsx', { s3_key: s3Key })}
                >Export DH Load List</button>
            </div>

            {preview && (
                <div className="mt-4">
                    <div className="font-medium">Headers:</div>
                    <pre className="text-xs bg-gray-100 p-2 rounded">{JSON.stringify(preview.headers, null, 2)}</pre>
                    <div className="font-medium">Row count: {preview.rowCount}</div>
                    <div className="font-medium">Missing required columns:</div>
                    <pre className="text-xs bg-gray-100 p-2 rounded">{JSON.stringify(preview.missingRequiredColumns, null, 2)}</pre>
                    <div className="font-medium">Sample (first 5 rows):</div>
                    <pre className="text-xs bg-gray-100 p-2 rounded">{JSON.stringify(preview.sample, null, 2)}</pre>
                </div>
            )}

            {trucks.length > 0 && (
                <div className="mt-6 space-y-3">
                    <h2 className="text-xl font-semibold">Truck Summary</h2>
                    <div className="overflow-auto">
                        <table className="min-w-[900px] text-sm">
                            <thead>
                                <tr className="text-left border-b">
                                    <th className="p-2">#</th>
                                    <th className="p-2">Customer</th>
                                    <th className="p-2">City</th>
                                    <th className="p-2">State</th>
                                    <th className="p-2">Total Wt</th>
                                    <th className="p-2">Min/Max</th>
                                    <th className="p-2">Lines</th>
                                    <th className="p-2">Pieces</th>
                                    <th className="p-2">Overwidth%</th>
                                    <th className="p-2">Priority</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trucks.map(t => (
                                    <tr key={t.truckNumber} className="border-b">
                                        <td className="p-2">{t.truckNumber}</td>
                                        <td className="p-2">{t.customerName}</td>
                                        <td className="p-2">{t.customerCity}</td>
                                        <td className="p-2">{t.customerState}</td>
                                        <td className="p-2">{Math.round(t.totalWeight)}</td>
                                        <td className="p-2">{t.minWeight}/{t.maxWeight}</td>
                                        <td className="p-2">{t.totalLines}</td>
                                        <td className="p-2">{t.totalPieces}</td>
                                        <td className="p-2">{t.percentOverwidth.toFixed(0)}%</td>
                                        <td className="p-2">{t.priorityBucket}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <h2 className="text-xl font-semibold">Line Assignments</h2>
                    <div className="overflow-auto">
                        <table className="min-w-[1100px] text-sm">
                            <thead>
                                <tr className="text-left border-b">
                                    <th className="p-2">Truck #</th>
                                    <th className="p-2">SO</th>
                                    <th className="p-2">Line</th>
                                    <th className="p-2">Customer</th>
                                    <th className="p-2">Dest</th>
                                    <th className="p-2">Pieces</th>
                                    <th className="p-2">Wt/Pc</th>
                                    <th className="p-2">Total Wt</th>
                                    <th className="p-2">Width</th>
                                    <th className="p-2">Late</th>
                                </tr>
                            </thead>
                            <tbody>
                                {assignments.map((a, i) => (
                                    <tr key={i} className="border-b">
                                        <td className="p-2">{a.truckNumber}</td>
                                        <td className="p-2">{a.so}</td>
                                        <td className="p-2">{a.line}</td>
                                        <td className="p-2">{a.customerName}</td>
                                        <td className="p-2">{a.customerCity}, {a.customerState}</td>
                                        <td className="p-2">{a.piecesOnTransport}/{a.totalReadyPieces}</td>
                                        <td className="p-2">{Math.round(a.weightPerPiece)}</td>
                                        <td className="p-2">{Math.round(a.totalWeight)}</td>
                                        <td className="p-2">{a.width}{a.isOverwidth ? ' (OW)' : ''}</td>
                                        <td className="p-2">{a.isLate ? 'Yes' : 'No'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    )
}
