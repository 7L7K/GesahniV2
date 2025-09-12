#!/usr/bin/env python3
"""
GesahniV2 Python Client Example
Demonstrates automatic redirect handling for deprecated endpoints
"""

import asyncio

from gesahni_client import AsyncGesahniClient, GesahniClient


def basic_example():
    """Basic usage with automatic redirects."""
    print("=== Basic Example ===")

    client = GesahniClient(
        base_url='http://localhost:8000',  # Note: no /v1 prefix
        log_redirects=True  # Log when redirects happen
    )

    try:
        # This will automatically follow 308 redirect from /ask to /v1/ask
        response = client.ask(prompt='Hello, world!')
        print('Response:', response)
    except Exception as error:
        print('Error:', str(error))


def auth_example():
    """Authentication flow example."""
    print("\n=== Authentication Example ===")

    client = GesahniClient(base_url='http://localhost:8000/v1')

    try:
        # Login (this might redirect from /login to /v1/auth/login)
        auth = client.login(username='demo', password='demo123')
        print('Logged in successfully')
        client.set_auth_token(auth.access_token)

        # Use authenticated endpoint
        whoami = client.whoami()
        print('Current user:', whoami)

    except Exception as error:
        print('Auth error:', str(error))


def manual_redirect_example():
    """Manual redirect handling example."""
    print("\n=== Manual Redirect Handling ===")

    import requests

    response = requests.post(
        'http://localhost:8000/ask',
        json={'prompt': 'Test message'},
        allow_redirects=False  # Don't follow redirects automatically
    )

    if response.status_code == 308:
        print('Got 308 redirect to:', response.headers.get('location'))
        print('Deprecation notice:', response.headers.get('deprecation'))
        print('Sunset date:', response.headers.get('sunset'))

        # Follow the redirect
        new_url = response.headers.get('location')
        final_response = requests.post(
            f'http://localhost:8000{new_url}',
            json={'prompt': 'Test message'}
        )
        print('Final response status:', final_response.status_code)


def spotify_example():
    """Spotify integration example."""
    print("\n=== Spotify Integration Example ===")

    client = GesahniClient(base_url='http://localhost:8000/v1')

    try:
        # Check Spotify status (might redirect from /spotify/status to /v1/spotify/status)
        status = client.spotify_status()
        print('Spotify status:', status)

        if not status.get('connected', False):
            # Start OAuth flow (might redirect from /spotify/connect to /v1/spotify/connect)
            connect_url = client.spotify_connect()
            print('Connect URL:', connect_url)
            # In a real app, you'd redirect the user to this URL

    except Exception as error:
        print('Spotify error:', str(error))


def error_handling_example():
    """Error handling example."""
    print("\n=== Error Handling Example ===")

    client = GesahniClient(base_url='http://localhost:8000/v1')

    try:
        client.ask(prompt='Test')
    except Exception as error:
        # Check if it's an HTTP error
        if hasattr(error, 'status_code'):
            if error.status_code == 308:
                print('Endpoint deprecated - please update your code')
                print('New location:', error.headers.get('location') if hasattr(error, 'headers') else 'unknown')
            elif error.status_code == 401:
                print('Authentication required')
            elif error.status_code == 429:
                retry_after = error.headers.get('retry-after') if hasattr(error, 'headers') else 'unknown'
                print(f'Rate limited - retry after: {retry_after}')
            else:
                print('API error:', str(error))
        else:
            print('Error:', str(error))


async def async_example():
    """Async client example."""
    print("\n=== Async Example ===")

    client = AsyncGesahniClient(base_url='http://localhost:8000/v1')

    try:
        # Async login
        auth = await client.login(username='demo', password='demo123')
        print('Logged in successfully (async)')
        client.set_auth_token(auth.access_token)

        # Async API call
        response = await client.ask(prompt='Hello from async!')
        print('Async response:', response)

    except Exception as error:
        print('Async error:', str(error))


def streaming_example():
    """Streaming response example."""
    print("\n=== Streaming Example ===")

    client = GesahniClient(base_url='http://localhost:8000/v1')

    try:
        # Enable streaming
        print('Streaming response: ', end='', flush=True)
        for chunk in client.ask(prompt='Tell me a story', stream=True):
            print(chunk, end='', flush=True)
        print('\nStreaming complete')

    except Exception as error:
        print('Streaming error:', str(error))


def batch_example():
    """Batch operations example."""
    print("\n=== Batch Operations Example ===")

    client = GesahniClient(base_url='http://localhost:8000/v1')
    prompts = ['Hello', 'How are you?', 'What is AI?']
    responses = []

    try:
        for prompt in prompts:
            response = client.ask(prompt=prompt)
            responses.append(response)
            print(f'Processed: {prompt}')

        print(f'Batch complete: {len(responses)} responses')

    except Exception as error:
        print('Batch error:', str(error))


def run_sync_examples():
    """Run all synchronous examples."""
    print('GesahniV2 Python Client Examples\n')

    basic_example()
    auth_example()
    manual_redirect_example()
    spotify_example()
    error_handling_example()
    streaming_example()
    batch_example()


async def run_all_examples():
    """Run all examples including async."""
    run_sync_examples()
    await async_example()
    print('\n=== All Examples Complete ===')


if __name__ == '__main__':
    # Run sync examples
    run_sync_examples()

    # Run async examples
    print('\nRunning async examples...')
    asyncio.run(async_example())

    print('\n=== Examples Complete ===')
