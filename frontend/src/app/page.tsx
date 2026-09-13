"use client";

import { useEffect, useState } from "react";

type Probe = { path: string; ms: number; body: string };

const PATHS = ["/api/health", "/api/config/default"];

export default function Home() {
  const [probes, setProbes] = useState<Probe[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const results: Probe[] = [];
      for (const path of PATHS) {
        const t0 = performance.now();
        const res = await fetch(path);
        const body = await res.text();
        results.push({ path, ms: Math.round(performance.now() - t0), body });
      }
      if (!cancelled) setProbes(results);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-2xl p-8 font-mono text-sm">
      <h1 className="mb-4 text-lg font-semibold">Cost Signals — scaffold</h1>
      {probes.length === 0 ? (
        <p>Probing API…</p>
      ) : (
        <ul className="space-y-3">
          {probes.map((p) => (
            <li key={p.path}>
              <div>
                <span className="font-semibold">{p.path}</span> — {p.ms} ms
              </div>
              <pre className="mt-1 overflow-x-auto rounded bg-zinc-100 p-2 dark:bg-zinc-900">{p.body}</pre>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
