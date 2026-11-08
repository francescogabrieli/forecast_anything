import { useEffect, useState } from "react";
import type { ApiClient } from "../../api/client";
import type { QuestionPage } from "../../api/schema.generated";

export function Questions({ client, workspaceId }: { client: ApiClient; workspaceId: string }) {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<QuestionPage>();
  const [error, setError] = useState<string>();
  const [editing, setEditing] = useState<string>();
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setPage(undefined); setError(undefined);
    void client.getQuestions(offset).then(value => { if (active) setPage(value); }).catch(() => { if (active) setError("Impossibile caricare le domande."); });
    return () => { active = false; };
  }, [client, offset, version]);
  async function rename(id: string) {
    try { await client.renameQuestion(id, title.trim()); setEditing(undefined); setVersion(value => value + 1); }
    catch { setError("Impossibile aggiornare il titolo."); }
  }
  return <section aria-labelledby="questions-title"><h2 id="questions-title">Domande salvate</h2>
    {error && <p role="alert">{error}</p>}{!page && !error && <p role="status">Caricamento…</p>}
    {page && (page.questions.length ? <ul>{page.questions.map(question => <li key={question.question_id}>
      <a href={`#/w/${workspaceId}/question/${encodeURIComponent(question.question_id)}/full`}>{question.title}</a> · {question.status} · revisione {question.current_revision}
      {editing === question.question_id ? <form onSubmit={event => { event.preventDefault(); void rename(question.question_id); }}><label>Nuovo titolo<input value={title} onChange={event => setTitle(event.target.value)} /></label><button disabled={!title.trim()}>Salva titolo</button><button type="button" onClick={() => setEditing(undefined)}>Annulla</button></form> : <button type="button" onClick={() => { setEditing(question.question_id); setTitle(question.title); }}>Rinomina</button>}
    </li>)}</ul> : <p>Nessuna domanda salvata.</p>)}
    {offset > 0 && <button onClick={() => setOffset(Math.max(0, offset - 25))}>Precedenti</button>}{page?.next_offset != null && <button onClick={() => setOffset(page.next_offset!)}>Altre domande</button>}
  </section>;
}
