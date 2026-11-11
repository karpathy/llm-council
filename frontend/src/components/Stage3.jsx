import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api';
import './Stage3.css';

export default function Stage3({
  finalResponse,
  conversationId,
  messageIndex,
  initialReviews = [],
  canRequestReview = false,
}) {
  const [reviews, setReviews] = useState(initialReviews);
  const [showForm, setShowForm] = useState(false);
  const [reviewer, setReviewer] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!finalResponse) {
    return null;
  }

  const submitReview = async (e) => {
    e.preventDefault();
    if (!reviewer.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const review = await api.requestReview(
        conversationId,
        messageIndex,
        reviewer.trim(),
        note.trim()
      );
      setReviews((prev) => [...prev, review]);
      setReviewer('');
      setNote('');
      setShowForm(false);
    } catch {
      setError('Could not send the review request. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Chairman: {finalResponse.model.split('/')[1] || finalResponse.model}
        </div>
        <div className="final-text markdown-content">
          <ReactMarkdown>{finalResponse.response}</ReactMarkdown>
        </div>
      </div>

      <div className="review-section">
        {reviews.map((r) => (
          <div key={r.id} className="review-item">
            Review requested from <strong>{r.reviewer}</strong> ({r.status})
            {r.note && <span className="review-note"> — {r.note}</span>}
          </div>
        ))}
        {showForm ? (
          <form className="review-form" onSubmit={submitReview}>
            <input
              type="text"
              placeholder="Reviewer name or email"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              required
            />
            <textarea
              placeholder="Note for the reviewer (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
            {error && <div className="review-error">{error}</div>}
            <div className="review-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? 'Sending...' : 'Send request'}
              </button>
              <button type="button" onClick={() => setShowForm(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            className="review-button"
            disabled={!canRequestReview}
            onClick={() => setShowForm(true)}
          >
            Request team review
          </button>
        )}
      </div>
    </div>
  );
}
