"use client";

import { use, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DEPARTMENTS, STATUS_LABELS, api, formatDate, useApi, type RunDetail } from "@/lib/api";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, reload } = useApi<RunDetail>(`/runs/${id}`, 3000);
  const [selected, setSelected] = useState<string[]>([]);
  const [feedback, setFeedback] = useState("");
  const [sending, setSending] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const actions = data?.state.interrupt?.actions ?? [];
  const awaiting = data?.run.status === "awaiting_approval";

  useEffect(() => {
    if (awaiting) setSelected(actions.map((a) => a.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awaiting, actions.length]);

  async function decide(approved: boolean) {
    setSending(true);
    setDecisionError(null);
    try {
      await api(`/runs/${id}/decision`, {
        method: "POST",
        body: { approved, approved_action_ids: approved ? selected : [], feedback },
      });
      setFeedback("");
      await reload();
    } catch (e) {
      setDecisionError((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (error) return <div className="error">{error}</div>;
  if (!data) return <p className="muted">Chargement…</p>;

  const { run, state, assets, usage } = data;
  const report = assets.find((a) => a.kind === "report");
  const media = assets.filter((a) => a.kind !== "report");

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>{data.client.name}</h1>
          <span className="muted">
            {run.id} · {formatDate(run.created_at)} · source {run.source} · {usage.calls} appels modèles ·{" "}
            {(usage.input_tokens + usage.output_tokens).toLocaleString("fr-FR")} tokens
          </span>
        </div>
        <span className={`badge ${run.status}`}>{STATUS_LABELS[run.status] ?? run.status}</span>
      </div>

      <div className="panel">
        <h2>Brief</h2>
        <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{run.brief}</p>
        {run.error && <div className="error">{run.error}</div>}
      </div>

      {state.plan && (
        <div className="panel">
          <h2>Plan du Directeur de compte</h2>
          <table>
            <tbody>
              {state.plan.map((t) => (
                <tr key={t.department}>
                  <td style={{ width: 200 }}>
                    <strong>{DEPARTMENTS[t.department] ?? t.department}</strong>
                    {run.status === "running" && state.current?.department === t.department && (
                      <span className="badge running" style={{ marginLeft: 6 }}>
                        en cours
                      </span>
                    )}
                    {state.results?.[t.department] && <span className="muted"> ✓</span>}
                  </td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{t.instruction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {state.review && (
        <div className="panel">
          <h2>
            Brand Guardian : {state.review.approved ? "conforme" : "réserves"} ({state.review.score}/10)
            {state.revisions ? <span className="muted"> · {state.revisions} révision(s) automatique(s)</span> : null}
          </h2>
          {state.review.feedback && <p>{state.review.feedback}</p>}
          {state.review.issues.length > 0 && (
            <ul>
              {state.review.issues.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {awaiting && (
        <div className="panel" style={{ borderColor: "var(--warn)" }}>
          <h2>Validation</h2>
          {actions.length === 0 ? (
            <p className="muted">Aucune action externe : valider clôture le livrable.</p>
          ) : (
            <>
              <p className="muted">Coche les actions à exécuter. Les autres seront ignorées.</p>
              {actions.map((a) => (
                <div className="action" key={a.id}>
                  <label className="inline">
                    <input
                      type="checkbox"
                      checked={selected.includes(a.id)}
                      onChange={() =>
                        setSelected((s) => (s.includes(a.id) ? s.filter((x) => x !== a.id) : [...s, a.id]))
                      }
                    />
                    <strong>{a.kind}</strong> <span className="muted">({DEPARTMENTS[a.department]})</span> : {a.summary}
                  </label>
                  <pre>{JSON.stringify(a.payload, null, 2)}</pre>
                </div>
              ))}
            </>
          )}
          <label>Retour (obligatoire pour demander une révision)</label>
          <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Ce qu'il faut changer…" />
          {decisionError && <div className="error">{decisionError}</div>}
          <div className="row" style={{ marginTop: 12 }}>
            <button disabled={sending} onClick={() => decide(true)}>
              Valider{actions.length ? ` et exécuter ${selected.length} action(s)` : ""}
            </button>
            <button className="secondary" disabled={sending || !feedback.trim()} onClick={() => decide(false)}>
              Demander une révision
            </button>
            <button className="danger" disabled={sending || !!feedback.trim()} onClick={() => decide(false)}>
              Rejeter
            </button>
          </div>
        </div>
      )}

      {state.executed && state.executed.length > 0 && (
        <div className="panel">
          <h2>Actions exécutées</h2>
          {state.executed.map((x) => (
            <div className="action" key={x.id}>
              <strong>{x.kind}</strong> : {x.ok ? <span style={{ color: "var(--ok)" }}>succès</span> : <span style={{ color: "var(--err)" }}>échec</span>}
              <pre>{x.ok ? JSON.stringify(x.result, null, 2) : x.error}</pre>
            </div>
          ))}
        </div>
      )}

      {(media.length > 0 || report) && (
        <div className="panel">
          <h2>Assets</h2>
          {report && (
            <p>
              <a href={report.url} target="_blank" rel="noreferrer">
                Télécharger le livrable PDF
              </a>
            </p>
          )}
          <div className="assets">
            {media.map((a) =>
              a.kind === "image" ? (
                <a key={a.id} href={a.url} target="_blank" rel="noreferrer" title={a.prompt ?? ""}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={a.url} alt={a.prompt ?? `asset ${a.id}`} />
                  <div className="muted">asset {a.id}</div>
                </a>
              ) : (
                <div key={a.id}>
                  <audio controls src={a.url} />
                  <div className="muted">asset {a.id}</div>
                </div>
              ),
            )}
          </div>
        </div>
      )}

      {state.deliverable ? (
        <div className="panel markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{state.deliverable}</ReactMarkdown>
        </div>
      ) : (
        Object.entries(state.results ?? {}).map(([dep, text]) => (
          <div className="panel markdown" key={dep}>
            <h2>{DEPARTMENTS[dep] ?? dep}</h2>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ))
      )}
    </>
  );
}
