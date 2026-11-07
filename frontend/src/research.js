/** Conservative link validation only, not a DNS or source-quality check. */
export function safeCitationUrl(value) {
  if (typeof value !== 'string' || [...value].some((char) => char.charCodeAt(0) <= 32 || char.charCodeAt(0) === 127)) return null;
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    // Reject all IP literals, including numeric/hex IPv4 normalized by URL.
    if (!host.includes('.') || /^[\d.]+$/.test(host) || host.includes(':') || host.startsWith('[')) return null;
    if (/(^|\.)(localhost|local|internal|lan|home|test|invalid|example)$/.test(host)) return null;
    return url.href;
  } catch { return null; }
}

export function safeCitations(citations) {
  if (!Array.isArray(citations)) return [];
  const seen = new Set();
  return citations.flatMap((citation) => {
    if (!citation || typeof citation !== 'object') return [];
    const url = safeCitationUrl(citation.url);
    if (!url || seen.has(url)) return [];
    seen.add(url);
    return [{ url, title: typeof citation.title === 'string' ? citation.title.slice(0, 300) : url,
      content: typeof citation.content === 'string' ? citation.content.slice(0, 2000) : '' }];
  }).slice(0, 312);
}

export function researchWarnings(research, sourceCount) {
  if (!research?.requested) return [];
  const warnings = Array.isArray(research.warnings) ? research.warnings.filter((value) => typeof value === 'string') : [];
  const failed = Array.isArray(research.failed_models) ? research.failed_models.filter((value) => typeof value === 'string') : [];
  const unsourced = Array.isArray(research.no_source_models) ? research.no_source_models.filter((value) => typeof value === 'string') : [];
  if (failed.length) warnings.push(`Research failed for: ${failed.join(', ')}.`);
  if (unsourced.length) warnings.push(`No usable source citations from: ${unsourced.join(', ')}.`);
  if (sourceCount === 0 && !warnings.some((warning) => /no usable source citations/i.test(warning))) {
    warnings.push('No usable source citations were returned. Treat this answer as unverified web research.');
  }
  return [...new Set(warnings)];
}
