import Link from "next/link";
import { ProAppShell } from "@/components/hazewatch/ProAppShell";
export default function Page(){return <ProAppShell activePage="institutions"><main className="p-8"><h2 className="text-3xl font-extrabold">Institutions</h2><p className="mt-2 text-sm text-slate-500">Next Pro screen to be integrated from the approved visual.</p><Link className="mt-5 inline-block text-sm font-bold text-blue-600" href="/pro/live-monitor">← Back to Live Monitor</Link></main></ProAppShell>}
