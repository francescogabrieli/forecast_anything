import { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { useApp } from "@modelcontextprotocol/ext-apps/react";
import type { App } from "@modelcontextprotocol/ext-apps";
import type { ApiClient } from "../api/client";
import type { BacktestPresentation, ForecastPresentation, QuestionPresentation } from "../api/schema.generated";
import { ContextView } from "../features/context/ContextView";
import "../styles.css";

type ViewData = { kind: "run" | "question" | "report"; browser_link: { url: string; workspace_id: string; resource_id: string }; presentation: ForecastPresentation | QuestionPresentation | BacktestPresentation };

function View() {
  const [value, setValue] = useState<ViewData>();
  const [failed, setFailed] = useState(false);
  const { app, error } = useApp({ appInfo: { name: "Forecast Anything", version: "1.0.0" }, capabilities: {}, onAppCreated: bridge => {
    bridge.ontoolresult = async result => {
      const envelope = result.structuredContent as { ok?: boolean; data?: ViewData } | undefined;
      if (envelope?.ok && envelope.data?.browser_link && envelope.data.presentation) setValue(envelope.data);
      else setFailed(true);
    };
    bridge.ontoolcancelled = () => setFailed(true);
  } });
  const client = useMemo(() => app && value ? mediatedClient(app, value) : undefined, [app, value]);
  if (error || failed) return <main><p role="alert">Vista non disponibile. Usa il collegamento browser nella risposta dell’assistente.</p></main>;
  if (!app || !value || !client) return <main><p role="status">Caricamento del risultato…</p></main>;
  return <main className="app-sheet" onClick={event => {
    const anchor = (event.target as Element).closest("a");
    const href = anchor?.getAttribute("href");
    if (!href?.startsWith("#/w/")) return;
    event.preventDefault();
    const origin = new URL(value.browser_link.url).origin;
    void app.openLink({ url: `${origin}/${href}` });
  }}><ContextView client={client} workspaceId={value.browser_link.workspace_id} resource={{ kind: value.kind, id: value.browser_link.resource_id }} /><button type="button" onClick={() => void app.openLink({ url: value.browser_link.url })}>Apri nel browser</button></main>;
}

function mediatedClient(app: App, value: ViewData): ApiClient {
  async function call(name: string, args: Record<string, unknown>): Promise<any> {
    const result = await app.callServerTool({ name, arguments: args });
    const envelope = result.structuredContent as { ok?: boolean; data?: unknown } | undefined;
    if (!envelope?.ok) throw new Error("unavailable");
    return envelope.data;
  }
  const report = value.kind === "report" ? value.presentation as BacktestPresentation : undefined;
  return {
    getForecastPresentation: async () => value.presentation,
    getQuestionPresentation: async (id: string, offset: number) => offset === 0 ? value.presentation : call("get_question_presentation", { question_id: id, offset, limit: 3 }),
    getReportPresentation: async () => value.presentation,
    getReportOrigins: async (_id: string, offset: number) => call("list_backtest_origins", { backtest_id: report?.summary.backtest_id, offset, limit: 50 }),
    getBacktestPresentation: async () => value.presentation,
    getBacktestOrigins: async (_id: string, offset: number) => call("list_backtest_origins", { backtest_id: report?.summary.backtest_id, offset, limit: 50 }),
    getRun: async (id: string) => call("get_run", { run_id: id }),
    getGraph: async (id: string, version: number) => call("get_graph", { graph_id: id, version }),
    getRunEvaluations: async (id: string) => call("list_run_evaluations", { run_id: id }),
    getEvents: async () => [],
    streamEvents: async () => undefined,
  } as unknown as ApiClient;
}

createRoot(document.getElementById("root")!).render(<View />);
