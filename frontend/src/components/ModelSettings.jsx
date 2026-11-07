import { useState } from 'react';
import { validModelId, distinctChairman, resetSelection } from '../modelSettings';
import './ModelSettings.css';

export default function ModelSettings({ models, selection, defaults, onChange, disabled, notice }) {
  const [candidate, setCandidate] = useState('');
  const [error, setError] = useState('');
  const describe = (id) => models.find((model) => model.id === id)?.name || id;
  const addMember = () => {
    const id = candidate.trim();
    if (!validModelId(id)) return setError('Enter an OpenRouter model ID, such as provider/model.');
    if (selection.council_models.includes(id)) return setError('That model is already on the council.');
    if (!distinctChairman({ ...selection, council_models: [id] })) return setError('The chairman cannot also be a council judge. Choose a different model.');
    if (selection.council_models.length >= 26) return setError('The council supports at most 26 members.');
    onChange({ ...selection, council_models: [...selection.council_models, id] });
    setCandidate('');
    setError('');
  };
  return (
    <details className="model-settings">
      <summary>{selection.research ? 'Research on · ' : ''}Council models · {selection.council_models.length} members · Chairman: {describe(selection.chairman_model)}</summary>
      <fieldset disabled={disabled}>
        <legend>Models for your next question</legend>
        <p>OpenAI, Google, Anthropic and xAI appear first. Add any text model on OpenRouter. The chairman must be different from every judge. Each extra member adds answer and review calls, increasing cost.</p>
        <label className="research-toggle" htmlFor="research-mode">
          <input id="research-mode" type="checkbox" aria-describedby="research-mode-description" checked={selection.research === true} onChange={(event) => onChange({ ...selection, research: event.target.checked })} />
          Research the web
        </label>
        <p id="research-mode-description">Off for ordinary reasoning. When on, each judge can independently search and fetch pages through OpenRouter: at most 2 searches and 2 page fetches per judge. This adds search fees, token costs, and latency. Queries may be sent to a web search provider; do not include secrets.</p>
        {notice && <p className="model-notice" role="status">{notice}</p>}
        <ul className="model-members">
          {selection.council_models.map((id) => (
            <li key={id}>
              <span><strong>{describe(id)}</strong><small>{id}</small></span>
              <button type="button" onClick={() => onChange({ ...selection, council_models: selection.council_models.filter((model) => model !== id) })} disabled={selection.council_models.length === 1} aria-label={`Remove ${describe(id)}`}>Remove</button>
            </li>
          ))}
        </ul>
        <label htmlFor="member-model">Add a council member</label>
        <div className="model-add">
          <input id="member-model" list="openrouter-models" value={candidate} onChange={(event) => setCandidate(event.target.value)} placeholder="Search or enter provider/model" onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addMember(); } }} />
          <button type="button" onClick={addMember} disabled={!candidate.trim() || selection.council_models.length >= 26}>Add</button>
        </div>
        <label htmlFor="chairman-model">Chairman (independent final synthesis)</label>
        <input id="chairman-model" list="chairman-models" value={selection.chairman_model} onChange={(event) => onChange({ ...selection, chairman_model: event.target.value.trim() })} aria-invalid={!validModelId(selection.chairman_model) || !distinctChairman(selection)} />
        {!validModelId(selection.chairman_model) && <p className="model-error">Choose a chairman using a provider/model ID before sending.</p>}
        {!distinctChairman(selection) && <p className="model-error" role="alert">The chairman is already a council judge. Choose a different model or remove it from the council.</p>}
        <datalist id="openrouter-models">{models.filter((model) => distinctChairman({ ...selection, council_models: [model.id] })).map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</datalist>
        <datalist id="chairman-models">{models.filter((model) => distinctChairman({ ...selection, chairman_model: model.id })).map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}</datalist>
        {error && <p className="model-error" role="alert">{error}</p>}
        <button className="model-reset" type="button" onClick={() => { onChange(resetSelection(defaults)); setError(''); }}>Reset to configured defaults</button>
      </fieldset>
    </details>
  );
}
