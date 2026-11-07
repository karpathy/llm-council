import ReactMarkdown from 'react-markdown';
import { safeCitationUrl } from '../research';

function ResearchLink({ href, children }) {
  const safe = safeCitationUrl(href);
  return safe ? <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>;
}
function ResearchImage({ alt }) {
  return <span>{alt ? `[Image: ${alt}]` : '[Image omitted]'}</span>;
}

export default function ResearchMarkdown({ children, research }) {
  if (!research) return <ReactMarkdown>{children}</ReactMarkdown>;
  return <ReactMarkdown urlTransform={(url) => safeCitationUrl(url) || ''} components={{ a: ResearchLink, img: ResearchImage }}>{children}</ReactMarkdown>;
}
