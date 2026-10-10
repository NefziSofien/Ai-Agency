"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { DEPARTMENTS, STATUS_LABELS, api, formatDate, useApi, type Client, type Run } from "@/lib/api";

export default function BriefsPage() {
  const router = useRouter();
  const clients = useApi<Client[]>("/clients");
  const runs = useApi<Run[]>("/runs?limit=50", 4000);
  const [clientId, setClientId] = useState("");
  const [brief, setBrief] = useState("");
  const [departments, setDepartments] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const selectedClient = clientId || clients.data?.[0]?.id || "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const run = await api<{ id: string }>("/runs", {
        method: "POST",
        body: { client_id: selectedClient, brief, departments },
      });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSending(false);
    }
  }

  function toggle(dep: string) {
    setDepartments((d) => (d.includes(dep) ? d.filter((x) => x !== dep) : [...d, dep]));
  }

  return (
    <div className="grid">
      <form className="panel" onSubmit={submit}>
        <h2>Nouveau brief</h2>
        {clients.data && clients.data.length === 0 && (
          <p className="muted">
            Aucun client. <Link href="/clients">Crée un premier client</Link> avec son brand kit.
          </p>
        )}
        <label>Client</label>
        <select value={selectedClient} onChange={(e) => setClientId(e.target.value)} required>
          {clients.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        <label>Brief</label>
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Ex. : Lancer notre nouvelle offre de formation IA auprès des PME, campagne LinkedIn et Instagram sur 2 semaines, avec visuels et 6 posts programmés."
          required
          minLength={5}
        />

        <label>Départements</label>
        <p className="muted" style={{ margin: "0 0 8px" }}>
          Laisse vide pour laisser le Directeur de compte choisir.
        </p>
        <div className="checks">
          {Object.entries(DEPARTMENTS).map(([id, label]) => (
            <label key={id}>
              <input type="checkbox" checked={departments.includes(id)} onChange={() => toggle(id)} />
              {label}
            </label>
          ))}
        </div>

        {error && <div className="error">{error}</div>}
        <div style={{ marginTop: 16 }}>
          <button disabled={sending || !selectedClient}>{sending ? "Envoi…" : "Lancer les agents"}</button>
        </div>
      </form>

      <section className="panel">
        <h2>Derniers runs</h2>
        {runs.error && <div className="error">{runs.error}</div>}
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Client</th>
              <th>Brief</th>
              <th>Source</th>
              <th>Statut</th>
            </tr>
          </thead>
          <tbody>
            {runs.data?.map((r) => (
              <tr key={r.id}>
                <td className="muted">{formatDate(r.created_at)}</td>
                <td>{r.client_name}</td>
                <td>
                  <Link href={`/runs/${r.id}`}>{r.brief.length > 90 ? `${r.brief.slice(0, 90)}…` : r.brief}</Link>
                </td>
                <td className="muted">{r.source}</td>
                <td>
                  <span className={`badge ${r.status}`}>{STATUS_LABELS[r.status] ?? r.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs.data?.length === 0 && <p className="muted">Aucun run pour l'instant.</p>}
      </section>
    </div>
  );
}
