import { dashboard } from './worker/dashboard.js';
import { track } from './worker/track.js';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === '/track') {
      return track(request, env);
    }

    if (url.pathname === '/dashboard') {
      return dashboard(request, env);
    }

    return env.ASSETS.fetch(request);
  },
};
