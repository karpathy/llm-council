// Offline fallback only; the backend's configured defaults take precedence.
export const FALLBACK_DEFAULTS = {
  council_models: ['openai/gpt-6.1-sol', 'google/gemini-4-argon', 'anthropic/claude-sonnet-5.5', 'x-ai/grok-4.7', 'moonshotai/kimi-k3.1-pro', 'deepseek/deepseek-v4.1-flash', 'qwen/qwen3.8-max-0902'],
  chairman_model: 'anthropic/claude-opus-5.5',
};
export function validModelId(value) {
  return typeof value === 'string' && /^[^\s/]+\/[^\s]+$/.test(value);
}
export function distinctChairman(selection) {
  const identity = (id) => id.trim().split(':', 1)[0];
  return !selection.council_models.some((model) => identity(model) === identity(selection.chairman_model));
}
export function validSelection(selection) {
  return selection.council_models.length >= 1 && selection.council_models.length <= 26 &&
    new Set(selection.council_models).size === selection.council_models.length &&
    selection.council_models.every(validModelId) && validModelId(selection.chairman_model) && distinctChairman(selection);
}
