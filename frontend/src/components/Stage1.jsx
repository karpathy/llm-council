import { useState } from 'react';
import ResearchMarkdown from './ResearchMarkdown';
import ResearchEvidence from './ResearchEvidence';
import './Stage1.css';

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div className="tabs">
        {responses.map((resp, index) => (
          <button
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {resp.model.split('/')[1] || resp.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">{responses[activeTab].model}</div>
        <div className="response-text markdown-content">
          <ResearchMarkdown research={responses[activeTab].research?.requested}>{responses[activeTab].response}</ResearchMarkdown>
        </div>
        <ResearchEvidence citations={responses[activeTab].citations} research={responses[activeTab].research} />
      </div>
    </div>
  );
}
