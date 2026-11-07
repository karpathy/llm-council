import { safeCitations, researchWarnings } from '../research';
import './ResearchEvidence.css';

export default function ResearchEvidence({ citations, research, synthesis = false }) {
  const sources = safeCitations(citations);
  if (!research?.requested && sources.length === 0) return null;
  const warnings = researchWarnings(research, sources.length);
  return (
    <section className="research-evidence" aria-label="Research evidence">
      <span className="research-badge">Research mode</span>
      {warnings.length > 0 && <ul className="research-warnings" role="status">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
      <h4>{synthesis ? 'Council evidence' : 'Sources returned by OpenRouter'}</h4>
      <p className="research-note">{synthesis ? 'These sources were available to the chairman. The list does not prove each page was opened or supports every claim.' : 'Returned citations are source evidence, not independent confirmation that a page was fetched or a claim verified.'}</p>
      {sources.length > 0 && <ol>{sources.map((source) => (
        <li key={source.url}>
          <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title || source.url}</a>
          <small>{source.url}</small>
          {source.content && <details><summary>Source excerpt</summary><p>{source.content}</p></details>}
        </li>
      ))}</ol>}
    </section>
  );
}
