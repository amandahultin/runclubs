export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try {
    body = await request.json();
  } catch (_) {
    return new Response('Bad Request', { status: 400 });
  }

  const { page, url, text, type } = body;
  if (!page || !url) return new Response('Bad Request', { status: 400 });

  // Skip self-referential dashboard tracking
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

export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: cors(),
  });
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
