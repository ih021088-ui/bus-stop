export async function onRequest(context) {
    const { searchParams } = new URL(context.request.url);
    const stationId = searchParams.get('stationId');

    if (!stationId) {
        return new Response(JSON.stringify({ error: 'stationId 필요' }), {
            status: 400,
            headers: { 'Content-Type': 'application/json' },
        });
    }

    const API_KEY = 'J1NNfn5UJ4zegGKBELL2lGTySAkSdNuFdugnZ0Pf5/e2OsLWJOSJOEeSiQObz15Ns1opof3iEqWhwbhTAg5U4A==';
    const url = `https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2?serviceKey=${encodeURIComponent(API_KEY)}&stationId=${stationId}`;

    try {
        const res = await fetch(url);
        const data = await res.json();

        return new Response(JSON.stringify(data), {
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
        });
    } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
            status: 500,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            },
        });
    }
}
