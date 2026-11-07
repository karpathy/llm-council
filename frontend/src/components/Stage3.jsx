import ResearchMarkdown from './ResearchMarkdown';
import ResearchEvidence from './ResearchEvidence';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Chairman: {finalResponse.model.split('/')[1] || finalResponse.model}
        </div>
        <div className="final-text markdown-content">
          <ResearchMarkdown research={finalResponse.research?.requested}>{finalResponse.response}</ResearchMarkdown>
        </div>
        <ResearchEvidence citations={finalResponse.citations} research={finalResponse.research} synthesis />
      </div>
    </div>
  );
}
