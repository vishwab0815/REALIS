import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api, setAccessCode } from "../api";
import { LogoMark } from "./Icons";

/** Shown when the server requires an access code and this browser has no valid one. */
export function AccessGate({ onUnlock }: { onUnlock: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    setAccessCode(code.trim());
    try {
      await api.cases(); // any protected call: succeeds only with the right code
      onUnlock();
    } catch (err) {
      setAccessCode("");
      setError(err instanceof ApiError && err.status === 401 ? "That access code is not valid." : String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center gate">
      <form className="card gate-card" onSubmit={submit}>
        <LogoMark size={40} />
        <h1>Welcome to REALIS</h1>
        <p className="muted">This workspace is private. Enter the access code you were given.</p>
        <input className="text-input" type="password" autoFocus placeholder="Access code" value={code}
               onChange={(e) => setCode(e.target.value)} aria-label="Access code" autoComplete="current-password" />
        {error && <p className="gate-error" role="alert">{error}</p>}
        <button className="btn primary wide" disabled={busy || !code.trim()}>{busy ? "Checking…" : "Continue"}</button>
      </form>
    </div>
  );
}
