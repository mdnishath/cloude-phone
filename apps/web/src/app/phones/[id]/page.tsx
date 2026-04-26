"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth";

interface Device {
  id: string; name: string; state: string; state_reason: string | null;
  adb_host_port: number | null; profile_id: string; proxy_id: string | null;
  created_at: string; started_at: string | null; stopped_at: string | null;
}

interface AdbInfo {
  host: string; port: number; command: string;
}

export default function PhoneDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [device, setDevice] = useState<Device | null>(null);
  const [adb, setAdb] = useState<AdbInfo | null>(null);
  const [streamToken, setStreamToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const a = auth.access(); if (!a) { router.push("/login"); return; }
    try {
      const d = await apiFetch<Device>(`/api/v1/devices/${id}`, {}, a);
      setDevice(d);
      if (d.state === "running" && d.adb_host_port) {
        try { setAdb(await apiFetch<AdbInfo>(`/api/v1/devices/${id}/adb-info`, {}, a)); } catch {}
      } else { setAdb(null); }
    } catch (e: any) {
      if (e.message?.startsWith("401")) { auth.clear(); router.push("/login"); return; }
      setError(e.message);
    }
  }, [id, router]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { const i = setInterval(load, 3000); return () => clearInterval(i); }, [load]);

  const fetchStreamToken = async () => {
    const a = auth.access(); if (!a) return;
    try {
      const r = await apiFetch<{ token: string; ttl_seconds: number }>(`/api/v1/devices/${id}/stream-token`, {}, a);
      setStreamToken(r.token);
    } catch (e: any) { setError(e.message); }
  };

  const action = async (verb: "start" | "stop") => {
    const a = auth.access(); if (!a) return;
    try { await apiFetch(`/api/v1/devices/${id}/${verb}`, { method: "POST" }, a); load(); }
    catch (e: any) { setError(e.message); }
  };

  const del = async () => {
    if (!confirm("Delete this phone?")) return;
    const a = auth.access(); if (!a) return;
    await apiFetch(`/api/v1/devices/${id}`, { method: "DELETE" }, a);
    router.push("/");
  };

  if (!device) return <main className="min-h-screen grid place-items-center text-zinc-400">Loading…</main>;

  return (
    <main className="min-h-screen">
      <header className="border-b border-border px-6 py-4 flex items-center justify-between gap-4">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200 whitespace-nowrap">← Back</Link>
        <h1 className="text-lg font-semibold flex-1 truncate">📱 {device.name}</h1>
        <div className="flex gap-2">
          {device.state === "running" && <button onClick={() => action("stop")} className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded">Stop</button>}
          {(device.state === "stopped" || device.state === "error") && <button onClick={() => action("start")} className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 rounded">Start</button>}
          <button onClick={del} className="px-3 py-1.5 text-sm bg-red-700/40 hover:bg-red-700/60 rounded">Delete</button>
        </div>
      </header>

      <section className="max-w-3xl mx-auto p-6 space-y-6">
        {error && <div className="p-3 bg-red-500/10 border border-red-500/40 text-red-300 rounded text-sm">{error}</div>}

        <div className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-medium mb-3">State</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-zinc-500 text-xs">State</dt><dd>{device.state}</dd></div>
            <div><dt className="text-zinc-500 text-xs">ID</dt><dd className="font-mono text-xs break-all">{device.id}</dd></div>
            <div><dt className="text-zinc-500 text-xs">Created</dt><dd>{new Date(device.created_at).toLocaleString()}</dd></div>
            <div><dt className="text-zinc-500 text-xs">ADB port</dt><dd>{device.adb_host_port ?? "—"}</dd></div>
            {device.state_reason && <div className="col-span-2"><dt className="text-zinc-500 text-xs">Reason</dt><dd className="text-red-300">{device.state_reason}</dd></div>}
          </dl>
        </div>

        {adb && (
          <div className="bg-card border border-border rounded-lg p-4">
            <h2 className="text-sm font-medium mb-3">Connect via ADB</h2>
            <pre className="text-xs bg-black/40 p-3 rounded font-mono overflow-x-auto">{adb.command}</pre>
            <p className="text-xs text-zinc-500 mt-2">⚠️ P1a stub — port returned but no real Android container behind it yet. Real spawn lands in P1b.</p>
          </div>
        )}

        {device.state === "running" && (
          <div className="bg-card border border-border rounded-lg p-4">
            <h2 className="text-sm font-medium mb-3">Live stream</h2>
            {!streamToken ? (
              <button onClick={fetchStreamToken} className="px-3 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded">
                Get stream token
              </button>
            ) : (
              <>
                <pre className="text-xs bg-black/40 p-3 rounded font-mono overflow-x-auto break-all whitespace-pre-wrap">{streamToken}</pre>
                <p className="text-xs text-zinc-500 mt-2">⚠️ ws-scrcpy bridge lands in P1b — token is real, but no streamer to consume it yet.</p>
              </>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
