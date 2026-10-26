import { createOpenAI } from "@ai-sdk/openai";
import { defineAgent } from "eve";
import { openAIProviderFetch } from "../src/egress.js";
import { selectOpenAIModelId } from "../src/model-config.js";
import { createScriptedDiscoveryModel } from "../src/scripted-discovery-model.js";

// Model credentials are read by the provider from the agent service environment.
function orchestrationModel() {
  if (process.env.FORECAST_AGENT_SCRIPTED_MODEL === "1") {
    if (process.env.NODE_ENV !== "test" && process.env.NODE_ENV !== "development") {
      throw new Error("scripted_model_requires_nonproduction_environment");
    }
    return createScriptedDiscoveryModel({
      resumeMarkerPath: process.env.FORECAST_AGENT_SCRIPTED_RESUME_MARKER,
    });
  }
  const openai = createOpenAI({ fetch: openAIProviderFetch() });
  return openai.responses(selectOpenAIModelId(process.env.OPENAI_MODEL_ID));
}

export default defineAgent({
  model: orchestrationModel(),
  defaultTools: false,
  experimental: { workflow: { world: "@workflow/world-postgres" } },
});
