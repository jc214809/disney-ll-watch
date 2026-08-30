const UPSTREAM = 'wss://ws.themeparks.wiki/v1/live';

export default {
    async fetch(request, env, ctx) {
        const upgrade = request.headers.get('Upgrade');
        if (!upgrade || upgrade.toLowerCase() !== 'websocket') {
            return new Response('Expected WebSocket upgrade', { status: 426 });
        }

        const { 0: client, 1: server } = new WebSocketPair();
        server.accept();

        ctx.waitUntil(handleProxy(server, env.THEMEPARKS_API_KEY));

        return new Response(null, { status: 101, webSocket: client });
    },
};

async function handleProxy(server, apiKey) {
    const upstream = new WebSocket(UPSTREAM, {
        headers: { 'X-API-Key': apiKey },
    });

    const serverQueue = [];
    let upstreamReady = false;

    upstream.addEventListener('open', () => {
        upstreamReady = true;
        for (const msg of serverQueue) {
            try { upstream.send(msg); } catch {}
        }
        serverQueue.length = 0;
    });

    upstream.addEventListener('message', ({ data }) => {
        try { server.send(data); } catch {}
    });

    upstream.addEventListener('close', ({ code, reason }) => {
        try { server.close(code, reason); } catch {}
    });

    upstream.addEventListener('error', () => {
        try { server.close(1011, 'Upstream error'); } catch {}
    });

    server.addEventListener('message', ({ data }) => {
        if (upstreamReady) {
            try { upstream.send(data); } catch {}
        } else {
            serverQueue.push(data);
        }
    });

    server.addEventListener('close', ({ code, reason }) => {
        try { upstream.close(code, reason); } catch {}
    });
}
