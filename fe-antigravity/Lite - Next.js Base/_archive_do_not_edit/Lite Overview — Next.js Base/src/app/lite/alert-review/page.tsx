import Link from "next/link";

export default function AlertReviewPlaceholder() {
  return (
    <main className="min-h-screen bg-slate-50 p-10 text-slate-900">
      <div className="mx-auto max-w-2xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold text-blue-600">HazeWatch AI · Lite Mode</p>
        <h1 className="mt-2 text-3xl font-bold">Alert Review</h1>
        <p className="mt-3 text-slate-600">
          Placeholder route only. Replace this screen when the final Alert Review visual is supplied.
        </p>
        <Link className="mt-6 inline-flex rounded-xl bg-blue-600 px-4 py-2 font-semibold text-white" href="/">
          Back to Overview
        </Link>
      </div>
    </main>
  );
}
