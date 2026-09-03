const UPSTREAM = 'https://ws.themeparks.wiki/v1/live';

export default {
    async fetch(request, env, ctx) {
        const upgrade = request.headers.get('Upgrade');
        if (!upgrade || upgrade.toLowerCase() !== 'websocket') {
            return new Response('Expected WebSocket upgrade', { status: 426 });
        }

        const upstreamResp = await fetch(UPSTREAM, {
            headers: {
                Upgrade: 'websocket',
                Connection: 'Upgrade',
                'X-API-Key': env.THEMEPARKS_API_KEY,
            },
        });

        const upstream = upstreamResp.webSocket;
        if (!upstream) {
            return new Response('Upstream WebSocket failed', { status: 502 });
        }
        upstream.accept();

        const { 0: client, 1: server } = new WebSocketPair();
        server.accept();

        // Send auth message immediately
        upstream.send(JSON.stringify({ type: 'auth', apiKey: env.THEMEPARKS_API_KEY }));

        upstream.addEventListener('message', ({ data }) => {
            try { server.send(data); } catch {}
        });
        upstream.addEventListener('close', ({ code, reason }) => {
            try { server.close(code, reason); } catch {}
        });

        server.addEventListener('message', ({ data }) => {
            try { upstream.send(data); } catch {}
        });
        server.addEventListener('close', ({ code, reason }) => {
            try { upstream.close(code, reason); } catch {}
        });

        ctx.waitUntil(new Promise(resolve => {
            server.addEventListener('close', resolve);
            upstream.addEventListener('close', resolve);
        }));

        return new Response(null, { status: 101, webSocket: client });
    },
};
