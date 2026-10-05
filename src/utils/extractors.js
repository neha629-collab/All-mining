function extractInitData(raw) {
  if (!raw || typeof raw !== 'string') return null;
  let text = raw.trim();

  // Handle URL hash format like #tgWebAppData=...
  if (text.includes('#tgWebAppData=')) {
    let segment = text.split('#tgWebAppData=')[1];
    // Don't split on & if the init data params are URL-encoded or query params
    // Look for next hash or tgWebAppPlatform if appended as separate query params
    const nextAmp = segment.indexOf('&tgWebApp');
    if (nextAmp !== -1) {
      segment = segment.substring(0, nextAmp);
    }
    try {
      segment = decodeURIComponent(segment);
    } catch (e) {}
    text = segment;
  } else if (text.includes('tgWebAppData=')) {
    let segment = text.split('tgWebAppData=')[1];
    const nextAmp = segment.indexOf('&tgWebApp');
    if (nextAmp !== -1) {
      segment = segment.substring(0, nextAmp);
    }
    try {
      segment = decodeURIComponent(segment);
    } catch (e) {}
    text = segment;
  }

  // Must contain user= or hash= or query_id=
  if (text.includes('hash=') && (text.includes('user=') || text.includes('query_id=') || text.includes('auth_date='))) {
    return text;
  }
  return text.startsWith('query_id=') || text.startsWith('user=') ? text : null;
}

function sanitizeMarkdown(text) {
  if (!text) return '';
  return String(text).replace(/[_*[\]()~`>#+\-=|{}.!]/g, '\\$&');
}

function solveMath(expression) {
  if (!expression) return '0';
  const cleaned = expression.replace(/[^0-9+\-*/().]/g, '');
  try {
    const math = require('mathjs');
    const result = math.evaluate(cleaned);
    return String(Math.round(result));
  } catch (err) {
    return '0';
  }
}

module.exports = {
  extractInitData,
  sanitizeMarkdown,
  solveMath
};
