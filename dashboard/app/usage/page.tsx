"use client";

import { useState } from "react";
import { formatDate, useApi } from "@/lib/api";

type Row = { calls: number; input_tokens: number; output_tokens: number };
type Usage = {
  by_client: (Row & { client_id: string; client_name: string | null })[];
  by_model: (Row & { model: string; role: string })[];
  daily: { day: string; tokens: number }[];
};
type Health = { api: string; omniroute: string; models: number; roles: Record<string, string> };
type Alert = { id: number; source: string; level: string; message: string; created_at: string };

const n = (x: number) => Number(x ?? 0).toLocaleString("fr-FR");

export default function UsagePage() {
  const [days, setDays] = useState(30);
  const usage = useApi<Usage>(`/usage?days=${days}`, 10000);
  const health = useApi<Health>("/health", 10000);
  const alerts = useApi<Alert[]>("/alerts?limit=20", 10000);

  const total = (usage.data?.by_client ?? []).reduce(
    (acc, r) => ({ calls: acc.calls + Number(r.calls), tokens: acc.tokens + Number(r.input_tokens) + Number(r.output_tokens) }),
    { calls: 0, tokens: 0 },
  );
  const maxDaily = Math.max(1, ...(usage.data?.daily ?? []).map((d) => Number(d.tokens)));

  return (
    <>
      <div className="panel">
        <h1>Santé</h1>
        {health.error && <div className="error">{health.error}</div>}
        {health.data && (
          <div className="stats">
            <div className="stat">
              <span className="muted">API</span>
              <strong>{health.data.api}</strong>
            </div>
            <div className="stat">
              <span className="muted">OmniRoute</span>
              <strong style={{ color: health.data.omniroute === "ok" ? "var(--ok)" : "var(--err)" }}>
                {health.data.omniroute}
              </strong>
            </div>
            <div className="stat">
              <span className="muted">Modèles disponibles</span>
              <strong>{health.data.models}</strong>
            </div>
            <div className="stat">
              <span className="muted">Modèles par rôle</span>
              <div>
                {Object.entries(health.data.roles).map(([role, model]) => (
                  <div key={role}>
                    {role} : <code>{model}</code>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {health.data && health.data.omniroute === "ok" && health.data.models === 0 && (
          <p className="error">
            OmniRoute répond mais aucun modèle n'est disponible : connecte un fournisseur dans http://localhost:20128.
          </p>
        )}
      </div>

      <div className="panel">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1 style={{ margin: 0 }}>Usage des modèles (via OmniRoute)</h1>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: 160 }}>
            <option value={7}>7 jours</option>
            <option value={30}>30 jours</option>
            <option value={90}>90 jours</option>
          </select>
        </div>
        <p className="muted">
          {n(total.calls)} appels · {n(total.tokens)} tokens. Les coûts détaillés par fournisseur sont dans le dashboard
          OmniRoute.
        </p>

        <h2>Par jour</h2>
        <table>
          <tbody>
            {usage.data?.daily.map((d) => (
              <tr key={d.day}>
                <td style={{ width: 110 }} className="muted">
                  {d.day}
                </td>
                <td>
                  <div className="bar" style={{ width: `${(Number(d.tokens) / maxDaily) * 100}%` }} />
                </td>
                <td style={{ width: 120, textAlign: "right" }}>{n(d.tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ marginTop: 20 }}>Par client</h2>
        <table>
          <thead>
            <tr>
              <th>Client</th>
              <th>Appels</th>
              <th>Tokens entrée</th>
              <th>Tokens sortie</th>
            </tr>
          </thead>
          <tbody>
            {usage.data?.by_client.map((r) => (
              <tr key={r.client_id ?? "?"}>
                <td>{r.client_name ?? r.client_id}</td>
                <td>{n(r.calls)}</td>
                <td>{n(r.input_tokens)}</td>
                <td>{n(r.output_tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ marginTop: 20 }}>Par modèle et rôle</h2>
        <table>
          <thead>
            <tr>
              <th>Modèle</th>
              <th>Rôle</th>
              <th>Appels</th>
              <th>Tokens entrée</th>
              <th>Tokens sortie</th>
            </tr>
          </thead>
          <tbody>
            {usage.data?.by_model.map((r) => (
              <tr key={`${r.model}-${r.role}`}>
                <td>
                  <code>{r.model}</code>
                </td>
                <td>{r.role}</td>
                <td>{n(r.calls)}</td>
                <td>{n(r.input_tokens)}</td>
                <td>{n(r.output_tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h1>Alertes des automatisations</h1>
        {alerts.data?.length === 0 && <p className="muted">Aucune alerte.</p>}
        <table>
          <tbody>
            {alerts.data?.map((a) => (
              <tr key={a.id}>
                <td className="muted" style={{ width: 140 }}>
                  {formatDate(a.created_at)}
                </td>
                <td style={{ width: 90 }}>
                  <span className={`badge ${a.level === "error" ? "failed" : ""}`}>{a.level}</span>
                </td>
                <td style={{ width: 90 }}>{a.source}</td>
                <td>{a.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
