"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/lib/auth";

export default function RedeemPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="min-h-screen grid place-items-center px-4">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setErr(null);
          try {
            await auth.redeem(token.trim(), email.trim(), password);
            router.push("/");
          } catch (e: any) {
            setErr(e.message);
          } finally {
            setLoading(false);
          }
        }}
        className="w-full max-w-sm space-y-4 p-6 bg-card rounded-lg border border-border"
      >
        <div>
          <h1 className="text-2xl font-semibold">Redeem invite</h1>
          <p className="text-sm text-zinc-400 mt-1">Use the token your admin gave you</p>
        </div>
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="invite token"
          required
          minLength={10}
          className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="your email"
          type="email"
          required
          className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="choose a password (8+ chars)"
          type="password"
          required
          minLength={8}
          className="w-full px-3 py-2 bg-zinc-800 rounded outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          disabled={loading}
          className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded font-medium"
        >
          {loading ? "Creating account..." : "Create account"}
        </button>
        {err && <p className="text-red-400 text-sm">{err}</p>}
      </form>
    </main>
  );
}
