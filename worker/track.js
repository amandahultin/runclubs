export async function track(request, env) {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: cors() });
  }
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let body;
  try {
    body = await request.json();
  } catch (_) {
    return new Response('Bad Request', { status: 400 });
  }

  const { page, url, text, type } = body;
  if (!page || !url) return new Response('Bad Request', { status: 400 });
  if (page.startsWith('/dashboard')) return ok();

  try {
    await env.DB.prepare(
      'INSERT INTO click_events (ts, page, link_url, link_text, link_type) VALUES (datetime("now"), ?, ?, ?, ?)'
    )
      .bind(
        String(page).slice(0, 200),
        String(url).slice(0, 500),
        String(text || '').slice(0, 100),
        String(type || 'unknown')
      )
      .run();
  } catch (err) {
    return new Response('Error', { status: 500 });
  }

  return ok();
}

function ok() {
  return new Response('OK', { status: 200, headers: cors() });
}

function cors() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}
