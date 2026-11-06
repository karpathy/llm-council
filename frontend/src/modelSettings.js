// Offline fallback only; the backend's configured defaults take precedence.
export const FALLBACK_DEFAULTS = {
  council_models: ['openai/gpt-6.1-sol', 'google/gemini-4-argon', 'anthropic/claude-sonnet-5.5', 'x-ai/grok-4.7'],
  chairman_model: 'google/gemini-4-argon',
};
export function validModelId(value) {
  return typeof value === 'string' && /^[^\s/]+\/[^\s]+$/.test(value);
}
export function validSelection(selection) {
  return selection.council_models.length >= 1 && selection.council_models.length <= 26 &&
    new Set(selection.council_models).size === selection.council_models.length &&
    selection.council_models.every(validModelId) && validModelId(selection.chairman_model);
}
