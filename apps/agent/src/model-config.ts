const DEFAULT_OPENAI_MODEL_ID = "gpt-6-luna";

export function selectOpenAIModelId(configuredModelId: string | undefined): string {
  const modelId = configuredModelId?.trim();
  return modelId || DEFAULT_OPENAI_MODEL_ID;
}
