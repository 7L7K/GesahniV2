const isProduction = process.env.NODE_ENV === 'production';

export async function GET() {
  if (isProduction) {
    return new Response('Not Found', { status: 404 });
  }

  return Response.json(
    { error: 'Unexpected /api/auth/whoami hit. Something rewrote /v1 → /api.' },
    { status: 499 },
  );
}

