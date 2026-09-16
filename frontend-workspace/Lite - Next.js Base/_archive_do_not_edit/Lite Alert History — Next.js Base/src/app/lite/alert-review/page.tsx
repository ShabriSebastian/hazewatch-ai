import Link from "next/link";
import { AppShell } from "@/components/hazewatch/AppShell";

export default function AlertReviewPlaceholder() {
  return (
    <AppShell activePage="alert-review">
      <main className="p-8">
        <div className="mx-auto max-w-2xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-semibold text-blue-600">HazeWatch AI · Lite Mode</p>
          <h1 className="mt-2 text-3xl font-bold">Alert Review</h1>
          <p className="mt-3 text-slate-600">Placeholder route only. The final Alert Review visual will replace this screen.</p>
          <Link className="mt-6 inline-flex rounded-xl bg-blue-600 px-4 py-2 font-semibold text-white" href="/lite/institution-detail">Back to Institution Detail</Link>
        </div>
      </main>
    </AppShell>
  );
}
